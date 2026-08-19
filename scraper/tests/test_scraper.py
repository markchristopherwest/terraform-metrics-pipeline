"""
Unit tests for metrics_scraper.py - run with:  python3 -m unittest discover -s scraper/tests -v
(no pytest required; only prometheus_client)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

from prometheus_client import REGISTRY, generate_latest  # noqa: E402

import fixtures  # noqa: E402
import metrics_scraper as ms  # noqa: E402


def metric_lines(text: str, name: str):
    return [ln for ln in text.splitlines() if ln.startswith(name + "{") or ln.startswith(name + " ")]


def sample(text: str, metric: str, **labels):
    for ln in metric_lines(text, metric):
        if all(f'{k}="{v}"' in ln for k, v in labels.items()):
            return float(ln.rsplit(" ", 1)[1])
    return None


class ScraperTest(unittest.TestCase):
    scraper = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.reports = Path(cls.tmp.name) / "reports"
        cls.derived = cls.reports / "derived"
        fixtures.write_reports(cls.reports, 1)
        cls.scraper = ms.Scraper(cls.reports, cls.derived, stale_after=900)

    @classmethod
    def tearDownClass(cls):
        try:
            REGISTRY.unregister(cls.scraper)
        except Exception:  # noqa: BLE001
            pass
        cls.tmp.cleanup()

    def test_01_first_scan_and_metric_names(self):
        changed = self.scraper.scan()
        self.assertEqual(changed, 6, "all six report files should load on the first scan")
        out = generate_latest(REGISTRY).decode()

        # summary leaves
        self.assertEqual(sample(out, "prisma_cloud_accounts_total", tenant="acme-test"), 4)
        self.assertEqual(sample(out, "prisma_users_human_active_30d", tenant="acme-test"), 1)
        self.assertEqual(sample(out, "prisma_alerts_open", tenant="acme-test"), 312)
        self.assertEqual(sample(out, "prisma_license_workloads_purchased"), 2000)
        self.assertEqual(sample(out, "prisma_scores_risk_score"), 15 + 10 * 0)  # single_active_user only
        # by_<label> maps
        self.assertEqual(sample(out, "prisma_cloud_accounts_by_cloud_type", cloud_type="aws"), 2)
        self.assertEqual(sample(out, "prisma_policies_enabled_by_severity", severity="high"), 312)
        self.assertEqual(sample(out, "prisma_inventory_by_cloud_type_total_resources", cloud_type="azure"), 2400)
        self.assertEqual(sample(out, "prisma_license_usage_by_cloud_type", cloud_type="aws"), 1025)
        self.assertEqual(sample(out, "prisma_activity_events_by_user", user="svc-terraform"), 48)
        self.assertEqual(sample(out, "prisma_enterprise_settings_default_policies_enabled_by_severity", severity="low"), 0)
        self.assertEqual(sample(out, "prisma_scores_risk_points_by_signal", signal="single_active_user_30d"), 15)
        # booleans -> 1/0
        self.assertEqual(sample(out, "prisma_enterprise_settings_audit_logs_enabled"), 1)
        # curated arrays
        self.assertEqual(sample(out, "prisma_alerts_top_policy_open_alerts", policy_id="p1"), 38)
        self.assertEqual(sample(out, "prisma_scores_risk_flag", flag="single_active_user_30d"), 1)
        # arrays that must NOT be flattened
        self.assertEqual(metric_lines(out, "prisma_license_time_series"), [])
        # entities
        self.assertEqual(sample(out, "prisma_cloud_account_info", account_id="210987654321"), 1)
        self.assertEqual(sample(out, "prisma_cloud_account_resources_total", name="acme-prod-aws"), 5210)
        self.assertEqual(sample(out, "prisma_user_days_since_login", user_id="bob.secops@acme.example"), 40)
        self.assertEqual(sample(out, "prisma_user_days_since_login", user_id="carol.cloud@acme.example"), -1)
        self.assertEqual(sample(out, "prisma_integration_valid", integration_id="int-2"), 1)
        self.assertEqual(sample(out, "prisma_alert_rule_enabled", rule_id="rule-2"), 1)
        self.assertEqual(sample(out, "prisma_custom_policy_enabled", policy_id="custom-1"), 1)
        # pipeline / runner
        self.assertEqual(sample(out, "prisma_report_lines", report="users"), 4)
        self.assertEqual(sample(out, "prisma_runner_last_run_success", module="fixtures"), 1)
        self.assertIsNotNone(sample(out, "prisma_snapshot_timestamp_seconds", report="summary"))
        self.assertEqual(sample(out, "prisma_scraper_dropped_samples"), 0)
        # info metrics
        self.assertIn('prisma_tenant_info{', out)
        self.assertIn('plan_type="ENTERPRISE"', out)

        # exposition must be parseable by Prometheus' text parser
        from prometheus_client.parser import text_string_to_metric_families
        families = list(text_string_to_metric_families(out))
        names = [f.name for f in families]
        self.assertEqual(len(names), len(set(names)), "duplicate metric families in exposition")

    def test_02_baseline_event_written(self):
        feed = self.derived / "prisma_changes.jsonl"
        self.assertTrue(feed.exists())
        events = [json.loads(l) for l in feed.read_text().splitlines() if l.strip()]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["change"], "baseline")
        self.assertEqual(events[0]["report"], "changes")
        self.assertEqual(events[0]["tenant"], "acme-test")
        self.assertTrue((self.derived / ".scraper_state.json").exists())

    def test_03_unchanged_rescan_is_noop(self):
        self.assertEqual(self.scraper.scan(), 0)

    def test_04_partial_write_is_ignored(self):
        p = self.reports / "prisma_integrations.jsonl"
        good = p.read_text()
        p.write_text(good.rstrip("\n"))          # no trailing newline = mid-write
        self.assertEqual(self.scraper.scan(), 0)
        p.write_text(good)                        # restore (same sha as before -> no reload)
        self.assertEqual(self.scraper.scan(), 0)

    def test_05_second_run_changes(self):
        fixtures.write_reports(self.reports, 2)
        changed = self.scraper.scan()
        self.assertGreaterEqual(changed, 5)
        feed = self.derived / "prisma_changes.jsonl"
        events = [json.loads(l) for l in feed.read_text().splitlines() if l.strip()]
        kinds = {(e["entity"], e["change"], e.get("id")) for e in events}
        self.assertIn(("cloud_account", "disabled", "210987654321"), kinds)
        self.assertIn(("cloud_account", "changed", "f5b1c2d3-0001"), kinds)        # status ok -> warning
        self.assertIn(("cloud_account", "removed", "acme-platform-gcp"), kinds)
        self.assertIn(("user", "logged_in", "bob.secops@acme.example"), kinds)
        self.assertIn(("user", "added", "dave.new@acme.example"), kinds)
        self.assertIn(("integration", "broken", "int-2"), kinds)
        self.assertIn(("alert_rule", "disabled", "rule-2"), kinds)
        self.assertIn(("custom_policy", "added", "custom-2"), kinds)
        self.assertIn(("summary", "metric_changed", "cloud_accounts.total"), kinds)
        self.assertIn(("risk_flag", "raised", "accounts_disabled"), kinds)
        self.assertIn(("risk_flag", "cleared", "single_active_user_30d"), kinds)
        # every event carries the Loki-friendly envelope
        for e in events:
            for k in ("@timestamp", "report", "tenant", "entity", "change", "id", "name", "detail"):
                self.assertIn(k, e, f"missing {k} in {e}")
        removed = [e for e in events if e["change"] == "removed"][0]
        self.assertEqual(removed["cloud_type"], "gcp")

        out = generate_latest(REGISTRY).decode()
        # removed account no longer exported, disabled account shows 0
        self.assertIsNone(sample(out, "prisma_cloud_account_info", account_id="acme-platform-gcp"))
        self.assertEqual(sample(out, "prisma_cloud_account_info", account_id="210987654321"), 0)
        self.assertEqual(sample(out, "prisma_cloud_accounts_total"), 3)
        self.assertEqual(sample(out, "prisma_integration_valid", integration_id="int-2"), 0)
        self.assertEqual(sample(out, "prisma_scores_risk_flag", flag="accounts_disabled"), 1)
        self.assertIsNone(sample(out, "prisma_scores_risk_flag", flag="single_active_user_30d"))
        self.assertGreaterEqual(sample(out, "prisma_changes_total", entity="cloud_account", change="removed"), 1)

    def test_06_state_survives_restart(self):
        # a fresh scraper on the same dir must not re-emit a baseline or fake "added" events
        REGISTRY.unregister(self.scraper)
        s2 = ms.Scraper(self.reports, self.derived, stale_after=900)
        try:
            before = len((self.derived / "prisma_changes.jsonl").read_text().splitlines())
            s2.scan()
            after = len((self.derived / "prisma_changes.jsonl").read_text().splitlines())
            self.assertEqual(before, after)
        finally:
            REGISTRY.unregister(s2)
            REGISTRY.register(self.scraper)

    def test_07_state_endpoint_json(self):
        data = json.loads(self.scraper.state_json())
        self.assertEqual(data["tenant"], "acme-test")
        self.assertEqual(data["reports"]["users"]["lines"], 5)


class HelperTest(unittest.TestCase):
    def test_by_label(self):
        self.assertEqual(ms.by_label("by_cloud_type"), "cloud_type")
        self.assertEqual(ms.by_label("enabled_by_severity"), "severity")
        self.assertEqual(ms.by_label("events_by_user"), "user")
        self.assertIsNone(ms.by_label("total"))
        self.assertIsNone(ms.by_label("standby"))

    def test_sanitize(self):
        self.assertEqual(ms.sanitize("90d+"), "_90d_")
        self.assertEqual(ms.sanitize("1abc"), "_1abc")

    def test_parse_ts(self):
        self.assertEqual(ms.parse_ts("2026-08-19T12:00:00Z"), 1787140800.0)
        self.assertIsNone(ms.parse_ts("nope"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
