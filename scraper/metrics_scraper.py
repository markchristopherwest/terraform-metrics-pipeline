#!/usr/bin/env python3
"""
metrics_scraper.py - Prometheus exporter + change-feed writer for the JSON
reports that Terraform writes into ./reports (Prisma Cloud tenant snapshots).

What it does every SCAN_INTERVAL seconds
  1. Looks at reports/*.json and reports/*.jsonl (+ reports/.runner/last_run.json).
  2. Re-parses any file whose content hash changed (Terraform re-creates the
     files every run, so mtime/inode change every time; content may not).
  3. Rebuilds the metric set from the parsed documents (a custom Collector, so
     vanished entities simply disappear - no stale series).
  4. Diffs entity files and a curated list of summary fields against the
     previous snapshot and appends one JSON line per change to
     reports/derived/prisma_changes.jsonl. Promtail tails that file into Loki
     ("change feed"); the same events are counted in prisma_changes_total.

Metric naming (see docs/metrics.md)
  summary: every numeric/boolean leaf  ->  prisma_<path_joined_by_underscore>{tenant}
           maps named by_<label> / *_by_<label> -> one series per key, key in <label>
           arrays are ignored except alerts.top_policies, scores.risk_flags
  entity files: prisma_cloud_account_*, prisma_user_*, prisma_integration_*,
           prisma_alert_rule_*, prisma_custom_policy_*
  pipeline: prisma_snapshot_*, prisma_report_*, prisma_runner_*, prisma_changes_total

Endpoints: /metrics (Prometheus), /healthz, /state (latest summary as JSON)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from prometheus_client import (CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge,
                               generate_latest)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, InfoMetricFamily

VERSION = "1.0.0"
LOG = logging.getLogger("metrics_scraper")

# --------------------------------------------------------------------------- #
# Report catalogue                                                             #
# --------------------------------------------------------------------------- #

# file name -> (report name, kind, id field, name field, label fields for entity
#               metrics, watched fields for the change feed)
REPORTS: Dict[str, Dict[str, Any]] = {
    "prisma_summary.json": {"report": "summary", "kind": "object"},
    "prisma_cloud_accounts.jsonl": {
        "report": "cloud_accounts", "kind": "lines", "entity": "cloud_account",
        "id": "account_id", "name": "name",
        "labels": ["account_id", "name", "cloud_type", "account_type", "status", "protection_mode"],
        "dims": ["cloud_type"],
        "watch": ["enabled", "status", "protection_mode", "name", "account_groups",
                  "storage_scan_enabled", "number_of_child_accounts"],
    },
    "prisma_users.jsonl": {
        "report": "users", "kind": "lines", "entity": "user",
        "id": "user_id", "name": "user_id",
        "labels": ["user_id", "account_type", "default_role_type"],
        "dims": ["account_type"],
        "watch": ["enabled", "last_login_ts", "is_admin", "role_count", "default_role"],
    },
    "prisma_integrations.jsonl": {
        "report": "integrations", "kind": "lines", "entity": "integration",
        "id": "integration_id", "name": "name",
        "labels": ["integration_id", "name", "integration_type", "status"],
        "dims": ["integration_type"],
        "watch": ["enabled", "valid", "status", "name"],
    },
    "prisma_alert_rules.jsonl": {
        "report": "alert_rules", "kind": "lines", "entity": "alert_rule",
        "id": "rule_id", "name": "name",
        "labels": ["rule_id", "name"],
        "dims": [],
        "watch": ["enabled", "scan_all", "policies_count", "name", "owner"],
    },
    "prisma_policies.jsonl": {
        "report": "policies", "kind": "lines", "entity": "custom_policy",
        "id": "policy_id", "name": "name",
        "labels": ["policy_id", "name", "severity", "policy_type", "cloud_type"],
        "dims": ["policy_type", "severity"],
        "watch": ["enabled", "severity", "name", "remediable"],
    },
}

# Summary fields whose change is worth a line in the change feed (structural,
# not the counters that wobble every run such as alerts.open).
SUMMARY_WATCH = [
    "cloud_accounts.total", "cloud_accounts.enabled", "cloud_accounts.disabled",
    "account_groups.total",
    "users.total", "users.enabled", "users.admins", "users.service_accounts",
    "users.human_active_30d",
    "roles.total", "roles.custom",
    "policies.enabled", "policies.custom", "policies.custom_enabled",
    "alert_rules.total", "alert_rules.enabled",
    "integrations.total", "integrations.enabled", "integrations.valid",
    "compliance_standards.custom", "reports.total", "saved_searches.saved",
    "license.workloads_purchased", "license.credits.purchased",
    "inventory.total_resources",
    "enterprise_settings.audit_logs_enabled", "enterprise_settings.apply_default_policies_enabled",
    "scores.adoption_score", "scores.risk_score",
]

ARRAY_HANDLERS = {"alerts.top_policies", "scores.risk_flags"}
SKIP_PREFIXES = ("license.time_series", "run.collect")

LABEL_RE = re.compile(r"[^a-zA-Z0-9_]")


def sanitize(name: str) -> str:
    n = LABEL_RE.sub("_", name)
    if n and n[0].isdigit():
        n = "_" + n
    return n


def by_label(key: str) -> Optional[str]:
    """'by_cloud_type' -> 'cloud_type', 'enabled_by_severity' -> 'severity', else None."""
    if key.startswith("by_"):
        return key[3:]
    idx = key.rfind("_by_")
    if idx >= 0:
        return key[idx + 4:]
    return None


def is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def num_value(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if is_num(v):
        return float(v)
    return None


def parse_ts(ts: Any) -> Optional[float]:
    if not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_path(doc: Any, path: str) -> Any:
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


# --------------------------------------------------------------------------- #
# State                                                                        #
# --------------------------------------------------------------------------- #

class ReportState:
    """Last successfully parsed version of one report file."""

    def __init__(self, name: str, spec: Dict[str, Any]):
        self.name = name
        self.spec = spec
        self.report = spec["report"]
        self.doc: Any = None                 # dict (object) or list[dict] (lines)
        self.sha: Optional[str] = None
        self.mtime: float = 0.0
        self.size: int = 0
        self.snapshot_ts: Optional[float] = None
        self.tenant: str = ""
        self.loaded_at: float = 0.0

    def entity_index(self) -> Dict[str, Dict[str, Any]]:
        idx: Dict[str, Dict[str, Any]] = {}
        if self.spec["kind"] != "lines" or not isinstance(self.doc, list):
            return idx
        key = self.spec["id"]
        for line in self.doc:
            if isinstance(line, dict) and line.get(key) is not None:
                idx[str(line[key])] = line
        return idx


# --------------------------------------------------------------------------- #
# Scraper                                                                      #
# --------------------------------------------------------------------------- #

class Scraper:
    def __init__(self, reports_dir: Path, derived_dir: Path, *, write_changes: bool = True,
                 entity_metrics: bool = True, user_metrics: bool = True,
                 max_entity_series: int = 5000, stale_after: float = 900.0,
                 changes_max_bytes: int = 50 * 1024 * 1024, registry=None):
        self.reports_dir = reports_dir
        self.derived_dir = derived_dir
        self.changes_file = derived_dir / "prisma_changes.jsonl"
        self.state_file = derived_dir / ".scraper_state.json"
        self.write_changes = write_changes
        self.entity_metrics = entity_metrics
        self.user_metrics = user_metrics
        self.max_entity_series = max_entity_series
        self.stale_after = stale_after
        self.changes_max_bytes = changes_max_bytes

        self.reports: Dict[str, ReportState] = {f: ReportState(f, s) for f, s in REPORTS.items()}
        self.runner: Optional[Dict[str, Any]] = None
        self.lock = threading.RLock()
        self.last_scan: float = 0.0
        self.scans = 0
        self.tenant = "unknown"

        # previous snapshot used for diffs (persisted across restarts)
        self.prev: Dict[str, Any] = {"entities": {}, "summary": {}, "risk_flags": None, "baseline_done": False}
        self._load_state()

        # real (monotonic) counters - owned by this collector (registry=None), exposed via collect()
        self.c_loads = Counter("prisma_report_loads", "Report files (re)parsed", ["report"], registry=None)
        self.c_parse_errors = Counter("prisma_report_parse_errors", "Report files that failed to parse", ["report"], registry=None)
        self.c_changes = Counter("prisma_changes", "Change-feed events emitted", ["tenant", "entity", "change"], registry=None)
        self.c_scans = Counter("prisma_scraper_scans", "Directory scans performed", registry=None)
        self.g_last_change = Gauge("prisma_last_change_timestamp_seconds", "Unix time of the last change event per entity type", ["tenant", "entity"], registry=None)

        self.registry = registry if registry is not None else REGISTRY
        self.registry.register(self)

    # ---- persistence -------------------------------------------------------
    def _load_state(self) -> None:
        try:
            if self.state_file.exists():
                with self.state_file.open() as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and "entities" in data:
                    self.prev = data
                    self.prev.setdefault("summary", {})
                    self.prev.setdefault("risk_flags", None)
                    self.prev.setdefault("baseline_done", True)
                    LOG.info("restored previous snapshot state from %s", self.state_file)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("could not read %s: %s (starting from scratch)", self.state_file, exc)

    def _save_state(self) -> None:
        try:
            self.derived_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.state_file.with_suffix(".tmp")
            with tmp.open("w") as fh:
                json.dump(self.prev, fh)
            os.replace(tmp, self.state_file)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("could not persist state: %s", exc)

    # ---- scanning ------------------------------------------------------------
    def scan(self) -> int:
        """Re-read changed files. Returns the number of files that changed."""
        changed = 0
        with self.lock:
            self.scans += 1
            self.c_scans.inc()
            for fname, st in self.reports.items():
                path = self.reports_dir / fname
                if not path.exists():
                    if st.doc is not None:
                        LOG.info("%s disappeared", fname)
                    st.doc = None
                    st.sha = None
                    continue
                try:
                    raw = path.read_bytes()
                except OSError as exc:
                    LOG.warning("cannot read %s: %s", path, exc)
                    continue
                sha = hashlib.sha256(raw).hexdigest()
                if sha == st.sha:
                    continue
                parsed = self._parse(st, raw)
                if parsed is None:
                    continue  # partial write / bad JSON: try again next scan
                doc, snapshot_ts, tenant = parsed
                st.doc, st.sha, st.snapshot_ts = doc, sha, snapshot_ts
                st.mtime = path.stat().st_mtime
                st.size = len(raw)
                st.loaded_at = time.time()
                if tenant:
                    st.tenant = tenant
                    self.tenant = tenant
                self.c_loads.labels(st.report).inc()
                changed += 1
                LOG.info("loaded %s (%d bytes, snapshot %s)", fname, len(raw),
                         datetime.fromtimestamp(snapshot_ts, timezone.utc).isoformat() if snapshot_ts else "?")
            self._load_runner()
            if changed:
                self._detect_changes()
            self.last_scan = time.time()
        return changed

    def _parse(self, st: ReportState, raw: bytes) -> Optional[Tuple[Any, Optional[float], str]]:
        try:
            text = raw.decode("utf-8")
            if st.spec["kind"] == "object":
                if not text.strip():
                    return None
                doc = json.loads(text)
                if not isinstance(doc, dict):
                    raise ValueError("summary is not a JSON object")
                return doc, parse_ts(doc.get("@timestamp")), str(doc.get("tenant") or "")
            lines: List[Dict[str, Any]] = []
            if text and not text.endswith("\n"):
                # Terraform writes the whole file in one go; a missing trailing
                # newline means we caught it mid-write.
                return None
            for ln in text.splitlines():
                if ln.strip():
                    obj = json.loads(ln)
                    if isinstance(obj, dict):
                        lines.append(obj)
            ts = parse_ts(lines[0].get("@timestamp")) if lines else None
            tenant = str(lines[0].get("tenant") or "") if lines else ""
            return lines, ts, tenant
        except (ValueError, UnicodeDecodeError) as exc:
            self.c_parse_errors.labels(st.report).inc()
            LOG.warning("parse error in %s: %s", st.name, exc)
            return None

    def _load_runner(self) -> None:
        path = self.reports_dir / ".runner" / "last_run.json"
        if not path.exists():
            return
        try:
            self.runner = json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            LOG.debug("runner status unreadable: %s", exc)

    # ---- change detection -----------------------------------------------------
    def _detect_changes(self) -> None:
        events: List[Dict[str, Any]] = []
        ts = now_iso()
        summary = self.reports["prisma_summary.json"].doc
        snapshot_ts = None
        for st in self.reports.values():
            if st.snapshot_ts:
                snapshot_ts = st.snapshot_ts
        snap_iso = datetime.fromtimestamp(snapshot_ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if snapshot_ts else None

        base = {"@timestamp": ts, "report": "changes", "tenant": self.tenant, "snapshot_ts": snap_iso,
                "producer": "metrics_scraper"}

        if not self.prev.get("baseline_done"):
            counts = {st.spec.get("entity", st.report): (len(st.doc) if isinstance(st.doc, list) else 1)
                      for st in self.reports.values() if st.doc is not None}
            events.append({**base, "entity": "tenant", "change": "baseline", "id": self.tenant,
                           "name": self.tenant, "detail": "first snapshot seen by the scraper: " +
                           ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))})
            self.prev["baseline_done"] = True
            # seed previous state without emitting per-entity events
            for st in self.reports.values():
                if st.spec["kind"] == "lines" and st.doc is not None:
                    self.prev["entities"][st.report] = self._watched_view(st)
            if isinstance(summary, dict):
                self.prev["summary"] = {p: get_path(summary, p) for p in SUMMARY_WATCH}
                self.prev["risk_flags"] = get_path(summary, "scores.risk_flags")
            self._emit(events)
            self._save_state()
            return

        # entities
        for st in self.reports.values():
            if st.spec["kind"] != "lines" or st.doc is None:
                continue
            prev_idx: Dict[str, Dict[str, Any]] = self.prev["entities"].get(st.report, {})
            cur_view = self._watched_view(st)
            cur_idx = st.entity_index()
            entity = st.spec["entity"]
            name_f = st.spec["name"]
            for eid, line in cur_idx.items():
                ev = {**base, "entity": entity, "id": eid, "name": str(line.get(name_f, eid))}
                for d in st.spec["dims"]:
                    if line.get(d) is not None:
                        ev[d] = line[d]
                if eid not in prev_idx:
                    events.append({**ev, "change": "added", "detail": f"{entity} {ev['name']} appeared"})
                    continue
                old = prev_idx[eid]
                for field in st.spec["watch"]:
                    ov, nv = old.get(field), cur_view[eid].get(field)
                    if ov == nv:
                        continue
                    events.append({**ev, **self._describe(entity, field, ov, nv, ev["name"])})
            for eid, old in prev_idx.items():
                if eid not in cur_idx:
                    ev = {**base, "entity": entity, "id": eid, "name": str(old.get("_name", eid)),
                          "change": "removed", "detail": f"{entity} {old.get('_name', eid)} is gone"}
                    for d in st.spec["dims"]:
                        if old.get(d) is not None:
                            ev[d] = old[d]
                    events.append(ev)
            self.prev["entities"][st.report] = cur_view

        # summary fields
        if isinstance(summary, dict):
            prev_sum = self.prev.get("summary", {})
            for p in SUMMARY_WATCH:
                nv = get_path(summary, p)
                ov = prev_sum.get(p)
                if nv is None or ov is None or nv == ov:
                    continue
                delta = (nv - ov) if (is_num(nv) and is_num(ov)) else None
                events.append({**base, "entity": "summary", "change": "metric_changed", "id": p, "name": p,
                               "field": p, "old": ov, "new": nv, "delta": delta,
                               "detail": f"{p}: {ov} -> {nv}"})
            self.prev["summary"] = {p: get_path(summary, p) for p in SUMMARY_WATCH}
            # risk flags raised / cleared
            new_flags = set(get_path(summary, "scores.risk_flags") or [])
            old_flags = self.prev.get("risk_flags")
            if old_flags is not None:
                for f in sorted(new_flags - set(old_flags)):
                    events.append({**base, "entity": "risk_flag", "change": "raised", "id": f, "name": f,
                                   "detail": f"churn-risk signal {f} is now active"})
                for f in sorted(set(old_flags) - new_flags):
                    events.append({**base, "entity": "risk_flag", "change": "cleared", "id": f, "name": f,
                                   "detail": f"churn-risk signal {f} cleared"})
            self.prev["risk_flags"] = sorted(new_flags)

        self._emit(events)
        self._save_state()

    def _watched_view(self, st: ReportState) -> Dict[str, Dict[str, Any]]:
        view: Dict[str, Dict[str, Any]] = {}
        for eid, line in st.entity_index().items():
            v = {f: line.get(f) for f in st.spec["watch"]}
            v["_name"] = line.get(st.spec["name"], eid)
            for d in st.spec["dims"]:
                v[d] = line.get(d)
            view[eid] = v
        return view

    @staticmethod
    def _describe(entity: str, field: str, ov: Any, nv: Any, name: str) -> Dict[str, Any]:
        ev: Dict[str, Any] = {"field": field, "old": ov, "new": nv}
        if field == "enabled":
            ev["change"] = "enabled" if nv else "disabled"
            ev["detail"] = f"{entity} {name} was {'enabled' if nv else 'disabled'}"
        elif field == "valid":
            ev["change"] = "recovered" if nv else "broken"
            ev["detail"] = f"{entity} {name} is now {'valid' if nv else 'INVALID'}"
        elif field == "last_login_ts":
            if is_num(nv) and is_num(ov) and nv > ov:
                ev["change"] = "logged_in"
                ev["detail"] = f"{name} logged in"
            else:
                ev["change"] = "changed"
                ev["detail"] = f"{name}: last login changed"
        elif field == "is_admin":
            ev["change"] = "admin_granted" if nv else "admin_revoked"
            ev["detail"] = f"{name}: System Admin {'granted' if nv else 'revoked'}"
        else:
            ev["change"] = "changed"
            ev["detail"] = f"{entity} {name}: {field} {ov} -> {nv}"
        return ev

    def _emit(self, events: List[Dict[str, Any]]) -> None:
        if not events:
            return
        now = time.time()
        for ev in events:
            self.c_changes.labels(ev.get("tenant", ""), ev["entity"], ev["change"]).inc()
            self.g_last_change.labels(ev.get("tenant", ""), ev["entity"]).set(now)
            LOG.info("change: %s %s %s", ev["entity"], ev["change"], ev.get("detail", ""))
        if not self.write_changes:
            return
        try:
            self.derived_dir.mkdir(parents=True, exist_ok=True)
            self._rotate_changes()
            with self.changes_file.open("a", encoding="utf-8") as fh:
                for ev in events:
                    fh.write(json.dumps(ev, separators=(",", ":"), sort_keys=True) + "\n")
        except OSError as exc:
            LOG.error("cannot append to %s: %s", self.changes_file, exc)

    def _rotate_changes(self) -> None:
        try:
            if self.changes_file.exists() and self.changes_file.stat().st_size > self.changes_max_bytes:
                rotated = self.changes_file.with_suffix(".jsonl.1")
                os.replace(self.changes_file, rotated)
                LOG.info("rotated change feed to %s", rotated)
        except OSError as exc:
            LOG.warning("rotation failed: %s", exc)

    # ---- Prometheus collector ---------------------------------------------------
    def describe(self) -> Iterable[Any]:   # keeps the registry from calling collect at registration
        return []

    def collect(self) -> Iterable[Any]:
        with self.lock:
            for owned in (self.c_loads, self.c_parse_errors, self.c_changes, self.c_scans, self.g_last_change):
                yield from owned.collect()
            yield from self._collect_meta()
            summary = self.reports["prisma_summary.json"].doc
            if isinstance(summary, dict):
                yield from self._collect_summary(summary)
            if self.entity_metrics:
                yield from self._collect_entities()

    def _collect_meta(self) -> Iterable[Any]:
        info = InfoMetricFamily("prisma_scraper", "metrics_scraper build info")
        info.add_metric([], {"version": VERSION, "reports_dir": str(self.reports_dir)})
        yield info
        g_last = GaugeMetricFamily("prisma_scraper_last_scan_timestamp_seconds", "Unix time of the last directory scan")
        g_last.add_metric([], self.last_scan)
        yield g_last

        g_ts = GaugeMetricFamily("prisma_snapshot_timestamp_seconds", "@timestamp of the last parsed snapshot", labels=["tenant", "report"])
        g_age = GaugeMetricFamily("prisma_snapshot_age_seconds", "Seconds since the snapshot @timestamp", labels=["tenant", "report"])
        g_stale = GaugeMetricFamily("prisma_snapshot_stale", "1 when the snapshot is older than STALE_AFTER_SECONDS", labels=["tenant", "report"])
        g_mtime = GaugeMetricFamily("prisma_report_mtime_seconds", "File modification time", labels=["tenant", "report"])
        g_bytes = GaugeMetricFamily("prisma_report_bytes", "File size in bytes", labels=["tenant", "report"])
        g_lines = GaugeMetricFamily("prisma_report_lines", "Entity lines in the report (1 for summary)", labels=["tenant", "report"])
        g_present = GaugeMetricFamily("prisma_report_present", "1 when the report file exists and parsed", labels=["tenant", "report"])
        now = time.time()
        for st in self.reports.values():
            tenant = st.tenant or self.tenant
            present = 1.0 if st.doc is not None else 0.0
            g_present.add_metric([tenant, st.report], present)
            if st.doc is None:
                continue
            if st.snapshot_ts:
                g_ts.add_metric([tenant, st.report], st.snapshot_ts)
                age = max(0.0, now - st.snapshot_ts)
                g_age.add_metric([tenant, st.report], age)
                g_stale.add_metric([tenant, st.report], 1.0 if age > self.stale_after else 0.0)
            g_mtime.add_metric([tenant, st.report], st.mtime)
            g_bytes.add_metric([tenant, st.report], st.size)
            g_lines.add_metric([tenant, st.report], len(st.doc) if isinstance(st.doc, list) else 1)
        yield from (g_ts, g_age, g_stale, g_mtime, g_bytes, g_lines, g_present)

        if self.runner:
            r = self.runner
            mod = str(r.get("module", ""))
            for key, desc in (("success", "1 if the last terraform apply succeeded"),
                              ("duration_seconds", "Duration of the last terraform apply"),
                              ("exit_code", "Exit code of the last terraform apply"),
                              ("interval_seconds", "Configured scheduler interval"),
                              ("runs_total", "Applies since the runner started"),
                              ("failures_total", "Failed applies since the runner started")):
                val = num_value(r.get(key))
                if val is None:
                    continue
                g = GaugeMetricFamily(f"prisma_runner_last_run_{key}" if key in ("success", "duration_seconds", "exit_code") else f"prisma_runner_{key}", desc, labels=["module"])
                g.add_metric([mod], val)
                yield g
            ts = parse_ts(r.get("@timestamp"))
            if ts:
                g = GaugeMetricFamily("prisma_runner_last_run_timestamp_seconds", "Unix time of the last terraform apply", labels=["module"])
                g.add_metric([mod], ts)
                yield g

    # -- summary ------------------------------------------------------------------
    def _collect_summary(self, summary: Dict[str, Any]) -> Iterable[Any]:
        tenant = str(summary.get("tenant") or self.tenant)
        families: Dict[str, GaugeMetricFamily] = {}
        family_labels: Dict[str, List[str]] = {}
        sink = GaugeMetricFamily("prisma_scraper_dropped_samples", "Samples dropped because a metric name was reused with a different label set")
        dropped = 0

        def fam(name: str, labels: List[str], help_: str) -> GaugeMetricFamily:
            nonlocal dropped
            if name not in families:
                families[name] = GaugeMetricFamily(name, help_, labels=labels)
                family_labels[name] = labels
            elif family_labels[name] != labels:
                dropped += 1
                return GaugeMetricFamily(name + "_discarded", help_, labels=labels)  # throw-away
            return families[name]

        def walk(node: Any, path: List[str]) -> None:
            dotted = ".".join(path)
            if dotted in ARRAY_HANDLERS or any(dotted.startswith(p) for p in SKIP_PREFIXES):
                return
            if isinstance(node, dict):
                for k, v in node.items():
                    if k.startswith("@"):
                        continue
                    label = by_label(k)
                    sub = path + [sanitize(k)]
                    if label and isinstance(v, dict):
                        mname = "prisma_" + "_".join(sub)
                        for dim_val, child in v.items():
                            if isinstance(child, dict):
                                for leaf, lv in child.items():
                                    val = num_value(lv)
                                    if val is None:
                                        continue
                                    fam(f"{mname}_{sanitize(leaf)}", ["tenant", sanitize(label)],
                                        f"summary {dotted}.{k}.<{label}>.{leaf}").add_metric([tenant, str(dim_val)], val)
                            else:
                                val = num_value(child)
                                if val is None:
                                    continue
                                fam(mname, ["tenant", sanitize(label)], f"summary {dotted}.{k}.<{label}>").add_metric([tenant, str(dim_val)], val)
                        continue
                    walk(v, sub)
                return
            val = num_value(node)
            if val is not None and path:
                fam("prisma_" + "_".join(path), ["tenant"], f"summary {dotted}").add_metric([tenant], val)

        for k, v in summary.items():
            if k.startswith("@") or k in ("report", "tenant", "schema_version"):
                continue
            walk(v, [sanitize(k)])

        # info metric with the useful strings
        run = summary.get("run") if isinstance(summary.get("run"), dict) else {}
        lic = summary.get("license") if isinstance(summary.get("license"), dict) else {}
        info = InfoMetricFamily("prisma_tenant", "Tenant / collector identity")
        info.add_metric([], {
            "tenant": tenant,
            "api_url": str(run.get("api_url") or ""),
            "customer_name": str(run.get("customer_name") or ""),
            "terraform_module": str(run.get("terraform_module") or ""),
            "provider": str(run.get("provider") or ""),
            "plan_type": str((lic or {}).get("plan_type") or ""),
            "schema_version": str(summary.get("schema_version") or ""),
        })
        yield info

        # curated arrays
        top = get_path(summary, "alerts.top_policies")
        if isinstance(top, list):
            g = GaugeMetricFamily("prisma_alerts_top_policy_open_alerts", "Open alerts of the top alert-generating policies",
                                  labels=["tenant", "policy_id", "policy_name", "severity", "policy_type", "cloud_type"])
            for p in top:
                if not isinstance(p, dict):
                    continue
                val = num_value(p.get("alert_count"))
                if val is None:
                    continue
                g.add_metric([tenant, str(p.get("policy_id", "")), str(p.get("policy_name", "")), str(p.get("severity", "")),
                              str(p.get("policy_type", "")), str(p.get("cloud_type", ""))], val)
            yield g
        flags = get_path(summary, "scores.risk_flags")
        if isinstance(flags, list):
            g = GaugeMetricFamily("prisma_scores_risk_flag", "Active churn-risk signals (1 = active)", labels=["tenant", "flag"])
            for f in flags:
                g.add_metric([tenant, str(f)], 1.0)
            yield g

        yield from families.values()
        sink.add_metric([], float(dropped))
        yield sink

    # -- entities -------------------------------------------------------------------
    def _collect_entities(self) -> Iterable[Any]:
        budget = self.max_entity_series

        def labels_of(line: Dict[str, Any], fields: List[str]) -> List[str]:
            return [str(line.get(f) if line.get(f) is not None else "") for f in fields]

        # cloud accounts
        st = self.reports["prisma_cloud_accounts.jsonl"]
        if isinstance(st.doc, list):
            lf = ["tenant"] + st.spec["labels"]
            g_info = GaugeMetricFamily("prisma_cloud_account_info", "One series per onboarded cloud account (value = 1 enabled, 0 disabled, -1 unknown)", labels=lf)
            g_res = GaugeMetricFamily("prisma_cloud_account_resources_total", "Assets in the account (inventory)", labels=["tenant", "account_id", "name", "cloud_type"])
            g_fail = GaugeMetricFamily("prisma_cloud_account_resources_failed", "Assets failing at least one policy", labels=["tenant", "account_id", "name", "cloud_type"])
            g_lic = GaugeMetricFamily("prisma_cloud_account_license_workloads", "Licence workloads attributed to the account", labels=["tenant", "account_id", "name", "cloud_type"])
            g_child = GaugeMetricFamily("prisma_cloud_account_child_accounts", "Member accounts under an organisation account", labels=["tenant", "account_id", "name", "cloud_type"])
            for line in st.doc[:budget]:
                if not isinstance(line, dict):
                    continue
                tenant = str(line.get("tenant") or self.tenant)
                en = line.get("enabled")
                g_info.add_metric([tenant] + labels_of(line, st.spec["labels"]), 1.0 if en is True else 0.0 if en is False else -1.0)
                short = [tenant] + labels_of(line, ["account_id", "name", "cloud_type"])
                for g, key in ((g_res, "resources_total"), (g_fail, "resources_failed"), (g_lic, "license_workloads"), (g_child, "number_of_child_accounts")):
                    val = num_value(line.get(key))
                    if val is not None:
                        g.add_metric(short, val)
            yield from (g_info, g_res, g_fail, g_lic, g_child)

        # users
        st = self.reports["prisma_users.jsonl"]
        if self.user_metrics and isinstance(st.doc, list):
            lf = ["tenant"] + st.spec["labels"]
            g_days = GaugeMetricFamily("prisma_user_days_since_login", "Days since the user's last login (-1 = never)", labels=lf)
            g_en = GaugeMetricFamily("prisma_user_enabled", "1 if the user profile is enabled", labels=lf)
            g_adm = GaugeMetricFamily("prisma_user_is_admin", "1 if the user holds a System Admin role", labels=lf)
            for line in st.doc[:budget]:
                if not isinstance(line, dict):
                    continue
                tenant = str(line.get("tenant") or self.tenant)
                lv = [tenant] + labels_of(line, st.spec["labels"])
                d = line.get("days_since_login")
                g_days.add_metric(lv, float(d) if is_num(d) else -1.0)
                g_en.add_metric(lv, 1.0 if line.get("enabled") else 0.0)
                g_adm.add_metric(lv, 1.0 if line.get("is_admin") else 0.0)
            yield from (g_days, g_en, g_adm)

        # integrations
        st = self.reports["prisma_integrations.jsonl"]
        if isinstance(st.doc, list):
            lf = ["tenant"] + st.spec["labels"]
            g_valid = GaugeMetricFamily("prisma_integration_valid", "1 if Prisma reports the integration as valid", labels=lf)
            g_en = GaugeMetricFamily("prisma_integration_enabled", "1 if the integration is enabled", labels=lf)
            for line in st.doc[:budget]:
                if not isinstance(line, dict):
                    continue
                tenant = str(line.get("tenant") or self.tenant)
                lv = [tenant] + labels_of(line, st.spec["labels"])
                g_valid.add_metric(lv, 1.0 if line.get("valid") else 0.0)
                g_en.add_metric(lv, 1.0 if line.get("enabled") else 0.0)
            yield from (g_valid, g_en)

        # alert rules
        st = self.reports["prisma_alert_rules.jsonl"]
        if isinstance(st.doc, list):
            lf = ["tenant"] + st.spec["labels"]
            g_en = GaugeMetricFamily("prisma_alert_rule_enabled", "1 if the alert rule is enabled", labels=lf)
            g_open = GaugeMetricFamily("prisma_alert_rule_open_alerts", "Open alerts attributed to the rule", labels=lf)
            g_pol = GaugeMetricFamily("prisma_alert_rule_policies", "Policies attached to the rule", labels=lf)
            for line in st.doc[:budget]:
                if not isinstance(line, dict):
                    continue
                tenant = str(line.get("tenant") or self.tenant)
                lv = [tenant] + labels_of(line, st.spec["labels"])
                g_en.add_metric(lv, 1.0 if line.get("enabled") else 0.0)
                for g, key in ((g_open, "open_alerts_count"), (g_pol, "policies_count")):
                    val = num_value(line.get(key))
                    if val is not None:
                        g.add_metric(lv, val)
            yield from (g_en, g_open, g_pol)

        # custom policies
        st = self.reports["prisma_policies.jsonl"]
        if isinstance(st.doc, list):
            lf = ["tenant"] + st.spec["labels"]
            g_en = GaugeMetricFamily("prisma_custom_policy_enabled", "1 if the custom policy is enabled", labels=lf)
            g_open = GaugeMetricFamily("prisma_custom_policy_open_alerts", "Open alerts of the custom policy", labels=lf)
            for line in st.doc[:budget]:
                if not isinstance(line, dict):
                    continue
                tenant = str(line.get("tenant") or self.tenant)
                lv = [tenant] + labels_of(line, st.spec["labels"])
                g_en.add_metric(lv, 1.0 if line.get("enabled") else 0.0)
                val = num_value(line.get("open_alerts_count"))
                if val is not None:
                    g_open.add_metric(lv, val)
            yield from (g_en, g_open)

    # ---- misc -------------------------------------------------------------------------
    def state_json(self) -> bytes:
        with self.lock:
            out = {
                "tenant": self.tenant,
                "last_scan": self.last_scan,
                "reports": {st.report: {"present": st.doc is not None, "snapshot_ts": st.snapshot_ts,
                                        "lines": (len(st.doc) if isinstance(st.doc, list) else (1 if st.doc else 0)),
                                        "sha256": st.sha} for st in self.reports.values()},
                "runner": self.runner,
                "summary": self.reports["prisma_summary.json"].doc,
            }
        return json.dumps(out, indent=2, default=str).encode()


# --------------------------------------------------------------------------- #
# HTTP                                                                         #
# --------------------------------------------------------------------------- #

def make_handler(scraper: Scraper):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.startswith("/metrics"):
                body = generate_latest(REGISTRY)
                self._send(200, CONTENT_TYPE_LATEST, body)
            elif self.path.startswith("/healthz"):
                ok = scraper.last_scan > 0
                self._send(200 if ok else 503, "text/plain", b"ok\n" if ok else b"no scan yet\n")
            elif self.path.startswith("/state"):
                self._send(200, "application/json", scraper.state_json())
            else:
                self._send(404, "text/plain", b"/metrics /healthz /state\n")

        def _send(self, code: int, ctype: str, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # quiet access log
            LOG.debug(fmt, *args)

    return Handler


# --------------------------------------------------------------------------- #
# main                                                                         #
# --------------------------------------------------------------------------- #

def env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reports-dir", default=os.environ.get("REPORTS_DIR", "/reports"))
    ap.add_argument("--derived-dir", default=os.environ.get("DERIVED_DIR"), help="default: <reports-dir>/derived")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", "9464")))
    ap.add_argument("--bind", default=os.environ.get("BIND", "0.0.0.0"))
    ap.add_argument("--scan-interval", type=float, default=float(os.environ.get("SCAN_INTERVAL", "5")))
    ap.add_argument("--stale-after", type=float, default=float(os.environ.get("STALE_AFTER_SECONDS", "900")))
    ap.add_argument("--once", action="store_true", help="scan once, print metrics to stdout, exit")
    ap.add_argument("--log-level", default=os.environ.get("LOG_LEVEL", "INFO"))
    args = ap.parse_args(argv)

    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    reports_dir = Path(args.reports_dir)
    derived_dir = Path(args.derived_dir) if args.derived_dir else reports_dir / "derived"
    scraper = Scraper(
        reports_dir, derived_dir,
        write_changes=env_bool("WRITE_CHANGES", True),
        entity_metrics=env_bool("ENTITY_METRICS", True),
        user_metrics=env_bool("USER_METRICS", True),
        max_entity_series=int(os.environ.get("MAX_ENTITY_SERIES", "5000")),
        stale_after=args.stale_after,
    )

    if args.once:
        scraper.scan()
        sys.stdout.write(generate_latest(REGISTRY).decode())
        return 0

    server = ThreadingHTTPServer((args.bind, args.port), make_handler(scraper))
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, name="http", daemon=True)
    t.start()
    LOG.info("metrics_scraper %s listening on %s:%d, watching %s every %.1fs",
             VERSION, args.bind, args.port, reports_dir, args.scan_interval)

    stop = threading.Event()

    def _sig(*_):
        stop.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    while not stop.is_set():
        try:
            scraper.scan()
        except Exception:  # noqa: BLE001
            LOG.exception("scan failed")
        stop.wait(args.scan_interval)
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
