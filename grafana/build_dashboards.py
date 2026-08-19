#!/usr/bin/env python3
"""
Generates the Grafana dashboards in grafana/dashboards/*.json.

    python3 grafana/build_dashboards.py            # rewrite the JSON files
    python3 grafana/build_dashboards.py --check    # fail if the files are out of date

Keeping the dashboards as code makes the ~3000 lines of panel JSON reviewable:
metric names live in ONE place, colours follow the same palette everywhere
(cloud type / severity / status are always the same hue), and the layout is
computed instead of hand-edited.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

OUT = Path(__file__).resolve().parent / "dashboards"

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
TENANT = '{tenant=~"$tenant"}'          # every Prometheus query is scoped by the tenant variable
LOKI_STREAM = 'job="prisma_reports", tenant=~"$tenant"'

# ---------------------------------------------------------------------------
# Palette (dark-surface steps of a CVD-validated categorical order; status colours
# are reserved for "how bad is it" and never reused for a category)
# ---------------------------------------------------------------------------
CAT = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
CLOUD_COLORS = {"aws": CAT[0], "azure": CAT[1], "gcp": CAT[2], "oci": CAT[3], "alibaba_cloud": CAT[4],
                "ibm": CAT[5], "other": CAT[6], "all": CAT[6], "unknown": "#8e8e8e"}
SEVERITY_COLORS = {"critical": "#d03b3b", "high": "#ec835a", "medium": "#fab219", "low": "#86b6ef",
                   "informational": "#9ec5f4", "unknown": "#8e8e8e"}
STATUS_COLORS = {"open": "#ec835a", "resolved": "#0ca30c", "dismissed": "#8e8e8e", "snoozed": "#fab219",
                 "ok": "#0ca30c", "warning": "#fab219", "error": "#d03b3b", "enabled": "#0ca30c", "disabled": "#d03b3b",
                 "valid": "#0ca30c", "invalid": "#d03b3b", "purchased": "#8e8e8e", "used": CAT[0], "total": CAT[0]}
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
NEUTRAL = "text"


def color_overrides(mapping: Dict[str, str]) -> List[Dict[str, Any]]:
    return [{"matcher": {"id": "byName", "options": k},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": v}}]} for k, v in mapping.items()]


def thresholds(steps: List[tuple]) -> Dict[str, Any]:
    """steps: [(None, color), (value, color), ...]"""
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for v, c in steps]}


NEUTRAL_THRESHOLDS = thresholds([(None, NEUTRAL)])

# ---------------------------------------------------------------------------
# Layout helper
# ---------------------------------------------------------------------------


class Grid:
    def __init__(self):
        self.y = 0
        self.x = 0
        self.row_h = 0
        self.panels: List[Dict[str, Any]] = []
        self._id = 0

    def next_id(self) -> int:
        self._id += 1
        return self._id

    def place(self, panel: Dict[str, Any], w: int, h: int) -> Dict[str, Any]:
        if self.x + w > 24:
            self.newline()
        panel["gridPos"] = {"h": h, "w": w, "x": self.x, "y": self.y}
        panel["id"] = self.next_id()
        self.x += w
        self.row_h = max(self.row_h, h)
        self.panels.append(panel)
        return panel

    def newline(self):
        if self.x > 0:
            self.y += self.row_h
        self.x = 0
        self.row_h = 0

    def row(self, title: str):
        self.newline()
        self.panels.append({"type": "row", "title": title, "collapsed": False, "id": self.next_id(),
                            "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []})
        self.y += 1


# ---------------------------------------------------------------------------
# Panel builders
# ---------------------------------------------------------------------------


def prom_target(expr: str, legend: str = "", ref: str = "A", instant: bool = False, fmt: str = "time_series") -> Dict[str, Any]:
    t = {"refId": ref, "datasource": PROM, "expr": expr, "legendFormat": legend or "__auto", "editorMode": "code"}
    if instant:
        t.update({"instant": True, "range": False, "format": fmt})
    else:
        t.update({"instant": False, "range": True, "format": fmt})
    return t


def loki_target(expr: str, ref: str = "A", legend: str = "", instant: bool = False) -> Dict[str, Any]:
    t = {"refId": ref, "datasource": LOKI, "expr": expr, "queryType": "instant" if instant else "range",
         "editorMode": "code"}
    if legend:
        t["legendFormat"] = legend
    return t


def stat(title: str, expr: str, *, unit: str = "short", decimals: int = 0, thr: Optional[Dict[str, Any]] = None,
         description: str = "", color_mode: str = "value", graph: str = "none", legend: str = "") -> Dict[str, Any]:
    return {
        "type": "stat", "title": title, "description": description, "datasource": PROM,
        "targets": [prom_target(expr, legend=legend, instant=False)],
        "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "thresholds"},
                                     "thresholds": thr or NEUTRAL_THRESHOLDS, "noValue": "–"}, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "colorMode": color_mode, "graphMode": graph, "textMode": "auto", "orientation": "auto",
                    "justifyMode": "center", "wideLayout": True, "showPercentChange": False},
    }


def timeseries(title: str, targets: List[Dict[str, Any]], *, unit: str = "short", decimals: Optional[int] = None,
               stack: bool = False, fill: int = 8, description: str = "", overrides: Optional[List[Dict[str, Any]]] = None,
               legend: bool = True, min_val: Optional[float] = None, max_val: Optional[float] = None,
               thr: Optional[Dict[str, Any]] = None, thr_style: str = "off", datasource: Dict[str, Any] = PROM,
               draw: str = "line", interpolation: str = "stepAfter", step_width: int = 2) -> Dict[str, Any]:
    custom = {
        "drawStyle": draw, "lineInterpolation": interpolation, "lineWidth": step_width, "fillOpacity": fill,
        "gradientMode": "none", "showPoints": "never", "pointSize": 4, "spanNulls": 1800000,
        "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        "axisPlacement": "auto", "axisLabel": "", "axisBorderShow": False, "scaleDistribution": {"type": "linear"},
        "thresholdsStyle": {"mode": thr_style}, "barAlignment": 0,
    }
    defaults: Dict[str, Any] = {"unit": unit, "color": {"mode": "palette-classic"}, "custom": custom,
                                "thresholds": thr or NEUTRAL_THRESHOLDS}
    if decimals is not None:
        defaults["decimals"] = decimals
    if min_val is not None:
        defaults["min"] = min_val
    if max_val is not None:
        defaults["max"] = max_val
    return {
        "type": "timeseries", "title": title, "description": description, "datasource": datasource,
        "targets": targets,
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        "options": {"legend": {"displayMode": "list", "placement": "bottom", "showLegend": legend, "calcs": []},
                    "tooltip": {"mode": "multi", "sort": "desc"}},
    }


def bargauge(title: str, expr: str, legend: str, *, unit: str = "short", description: str = "",
             overrides: Optional[List[Dict[str, Any]]] = None, color: str = CAT[0], max_val: Optional[float] = None,
             thr: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {"unit": unit, "decimals": 0, "color": {"mode": "fixed", "fixedColor": color},
                                "thresholds": NEUTRAL_THRESHOLDS, "min": 0}
    if thr:
        defaults["color"] = {"mode": "thresholds"}
        defaults["thresholds"] = thr
    if max_val is not None:
        defaults["max"] = max_val
    return {
        "type": "bargauge", "title": title, "description": description, "datasource": PROM,
        "targets": [prom_target(expr, legend=legend, instant=True)],
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        "options": {"orientation": "horizontal", "displayMode": "basic", "showUnfilled": True, "valueMode": "color",
                    "namePlacement": "left", "sizing": "auto", "minVizWidth": 8, "minVizHeight": 16, "maxVizHeight": 300,
                    "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                    "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom", "calcs": []}},
    }


def table(title: str, targets: List[Dict[str, Any]], transformations: List[Dict[str, Any]], *, description: str = "",
          overrides: Optional[List[Dict[str, Any]]] = None, datasource: Dict[str, Any] = PROM,
          sort_by: Optional[str] = None, desc: bool = True) -> Dict[str, Any]:
    opts: Dict[str, Any] = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False, "reducer": ["sum"], "fields": ""}}
    if sort_by:
        opts["sortBy"] = [{"displayName": sort_by, "desc": desc}]
    return {
        "type": "table", "title": title, "description": description, "datasource": datasource,
        "targets": targets, "transformations": transformations,
        "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True},
                                     "thresholds": NEUTRAL_THRESHOLDS, "color": {"mode": "thresholds"}},
                        "overrides": overrides or []},
        "options": opts,
    }


def logs(title: str, expr: str, *, description: str = "") -> Dict[str, Any]:
    return {
        "type": "logs", "title": title, "description": description, "datasource": LOKI,
        "targets": [loki_target(expr)],
        "options": {"showTime": True, "showLabels": False, "showCommonLabels": False, "wrapLogMessage": True,
                    "prettifyLogMessage": False, "enableLogDetails": True, "dedupStrategy": "none",
                    "sortOrder": "Descending"},
    }


def text(title: str, md: str, h: int = 8) -> Dict[str, Any]:
    return {"type": "text", "title": title, "options": {"mode": "markdown", "content": md}, "_h": h}


def state_timeline(title: str, expr: str, legend: str, *, description: str = "") -> Dict[str, Any]:
    return {
        "type": "state-timeline", "title": title, "description": description, "datasource": PROM,
        "targets": [prom_target(expr, legend=legend)],
        "fieldConfig": {"defaults": {"custom": {"lineWidth": 0, "fillOpacity": 75, "spanNulls": False},
                                     "color": {"mode": "thresholds"},
                                     "thresholds": thresholds([(None, "transparent"), (1, SERIOUS)]),
                                     "mappings": [{"type": "value", "options": {"1": {"text": "active", "color": SERIOUS}}}]},
                        "overrides": []},
        "options": {"showValue": "never", "mergeValues": True, "rowHeight": 0.8, "alignValue": "left",
                    "legend": {"showLegend": False, "displayMode": "list", "placement": "bottom"},
                    "tooltip": {"mode": "single", "sort": "none"}},
    }


def dashboard(uid: str, title: str, panels: List[Dict[str, Any]], *, description: str, tags: List[str],
              extra_vars: Optional[List[Dict[str, Any]]] = None, time_from: str = "now-24h", links: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    tenant_var = {
        "name": "tenant", "label": "Tenant", "type": "query", "datasource": PROM,
        "definition": "label_values(prisma_cloud_accounts_total, tenant)",
        "query": {"query": "label_values(prisma_cloud_accounts_total, tenant)", "refId": "PrometheusVariableQueryEditor-VariableQuery"},
        "refresh": 2, "includeAll": True, "multi": True, "allValue": ".*", "sort": 1,
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]}, "hide": 0, "options": [],
    }
    return {
        "uid": uid, "title": title, "description": description, "tags": tags, "timezone": "browser",
        "editable": True, "graphTooltip": 1, "fiscalYearStartMonth": 0, "liveNow": False,
        "refresh": "1m", "schemaVersion": 39, "version": 1, "weekStart": "",
        "time": {"from": time_from, "to": "now"},
        "timepicker": {"refresh_intervals": ["30s", "1m", "5m", "15m", "1h"]},
        "templating": {"list": [tenant_var] + (extra_vars or [])},
        "annotations": {"list": [
            {"builtIn": 1, "datasource": {"type": "grafana", "uid": "-- Grafana --"}, "enable": True, "hide": True,
             "iconColor": "rgba(0, 211, 255, 1)", "name": "Annotations & Alerts", "type": "dashboard"},
            {"datasource": LOKI, "enable": True, "hide": False, "iconColor": SERIOUS, "name": "Removed / disabled / broken",
             "expr": '{' + LOKI_STREAM + ', report="changes"} | json | change=~"removed|disabled|broken|admin_granted" | line_format "{{.entity}} {{.change}}: {{.name}}"',
             "target": {"expr": '{' + LOKI_STREAM + ', report="changes"} | json | change=~"removed|disabled|broken|admin_granted" | line_format "{{.entity}} {{.change}}: {{.name}}"', "refId": "Anno"}},
        ]},
        "links": links or [
            {"title": "Consumption & Adoption", "type": "link", "url": "/d/prisma-consumption", "icon": "dashboard", "keepTime": True, "includeVars": True},
            {"title": "Churn Risk & Health", "type": "link", "url": "/d/prisma-churn", "icon": "dashboard", "keepTime": True, "includeVars": True},
            {"title": "Snapshot Explorer (Loki)", "type": "link", "url": "/d/prisma-explorer", "icon": "dashboard", "keepTime": True, "includeVars": True},
        ],
        "panels": panels,
    }


# ---------------------------------------------------------------------------
# Dashboard 1: Consumption & Adoption
# ---------------------------------------------------------------------------

def build_consumption() -> Dict[str, Any]:
    g = Grid()
    g.row("Tenant at a glance")
    util_thr = thresholds([(None, CRIT), (25, SERIOUS), (50, WARN), (75, GOOD)])
    adoption_thr = thresholds([(None, CRIT), (40, SERIOUS), (60, WARN), (75, GOOD)])
    tiles = [
        ("Cloud accounts", f"prisma_cloud_accounts_total{TENANT}", "short", None, "Accounts onboarded (provider listing)."),
        ("Enabled accounts", f"prisma_cloud_accounts_enabled{TENANT}", "short", None, "Accounts with enabled=true (GET /cloud enrichment)."),
        ("Resources monitored", f"prisma_inventory_total_resources{TENANT}", "short", None, "Asset inventory total (GET /v3/inventory)."),
        ("Licence workloads in use", f"prisma_license_usage_total{TENANT}", "short", None, "Average workloads over the usage window (POST /license/api/v2/usage)."),
        ("Workloads purchased", f"prisma_license_workloads_purchased{TENANT}", "short", None, "From the licence time-series endpoint."),
        ("Licence utilisation", f"prisma_license_utilization_pct{TENANT}", "percent", util_thr, "usage / purchased. < 25 % means the customer is paying for capacity it does not use - a classic churn precursor."),
    ]
    for title, expr, unit, thr, desc in tiles:
        g.place(stat(title, expr, unit=unit, thr=thr, description=desc), 4, 4)
    tiles2 = [
        ("Human users", f"prisma_users_human_total{TENANT}", "short", None, "USER_ACCOUNT profiles (service accounts excluded)."),
        ("Active humans (30d)", f"prisma_users_human_active_30d{TENANT}", "short", None, "Humans with a login in the last 30 days."),
        ("Policies enabled", f"prisma_policies_enabled{TENANT}", "short", None, ""),
        ("Custom policies", f"prisma_policies_custom_enabled{TENANT}", "short", None, "Enabled non-default policies - depth of adoption."),
        ("Alert rules enabled", f"prisma_alert_rules_enabled{TENANT}", "short", None, ""),
        ("Adoption score", f"prisma_scores_adoption_score{TENANT}", "short", adoption_thr, "0-100, weights in terraform/variables.tf (adoption_weights)."),
    ]
    for title, expr, unit, thr, desc in tiles2:
        g.place(stat(title, expr, unit=unit, thr=thr, description=desc), 4, 4)

    g.row("Consumption over time")
    g.place(timeseries("Cloud accounts by cloud type", [prom_target(f"prisma_cloud_accounts_by_cloud_type{TENANT}", "{{cloud_type}}")],
                       overrides=color_overrides(CLOUD_COLORS), description="Onboarded accounts per provider. A falling line = accounts removed."), 8, 8)
    g.place(timeseries("Resources by cloud type", [prom_target(f"prisma_inventory_by_cloud_type_total_resources{TENANT}", "{{cloud_type}}")],
                       overrides=color_overrides(CLOUD_COLORS), description="Asset inventory per provider - the footprint Prisma is actually scanning."), 8, 8)
    g.place(timeseries("Licence usage by cloud type vs purchased",
                       [prom_target(f"prisma_license_usage_by_cloud_type{TENANT}", "{{cloud_type}}"),
                        prom_target(f"prisma_license_workloads_purchased{TENANT}", "purchased", ref="B")],
                       stack=True, fill=30,
                       overrides=color_overrides(CLOUD_COLORS) + [
                           {"matcher": {"id": "byName", "options": "purchased"},
                            "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": "#8e8e8e"}},
                                           {"id": "custom.stacking", "value": {"mode": "none", "group": "A"}},
                                           {"id": "custom.fillOpacity", "value": 0},
                                           {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}}]}],
                       description="Stacked usage against the entitlement (dashed). The gap is unconsumed licence."), 8, 8)
    g.place(timeseries("Licence usage by resource type", [prom_target(f"prisma_license_usage_by_resource_type{TENANT}", "{{resource_type}}")],
                       stack=True, fill=30, description="Which workload classes drive consumption (VMs, containers, serverless, PaaS ...)."), 8, 8)
    g.place(timeseries("Credits purchased vs used",
                       [prom_target(f"prisma_license_credits_purchased{TENANT}", "purchased"),
                        prom_target(f"prisma_license_credits_used{TENANT}", "used", ref="B")],
                       overrides=color_overrides(STATUS_COLORS), description="Credit-based licences only (POST /license/api/v1/credit-allocation-rule-summary). Empty on workload-based plans."), 8, 8)
    g.place(timeseries("Inventory: total / passed / failed",
                       [prom_target(f"prisma_inventory_total_resources{TENANT}", "total"),
                        prom_target(f"prisma_inventory_passed_resources{TENANT}", "passed", ref="B"),
                        prom_target(f"prisma_inventory_failed_resources{TENANT}", "failed", ref="C")],
                       overrides=color_overrides({"total": CAT[0], "passed": GOOD, "failed": SERIOUS}),
                       description="Compliance posture of the scanned estate."), 8, 8)

    g.row("Adoption depth - is the product wired into how they work?")
    g.place(timeseries("Policies enabled by type", [prom_target(f"prisma_policies_enabled_by_type{TENANT}", "{{type}}")],
                       description="config / network / audit_event / anomaly / iam / data ... Modules that stay at 0 are modules they bought but do not use."), 8, 8)
    g.place(timeseries("Customisation footprint",
                       [prom_target(f"prisma_policies_custom_enabled{TENANT}", "custom policies"),
                        prom_target(f"prisma_compliance_standards_custom{TENANT}", "custom compliance standards", ref="B"),
                        prom_target(f"prisma_saved_searches_saved{TENANT}", "saved searches", ref="C"),
                        prom_target(f"prisma_reports_total{TENANT}", "scheduled reports", ref="D"),
                        prom_target(f"prisma_roles_custom{TENANT}", "custom roles", ref="E")],
                       description="Things a customer only creates when the product is part of their process."), 8, 8)
    g.place(timeseries("Alert rules & integrations",
                       [prom_target(f"prisma_alert_rules_enabled{TENANT}", "alert rules enabled"),
                        prom_target(f"prisma_alert_rules_disabled{TENANT}", "alert rules disabled", ref="B"),
                        prom_target(f"prisma_integrations_valid{TENANT}", "integrations valid", ref="C"),
                        prom_target(f"prisma_integrations_invalid{TENANT}", "integrations invalid", ref="D")],
                       overrides=color_overrides({"alert rules enabled": CAT[0], "alert rules disabled": "#8e8e8e",
                                                  "integrations valid": GOOD, "integrations invalid": CRIT}),
                       description="No enabled alert rule or no valid integration = findings never reach anybody."), 8, 8)
    g.place(bargauge("Integrations by type", f"prisma_integrations_by_type{TENANT}", "{{integration_type}}",
                     description="Slack / Splunk / ServiceNow / PagerDuty ... - each is a hook into the customer's workflow."), 6, 8)
    g.place(bargauge("Adoption points by signal", f"prisma_scores_adoption_points_by_signal{TENANT}", "{{signal}}",
                     description="How the adoption score is earned (terraform/variables.tf: adoption_weights)."), 9, 8)
    g.place(timeseries("Adoption score", [prom_target(f"prisma_scores_adoption_score{TENANT}", "adoption score")],
                       min_val=0, max_val=100, thr=adoption_thr, thr_style="area", legend=False,
                       description="Point-in-time adoption heuristic computed by Terraform every run."), 9, 8)

    g.row("Who is using it? (engagement)")
    g.place(timeseries("Human users: active vs total",
                       [prom_target(f"prisma_users_human_total{TENANT}", "total"),
                        prom_target(f"prisma_users_human_active_90d{TENANT}", "active 90d", ref="B"),
                        prom_target(f"prisma_users_human_active_30d{TENANT}", "active 30d", ref="C"),
                        prom_target(f"prisma_users_human_active_7d{TENANT}", "active 7d", ref="D")],
                       overrides=color_overrides({"total": "#8e8e8e", "active 90d": CAT[3], "active 30d": CAT[0], "active 7d": CAT[2]}),
                       description="Derived from last_login_ts of every user profile."), 8, 8)
    g.place(bargauge("Humans by last login", f"prisma_users_by_login_bucket{TENANT}", "{{login_bucket}}",
                     description="7d / 30d / 90d / 90d_plus / never."), 4, 8)
    g.place(timeseries("Console activity (audit log, trailing window)", [prom_target(f"prisma_activity_by_action_type{TENANT}", "{{action_type}}")],
                       stack=True, fill=30, description="Events by action type in the last activity window (default 24h). Flat zero = nobody is in the console."), 6, 8)
    g.place(bargauge("Most active identities (audit log)", f"prisma_activity_events_by_user{TENANT}", "{{user}}",
                     description="Top identities by audit events. Only service accounts here = automation without humans."), 6, 8)

    g.row("Accounts & policies (current snapshot)")
    acct_tbl = table("Cloud accounts",
                     [prom_target(f"prisma_cloud_account_info{TENANT}", instant=True, fmt="table", ref="A"),
                      prom_target(f"prisma_cloud_account_resources_total{TENANT}", instant=True, fmt="table", ref="B"),
                      prom_target(f"prisma_cloud_account_resources_failed{TENANT}", instant=True, fmt="table", ref="C"),
                      prom_target(f"prisma_cloud_account_license_workloads{TENANT}", instant=True, fmt="table", ref="D"),
                      prom_target(f"prisma_cloud_account_child_accounts{TENANT}", instant=True, fmt="table", ref="E")],
                     [{"id": "merge", "options": {}},
                      {"id": "organize", "options": {
                          "excludeByName": {"Time": True, "__name__": True, "instance": True, "job": True, "tenant": True},
                          "renameByName": {"Value #A": "enabled", "Value #B": "resources", "Value #C": "failing",
                                           "Value #D": "licence workloads", "Value #E": "child accounts"},
                          "indexByName": {"name": 0, "cloud_type": 1, "account_id": 2, "account_type": 3, "status": 4,
                                          "protection_mode": 5, "enabled": 6, "resources": 7, "failing": 8,
                                          "licence workloads": 9, "child accounts": 10}}}],
                     description="One row per onboarded account (enabled: 1 yes, 0 no, -1 unknown without API enrichment).",
                     overrides=[{"matcher": {"id": "byName", "options": "enabled"},
                                 "properties": [{"id": "custom.cellOptions", "value": {"type": "color-text"}},
                                                {"id": "thresholds", "value": thresholds([(None, "#8e8e8e"), (0, CRIT), (1, GOOD)])},
                                                {"id": "color", "value": {"mode": "thresholds"}}]}],
                     sort_by="resources")
    g.place(acct_tbl, 14, 10)
    top_tbl = table("Top alert-generating policies (open alerts)",
                    [prom_target(f"prisma_alerts_top_policy_open_alerts{TENANT}", instant=True, fmt="table")],
                    [{"id": "organize", "options": {
                        "excludeByName": {"Time": True, "__name__": True, "instance": True, "job": True, "tenant": True, "policy_id": True},
                        "renameByName": {"Value": "open alerts"},
                        "indexByName": {"policy_name": 0, "severity": 1, "policy_type": 2, "cloud_type": 3, "open alerts": 4}}}],
                    description="Where the noise comes from. A handful of policies producing most alerts = tuning conversation.",
                    overrides=[{"matcher": {"id": "byName", "options": "open alerts"},
                                "properties": [{"id": "custom.cellOptions", "value": {"type": "gauge", "mode": "basic"}},
                                               {"id": "color", "value": {"mode": "fixed", "fixedColor": SERIOUS}}]}],
                    sort_by="open alerts")
    g.place(top_tbl, 10, 10)

    return dashboard("prisma-consumption", "Prisma Cloud - Consumption & Adoption", g.panels,
                     description="What the customer is consuming and how deeply the product is adopted. Source: Terraform snapshots every 5 min -> metrics_scraper -> Prometheus.",
                     tags=["prisma-cloud", "consumption", "post-sales"])


# ---------------------------------------------------------------------------
# Dashboard 2: Churn Risk & Health
# ---------------------------------------------------------------------------

PLAYBOOK_MD = """
### How to read this dashboard (post-sales view)

**Churn-risk score** = point-in-time heuristic computed by Terraform from the latest snapshot
(`scores.risk_score`, weights in `terraform/variables.tf`). **Trend score** = Prometheus recording
rules that need history (`prometheus/rules/prisma_rules.yml`). Both are 0 (healthy) to 100.

| Signal | Why it predicts churn | Typical action |
|---|---|---|
| No human login 14-30 d, active users &darr; | Nobody is looking at findings - the tool is shelf-ware | Exec sponsor check-in, enablement session |
| Cloud accounts shrinking / disabled | Footprint being pulled out, or a migration you don't know about | Ask about cloud strategy; re-onboard |
| Licence utilisation &lt; 25-50 % | Paying for unused capacity = renewal pressure | Right-size or drive onboarding of more accounts |
| Open alerts flat/growing with 0 resolved / dismissed | Alert fatigue, no owner | Tune policies & alert rules, integrate with ticketing |
| Integrations invalid, alert rules disabled | Findings no longer reach the customer's tools | Fix credentials, re-enable |
| Custom policies / saved searches / reports at 0 | Product never became part of their process | Workshop: custom policies, compliance reports |

**Consumption** (&rarr; *Consumption & Adoption*): workloads/credits used vs purchased, resources by cloud,
policies enabled per module, integrations. Growth = expansion signal; decline = early churn signal.
"""


def build_churn() -> Dict[str, Any]:
    g = Grid()
    g.row("Risk at a glance")
    risk_thr = thresholds([(None, GOOD), (25, WARN), (50, SERIOUS), (75, CRIT)])
    days_thr = thresholds([(None, GOOD), (7, WARN), (30, SERIOUS), (90, CRIT)])
    stale_thr = thresholds([(None, GOOD), (600, WARN), (900, SERIOUS), (1800, CRIT)])
    util_thr = thresholds([(None, CRIT), (25, SERIOUS), (50, WARN), (75, GOOD)])
    ratio_thr = thresholds([(None, CRIT), (0.25, SERIOUS), (0.5, WARN), (0.75, GOOD)])
    g.place(stat("Churn risk (snapshot)", f"prisma_scores_risk_score{TENANT}", thr=risk_thr, color_mode="background",
                 description="Point-in-time heuristic from the latest Terraform snapshot, 0-100."), 4, 4)
    g.place(stat("Churn risk (30-day trend)", 'prisma:churn_risk_trend_score{tenant=~"$tenant"}', thr=risk_thr, color_mode="background",
                 description="Prometheus recording rule over history (accounts shrinking, usage falling, logins drying up). Needs a few days of data."), 4, 4)
    g.place(stat("Days since last human login", f"prisma_users_days_since_last_human_login{TENANT}", unit="d", decimals=1, thr=days_thr,
                 description="Max over all USER_ACCOUNT profiles."), 4, 4)
    g.place(stat("Active humans 30d", f"prisma_users_human_active_30d{TENANT}"), 4, 4)
    g.place(stat("Active-user ratio 30d", 'prisma:users_active_ratio_30d{tenant=~"$tenant"}', unit="percentunit", decimals=0, thr=ratio_thr), 4, 4)
    g.place(stat("Licence utilisation", f"prisma_license_utilization_pct{TENANT}", unit="percent", thr=util_thr), 4, 4)
    g.place(stat("Accounts disabled", f"prisma_cloud_accounts_disabled{TENANT}", thr=thresholds([(None, GOOD), (1, SERIOUS)])), 4, 4)
    g.place(stat("Integrations invalid", f"prisma_integrations_invalid{TENANT}", thr=thresholds([(None, GOOD), (1, CRIT)])), 4, 4)
    g.place(stat("Alert rules enabled", f"prisma_alert_rules_enabled{TENANT}", thr=thresholds([(None, CRIT), (1, GOOD)])), 4, 4)
    g.place(stat("Open alerts", f"prisma_alerts_open{TENANT}"), 4, 4)
    g.place(stat("Resolved last 7d", f"prisma_alerts_resolved_7d{TENANT}", thr=thresholds([(None, SERIOUS), (1, GOOD)]),
                 description="0 resolved while alerts are open = nobody is working the queue."), 4, 4)
    g.place(stat("Snapshot age", 'prisma_snapshot_age_seconds{tenant=~"$tenant", report="summary"}', unit="s", thr=stale_thr,
                 description="Time since the last Terraform run wrote prisma_summary.json (expected < 5-10 min)."), 4, 4)

    g.row("Risk signals")
    g.place(state_timeline("Churn-risk flags over time", f"prisma_scores_risk_flag{TENANT}", "{{flag}}",
                           description="Each row is one risk signal; a filled segment means it was active in that snapshot."), 12, 8)
    g.place(bargauge("Risk points by signal (snapshot)", f"prisma_scores_risk_points_by_signal{TENANT}", "{{signal}}",
                     color=SERIOUS, description="How the snapshot risk score is composed."), 6, 8)
    g.place(bargauge("Risk points by signal (trend)", '{__name__=~"prisma:risk_component:.+", tenant=~"$tenant"}', "{{__name__}}",
                     color=CRIT, description="Trend components from Prometheus recording rules."), 6, 8)
    g.place(timeseries("Churn risk & adoption over time",
                       [prom_target(f"prisma_scores_risk_score{TENANT}", "risk (snapshot)"),
                        prom_target('prisma:churn_risk_trend_score{tenant=~"$tenant"}', "risk (trend)", ref="B"),
                        prom_target(f"prisma_scores_adoption_score{TENANT}", "adoption", ref="C")],
                       min_val=0, max_val=100, overrides=color_overrides({"risk (snapshot)": SERIOUS, "risk (trend)": CRIT, "adoption": GOOD}),
                       description="Risk up while adoption down is the pattern to act on."), 12, 8)
    g.place(timeseries("Change events per day (from the change feed)",
                       [prom_target(f'sum by (entity) (increase(prisma_changes_total{TENANT}[1d]))', "{{entity}}")],
                       stack=True, fill=30, draw="bars", interpolation="linear",
                       description="Structural changes detected by metrics_scraper between snapshots (accounts, users, integrations, rules, policies, risk flags)."), 12, 8)

    g.row("Engagement")
    g.place(timeseries("Human users: active vs total",
                       [prom_target(f"prisma_users_human_total{TENANT}", "total"),
                        prom_target(f"prisma_users_human_active_90d{TENANT}", "active 90d", ref="B"),
                        prom_target(f"prisma_users_human_active_30d{TENANT}", "active 30d", ref="C"),
                        prom_target(f"prisma_users_human_active_7d{TENANT}", "active 7d", ref="D")],
                       overrides=color_overrides({"total": "#8e8e8e", "active 90d": CAT[3], "active 30d": CAT[0], "active 7d": CAT[2]})), 8, 8)
    g.place(timeseries("Logins & distinct login users (audit log window)",
                       [prom_target(f"prisma_activity_logins{TENANT}", "logins"),
                        prom_target(f"prisma_activity_distinct_login_users{TENANT}", "distinct users logging in", ref="B")],
                       overrides=color_overrides({"logins": CAT[0], "distinct users logging in": CAT[2]})), 8, 8)
    g.place(timeseries("Days since last human login", [prom_target(f"prisma_users_days_since_last_human_login{TENANT}", "days")],
                       unit="d", decimals=1, legend=False, thr=days_thr, thr_style="area"), 8, 8)

    g.row("Alert hygiene")
    g.place(timeseries("Open alerts backlog", [prom_target(f"prisma_alerts_open{TENANT}", "open alerts")], legend=False,
                       overrides=color_overrides({"open alerts": SERIOUS}), description="All open alerts, any age (POST /alert/v1/aggregate)."), 8, 8)
    g.place(timeseries("7-day alert activity (opened / resolved / dismissed / snoozed)",
                       [prom_target(f"prisma_alerts_opened_7d{TENANT}", "opened"),
                        prom_target(f"prisma_alerts_resolved_7d{TENANT}", "resolved", ref="B"),
                        prom_target(f"prisma_alerts_dismissed_7d{TENANT}", "dismissed", ref="C"),
                        prom_target(f"prisma_alerts_snoozed_7d{TENANT}", "snoozed", ref="D")],
                       overrides=color_overrides({"opened": SERIOUS, "resolved": GOOD, "dismissed": "#8e8e8e", "snoozed": WARN}),
                       description="Counts from data.prismacloud_alerts windows (limit=1, totalRows)."), 8, 8)
    g.place(timeseries("Open alerts by severity", [prom_target(f"prisma_alerts_open_by_severity{TENANT}", "{{severity}}")],
                       stack=True, fill=30, overrides=color_overrides(SEVERITY_COLORS)), 8, 8)

    g.row("Footprint health")
    g.place(timeseries("Cloud accounts: total / enabled / disabled",
                       [prom_target(f"prisma_cloud_accounts_total{TENANT}", "total"),
                        prom_target(f"prisma_cloud_accounts_enabled{TENANT}", "enabled", ref="B"),
                        prom_target(f"prisma_cloud_accounts_disabled{TENANT}", "disabled", ref="C")],
                       overrides=color_overrides({"total": CAT[0], "enabled": GOOD, "disabled": CRIT})), 8, 8)
    g.place(timeseries("Accounts by onboarding status", [prom_target(f"prisma_cloud_accounts_by_status{TENANT}", "{{status}}")],
                       overrides=color_overrides(STATUS_COLORS), description="GET /cloud status per account (ok / warning / error ...)."), 8, 8)
    g.place(timeseries("Resources & licence usage (7-day % change)",
                       [prom_target('prisma:inventory_total_resources:pct7d{tenant=~"$tenant"}', "resources % 7d"),
                        prom_target('prisma:license_usage_total:pct7d{tenant=~"$tenant"}', "licence usage % 7d", ref="B")],
                       unit="percent", decimals=1, overrides=color_overrides({"resources % 7d": CAT[0], "licence usage % 7d": CAT[1]}),
                       description="Negative for several days = the customer is moving workloads out of Prisma's view."), 8, 8)

    g.row("Change feed & details")
    g.place(logs("Change feed (Loki)",
                 '{' + LOKI_STREAM + ', report="changes"} | json | line_format "{{.entity}} {{.change}} - {{.name}}: {{.detail}}"',
                 description="One line per structural change between consecutive snapshots. Filter with | entity=\"cloud_account\" or | change=\"removed\"."), 12, 12)
    users_tbl = table("Humans not seen for 30+ days (or never)",
                      [prom_target(f'prisma_user_days_since_login{{tenant=~"$tenant", account_type="USER_ACCOUNT"}} > 30 or prisma_user_days_since_login{{tenant=~"$tenant", account_type="USER_ACCOUNT"}} < 0',
                                   instant=True, fmt="table")],
                      [{"id": "organize", "options": {
                          "excludeByName": {"Time": True, "__name__": True, "instance": True, "job": True, "tenant": True, "account_type": True},
                          "renameByName": {"Value": "days since login (-1 = never)"},
                          "indexByName": {"user_id": 0, "default_role_type": 1, "days since login (-1 = never)": 2}}}],
                      description="Licensed seats nobody uses. Candidates for enablement - or for a smaller renewal.",
                      sort_by="days since login (-1 = never)")
    g.place(users_tbl, 12, 12)
    md = text("Playbook", PLAYBOOK_MD)
    h = md.pop("_h")
    g.place(md, 24, 10)

    return dashboard("prisma-churn", "Prisma Cloud - Churn Risk & Health", g.panels,
                     description="Early-warning view for post-sales / customer success: engagement, footprint, alert hygiene and a composite churn-risk score.",
                     tags=["prisma-cloud", "churn", "post-sales"], time_from="now-7d")


# ---------------------------------------------------------------------------
# Dashboard 3: Snapshot Explorer (Loki)
# ---------------------------------------------------------------------------

def build_explorer() -> Dict[str, Any]:
    g = Grid()
    report_var = {
        "name": "report", "label": "Report", "type": "query", "datasource": LOKI,
        "definition": 'label_values({job="prisma_reports"}, report)',
        "query": {"label": "report", "refId": "LokiVariableQueryEditor-VariableQuery", "stream": '{job="prisma_reports"}', "type": 1},
        "refresh": 2, "includeAll": False, "multi": False, "sort": 1,
        "current": {"selected": True, "text": "summary", "value": "summary"}, "hide": 0, "options": [],
    }
    summary_sel = '{' + LOKI_STREAM + ', report="summary"}'

    g.row("The files over time - straight from Loki (no Prometheus involved)")
    g.place(timeseries("Cloud accounts (unwrapped from prisma_summary.json)",
                       [loki_target(f'max_over_time({summary_sel} | json | __error__="" | unwrap cloud_accounts_total [$__auto])', legend="accounts")],
                       datasource=LOKI, legend=False, description="| json flattens nested keys with _ : cloud_accounts.total -> cloud_accounts_total"), 8, 8)
    g.place(timeseries("Licence usage & purchased (unwrapped)",
                       [loki_target(f'max_over_time({summary_sel} | json | __error__="" | unwrap license_usage_total [$__auto])', legend="usage"),
                        loki_target(f'max_over_time({summary_sel} | json | __error__="" | unwrap license_workloads_purchased [$__auto])', ref="B", legend="purchased")],
                       datasource=LOKI, overrides=color_overrides({"usage": CAT[0], "purchased": "#8e8e8e"})), 8, 8)
    g.place(timeseries("Open alerts & active users (unwrapped)",
                       [loki_target(f'max_over_time({summary_sel} | json | __error__="" | unwrap alerts_open [$__auto])', legend="open alerts"),
                        loki_target(f'max_over_time({summary_sel} | json | __error__="" | unwrap users_human_active_30d [$__auto])', ref="B", legend="active humans 30d")],
                       datasource=LOKI, overrides=color_overrides({"open alerts": SERIOUS, "active humans 30d": CAT[2]})), 8, 8)
    g.place(timeseries("Accounts per cloud type (counted from prisma_cloud_accounts.jsonl lines)",
                       [loki_target('count by (cloud_type) (last_over_time({' + LOKI_STREAM + ', report="cloud_accounts"} | json | __error__="" | label_format one="1" | unwrap one [$__auto]) by (account_id, cloud_type))', legend="{{cloud_type}}")],
                       datasource=LOKI, overrides=color_overrides(CLOUD_COLORS),
                       description="Every run re-writes one line per account; last_over_time per account_id then count by cloud_type."), 8, 8)
    g.place(timeseries("Lines ingested per report", [loki_target('sum by (report) (count_over_time({' + LOKI_STREAM + '} [$__auto]))', legend="{{report}}")],
                       datasource=LOKI, stack=True, fill=30, draw="bars", interpolation="linear",
                       description="Each Terraform run = one bar per report (summary = 1 line, entity files = N lines)."), 8, 8)
    g.place(timeseries("Change events per hour by type", [loki_target('sum by (change) (count_over_time({' + LOKI_STREAM + ', report="changes"} | json [1h]))', legend="{{change}}")],
                       datasource=LOKI, stack=True, fill=30, draw="bars", interpolation="linear"), 8, 8)

    g.row("Raw snapshot lines")
    g.place(logs("$report - latest lines", '{' + LOKI_STREAM + ', report="$report"}',
                 description="Raw JSON as written by Terraform. Use the Report variable to switch files; expand a line to see every field."), 24, 14)
    g.place(logs("Cloud accounts - compact view",
                 '{' + LOKI_STREAM + ', report="cloud_accounts"} | json | line_format "{{.cloud_type}} {{.name}} enabled={{.enabled}} status={{.status}} resources={{.resources_total}} workloads={{.license_workloads}}"'), 12, 10)
    g.place(logs("Users - compact view",
                 '{' + LOKI_STREAM + ', report="users"} | json | line_format "{{.user_id}} [{{.account_type}}] last login {{.days_since_login}}d ago ({{.login_bucket}}) admin={{.is_admin}} enabled={{.enabled}}"'), 12, 10)

    return dashboard("prisma-explorer", "Prisma Cloud - Snapshot Explorer (Loki)", g.panels,
                     description="Proves the 'changes in the files over time' story with Loki alone: every Terraform run's JSON lines are queryable and chartable.",
                     tags=["prisma-cloud", "loki", "explorer"], extra_vars=[report_var])


# ---------------------------------------------------------------------------

def render() -> Dict[str, str]:
    return {
        "prisma-consumption.json": json.dumps(build_consumption(), indent=2, sort_keys=True) + "\n",
        "prisma-churn.json": json.dumps(build_churn(), indent=2, sort_keys=True) + "\n",
        "prisma-explorer.json": json.dumps(build_explorer(), indent=2, sort_keys=True) + "\n",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rendered = render()
    stale = []
    for name, content in rendered.items():
        path = OUT / name
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(name)
        else:
            path.write_text(content)
            print(f"wrote {path}")
    if args.check:
        if stale:
            print("out of date:", ", ".join(stale))
            return 1
        print("dashboards up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
