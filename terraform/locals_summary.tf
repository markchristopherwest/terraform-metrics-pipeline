############################################################################
# Cloud-account entity lines, the tenant summary document, and the two
# post-sales heuristics (adoption score / churn-risk score).
############################################################################

locals {
  # ---- cloud accounts (provider listing + optional /cloud enrichment) ------
  account_lines = [for a in local.raw_accounts : {
    "@timestamp"    = local.now_rfc3339
    report          = "cloud_accounts"
    tenant          = var.tenant_label
    account_id      = tostring(a.account_id)
    name            = a.name
    cloud_type      = lower(coalesce(a.cloud_type, "unknown"))
    in_account_group = contains(local.account_grouped, tostring(a.account_id))
    # --- enrichment from GET /cloud (null when api_enrichment = false or the account is a child) ---
    enabled                  = try(local.api_account_by_id[tostring(a.account_id)][0].enabled, null)
    status                   = try(lower(local.api_account_by_id[tostring(a.account_id)][0].status), null)
    account_type             = try(lower(local.api_account_by_id[tostring(a.account_id)][0].accountType), null)
    protection_mode          = try(lower(local.api_account_by_id[tostring(a.account_id)][0].protectionMode), null)
    deployment_type          = try(lower(local.api_account_by_id[tostring(a.account_id)][0].deploymentType), null)
    number_of_child_accounts = try(local.api_account_by_id[tostring(a.account_id)][0].numberOfChildAccounts, null)
    added_on_ms              = try(local.api_account_by_id[tostring(a.account_id)][0].addedOn, null)
    last_modified_ms         = try(local.api_account_by_id[tostring(a.account_id)][0].lastModifiedTs, null)
    storage_scan_enabled     = try(local.api_account_by_id[tostring(a.account_id)][0].storageScanEnabled, null)
    account_groups           = try([for g in local.api_account_by_id[tostring(a.account_id)][0].accountGroupInfos : g.groupName], null)
    # --- inventory + licence joins ---
    resources_total   = try(local.inv_by_account[tostring(a.account_id)][0].total_resources, try(local.inv_by_account[a.name][0].total_resources, null))
    resources_failed  = try(local.inv_by_account[tostring(a.account_id)][0].failed_resources, try(local.inv_by_account[a.name][0].failed_resources, null))
    license_workloads = try(sum(local.lic_by_account[tostring(a.account_id)]), null)
  }]

  accounts_enriched = [for a in local.account_lines : a if a.enabled != null]

  cloud_accounts_summary = {
    total    = length(local.account_lines)
    enabled  = length([for a in local.accounts_enriched : a if a.enabled == true])
    disabled = length([for a in local.accounts_enriched : a if a.enabled == false])
    by_cloud_type = {
      for k, v in { for a in local.account_lines : a.cloud_type => a... } : k => length(v)
    }
    enabled_by_cloud_type = {
      for k, v in { for a in local.accounts_enriched : a.cloud_type => a... if a.enabled == true } : k => length(v)
    }
    by_account_type = {
      for k, v in { for a in local.accounts_enriched : coalesce(a.account_type, "unknown") => a... } : k => length(v)
    }
    by_status = {
      for k, v in { for a in local.accounts_enriched : coalesce(a.status, "unknown") => a... } : k => length(v)
    }
    by_protection_mode = {
      for k, v in { for a in local.accounts_enriched : coalesce(a.protection_mode, "unknown") => a... } : k => length(v)
    }
    child_accounts_total = length(local.accounts_enriched) > 0 ? sum([for a in local.accounts_enriched : coalesce(a.number_of_child_accounts, 0)]) : 0
    storage_scan_enabled = length([for a in local.accounts_enriched : a if a.storage_scan_enabled == true])
    added_last_30d       = length([for a in local.accounts_enriched : a if try(a.added_on_ms > local.now_epoch_ms - 30 * local.ms_per_day, false)])
    ungrouped            = length([for a in local.account_lines : a if !a.in_account_group])
    with_inventory       = length([for a in local.account_lines : a if a.resources_total != null])
    resources_total      = length(local.account_lines) > 0 ? sum([for a in local.account_lines : coalesce(a.resources_total, 0)]) : 0
  }

  # ---- heuristics ------------------------------------------------------------
  # Point-in-time signals; trend-based signals live in prometheus/rules.
  aw = var.adoption_weights
  rw = var.risk_weights

  license_util = try(local.license_summary.utilization_pct, null)
  credit_util  = try(local.license_summary.credits.utilization_pct, null)
  util_pct     = local.credit_util != null ? local.credit_util : local.license_util

  accounts_unhealthy = length([for a in local.accounts_enriched : a if a.enabled == false || (a.status == null ? false : !contains(["ok", "healthy", "success", "enabled"], a.status))])

  adoption_components = {
    all_accounts_healthy      = (length(local.account_lines) > 0 && local.accounts_unhealthy == 0) ? local.aw.all_accounts_healthy : 0
    multi_cloud               = length(local.cloud_accounts_summary.by_cloud_type) > 1 ? local.aw.multi_cloud : 0
    integration_valid         = length([for i in local.raw_integrations : i if i.enabled && i.valid]) > 0 ? local.aw.integration_valid : 0
    alert_rule_enabled        = local.alert_rules_summary.enabled > 0 ? local.aw.alert_rule_enabled : 0
    custom_policy             = local.policies_summary.custom_enabled > 0 ? local.aw.custom_policy : 0
    custom_compliance         = local.compliance_summary.custom > 0 ? local.aw.custom_compliance : 0
    saved_search              = local.saved_searches_summary.saved > 0 ? local.aw.saved_search : 0
    scheduled_report          = local.reports_summary.total > 0 ? local.aw.scheduled_report : 0
    two_active_users_30d      = local.users_summary.human_active_30d >= 2 ? local.aw.two_active_users_30d : 0
    audit_or_siem_enabled     = (try(local.enterprise_settings_summary.audit_logs_enabled, false) == true || try(local.enterprise_settings_summary.audit_log_siem_integrations, 0) > 0) ? local.aw.audit_or_siem_enabled : 0
    license_utilization_50pct = try(local.util_pct >= 50, false) ? local.aw.license_utilization_50pct : 0
  }
  adoption_max   = sum(values(local.aw))
  adoption_score = local.adoption_max > 0 ? min(100, floor(100 * sum(values(local.adoption_components)) / local.adoption_max + 0.5)) : 0

  risk_components = {
    no_human_login_30d      = (local.users_summary.human_total > 0 && local.users_summary.human_active_30d == 0) ? local.rw.no_human_login_30d : 0
    single_active_user_30d  = (local.users_summary.human_total > 1 && local.users_summary.human_active_30d == 1) ? local.rw.single_active_user_30d : 0
    accounts_disabled       = local.cloud_accounts_summary.disabled > 0 ? local.rw.accounts_disabled : 0
    integrations_broken     = ((local.integrations_summary.total > 0 && local.integrations_summary.valid == 0) || local.integrations_summary.invalid > 0) ? local.rw.integrations_broken : 0
    no_alert_rules          = local.alert_rules_summary.enabled == 0 ? local.rw.no_alert_rules : 0
    alerts_open_no_activity = (coalesce(local.alerts_summary.open, 0) > 0 && coalesce(local.alerts_summary.resolved_7d, 0) == 0 && coalesce(local.alerts_summary.dismissed_7d, 0) == 0) ? local.rw.alerts_open_no_activity : 0
    license_utilization_low = try(local.util_pct < 25, false) ? local.rw.license_utilization_low : 0
  }
  risk_score = min(100, sum(values(local.risk_components)))
  risk_flags = sort([for k, v in local.risk_components : k if v > 0])

  scores = {
    adoption_score            = local.adoption_score
    adoption_points_by_signal = local.adoption_components
    risk_score                = local.risk_score
    risk_points_by_signal     = local.risk_components
    risk_flags                = local.risk_flags
  }

  # ---- the summary document ---------------------------------------------------
  summary = {
    "@timestamp"   = local.now_rfc3339
    report         = "summary"
    schema_version = 1
    tenant         = var.tenant_label
    run = {
      epoch_ms              = local.now_epoch_ms
      interval_hint_seconds = var.interval_hint_seconds
      terraform_module      = "terraform"
      provider              = "PaloAltoNetworks/prismacloud"
      api_url               = var.prismacloud_url
      customer_name         = var.prismacloud_customer_name
      api_enrichment        = var.api_enrichment
      api_status            = local.api_status
      pseudonymized_users   = var.pseudonymize_users
      collect               = var.collect
    }
    cloud_accounts         = local.cloud_accounts_summary
    account_groups         = local.account_groups_summary
    users                  = local.users_summary
    roles                  = local.roles_summary
    permission_groups      = local.permission_groups_summary
    policies               = local.policies_summary
    alert_rules            = local.alert_rules_summary
    alerts                 = local.alerts_summary
    integrations           = local.integrations_summary
    notification_templates = local.notification_templates_summary
    compliance_standards   = local.compliance_summary
    reports                = local.reports_summary
    saved_searches         = local.saved_searches_summary
    resource_lists         = local.resource_lists_summary
    collections            = local.collections_summary
    trusted_ips            = local.trusted_ips_summary
    enterprise_settings    = local.enterprise_settings_summary
    anomaly_settings       = local.anomaly_summary
    inventory              = local.inventory_summary
    license                = local.license_summary
    activity               = local.activity_summary
    scores                 = local.scores
  }
}
