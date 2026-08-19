############################################################################
# Normalise what the prismacloud provider returned into plain lists/maps.
# try(..., []) makes every disabled or empty data source a no-op.
############################################################################

locals {
  # Alert-volume windows read through data.prismacloud_alerts (limit = 1).
  alert_windows = {
    opened_24h   = { status = "open", amount = 24, unit = "hour" }
    opened_7d    = { status = "open", amount = 7, unit = "day" }
    resolved_7d  = { status = "resolved", amount = 7, unit = "day" }
    dismissed_7d = { status = "dismissed", amount = 7, unit = "day" }
    snoozed_7d   = { status = "snoozed", amount = 7, unit = "day" }
  }

  # ---- raw listings ------------------------------------------------------
  raw_accounts        = try(data.prismacloud_cloud_accounts.all.listing, [])
  raw_account_groups  = try(data.prismacloud_account_groups.all.listing, [])
  raw_users           = try(data.prismacloud_user_profiles.all[0].listing, [])
  raw_roles           = try(data.prismacloud_user_roles.all[0].listing, [])
  raw_perm_groups     = try(data.prismacloud_permission_groups.all[0].listing, [])
  raw_policies        = try(data.prismacloud_policies.all[0].listing, [])
  raw_alert_rules     = try(data.prismacloud_alert_rules.all[0].listing, [])
  raw_integrations    = try(data.prismacloud_integrations.all[0].listing, [])
  raw_templates       = try(data.prismacloud_notification_templates.all[0].listing, [])
  raw_standards       = try(data.prismacloud_compliance_standards.all[0].listing, [])
  raw_reports         = try(data.prismacloud_reports.all[0].listing, [])
  raw_saved_searches  = try(data.prismacloud_rql_historic_searches.saved[0].listing, [])
  raw_recent_searches = try(data.prismacloud_rql_historic_searches.recent[0].listing, [])
  raw_resource_lists  = try(data.prismacloud_resource_lists.all[0].listing, [])
  raw_collections     = try(data.prismacloud_collections.all[0].listing, [])
  raw_login_ips       = try(data.prismacloud_trusted_login_ips.all[0].listing, [])
  raw_alert_ips       = try(data.prismacloud_trusted_alert_ips.all[0].listing, [])
  raw_anomaly_network = try(data.prismacloud_anomaly_settings.network[0].listing, [])
  raw_anomaly_ueba    = try(data.prismacloud_anomaly_settings.ueba[0].listing, [])
  ent                 = try(data.prismacloud_enterprise_settings.current[0], null)

  alert_window_totals = {
    for k, w in local.alert_windows :
    k => try(data.prismacloud_alerts.windows[k].total, null)
  }

  # ---- helpers -----------------------------------------------------------
  # Pseudonymisation for user identifiers (opt-in).
  uid = { for u in local.raw_users : u.username => (
    var.pseudonymize_users ? substr(sha256(lower(u.username)), 0, 16) : u.username
  ) }

  role_by_id      = { for r in local.raw_roles : r.role_id => r }
  admin_role_ids  = [for r in local.raw_roles : r.role_id if r.role_type == "System Admin"]
  builtin_roles   = ["System Admin", "Account Group Admin", "Account Group Read Only", "Cloud Provisioning Admin", "Account and Cloud Provisioning Admin", "Build and Deploy Security", "Developer", "NetSecOps"]
  account_grouped = distinct(flatten([for g in local.raw_account_groups : [for a in g.accounts : tostring(a.account_id)]]))

  # ---- users -------------------------------------------------------------
  users = [for u in local.raw_users : {
    "@timestamp"      = local.now_rfc3339
    report            = "users"
    tenant            = var.tenant_label
    user_id           = local.uid[u.username]
    account_type      = u.account_type
    enabled           = u.enabled
    last_login_ts     = coalesce(u.last_login_ts, 0)
    days_since_login  = coalesce(u.last_login_ts, 0) > 0 ? max(0, floor((local.now_epoch_ms - u.last_login_ts) / local.ms_per_day)) : null
    login_bucket      = coalesce(u.last_login_ts, 0) <= 0 ? "never" : (local.now_epoch_ms - u.last_login_ts) <= 7 * local.ms_per_day ? "7d" : (local.now_epoch_ms - u.last_login_ts) <= 30 * local.ms_per_day ? "30d" : (local.now_epoch_ms - u.last_login_ts) <= 90 * local.ms_per_day ? "90d" : "90d_plus"
    role_count        = try(length(u.role_ids), 0)
    default_role      = try(local.role_by_id[u.default_role_id].name, null)
    default_role_type = try(local.role_by_id[u.default_role_id].role_type, null)
    is_admin          = anytrue(try([for rid in u.role_ids : contains(local.admin_role_ids, rid)], []))
    last_modified_ts  = u.last_modified_ts
  }]

  human_users   = [for u in local.users : u if u.account_type != "SERVICE_ACCOUNT"]
  human_enabled = [for u in local.human_users : u if u.enabled]
  human_login_ts = [for u in local.human_users : u.last_login_ts if u.last_login_ts > 0]

  users_summary = {
    total                       = length(local.users)
    enabled                     = length([for u in local.users : u if u.enabled])
    disabled                    = length([for u in local.users : u if !u.enabled])
    service_accounts            = length([for u in local.users : u if u.account_type == "SERVICE_ACCOUNT"])
    human_total                 = length(local.human_users)
    human_enabled               = length(local.human_enabled)
    human_active_7d             = length([for u in local.human_users : u if u.login_bucket == "7d"])
    human_active_30d            = length([for u in local.human_users : u if contains(["7d", "30d"], u.login_bucket)])
    human_active_90d            = length([for u in local.human_users : u if contains(["7d", "30d", "90d"], u.login_bucket)])
    human_inactive_90d_plus     = length([for u in local.human_users : u if u.login_bucket == "90d_plus"])
    human_never_logged_in       = length([for u in local.human_users : u if u.login_bucket == "never"])
    admins                      = length([for u in local.users : u if u.is_admin])
    days_since_last_human_login = length(local.human_login_ts) > 0 ? max(0, (local.now_epoch_ms - max(local.human_login_ts...)) / local.ms_per_day) : null
    by_login_bucket = {
      for b in ["7d", "30d", "90d", "90d_plus", "never"] :
      b => length([for u in local.human_users : u if u.login_bucket == b])
    }
    by_account_type = {
      for k, v in { for u in local.users : lower(coalesce(u.account_type, "unknown")) => u... } : k => length(v)
    }
    by_default_role_type = {
      for k, v in { for u in local.users : coalesce(u.default_role_type, "unknown") => u... } : k => length(v)
    }
  }

  roles_summary = {
    total  = length(local.raw_roles)
    custom = length([for r in local.raw_roles : r if !contains(local.builtin_roles, r.role_type)])
    by_role_type = {
      for k, v in { for r in local.raw_roles : coalesce(r.role_type, "unknown") => r... } : k => length(v)
    }
  }

  permission_groups_summary = {
    total  = length(local.raw_perm_groups)
    custom = length([for g in local.raw_perm_groups : g if try(g.custom, false)])
  }

  # ---- policies ----------------------------------------------------------
  policies_live    = [for p in local.raw_policies : p if !try(p.deleted, false)]
  policies_enabled = [for p in local.policies_live : p if p.enabled]
  policies_custom  = [for p in local.policies_live : p if !p.system_default]

  # Entity lines: custom (non system-default) policies only - the whole
  # catalogue is thousands of lines and is summarised instead.
  policy_lines = [for p in local.policies_custom : {
    "@timestamp"      = local.now_rfc3339
    report            = "policies"
    tenant            = var.tenant_label
    policy_id         = p.policy_id
    name              = p.name
    policy_type       = p.policy_type
    policy_subtypes   = tolist(p.policy_subtypes)
    severity          = p.severity
    cloud_type        = lower(coalesce(p.cloud_type, "all"))
    enabled           = p.enabled
    system_default    = p.system_default
    remediable        = p.remediable
    policy_mode       = p.policy_mode
    open_alerts_count = coalesce(p.open_alerts_count, 0)
    labels            = tolist(p.labels)
  }]

  policies_summary = {
    total                  = length(local.policies_live)
    enabled                = length(local.policies_enabled)
    disabled               = length(local.policies_live) - length(local.policies_enabled)
    custom                 = length(local.policies_custom)
    custom_enabled         = length([for p in local.policies_custom : p if p.enabled])
    system_default         = length([for p in local.policies_live : p if p.system_default])
    system_default_enabled = length([for p in local.policies_enabled : p if p.system_default])
    remediable_enabled     = length([for p in local.policies_enabled : p if p.remediable])
    with_open_alerts       = length([for p in local.policies_live : p if coalesce(p.open_alerts_count, 0) > 0])
    open_alerts_sum        = length(local.policies_live) > 0 ? sum([for p in local.policies_live : coalesce(p.open_alerts_count, 0)]) : 0
    enabled_by_severity = {
      for k, v in { for p in local.policies_enabled : lower(coalesce(p.severity, "unknown")) => p... } : k => length(v)
    }
    enabled_by_type = {
      for k, v in { for p in local.policies_enabled : lower(coalesce(p.policy_type, "unknown")) => p... } : k => length(v)
    }
    enabled_by_cloud_type = {
      for k, v in { for p in local.policies_enabled : lower(coalesce(p.cloud_type, "all")) => p... } : k => length(v)
    }
    custom_by_type = {
      for k, v in { for p in local.policies_custom : lower(coalesce(p.policy_type, "unknown")) => p... } : k => length(v)
    }
  }

  # ---- alert rules -------------------------------------------------------
  alert_rules_live = [for r in local.raw_alert_rules : r if !try(r.deleted, false)]

  alert_rule_lines = [for r in local.alert_rules_live : {
    "@timestamp"      = local.now_rfc3339
    report            = "alert_rules"
    tenant            = var.tenant_label
    rule_id           = r.policy_scan_config_id
    name              = r.name
    enabled           = r.enabled
    scan_all          = r.scan_all
    policies_count    = try(length(r.policies), 0)
    open_alerts_count = coalesce(r.open_alerts_count, 0)
    owner             = r.owner
    read_only         = r.read_only
  }]

  alert_rules_summary = {
    total                 = length(local.alert_rules_live)
    enabled               = length([for r in local.alert_rules_live : r if r.enabled])
    disabled              = length([for r in local.alert_rules_live : r if !r.enabled])
    scan_all              = length([for r in local.alert_rules_live : r if r.scan_all])
    with_open_alerts      = length([for r in local.alert_rules_live : r if coalesce(r.open_alerts_count, 0) > 0])
    policies_attached_sum = length(local.alert_rules_live) > 0 ? sum([for r in local.alert_rules_live : try(length(r.policies), 0)]) : 0
    open_alerts_sum       = length(local.alert_rules_live) > 0 ? sum([for r in local.alert_rules_live : coalesce(r.open_alerts_count, 0)]) : 0
  }

  # ---- integrations ------------------------------------------------------
  integration_lines = [for i in local.raw_integrations : {
    "@timestamp"     = local.now_rfc3339
    report           = "integrations"
    tenant           = var.tenant_label
    integration_id   = i.integration_id
    name             = i.name
    integration_type = i.integration_type
    enabled          = i.enabled
    status           = coalesce(i.status, "unknown")
    valid            = i.valid
  }]

  integrations_summary = {
    total    = length(local.raw_integrations)
    enabled  = length([for i in local.raw_integrations : i if i.enabled])
    disabled = length([for i in local.raw_integrations : i if !i.enabled])
    valid    = length([for i in local.raw_integrations : i if i.valid])
    invalid  = length([for i in local.raw_integrations : i if !i.valid])
    by_type = {
      for k, v in { for i in local.raw_integrations : lower(i.integration_type) => i... } : k => length(v)
    }
    by_status = {
      for k, v in { for i in local.raw_integrations : lower(coalesce(i.status, "unknown")) => i... } : k => length(v)
    }
  }

  # ---- everything else (counts only) ---------------------------------------
  notification_templates_summary = {
    total   = length(local.raw_templates)
    enabled = length([for t in local.raw_templates : t if try(t.enabled, false)])
  }

  custom_standards = [for s in local.raw_standards : s if !s.system_default]

  compliance_summary = {
    total                        = length(local.raw_standards)
    custom                       = length(local.custom_standards)
    system_default               = length(local.raw_standards) - length(local.custom_standards)
    custom_policies_assigned_sum = length(local.custom_standards) > 0 ? sum([for s in local.custom_standards : coalesce(s.policies_assigned_count, 0)]) : 0
  }

  reports_summary = {
    total = length(local.raw_reports)
    by_type = {
      for k, v in { for r in local.raw_reports : lower(coalesce(r.report_type, "unknown")) => r... } : k => length(v)
    }
    by_status = {
      for k, v in { for r in local.raw_reports : lower(coalesce(r.status, "unknown")) => r... } : k => length(v)
    }
  }

  saved_searches_summary = {
    saved  = length(local.raw_saved_searches)
    recent = length(local.raw_recent_searches)
  }

  resource_lists_summary = {
    total = length(local.raw_resource_lists)
    by_type = {
      for k, v in { for r in local.raw_resource_lists : lower(coalesce(r.resource_list_type, "unknown")) => r... } : k => length(v)
    }
  }

  collections_summary = { total = length(local.raw_collections) }

  trusted_ips_summary = {
    login_allowlists = length(local.raw_login_ips)
    alert_allowlists = length(local.raw_alert_ips)
  }

  enterprise_settings_summary = local.ent == null ? null : {
    session_timeout_minutes         = try(local.ent.session_timeout, null)
    access_key_max_validity_days    = try(local.ent.access_key_max_validity, null)
    audit_logs_enabled              = try(local.ent.audit_logs_enabled, null)
    apply_default_policies_enabled  = try(local.ent.apply_default_policies_enabled, null)
    require_alert_dismissal_note    = try(local.ent.require_alert_dismissal_note, null)
    user_attribution_in_notification = try(local.ent.user_attribution_in_notification, null)
    alarm_enabled                   = try(local.ent.alarm_enabled, null)
    audit_log_siem_integrations     = try(length(local.ent.audit_log_siem_intgr_ids), 0)
    default_policies_enabled_by_severity = try({ for k, v in local.ent.default_policies_enabled : lower(k) => v }, {})
  }

  anomaly_summary = {
    network_policies = length(local.raw_anomaly_network)
    ueba_policies    = length(local.raw_anomaly_ueba)
  }

  account_groups_summary = {
    total            = length(local.raw_account_groups)
    auto_created     = length([for g in local.raw_account_groups : g if anytrue([for p in try(g.parent_info, []) : try(p.auto_created, false)])])
    with_alert_rules = length([for g in local.raw_account_groups : g if length(try(g.alert_rules, [])) > 0])
  }
}
