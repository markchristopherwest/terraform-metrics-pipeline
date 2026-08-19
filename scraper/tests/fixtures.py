"""
Fixture reports that mirror the schema written by ../terraform (and ../terraform-mock).
Used by the unit tests; also handy to seed ./reports without Terraform:

    python3 scraper/tests/fixtures.py --out reports --run 1
    python3 scraper/tests/fixtures.py --out reports --run 2   # introduces changes
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

TENANT = "acme-test"


def ts(run: int) -> str:
    base = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(minutes=5 * (run - 1))).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch_ms(run: int) -> int:
    return int(datetime.fromisoformat(ts(run).replace("Z", "+00:00")).timestamp() * 1000)


def accounts(run: int) -> List[Dict[str, Any]]:
    rows = [
        dict(account_id="123456789012", name="acme-prod-aws", cloud_type="aws", account_type="organization",
             enabled=True, status="ok", protection_mode="monitor_and_protect", number_of_child_accounts=42,
             resources_total=5210, resources_failed=310, license_workloads=820),
        dict(account_id="210987654321", name="acme-dev-aws", cloud_type="aws", account_type="account",
             enabled=True, status="ok", protection_mode="monitor", number_of_child_accounts=0,
             resources_total=1330, resources_failed=140, license_workloads=205),
        dict(account_id="f5b1c2d3-0001", name="acme-core-azure", cloud_type="azure", account_type="tenant",
             enabled=True, status="ok", protection_mode="monitor", number_of_child_accounts=9,
             resources_total=2400, resources_failed=120, license_workloads=390),
        dict(account_id="acme-platform-gcp", name="acme-platform-gcp", cloud_type="gcp", account_type="organization",
             enabled=True, status="ok", protection_mode="monitor", number_of_child_accounts=17,
             resources_total=1800, resources_failed=95, license_workloads=260),
    ]
    if run >= 2:
        rows[1]["enabled"] = False            # disabled
        rows[2]["status"] = "warning"         # status change
        rows.pop(3)                           # gcp org removed
    out = []
    for r in rows:
        out.append({"@timestamp": ts(run), "report": "cloud_accounts", "tenant": TENANT, "in_account_group": True,
                    "deployment_type": r["cloud_type"].upper(), "added_on_ms": epoch_ms(run) - 60 * 86400000,
                    "last_modified_ms": epoch_ms(run) - 3 * 86400000, "storage_scan_enabled": False,
                    "account_groups": ["Production"], **r})
    return out


def users(run: int) -> List[Dict[str, Any]]:
    now = epoch_ms(run)
    rows = [
        dict(user_id="alice.admin@acme.example", account_type="USER_ACCOUNT", enabled=True, last_login_ts=now - 3600000,
             days_since_login=0, login_bucket="7d", role_count=1, default_role="System Admin", default_role_type="System Admin", is_admin=True),
        dict(user_id="bob.secops@acme.example", account_type="USER_ACCOUNT", enabled=True, last_login_ts=now - 40 * 86400000,
             days_since_login=40, login_bucket="90d", role_count=1, default_role="Account Group Admin", default_role_type="Account Group Admin", is_admin=False),
        dict(user_id="carol.cloud@acme.example", account_type="USER_ACCOUNT", enabled=True, last_login_ts=-1,
             days_since_login=None, login_bucket="never", role_count=2, default_role="Developer", default_role_type="Developer", is_admin=False),
        dict(user_id="svc-terraform", account_type="SERVICE_ACCOUNT", enabled=True, last_login_ts=now - 60000,
             days_since_login=0, login_bucket="7d", role_count=1, default_role="System Admin", default_role_type="System Admin", is_admin=True),
    ]
    if run >= 2:
        rows[1]["last_login_ts"] = now - 120000   # bob logged in
        rows[1]["days_since_login"] = 0
        rows[1]["login_bucket"] = "7d"
        rows.append(dict(user_id="dave.new@acme.example", account_type="USER_ACCOUNT", enabled=True, last_login_ts=-1,
                         days_since_login=None, login_bucket="never", role_count=1, default_role="Developer",
                         default_role_type="Developer", is_admin=False))
    return [{"@timestamp": ts(run), "report": "users", "tenant": TENANT, "last_modified_ts": now - 86400000, **r} for r in rows]


def integrations(run: int) -> List[Dict[str, Any]]:
    rows = [
        dict(integration_id="int-1", name="SecOps Slack", integration_type="slack", enabled=True, status="ok", valid=True),
        dict(integration_id="int-2", name="Splunk HEC", integration_type="splunk", enabled=True, status="ok", valid=True),
    ]
    if run >= 2:
        rows[1]["valid"] = False
        rows[1]["status"] = "error"
    return [{"@timestamp": ts(run), "report": "integrations", "tenant": TENANT, **r} for r in rows]


def alert_rules(run: int) -> List[Dict[str, Any]]:
    rows = [
        dict(rule_id="rule-1", name="Production - critical & high", enabled=True, scan_all=False, policies_count=212,
             open_alerts_count=61, owner="alice.admin@acme.example", read_only=False),
        dict(rule_id="rule-2", name="Sandbox - informational", enabled=True, scan_all=True, policies_count=30,
             open_alerts_count=12, owner="bob.secops@acme.example", read_only=False),
    ]
    if run >= 2:
        rows[1]["enabled"] = False
    return [{"@timestamp": ts(run), "report": "alert_rules", "tenant": TENANT, **r} for r in rows]


def policies(run: int) -> List[Dict[str, Any]]:
    rows = [
        dict(policy_id="custom-1", name="ACME - S3 bucket without org tag", policy_type="config", policy_subtypes=["run"],
             severity="medium", cloud_type="aws", enabled=True, system_default=False, remediable=True, policy_mode="custom",
             open_alerts_count=7, labels=["acme"]),
    ]
    if run >= 2:
        rows.append(dict(policy_id="custom-2", name="ACME - Public snapshot", policy_type="config", policy_subtypes=["run"],
                         severity="high", cloud_type="aws", enabled=True, system_default=False, remediable=True,
                         policy_mode="custom", open_alerts_count=2, labels=["acme"]))
    return [{"@timestamp": ts(run), "report": "policies", "tenant": TENANT, **r} for r in rows]


def summary(run: int) -> Dict[str, Any]:
    accs = accounts(run)
    usr = users(run)
    ints = integrations(run)
    rules = alert_rules(run)
    pols = policies(run)
    human = [u for u in usr if u["account_type"] != "SERVICE_ACCOUNT"]
    by_cloud: Dict[str, int] = {}
    for a in accs:
        by_cloud[a["cloud_type"]] = by_cloud.get(a["cloud_type"], 0) + 1
    open_alerts = 312 if run == 1 else 330
    resolved_7d = 14 if run == 1 else 0
    risk_components = {
        "no_human_login_30d": 0,
        "single_active_user_30d": 0 if run >= 2 else 15,
        "accounts_disabled": 10 if any(not a["enabled"] for a in accs) else 0,
        "integrations_broken": 10 if any(not i["valid"] for i in ints) else 0,
        "no_alert_rules": 0,
        "alerts_open_no_activity": 10 if resolved_7d == 0 else 0,
        "license_utilization_low": 0,
    }
    usage_total = sum(a["license_workloads"] for a in accs)
    return {
        "@timestamp": ts(run),
        "report": "summary",
        "schema_version": 1,
        "tenant": TENANT,
        "run": {"epoch_ms": epoch_ms(run), "interval_hint_seconds": 300, "terraform_module": "fixtures",
                "provider": "fixtures", "api_url": "api.test.prismacloud.io", "customer_name": None,
                "api_enrichment": True, "api_status": {"cloud_accounts": 200, "inventory": 200, "license_usage": 200},
                "pseudonymized_users": False, "collect": {"users": True, "policies": True}},
        "cloud_accounts": {
            "total": len(accs), "enabled": sum(1 for a in accs if a["enabled"]),
            "disabled": sum(1 for a in accs if not a["enabled"]),
            "by_cloud_type": by_cloud,
            "enabled_by_cloud_type": {k: v for k, v in by_cloud.items()},
            "by_account_type": {"organization": 2, "account": 1, "tenant": 1} if run == 1 else {"organization": 1, "account": 1, "tenant": 1},
            "by_status": {"ok": len([a for a in accs if a["status"] == "ok"]), "warning": len([a for a in accs if a["status"] == "warning"])},
            "by_protection_mode": {"monitor": len(accs) - 1, "monitor_and_protect": 1},
            "child_accounts_total": sum(a["number_of_child_accounts"] for a in accs),
            "storage_scan_enabled": 0, "added_last_30d": 0, "ungrouped": 0, "with_inventory": len(accs),
            "resources_total": sum(a["resources_total"] for a in accs),
        },
        "account_groups": {"total": 3, "auto_created": 1, "with_alert_rules": 2},
        "users": {
            "total": len(usr), "enabled": len(usr), "disabled": 0, "service_accounts": 1,
            "human_total": len(human), "human_enabled": len(human),
            "human_active_7d": sum(1 for u in human if u["login_bucket"] == "7d"),
            "human_active_30d": sum(1 for u in human if u["login_bucket"] in ("7d", "30d")),
            "human_active_90d": sum(1 for u in human if u["login_bucket"] in ("7d", "30d", "90d")),
            "human_inactive_90d_plus": 0,
            "human_never_logged_in": sum(1 for u in human if u["login_bucket"] == "never"),
            "admins": 2, "days_since_last_human_login": 0.04,
            "by_login_bucket": {b: sum(1 for u in human if u["login_bucket"] == b) for b in ("7d", "30d", "90d", "90d_plus", "never")},
            "by_account_type": {"user_account": len(human), "service_account": 1},
            "by_default_role_type": {"System Admin": 2, "Account Group Admin": 1, "Developer": len(usr) - 3},
        },
        "roles": {"total": 8, "custom": 0, "by_role_type": {"System Admin": 1, "Developer": 1}},
        "permission_groups": {"total": 10, "custom": 0},
        "policies": {
            "total": 1320, "enabled": 905, "disabled": 415, "custom": len(pols), "custom_enabled": len(pols),
            "system_default": 1320 - len(pols), "system_default_enabled": 904, "remediable_enabled": 388,
            "with_open_alerts": 61, "open_alerts_sum": open_alerts,
            "enabled_by_severity": {"critical": 48, "high": 312, "medium": 401, "low": 120, "informational": 24},
            "enabled_by_type": {"config": 744, "network": 61, "audit_event": 58, "anomaly": 22, "iam": 10, "data": 6, "workload_vulnerability": 4},
            "enabled_by_cloud_type": {"aws": 411, "azure": 262, "gcp": 168, "all": 64},
            "custom_by_type": {"config": len(pols)},
        },
        "alert_rules": {"total": len(rules), "enabled": sum(1 for r in rules if r["enabled"]),
                        "disabled": sum(1 for r in rules if not r["enabled"]), "scan_all": 1, "with_open_alerts": 2,
                        "policies_attached_sum": 242, "open_alerts_sum": 73},
        "alerts": {
            "opened_24h": 9, "opened_7d": 66, "resolved_7d": resolved_7d, "dismissed_7d": 3, "snoozed_7d": 1,
            "open": open_alerts, "open_policies": 64,
            "open_by_severity": {"critical": 18, "high": 94, "medium": 137, "low": 53, "informational": 10},
            "open_by_policy_type": {"config": 256, "network": 25, "audit_event": 19, "anomaly": 12},
            "top_policies": [
                {"policy_id": "p1", "policy_name": "AWS S3 bucket publicly readable", "severity": "high", "policy_type": "config", "cloud_type": "aws", "alert_count": 38, "remediable": True},
                {"policy_id": "p2", "policy_name": "Azure storage account logging disabled", "severity": "medium", "policy_type": "config", "cloud_type": "azure", "alert_count": 31, "remediable": True},
            ],
        },
        "integrations": {"total": len(ints), "enabled": len(ints), "disabled": 0,
                         "valid": sum(1 for i in ints if i["valid"]), "invalid": sum(1 for i in ints if not i["valid"]),
                         "by_type": {"slack": 1, "splunk": 1},
                         "by_status": {"ok": sum(1 for i in ints if i["status"] == "ok"), "error": sum(1 for i in ints if i["status"] == "error")}},
        "notification_templates": {"total": 1, "enabled": 1},
        "compliance_standards": {"total": 46, "custom": 1, "system_default": 45, "custom_policies_assigned_sum": 24},
        "reports": {"total": 2, "by_type": {"compliance": 1, "inventory_overview": 1}, "by_status": {"ready": 2}},
        "saved_searches": {"saved": 7, "recent": 41},
        "resource_lists": {"total": 2, "by_type": {"tag": 2}},
        "collections": {"total": 0},
        "trusted_ips": {"login_allowlists": 1, "alert_allowlists": 0},
        "enterprise_settings": {"session_timeout_minutes": 60, "access_key_max_validity_days": 90, "audit_logs_enabled": True,
                                "apply_default_policies_enabled": True, "require_alert_dismissal_note": True,
                                "user_attribution_in_notification": False, "alarm_enabled": True, "audit_log_siem_integrations": 1,
                                "default_policies_enabled_by_severity": {"critical": True, "high": True, "medium": True, "low": False, "informational": False}},
        "anomaly_settings": {"network_policies": 0, "ueba_policies": 0},
        "inventory": {
            "timestamp_ms": epoch_ms(run) - 1800000,
            "total_resources": sum(a["resources_total"] for a in accs),
            "passed_resources": sum(a["resources_total"] - a["resources_failed"] for a in accs),
            "failed_resources": sum(a["resources_failed"] for a in accs), "unscanned_resources": 12, "pass_rate_pct": 93.4,
            "failed_by_severity": {"critical": 33, "high": 166, "medium": 300, "low": 133, "informational": 33},
            "vulnerable_by_severity": {"critical": 3, "high": 21, "medium": 77, "low": 140},
            "by_cloud_type": {ct: {"total_resources": sum(a["resources_total"] for a in accs if a["cloud_type"] == ct),
                                   "passed_resources": 0,
                                   "failed_resources": sum(a["resources_failed"] for a in accs if a["cloud_type"] == ct),
                                   "unscanned_resources": 0} for ct in by_cloud},
        },
        "license": {
            "available_as_of_ms": epoch_ms(run) - 3600000, "plan_type": "ENTERPRISE", "workloads_purchased": 2000,
            "usage_total": usage_total, "usage_window_days": 7, "utilization_pct": 100.0 * usage_total / 2000,
            "usage_by_cloud_type": {ct: sum(a["license_workloads"] for a in accs if a["cloud_type"] == ct) for ct in by_cloud},
            "usage_by_resource_type": {"vm": 800, "serverless": 150, "container": 400, "paas": 200},
            "accounts_reported": len(accs),
            "credits": {"purchased": 2000, "used": usage_total, "utilization_pct": 100.0 * usage_total / 2000},
            "trend": {"days": 30, "points": 30, "first_total": 1500, "last_total": usage_total,
                      "change_pct": 100.0 * (usage_total - 1500) / 1500, "time_unit": "day"},
            "time_series": [{"ts_ms": epoch_ms(run) - d * 86400000, "total": 1500 + d, "by_cloud_type": {"aws": 1000, "azure": 300, "gcp": 200}} for d in range(30)],
        },
        "activity": {"window_hours": 24, "events_total": 140, "logins": 9, "failed_events": 1, "distinct_users": 5,
                     "distinct_login_users": 4, "by_action_type": {"login": 9, "read": 110, "update": 14, "create": 4, "delete": 3},
                     "events_by_user": {"alice.admin@acme.example": 61, "svc-terraform": 48}},
        "scores": {
            "adoption_score": 85 if run == 1 else 70,
            "adoption_points_by_signal": {"all_accounts_healthy": 10 if run == 1 else 0, "multi_cloud": 5, "integration_valid": 15,
                                          "alert_rule_enabled": 15, "custom_policy": 10, "custom_compliance": 5, "saved_search": 5,
                                          "scheduled_report": 5, "two_active_users_30d": 0 if run == 1 else 15,
                                          "audit_or_siem_enabled": 5, "license_utilization_50pct": 10},
            "risk_score": sum(risk_components.values()),
            "risk_points_by_signal": risk_components,
            "risk_flags": sorted(k for k, v in risk_components.items() if v > 0),
        },
    }


def write_reports(out: Path, run: int) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "prisma_summary.json").write_text(json.dumps(summary(run), separators=(",", ":"), sort_keys=True) + "\n")
    for fname, rows in (("prisma_cloud_accounts.jsonl", accounts(run)), ("prisma_users.jsonl", users(run)),
                        ("prisma_integrations.jsonl", integrations(run)), ("prisma_alert_rules.jsonl", alert_rules(run)),
                        ("prisma_policies.jsonl", policies(run))):
        (out / fname).write_text("".join(json.dumps(r, separators=(",", ":"), sort_keys=True) + "\n" for r in rows))
    runner = out / ".runner"
    runner.mkdir(exist_ok=True)
    (runner / "last_run.json").write_text(json.dumps({"@timestamp": ts(run), "report": "runner", "success": 1,
                                                      "duration_seconds": 23, "exit_code": 0, "interval_seconds": 300,
                                                      "module": "fixtures", "runs_total": run, "failures_total": 0}) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports")
    ap.add_argument("--run", type=int, default=1)
    a = ap.parse_args()
    write_reports(Path(a.out), a.run)
    print(f"wrote fixture run {a.run} to {a.out}")
