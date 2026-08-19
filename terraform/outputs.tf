output "report_files" {
  description = "Files written by this run."
  value = [
    local_sensitive_file.summary.filename,
    local_sensitive_file.cloud_accounts.filename,
    local_sensitive_file.users.filename,
    local_sensitive_file.policies.filename,
    local_sensitive_file.alert_rules.filename,
    local_sensitive_file.integrations.filename,
  ]
}

output "snapshot" {
  description = "Headline numbers of this run (handy in the scheduler log)."
  value = {
    timestamp        = local.now_rfc3339
    tenant           = var.tenant_label
    cloud_accounts   = local.cloud_accounts_summary.total
    users            = local.users_summary.total
    users_active_30d = local.users_summary.human_active_30d
    policies_enabled = local.policies_summary.enabled
    custom_policies  = local.policies_summary.custom
    alert_rules      = local.alert_rules_summary.enabled
    integrations     = local.integrations_summary.total
    alerts_open      = local.alerts_summary.open
    resources_total  = try(local.inventory_summary.total_resources, null)
    license_usage    = try(local.license_summary.usage_total, null)
    adoption_score   = local.scores.adoption_score
    risk_score       = local.scores.risk_score
    risk_flags       = local.scores.risk_flags
    api_status       = local.api_status
  }
}
