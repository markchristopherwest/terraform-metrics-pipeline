############################################################################
# Parse the optional REST responses. Every section becomes null when the
# call was disabled, failed, or returned something unexpected.
############################################################################

locals {
  # Generic "did it work" helper: 200 + parseable JSON, else null.
  api_cloud_raw   = try(data.http.cloud_accounts[0].status_code, 0) == 200 ? try(jsondecode(data.http.cloud_accounts[0].response_body), null) : null
  api_inv_raw     = try(data.http.inventory[0].status_code, 0) == 200 ? try(jsondecode(data.http.inventory[0].response_body), null) : null
  api_inv_acc_raw = try(data.http.inventory_by_account[0].status_code, 0) == 200 ? try(jsondecode(data.http.inventory_by_account[0].response_body), null) : null
  api_lic_raw     = try(data.http.license_usage[0].status_code, 0) == 200 ? try(jsondecode(data.http.license_usage[0].response_body), null) : null
  api_lic_ts_raw  = try(data.http.license_time_series[0].status_code, 0) == 200 ? try(jsondecode(data.http.license_time_series[0].response_body), null) : null
  api_credit_raw  = try(data.http.credit_summary[0].status_code, 0) == 200 ? try(jsondecode(data.http.credit_summary[0].response_body), null) : null
  api_sev_raw     = try(data.http.alerts_by_severity[0].status_code, 0) == 200 ? try(jsondecode(data.http.alerts_by_severity[0].response_body), null) : null
  api_ptype_raw   = try(data.http.alerts_by_policy_type[0].status_code, 0) == 200 ? try(jsondecode(data.http.alerts_by_policy_type[0].response_body), null) : null
  api_apol_raw    = try(data.http.alerts_by_policy[0].status_code, 0) == 200 ? try(jsondecode(data.http.alerts_by_policy[0].response_body), null) : null
  api_audit_raw   = try(data.http.audit_log[0].status_code, 0) == 200 ? try(jsondecode(data.http.audit_log[0].response_body), null) : null

  api_status = {
    cloud_accounts      = try(data.http.cloud_accounts[0].status_code, null)
    inventory           = try(data.http.inventory[0].status_code, null)
    inventory_by_account = try(data.http.inventory_by_account[0].status_code, null)
    license_usage       = try(data.http.license_usage[0].status_code, null)
    license_time_series = try(data.http.license_time_series[0].status_code, null)
    credit_summary      = try(data.http.credit_summary[0].status_code, null)
    alerts_by_severity  = try(data.http.alerts_by_severity[0].status_code, null)
    alerts_by_policy_type = try(data.http.alerts_by_policy_type[0].status_code, null)
    alerts_by_policy    = try(data.http.alerts_by_policy[0].status_code, null)
    audit_log           = try(data.http.audit_log[0].status_code, null)
  }

  # ---- /cloud : rich account list -----------------------------------------
  api_accounts_list = try([for a in local.api_cloud_raw : a if can(a.accountId)], [])
  api_account_by_id = { for a in local.api_accounts_list : tostring(a.accountId) => a... }

  # ---- /v3/inventory --------------------------------------------------------
  inv_summary = try(local.api_inv_raw.summary, null)

  inv_by_cloud_type = {
    for g in try(local.api_inv_raw.groupedAggregates, []) :
    lower(coalesce(try(g.cloudTypeName, null), "unknown")) => {
      total_resources     = try(g.totalResources, null)
      passed_resources    = try(g.passedResources, null)
      failed_resources    = try(g.failedResources, null)
      unscanned_resources = try(g.unscannedResources, null)
    }...
  }

  inv_by_account = {
    for g in try(local.api_inv_acc_raw.groupedAggregates, []) :
    tostring(coalesce(try(g.accountId, null), try(g.accountName, null), "unknown")) => {
      account_name     = try(g.accountName, null)
      total_resources  = try(g.totalResources, null)
      failed_resources = try(g.failedResources, null)
      passed_resources = try(g.passedResources, null)
    }...
  }

  inventory_summary = local.inv_summary == null ? null : {
    timestamp_ms        = try(local.api_inv_raw.timestamp, null)
    total_resources     = try(local.inv_summary.totalResources, null)
    passed_resources    = try(local.inv_summary.passedResources, null)
    failed_resources    = try(local.inv_summary.failedResources, null)
    unscanned_resources = try(local.inv_summary.unscannedResources, null)
    pass_rate_pct       = try(local.inv_summary.totalResources > 0 ? 100 * local.inv_summary.passedResources / local.inv_summary.totalResources : null, null)
    failed_by_severity = {
      critical      = try(local.inv_summary.criticalSeverityFailedResources, null)
      high          = try(local.inv_summary.highSeverityFailedResources, null)
      medium        = try(local.inv_summary.mediumSeverityFailedResources, null)
      low           = try(local.inv_summary.lowSeverityFailedResources, null)
      informational = try(local.inv_summary.informationalSeverityFailedResources, null)
    }
    vulnerable_by_severity = {
      critical = try(local.inv_summary.criticalVulnerabilityFailedResources, null)
      high     = try(local.inv_summary.highVulnerabilityFailedResources, null)
      medium   = try(local.inv_summary.mediumVulnerabilityFailedResources, null)
      low      = try(local.inv_summary.lowVulnerabilityFailedResources, null)
    }
    # first element of each grouped list (one entry per cloud type)
    by_cloud_type = { for k, v in local.inv_by_cloud_type : k => v[0] }
  }

  # ---- /license/api/v2/usage ------------------------------------------------
  lic_items = try(local.api_lic_raw.items, [])

  lic_by_cloud_type_lists = { for i in local.lic_items : lower(coalesce(try(i.cloudType, null), "unknown")) => try(i.total, 0)... }
  lic_by_account          = { for i in local.lic_items : tostring(try(i.account.id, "unknown")) => try(i.total, 0)... }

  license_usage_total = length(local.lic_items) > 0 ? sum([for i in local.lic_items : try(i.total, 0)]) : (local.api_lic_raw == null ? null : 0)

  # ---- /license/api/v2/time_series ------------------------------------------
  lic_points_raw = try(local.api_lic_ts_raw.dataPoints, [])
  lic_points = [for dp in local.lic_points_raw : {
    # the spec models start/end as OptionalLong objects; accept both shapes
    ts_ms = try(dp.timeRange.startTime.asLong, try(dp.timeRange.startTime, null))
    total = try(sum(flatten([for ct, m in dp.counts : [for rt, c in m : c]])), 0)
    by_cloud_type = { for ct, m in try(dp.counts, {}) : lower(ct) => try(sum([for rt, c in m : c]), 0) }
  }]
  lic_points_nonzero = [for p in local.lic_points : p if p.total > 0]
  lic_first_total    = length(local.lic_points_nonzero) > 0 ? local.lic_points_nonzero[0].total : null
  lic_last_total     = length(local.lic_points_nonzero) > 0 ? local.lic_points_nonzero[length(local.lic_points_nonzero) - 1].total : null

  workloads_purchased = try(local.api_lic_ts_raw.workloadsPurchased, null)

  license_summary = (local.api_lic_raw == null && local.api_lic_ts_raw == null && local.api_credit_raw == null) ? null : {
    available_as_of_ms   = try(local.api_lic_ts_raw.availableAsOf, null)
    plan_type            = try(local.api_lic_raw.planType, null)
    workloads_purchased  = local.workloads_purchased
    usage_total          = local.license_usage_total
    usage_window_days    = var.license_usage_days
    utilization_pct      = try(local.workloads_purchased > 0 && local.license_usage_total != null ? 100 * local.license_usage_total / local.workloads_purchased : null, null)
    usage_by_cloud_type  = { for k, v in local.lic_by_cloud_type_lists : k => sum(v) }
    usage_by_resource_type = try({ for k, v in local.api_lic_raw.stats : lower(k) => v }, {})
    accounts_reported    = length(local.lic_items)
    credits = local.api_credit_raw == null ? null : {
      purchased       = try(local.api_credit_raw.purchased, null)
      used            = try(local.api_credit_raw.usage, null)
      utilization_pct = try(local.api_credit_raw.purchased > 0 ? 100 * local.api_credit_raw.usage / local.api_credit_raw.purchased : null, null)
    }
    trend = {
      days        = var.license_trend_days
      points      = length(local.lic_points)
      first_total = local.lic_first_total
      last_total  = local.lic_last_total
      change_pct  = try(local.lic_first_total > 0 ? 100 * (local.lic_last_total - local.lic_first_total) / local.lic_first_total : null, null)
      time_unit   = try(local.api_lic_ts_raw.timeUnit, null)
    }
    time_series = local.lic_points
  }

  # ---- alerts (aggregate) ---------------------------------------------------
  alerts_open_by_severity = { for g in try(local.api_sev_raw.groups, []) : lower(coalesce(try(g.group, null), "unknown")) => try(g.totalAlerts, 0)... }
  alerts_open_by_type     = { for g in try(local.api_ptype_raw.groups, []) : lower(coalesce(try(g.group, null), "unknown")) => try(g.totalAlerts, 0)... }

  # top-N policies by open alert count (sort() only sorts strings -> zero-pad the count)
  apol_list = [for p in try(local.api_apol_raw.policies, []) : {
    policy_id   = try(p.policyId, "")
    policy_name = try(p.policyName, "")
    severity    = lower(coalesce(try(p.severity, null), "unknown"))
    policy_type = lower(coalesce(try(p.policyType, null), "unknown"))
    cloud_type  = lower(coalesce(try(p.cloudType, null), "all"))
    alert_count = try(p.alertCount, 0)
    remediable  = try(p.remediable, null)
  } if can(p.policyId)]
  apol_by_id  = { for p in local.apol_list : p.policy_id => p... }
  apol_sorted = reverse(sort([for p in local.apol_list : format("%012d|%s", p.alert_count, p.policy_id)]))
  apol_top    = [for k in slice(local.apol_sorted, 0, min(var.top_n, length(local.apol_sorted))) : local.apol_by_id[split("|", k)[1]][0]]

  alerts_summary = {
    opened_24h   = local.alert_window_totals.opened_24h
    opened_7d    = local.alert_window_totals.opened_7d
    resolved_7d  = local.alert_window_totals.resolved_7d
    dismissed_7d = local.alert_window_totals.dismissed_7d
    snoozed_7d   = local.alert_window_totals.snoozed_7d
    # from /alert/v1/aggregate (all open alerts, any age)
    open               = try(local.api_sev_raw.countDetails.totalAlerts, null)
    open_policies      = try(local.api_sev_raw.countDetails.totalPolicies, null)
    open_by_severity   = { for k, v in local.alerts_open_by_severity : k => sum(v) }
    open_by_policy_type = { for k, v in local.alerts_open_by_type : k => sum(v) }
    top_policies       = local.apol_top
  }

  # ---- /audit/redlock -------------------------------------------------------
  audit_events = try([for e in local.api_audit_raw : {
    user        = var.pseudonymize_users ? substr(sha256(lower(coalesce(try(e.user, null), "unknown"))), 0, 16) : coalesce(try(e.user, null), "unknown")
    action_type = upper(coalesce(try(e.actionType, null), "unknown"))
    is_login    = upper(coalesce(try(e.actionType, null), "")) == "LOGIN" || lower(coalesce(try(e.resourceType, null), "")) == "login"
    failed      = lower(coalesce(try(e.result, null), "")) != "success"
  }], [])

  audit_by_user_lists = { for e in local.audit_events : e.user => e... }
  audit_by_user       = { for k, v in local.audit_by_user_lists : k => length(v) }
  audit_user_sorted   = reverse(sort([for k, v in local.audit_by_user : format("%012d|%s", v, k)]))
  audit_top_users = {
    for s in slice(local.audit_user_sorted, 0, min(var.top_n, length(local.audit_user_sorted))) :
    split("|", s)[1] => local.audit_by_user[split("|", s)[1]]
  }

  activity_summary = local.api_audit_raw == null ? null : {
    window_hours         = var.activity_window_hours
    events_total         = length(local.audit_events)
    logins               = length([for e in local.audit_events : e if e.is_login])
    failed_events        = length([for e in local.audit_events : e if e.failed])
    distinct_users       = length(distinct([for e in local.audit_events : e.user]))
    distinct_login_users = length(distinct([for e in local.audit_events : e.user if e.is_login]))
    by_action_type = {
      for k, v in { for e in local.audit_events : lower(e.action_type) => e... } : k => length(v)
    }
    events_by_user = local.audit_top_users
  }
}
