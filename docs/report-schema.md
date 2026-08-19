# Report schema (schema_version 1)

All files live in `reports/` and are rewritten (deleted + re-created) by every Terraform run.
Every line is a self-contained JSON object whose **first key is `"@timestamp"`** (RFC 3339, the run's
`plantimestamp()`), followed by `report` (the stream label) and `tenant` (`var.tenant_label`).
Arrays are kept for humans and the scraper; Loki's `| json` skips arrays and flattens nested objects
with `_` (`cloud_accounts.total` → `cloud_accounts_total`).

## `prisma_summary.json` — one object

| section | keys (all numbers unless noted) | source |
|---|---|---|
| `run` | `epoch_ms`, `interval_hint_seconds`, `terraform_module`, `provider`, `api_url`, `customer_name`, `api_enrichment` (bool), `api_status{endpoint: http code}`, `pseudonymized_users`, `collect{...}` | module |
| `cloud_accounts` | `total, enabled, disabled, by_cloud_type{}, enabled_by_cloud_type{}, by_account_type{}, by_status{}, by_protection_mode{}, child_accounts_total, storage_scan_enabled, added_last_30d, ungrouped, with_inventory, resources_total` | `prismacloud_cloud_accounts` + `GET /cloud` + inventory |
| `account_groups` | `total, auto_created, with_alert_rules` | `prismacloud_account_groups` |
| `users` | `total, enabled, disabled, service_accounts, human_total, human_enabled, human_active_7d/30d/90d, human_inactive_90d_plus, human_never_logged_in, admins, days_since_last_human_login (float), by_login_bucket{7d,30d,90d,90d_plus,never}, by_account_type{}, by_default_role_type{}` | `prismacloud_user_profiles` + `_user_roles` |
| `roles` | `total, custom, by_role_type{}` | `prismacloud_user_roles` |
| `permission_groups` | `total, custom` | `prismacloud_permission_groups` |
| `policies` | `total, enabled, disabled, custom, custom_enabled, system_default, system_default_enabled, remediable_enabled, with_open_alerts, open_alerts_sum, enabled_by_severity{}, enabled_by_type{}, enabled_by_cloud_type{}, custom_by_type{}` | `prismacloud_policies` |
| `alert_rules` | `total, enabled, disabled, scan_all, with_open_alerts, policies_attached_sum, open_alerts_sum` | `prismacloud_alert_rules` |
| `alerts` | `opened_24h, opened_7d, resolved_7d, dismissed_7d, snoozed_7d` (provider, `limit=1` → `total`), `open, open_policies, open_by_severity{}, open_by_policy_type{}, top_policies[{policy_id, policy_name, severity, policy_type, cloud_type, alert_count, remediable}]` (REST) | `prismacloud_alerts`, `/alert/v1/aggregate`, `/alert/v1/policy` |
| `integrations` | `total, enabled, disabled, valid, invalid, by_type{}, by_status{}` | `prismacloud_integrations` |
| `notification_templates` | `total, enabled` | `prismacloud_notification_templates` |
| `compliance_standards` | `total, custom, system_default, custom_policies_assigned_sum` | `prismacloud_compliance_standards` |
| `reports` | `total, by_type{}, by_status{}` | `prismacloud_reports` |
| `saved_searches` | `saved, recent` | `prismacloud_rql_historic_searches` |
| `resource_lists` / `collections` / `trusted_ips` | `total, by_type{}` / `total` / `login_allowlists, alert_allowlists` | respective data sources |
| `enterprise_settings` | `session_timeout_minutes, access_key_max_validity_days, audit_logs_enabled, apply_default_policies_enabled, require_alert_dismissal_note, user_attribution_in_notification, alarm_enabled (bools), audit_log_siem_integrations, default_policies_enabled_by_severity{bool}` | `prismacloud_enterprise_settings` |
| `anomaly_settings` | `network_policies, ueba_policies` | `prismacloud_anomaly_settings` (opt-in) |
| `inventory` (null without API) | `timestamp_ms, total_resources, passed_resources, failed_resources, unscanned_resources, pass_rate_pct, failed_by_severity{critical..informational}, vulnerable_by_severity{}, by_cloud_type{<ct>: {total_resources, passed_resources, failed_resources, unscanned_resources}}` | `GET /v3/inventory` |
| `license` (null without API) | `available_as_of_ms, plan_type (string), workloads_purchased, usage_total, usage_window_days, utilization_pct, usage_by_cloud_type{}, usage_by_resource_type{}, accounts_reported, credits{purchased, used, utilization_pct} (null on non-credit plans), trend{days, points, first_total, last_total, change_pct, time_unit}, time_series[{ts_ms, total, by_cloud_type{}}]` | `/license/api/v2/usage`, `/time_series`, `/license/api/v1/credit-allocation-rule-summary` |
| `activity` (null without API) | `window_hours, events_total, logins, failed_events, distinct_users, distinct_login_users, by_action_type{}, events_by_user{top-N}` | `GET /audit/redlock` |
| `scores` | `adoption_score, adoption_points_by_signal{}, risk_score, risk_points_by_signal{}, risk_flags[]` | module heuristics |

Null means "not collected / call failed"; `run.api_status` holds the HTTP status of every REST call.

## Entity files — one object per line (JSON Lines)

| file / `report` | id field | fields |
|---|---|---|
| `prisma_cloud_accounts.jsonl` / `cloud_accounts` | `account_id` | `name, cloud_type, in_account_group, enabled, status, account_type, protection_mode, deployment_type, number_of_child_accounts, added_on_ms, last_modified_ms, storage_scan_enabled, account_groups[], resources_total, resources_failed, license_workloads` (enrichment fields null without API) |
| `prisma_users.jsonl` / `users` | `user_id` | `account_type (USER_ACCOUNT|SERVICE_ACCOUNT), enabled, last_login_ts (epoch ms, ≤0 = never), days_since_login (null = never), login_bucket (7d|30d|90d|90d_plus|never), role_count, default_role, default_role_type, is_admin, last_modified_ts` |
| `prisma_policies.jsonl` / `policies` (custom only) | `policy_id` | `name, policy_type, policy_subtypes[], severity, cloud_type, enabled, system_default=false, remediable, policy_mode, open_alerts_count, labels[]` |
| `prisma_alert_rules.jsonl` / `alert_rules` | `rule_id` | `name, enabled, scan_all, policies_count, open_alerts_count, owner, read_only` |
| `prisma_integrations.jsonl` / `integrations` | `integration_id` | `name, integration_type, enabled, status, valid` |

## Derived (written by metrics_scraper.py)

`reports/derived/prisma_changes.jsonl` / `report="changes"` — one line per change between consecutive snapshots:
`entity` (`cloud_account|user|integration|alert_rule|custom_policy|summary|risk_flag|tenant`), `change`
(`added|removed|enabled|disabled|broken|recovered|logged_in|admin_granted|admin_revoked|changed|metric_changed|raised|cleared|baseline`),
`id`, `name`, `detail`, optional `field/old/new/delta`, dimension (`cloud_type`, `account_type`, ...), `snapshot_ts`, `producer`.

`reports/.runner/last_run.json` — `success, duration_seconds, exit_code, interval_seconds, module, runs_total, failures_total` (scheduler heartbeat; not shipped to Loki).
