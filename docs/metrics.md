# Metric catalogue (metrics_scraper.py)

Generated from the fixture snapshot (`make fixtures && make scrape`). Every summary metric carries `tenant`; `by_<label>` maps add that label.

Naming rule: `prisma_` + JSON path joined by `_`; maps named `by_<x>` / `*_by_<x>` become one series per key with label `<x>`; booleans are 1/0; arrays are skipped except `alerts.top_policies` and `scores.risk_flags`.

## Tenant summary (from prisma_summary.json)

| metric | labels | help |
|---|---|---|
| `prisma_account_groups_auto_created` | tenant | summary account_groups.auto_created |
| `prisma_account_groups_total` | tenant | summary account_groups.total |
| `prisma_account_groups_with_alert_rules` | tenant | summary account_groups.with_alert_rules |
| `prisma_activity_by_action_type` | action_type, tenant | summary activity.by_action_type.<action_type> |
| `prisma_activity_distinct_login_users` | tenant | summary activity.distinct_login_users |
| `prisma_activity_distinct_users` | tenant | summary activity.distinct_users |
| `prisma_activity_events_by_user` | tenant, user | summary activity.events_by_user.<user> |
| `prisma_activity_events_total` | tenant | summary activity.events_total |
| `prisma_activity_failed_events` | tenant | summary activity.failed_events |
| `prisma_activity_logins` | tenant | summary activity.logins |
| `prisma_activity_window_hours` | tenant | summary activity.window_hours |
| `prisma_alert_rules_disabled` | tenant | summary alert_rules.disabled |
| `prisma_alert_rules_enabled` | tenant | summary alert_rules.enabled |
| `prisma_alert_rules_open_alerts_sum` | tenant | summary alert_rules.open_alerts_sum |
| `prisma_alert_rules_policies_attached_sum` | tenant | summary alert_rules.policies_attached_sum |
| `prisma_alert_rules_scan_all` | tenant | summary alert_rules.scan_all |
| `prisma_alert_rules_total` | tenant | summary alert_rules.total |
| `prisma_alert_rules_with_open_alerts` | tenant | summary alert_rules.with_open_alerts |
| `prisma_alerts_dismissed_7d` | tenant | summary alerts.dismissed_7d |
| `prisma_alerts_open` | tenant | summary alerts.open |
| `prisma_alerts_open_by_policy_type` | policy_type, tenant | summary alerts.open_by_policy_type.<policy_type> |
| `prisma_alerts_open_by_severity` | severity, tenant | summary alerts.open_by_severity.<severity> |
| `prisma_alerts_open_policies` | tenant | summary alerts.open_policies |
| `prisma_alerts_opened_24h` | tenant | summary alerts.opened_24h |
| `prisma_alerts_opened_7d` | tenant | summary alerts.opened_7d |
| `prisma_alerts_resolved_7d` | tenant | summary alerts.resolved_7d |
| `prisma_alerts_snoozed_7d` | tenant | summary alerts.snoozed_7d |
| `prisma_alerts_top_policy_open_alerts` | cloud_type, policy_id, policy_name, policy_type, severity, tenant | Open alerts of the top alert-generating policies |
| `prisma_anomaly_settings_network_policies` | tenant | summary anomaly_settings.network_policies |
| `prisma_anomaly_settings_ueba_policies` | tenant | summary anomaly_settings.ueba_policies |
| `prisma_cloud_accounts_added_last_30d` | tenant | summary cloud_accounts.added_last_30d |
| `prisma_cloud_accounts_by_account_type` | account_type, tenant | summary cloud_accounts.by_account_type.<account_type> |
| `prisma_cloud_accounts_by_cloud_type` | cloud_type, tenant | summary cloud_accounts.by_cloud_type.<cloud_type> |
| `prisma_cloud_accounts_by_protection_mode` | protection_mode, tenant | summary cloud_accounts.by_protection_mode.<protection_mode> |
| `prisma_cloud_accounts_by_status` | status, tenant | summary cloud_accounts.by_status.<status> |
| `prisma_cloud_accounts_child_accounts_total` | tenant | summary cloud_accounts.child_accounts_total |
| `prisma_cloud_accounts_disabled` | tenant | summary cloud_accounts.disabled |
| `prisma_cloud_accounts_enabled` | tenant | summary cloud_accounts.enabled |
| `prisma_cloud_accounts_enabled_by_cloud_type` | cloud_type, tenant | summary cloud_accounts.enabled_by_cloud_type.<cloud_type> |
| `prisma_cloud_accounts_resources_total` | tenant | summary cloud_accounts.resources_total |
| `prisma_cloud_accounts_storage_scan_enabled` | tenant | summary cloud_accounts.storage_scan_enabled |
| `prisma_cloud_accounts_total` | tenant | summary cloud_accounts.total |
| `prisma_cloud_accounts_ungrouped` | tenant | summary cloud_accounts.ungrouped |
| `prisma_cloud_accounts_with_inventory` | tenant | summary cloud_accounts.with_inventory |
| `prisma_collections_total` | tenant | summary collections.total |
| `prisma_compliance_standards_custom` | tenant | summary compliance_standards.custom |
| `prisma_compliance_standards_custom_policies_assigned_sum` | tenant | summary compliance_standards.custom_policies_assigned_sum |
| `prisma_compliance_standards_system_default` | tenant | summary compliance_standards.system_default |
| `prisma_compliance_standards_total` | tenant | summary compliance_standards.total |
| `prisma_enterprise_settings_access_key_max_validity_days` | tenant | summary enterprise_settings.access_key_max_validity_days |
| `prisma_enterprise_settings_alarm_enabled` | tenant | summary enterprise_settings.alarm_enabled |
| `prisma_enterprise_settings_apply_default_policies_enabled` | tenant | summary enterprise_settings.apply_default_policies_enabled |
| `prisma_enterprise_settings_audit_log_siem_integrations` | tenant | summary enterprise_settings.audit_log_siem_integrations |
| `prisma_enterprise_settings_audit_logs_enabled` | tenant | summary enterprise_settings.audit_logs_enabled |
| `prisma_enterprise_settings_default_policies_enabled_by_severity` | severity, tenant | summary enterprise_settings.default_policies_enabled_by_severity.<severity> |
| `prisma_enterprise_settings_require_alert_dismissal_note` | tenant | summary enterprise_settings.require_alert_dismissal_note |
| `prisma_enterprise_settings_session_timeout_minutes` | tenant | summary enterprise_settings.session_timeout_minutes |
| `prisma_enterprise_settings_user_attribution_in_notification` | tenant | summary enterprise_settings.user_attribution_in_notification |
| `prisma_integrations_by_status` | status, tenant | summary integrations.by_status.<status> |
| `prisma_integrations_by_type` | tenant, type | summary integrations.by_type.<type> |
| `prisma_integrations_disabled` | tenant | summary integrations.disabled |
| `prisma_integrations_enabled` | tenant | summary integrations.enabled |
| `prisma_integrations_invalid` | tenant | summary integrations.invalid |
| `prisma_integrations_total` | tenant | summary integrations.total |
| `prisma_integrations_valid` | tenant | summary integrations.valid |
| `prisma_inventory_by_cloud_type_failed_resources` | cloud_type, tenant | summary inventory.by_cloud_type.<cloud_type>.failed_resources |
| `prisma_inventory_by_cloud_type_passed_resources` | cloud_type, tenant | summary inventory.by_cloud_type.<cloud_type>.passed_resources |
| `prisma_inventory_by_cloud_type_total_resources` | cloud_type, tenant | summary inventory.by_cloud_type.<cloud_type>.total_resources |
| `prisma_inventory_by_cloud_type_unscanned_resources` | cloud_type, tenant | summary inventory.by_cloud_type.<cloud_type>.unscanned_resources |
| `prisma_inventory_failed_by_severity` | severity, tenant | summary inventory.failed_by_severity.<severity> |
| `prisma_inventory_failed_resources` | tenant | summary inventory.failed_resources |
| `prisma_inventory_pass_rate_pct` | tenant | summary inventory.pass_rate_pct |
| `prisma_inventory_passed_resources` | tenant | summary inventory.passed_resources |
| `prisma_inventory_timestamp_ms` | tenant | summary inventory.timestamp_ms |
| `prisma_inventory_total_resources` | tenant | summary inventory.total_resources |
| `prisma_inventory_unscanned_resources` | tenant | summary inventory.unscanned_resources |
| `prisma_inventory_vulnerable_by_severity` | severity, tenant | summary inventory.vulnerable_by_severity.<severity> |
| `prisma_license_accounts_reported` | tenant | summary license.accounts_reported |
| `prisma_license_available_as_of_ms` | tenant | summary license.available_as_of_ms |
| `prisma_license_credits_purchased` | tenant | summary license.credits.purchased |
| `prisma_license_credits_used` | tenant | summary license.credits.used |
| `prisma_license_credits_utilization_pct` | tenant | summary license.credits.utilization_pct |
| `prisma_license_trend_change_pct` | tenant | summary license.trend.change_pct |
| `prisma_license_trend_days` | tenant | summary license.trend.days |
| `prisma_license_trend_first_total` | tenant | summary license.trend.first_total |
| `prisma_license_trend_last_total` | tenant | summary license.trend.last_total |
| `prisma_license_trend_points` | tenant | summary license.trend.points |
| `prisma_license_usage_by_cloud_type` | cloud_type, tenant | summary license.usage_by_cloud_type.<cloud_type> |
| `prisma_license_usage_by_resource_type` | resource_type, tenant | summary license.usage_by_resource_type.<resource_type> |
| `prisma_license_usage_total` | tenant | summary license.usage_total |
| `prisma_license_usage_window_days` | tenant | summary license.usage_window_days |
| `prisma_license_utilization_pct` | tenant | summary license.utilization_pct |
| `prisma_license_workloads_purchased` | tenant | summary license.workloads_purchased |
| `prisma_notification_templates_enabled` | tenant | summary notification_templates.enabled |
| `prisma_notification_templates_total` | tenant | summary notification_templates.total |
| `prisma_permission_groups_custom` | tenant | summary permission_groups.custom |
| `prisma_permission_groups_total` | tenant | summary permission_groups.total |
| `prisma_policies_custom` | tenant | summary policies.custom |
| `prisma_policies_custom_by_type` | tenant, type | summary policies.custom_by_type.<type> |
| `prisma_policies_custom_enabled` | tenant | summary policies.custom_enabled |
| `prisma_policies_disabled` | tenant | summary policies.disabled |
| `prisma_policies_enabled` | tenant | summary policies.enabled |
| `prisma_policies_enabled_by_cloud_type` | cloud_type, tenant | summary policies.enabled_by_cloud_type.<cloud_type> |
| `prisma_policies_enabled_by_severity` | severity, tenant | summary policies.enabled_by_severity.<severity> |
| `prisma_policies_enabled_by_type` | tenant, type | summary policies.enabled_by_type.<type> |
| `prisma_policies_open_alerts_sum` | tenant | summary policies.open_alerts_sum |
| `prisma_policies_remediable_enabled` | tenant | summary policies.remediable_enabled |
| `prisma_policies_system_default` | tenant | summary policies.system_default |
| `prisma_policies_system_default_enabled` | tenant | summary policies.system_default_enabled |
| `prisma_policies_total` | tenant | summary policies.total |
| `prisma_policies_with_open_alerts` | tenant | summary policies.with_open_alerts |
| `prisma_reports_by_status` | status, tenant | summary reports.by_status.<status> |
| `prisma_reports_by_type` | tenant, type | summary reports.by_type.<type> |
| `prisma_reports_total` | tenant | summary reports.total |
| `prisma_resource_lists_by_type` | tenant, type | summary resource_lists.by_type.<type> |
| `prisma_resource_lists_total` | tenant | summary resource_lists.total |
| `prisma_roles_by_role_type` | role_type, tenant | summary roles.by_role_type.<role_type> |
| `prisma_roles_custom` | tenant | summary roles.custom |
| `prisma_roles_total` | tenant | summary roles.total |
| `prisma_run_api_enrichment` | tenant | summary run.api_enrichment |
| `prisma_run_api_status_cloud_accounts` | tenant | summary run.api_status.cloud_accounts |
| `prisma_run_api_status_inventory` | tenant | summary run.api_status.inventory |
| `prisma_run_api_status_license_usage` | tenant | summary run.api_status.license_usage |
| `prisma_run_epoch_ms` | tenant | summary run.epoch_ms |
| `prisma_run_interval_hint_seconds` | tenant | summary run.interval_hint_seconds |
| `prisma_run_pseudonymized_users` | tenant | summary run.pseudonymized_users |
| `prisma_saved_searches_recent` | tenant | summary saved_searches.recent |
| `prisma_saved_searches_saved` | tenant | summary saved_searches.saved |
| `prisma_scores_adoption_points_by_signal` | signal, tenant | summary scores.adoption_points_by_signal.<signal> |
| `prisma_scores_adoption_score` | tenant | summary scores.adoption_score |
| `prisma_scores_risk_flag` | flag, tenant | Active churn-risk signals (1 = active) |
| `prisma_scores_risk_points_by_signal` | signal, tenant | summary scores.risk_points_by_signal.<signal> |
| `prisma_scores_risk_score` | tenant | summary scores.risk_score |
| `prisma_trusted_ips_alert_allowlists` | tenant | summary trusted_ips.alert_allowlists |
| `prisma_trusted_ips_login_allowlists` | tenant | summary trusted_ips.login_allowlists |
| `prisma_users_admins` | tenant | summary users.admins |
| `prisma_users_by_account_type` | account_type, tenant | summary users.by_account_type.<account_type> |
| `prisma_users_by_default_role_type` | default_role_type, tenant | summary users.by_default_role_type.<default_role_type> |
| `prisma_users_by_login_bucket` | login_bucket, tenant | summary users.by_login_bucket.<login_bucket> |
| `prisma_users_days_since_last_human_login` | tenant | summary users.days_since_last_human_login |
| `prisma_users_disabled` | tenant | summary users.disabled |
| `prisma_users_enabled` | tenant | summary users.enabled |
| `prisma_users_human_active_30d` | tenant | summary users.human_active_30d |
| `prisma_users_human_active_7d` | tenant | summary users.human_active_7d |
| `prisma_users_human_active_90d` | tenant | summary users.human_active_90d |
| `prisma_users_human_enabled` | tenant | summary users.human_enabled |
| `prisma_users_human_inactive_90d_plus` | tenant | summary users.human_inactive_90d_plus |
| `prisma_users_human_never_logged_in` | tenant | summary users.human_never_logged_in |
| `prisma_users_human_total` | tenant | summary users.human_total |
| `prisma_users_service_accounts` | tenant | summary users.service_accounts |
| `prisma_users_total` | tenant | summary users.total |

## Per-entity (from the .jsonl files)

| metric | labels | help |
|---|---|---|
| `prisma_alert_rule_enabled` | name, rule_id, tenant | 1 if the alert rule is enabled |
| `prisma_alert_rule_open_alerts` | name, rule_id, tenant | Open alerts attributed to the rule |
| `prisma_alert_rule_policies` | name, rule_id, tenant | Policies attached to the rule |
| `prisma_cloud_account_child_accounts` | account_id, cloud_type, name, tenant | Member accounts under an organisation account |
| `prisma_cloud_account_info` | account_id, account_type, cloud_type, name, protection_mode, status, tenant | One series per onboarded cloud account (value = 1 enabled, 0 disabled, -1 unknown) |
| `prisma_cloud_account_license_workloads` | account_id, cloud_type, name, tenant | Licence workloads attributed to the account |
| `prisma_cloud_account_resources_failed` | account_id, cloud_type, name, tenant | Assets failing at least one policy |
| `prisma_cloud_account_resources_total` | account_id, cloud_type, name, tenant | Assets in the account (inventory) |
| `prisma_custom_policy_enabled` | cloud_type, name, policy_id, policy_type, severity, tenant | 1 if the custom policy is enabled |
| `prisma_custom_policy_open_alerts` | cloud_type, name, policy_id, policy_type, severity, tenant | Open alerts of the custom policy |
| `prisma_integration_enabled` | integration_id, integration_type, name, status, tenant | 1 if the integration is enabled |
| `prisma_integration_valid` | integration_id, integration_type, name, status, tenant | 1 if Prisma reports the integration as valid |
| `prisma_user_days_since_login` | account_type, default_role_type, tenant, user_id | Days since the user's last login (-1 = never) |
| `prisma_user_enabled` | account_type, default_role_type, tenant, user_id | 1 if the user profile is enabled |
| `prisma_user_is_admin` | account_type, default_role_type, tenant, user_id | 1 if the user holds a System Admin role |

## Pipeline / scraper / runner

| metric | labels | help |
|---|---|---|
| `prisma_changes_total` | change, entity, tenant | Change-feed events emitted |
| `prisma_last_change_timestamp_seconds` | entity, tenant | Unix time of the last change event per entity type |
| `prisma_report_bytes` | report, tenant | File size in bytes |
| `prisma_report_lines` | report, tenant | Entity lines in the report (1 for summary) |
| `prisma_report_loads_total` | report | Report files (re)parsed |
| `prisma_report_mtime_seconds` | report, tenant | File modification time |
| `prisma_report_parse_errors_total` | — | Report files that failed to parse |
| `prisma_report_present` | report, tenant | 1 when the report file exists and parsed |
| `prisma_runner_failures_total` | module | Failed applies since the runner started |
| `prisma_runner_interval_seconds` | module | Configured scheduler interval |
| `prisma_runner_last_run_duration_seconds` | module | Duration of the last terraform apply |
| `prisma_runner_last_run_exit_code` | module | Exit code of the last terraform apply |
| `prisma_runner_last_run_success` | module | 1 if the last terraform apply succeeded |
| `prisma_runner_last_run_timestamp_seconds` | module | Unix time of the last terraform apply |
| `prisma_runner_runs_total` | module | Applies since the runner started |
| `prisma_scraper_dropped_samples` | — | Samples dropped because a metric name was reused with a different label set |
| `prisma_scraper_info` | reports_dir, version | metrics_scraper build info |
| `prisma_scraper_last_scan_timestamp_seconds` | — | Unix time of the last directory scan |
| `prisma_scraper_scans_total` | — | Directory scans performed |
| `prisma_snapshot_age_seconds` | report, tenant | Seconds since the snapshot @timestamp |
| `prisma_snapshot_stale` | report, tenant | 1 when the snapshot is older than STALE_AFTER_SECONDS |
| `prisma_snapshot_timestamp_seconds` | report, tenant | @timestamp of the last parsed snapshot |
| `prisma_tenant_info` | api_url, customer_name, plan_type, provider, schema_version, tenant, terraform_module | Tenant / collector identity |

## Recording rules (prometheus/rules/prisma_rules.yml)

`prisma:cloud_accounts_total:delta7d|delta30d`, `prisma:inventory_total_resources:delta7d|pct7d`, `prisma:license_usage_total:delta7d|pct7d|pct30d`, `prisma:license_headroom_workloads`, `prisma:users_active_ratio_30d|7d`, `prisma:logins_per_day`, `prisma:alerts_open:delta24h|delta7d`, `prisma:alert_hygiene_ratio_7d`, `prisma:changes_per_day`, `prisma:risk_component:*`, `prisma:churn_risk_trend_score`, `prisma:churn_risk_combined`.
