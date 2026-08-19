############################################################################
# Synthetic stand-in for ../terraform: writes the SAME files with the SAME
# schema, but from deterministic pseudo-random data derived from the clock.
# No Prisma Cloud tenant, no network. Use it to demo / test the pipeline:
#
#   TF_MODULE=terraform-mock docker compose up -d      (or: make demo)
#
# Data evolves run-to-run (users log in, an account gets disabled and
# re-enabled, an integration breaks, alert counts wander, licence usage
# drifts) so every dashboard panel and the change feed have something to show.
############################################################################

locals {
  now_rfc3339 = plantimestamp()

  # --- epoch from plantimestamp() (same algorithm as the real module) ---
  _t_year   = tonumber(formatdate("YYYY", local.now_rfc3339))
  _t_month  = tonumber(formatdate("MM", local.now_rfc3339))
  _t_day    = tonumber(formatdate("DD", local.now_rfc3339))
  _t_hour   = tonumber(formatdate("hh", local.now_rfc3339))
  _t_minute = tonumber(formatdate("mm", local.now_rfc3339))
  _t_second = tonumber(formatdate("ss", local.now_rfc3339))
  _t_y      = local._t_month <= 2 ? local._t_year - 1 : local._t_year
  _t_era    = floor(local._t_y / 400)
  _t_yoe    = local._t_y - local._t_era * 400
  _t_mp     = local._t_month > 2 ? local._t_month - 3 : local._t_month + 9
  _t_doy    = floor((153 * local._t_mp + 2) / 5) + local._t_day - 1
  _t_doe    = local._t_yoe * 365 + floor(local._t_yoe / 4) - floor(local._t_yoe / 100) + local._t_doy
  now_epoch = (local._t_era * 146097 + local._t_doe - 719468) * 86400 + local._t_hour * 3600 + local._t_minute * 60 + local._t_second

  now_epoch_ms = local.now_epoch * 1000
  ms_per_day   = 86400000
  run          = floor(local.now_epoch / var.interval_hint_seconds) # increments every interval
  day          = floor(local.now_epoch / 86400)

  # (terraform has no RNG; parseint(substr(sha256(seed+key))) is plenty for a demo)

  # Account catalogue: the tenant "onboards" one more account roughly every 2 days.
  account_catalogue = [
    { id = "123456789012", name = "acme-prod-aws", cloud = "aws", type = "organization", children = 42 },
    { id = "210987654321", name = "acme-dev-aws", cloud = "aws", type = "account", children = 0 },
    { id = "f5b1c2d3-0001-4a2b-9c3d-000000000001", name = "acme-core-azure", cloud = "azure", type = "tenant", children = 9 },
    { id = "f5b1c2d3-0002-4a2b-9c3d-000000000002", name = "acme-data-azure", cloud = "azure", type = "account", children = 0 },
    { id = "acme-platform-gcp", name = "acme-platform-gcp", cloud = "gcp", type = "organization", children = 17 },
    { id = "acme-ml-gcp", name = "acme-ml-gcp", cloud = "gcp", type = "account", children = 0 },
    { id = "ocid1.tenancy.oc1..aaaa0001", name = "acme-oci", cloud = "oci", type = "tenant", children = 3 },
    { id = "345678901234", name = "acme-sandbox-aws", cloud = "aws", type = "account", children = 0 },
    { id = "456789012345", name = "acme-payments-aws", cloud = "aws", type = "account", children = 0 },
    { id = "f5b1c2d3-0003-4a2b-9c3d-000000000003", name = "acme-eu-azure", cloud = "azure", type = "account", children = 0 },
    { id = "567890123456", name = "acme-analytics-aws", cloud = "aws", type = "account", children = 0 },
    { id = "acme-edge-gcp", name = "acme-edge-gcp", cloud = "gcp", type = "account", children = 0 },
  ]
  accounts_onboarded = min(length(local.account_catalogue), 8 + floor((local.day % 8) / 2))
  accounts_live      = slice(local.account_catalogue, 0, local.accounts_onboarded)

  # account #4 (index 3) goes disabled for 6 runs out of every 42; status warning on #2 every 3rd hour
  account_lines = [for i, a in local.accounts_live : {
    "@timestamp"             = local.now_rfc3339
    report                   = "cloud_accounts"
    tenant                   = var.tenant_label
    account_id               = a.id
    name                     = a.name
    cloud_type               = a.cloud
    in_account_group         = i != 7
    enabled                  = !(i == 3 && (local.run % 42) < 6)
    status                   = (i == 1 && (floor(local.run / 12) % 3) == 2) ? "warning" : "ok"
    account_type             = a.type
    protection_mode          = i % 4 == 0 ? "monitor_and_protect" : "monitor"
    deployment_type          = upper(a.cloud)
    number_of_child_accounts = a.children
    added_on_ms              = local.now_epoch_ms - (60 - i * 4) * local.ms_per_day
    last_modified_ms         = local.now_epoch_ms - (i + 1) * 3 * local.ms_per_day
    storage_scan_enabled     = i < 2
    account_groups           = i < 6 ? ["Production"] : ["Default Account Group"]
    resources_total          = 1200 + i * 431 + (parseint(substr(sha256("${var.seed}-res-${i}-${local.run}"), 0, 4), 16) % 60) + local.day % 7 * 9
    resources_failed         = 90 + i * 17 + (parseint(substr(sha256("${var.seed}-fail-${i}-${local.run}"), 0, 4), 16) % 12)
    license_workloads        = 80 + i * 23 + (local.day % 5) * 3
  }]

  # --- users ---
  user_catalogue = [
    { name = "alice.admin@acme.example", type = "USER_ACCOUNT", role = "System Admin", period = 2, admin = true },
    { name = "bob.secops@acme.example", type = "USER_ACCOUNT", role = "System Admin", period = 5, admin = true },
    { name = "carol.cloud@acme.example", type = "USER_ACCOUNT", role = "Account Group Admin", period = 13, admin = false },
    { name = "dave.devops@acme.example", type = "USER_ACCOUNT", role = "Developer", period = 40, admin = false },
    { name = "erin.audit@acme.example", type = "USER_ACCOUNT", role = "Account Group Read Only", period = 300, admin = false },
    { name = "frank.fin@acme.example", type = "USER_ACCOUNT", role = "Account Group Read Only", period = 0, admin = false },
    { name = "grace.grc@acme.example", type = "USER_ACCOUNT", role = "Account Group Read Only", period = 9000, admin = false },
    { name = "heidi.ir@acme.example", type = "USER_ACCOUNT", role = "Account Group Admin", period = 26, admin = false },
    { name = "ivan.platform@acme.example", type = "USER_ACCOUNT", role = "Developer", period = 0, admin = false },
    { name = "svc-terraform", type = "SERVICE_ACCOUNT", role = "System Admin", period = 1, admin = true },
    { name = "svc-jenkins-ci", type = "SERVICE_ACCOUNT", role = "Build and Deploy Security", period = 3, admin = false },
    { name = "svc-splunk", type = "SERVICE_ACCOUNT", role = "Account Group Read Only", period = 7, admin = false },
  ]

  # last login = the latest run that is a multiple of the user's period (0 = never)
  user_last_login = [for i, u in local.user_catalogue :
    u.period == 0 ? -1 : (local.run - ((local.run + i * 7) % u.period)) * var.interval_hint_seconds * 1000
  ]

  users = [for i, u in local.user_catalogue : {
    "@timestamp"      = local.now_rfc3339
    report            = "users"
    tenant            = var.tenant_label
    user_id           = var.pseudonymize_users ? substr(sha256(lower(u.name)), 0, 16) : u.name
    account_type      = u.type
    enabled           = i != 8
    last_login_ts     = local.user_last_login[i]
    days_since_login  = local.user_last_login[i] > 0 ? max(0, floor((local.now_epoch_ms - local.user_last_login[i]) / local.ms_per_day)) : null
    login_bucket      = local.user_last_login[i] <= 0 ? "never" : (local.now_epoch_ms - local.user_last_login[i]) <= 7 * local.ms_per_day ? "7d" : (local.now_epoch_ms - local.user_last_login[i]) <= 30 * local.ms_per_day ? "30d" : (local.now_epoch_ms - local.user_last_login[i]) <= 90 * local.ms_per_day ? "90d" : "90d_plus"
    role_count        = u.admin ? 1 : 2
    default_role      = u.role
    default_role_type = u.role
    is_admin          = u.admin
    last_modified_ts  = local.now_epoch_ms - 40 * local.ms_per_day
  }]
  human_users    = [for u in local.users : u if u.account_type != "SERVICE_ACCOUNT"]
  human_login_ts = [for u in local.human_users : u.last_login_ts if u.last_login_ts > 0]

  # --- policies (custom ones get lines) ---
  custom_policy_catalogue = [
    { name = "ACME - S3 bucket without org tag", type = "config", sev = "medium", cloud = "aws" },
    { name = "ACME - Public snapshot", type = "config", sev = "high", cloud = "aws" },
    { name = "ACME - AKS cluster without RBAC", type = "config", sev = "high", cloud = "azure" },
    { name = "ACME - Egress to sanctioned country", type = "network", sev = "critical", cloud = "all" },
    { name = "ACME - Root login", type = "audit_event", sev = "critical", cloud = "aws" },
    { name = "ACME - GKE public endpoint", type = "config", sev = "medium", cloud = "gcp" },
  ]
  custom_live = slice(local.custom_policy_catalogue, 0, 4 + floor((local.day % 6) / 3))
  policy_lines = [for i, p in local.custom_live : {
    "@timestamp"      = local.now_rfc3339
    report            = "policies"
    tenant            = var.tenant_label
    policy_id         = "custom-${i + 1}-${substr(sha256(p.name), 0, 8)}"
    name              = p.name
    policy_type       = p.type
    policy_subtypes   = [p.type == "config" ? "run" : "run_and_build"]
    severity          = p.sev
    cloud_type        = p.cloud
    enabled           = !(i == 2 && (local.run % 30) < 4)
    system_default    = false
    remediable        = i % 2 == 0
    policy_mode       = "custom"
    open_alerts_count = (parseint(substr(sha256("${var.seed}-pol-${i}-${floor(local.run / 3)}"), 0, 4), 16) % 25) + i * 3
    labels            = ["acme"]
  }]

  # --- alert rules ---
  alert_rule_lines = [for i, r in [
    { name = "Production - critical & high", policies = 212, owner = "alice.admin@acme.example" },
    { name = "All accounts - compliance weekly", policies = 480, owner = "bob.secops@acme.example" },
    { name = "Sandbox - informational", policies = 30, owner = "dave.devops@acme.example" },
  ] : {
    "@timestamp"      = local.now_rfc3339
    report            = "alert_rules"
    tenant            = var.tenant_label
    rule_id           = "rule-${i + 1}"
    name              = r.name
    enabled           = !(i == 2 && (local.run % 50) < 10)
    scan_all          = i == 1
    policies_count    = r.policies + (i == 0 ? (local.day % 3) : 0)
    open_alerts_count = 40 + i * 55 + (parseint(substr(sha256("${var.seed}-rule-${i}-${local.run}"), 0, 4), 16) % 15)
    owner             = r.owner
    read_only         = false
  }]

  # --- integrations ---
  integration_lines = [for i, g in [
    { name = "SecOps Slack", type = "slack" },
    { name = "Splunk HEC", type = "splunk" },
    { name = "ServiceNow ITSM", type = "service_now" },
  ] : {
    "@timestamp"     = local.now_rfc3339
    report           = "integrations"
    tenant           = var.tenant_label
    integration_id   = "int-${i + 1}"
    name             = g.name
    integration_type = g.type
    enabled          = true
    status           = (i == 1 && (local.run % 36) < 5) ? "error" : "ok"
    valid            = !(i == 1 && (local.run % 36) < 5)
  }]

  # --- counts that wander run to run ---
  noise_open  = parseint(substr(sha256("${var.seed}-open-${floor(local.run / 2)}"), 0, 4), 16) % 61
  alerts_open = 280 + local.noise_open + (local.day % 9) * 7
  resolved_7d = (local.run % 50) < 20 ? 0 : 14 + (local.run % 7)

  purchased        = 2000
  usage_total      = length(local.account_lines) > 0 ? sum([for a in local.account_lines : a.license_workloads]) : 0
  resources_total  = length(local.account_lines) > 0 ? sum([for a in local.account_lines : a.resources_total]) : 0
  resources_failed = length(local.account_lines) > 0 ? sum([for a in local.account_lines : a.resources_failed]) : 0

  count_by = {
    cloud = { for k, v in { for a in local.account_lines : a.cloud_type => a... } : k => length(v) }
  }

  license_points = [for d in range(30) : {
    ts_ms = (local.day - 29 + d) * local.ms_per_day
    total = 1050 + d * 4 + (parseint(substr(sha256("${var.seed}-lic-${local.day - 29 + d}"), 0, 4), 16) % 40)
    by_cloud_type = {
      aws   = 600 + d * 2
      azure = 300 + d
      gcp   = 150 + d
    }
  }]

  users_active_7d  = length([for u in local.human_users : u if u.login_bucket == "7d"])
  users_active_30d = length([for u in local.human_users : u if contains(["7d", "30d"], u.login_bucket)])
  users_active_90d = length([for u in local.human_users : u if contains(["7d", "30d", "90d"], u.login_bucket)])

  util_pct = 100 * local.usage_total / local.purchased

  risk_components = {
    no_human_login_30d      = local.users_active_30d == 0 ? 30 : 0
    single_active_user_30d  = local.users_active_30d == 1 ? 15 : 0
    accounts_disabled       = length([for a in local.account_lines : a if !a.enabled]) > 0 ? 10 : 0
    integrations_broken     = length([for g in local.integration_lines : g if !g.valid]) > 0 ? 10 : 0
    no_alert_rules          = length([for r in local.alert_rule_lines : r if r.enabled]) == 0 ? 15 : 0
    alerts_open_no_activity = (local.alerts_open > 0 && local.resolved_7d == 0) ? 10 : 0
    license_utilization_low = local.util_pct < 25 ? 10 : 0
  }
  adoption_components = {
    all_accounts_healthy      = length([for a in local.account_lines : a if !a.enabled || a.status != "ok"]) == 0 ? 10 : 0
    multi_cloud               = 5
    integration_valid         = length([for g in local.integration_lines : g if g.valid]) > 0 ? 15 : 0
    alert_rule_enabled        = 15
    custom_policy             = 10
    custom_compliance         = 5
    saved_search              = 5
    scheduled_report          = 5
    two_active_users_30d      = local.users_active_30d >= 2 ? 15 : 0
    audit_or_siem_enabled     = 5
    license_utilization_50pct = local.util_pct >= 50 ? 10 : 0
  }

  summary = {
    "@timestamp"   = local.now_rfc3339
    report         = "summary"
    schema_version = 1
    tenant         = var.tenant_label
    run = {
      epoch_ms              = local.now_epoch_ms
      interval_hint_seconds = var.interval_hint_seconds
      terraform_module      = "terraform-mock"
      provider              = "synthetic"
      api_url               = var.prismacloud_url
      customer_name         = var.prismacloud_customer_name
      api_enrichment        = var.api_enrichment
      api_status            = { cloud_accounts = 200, inventory = 200, inventory_by_account = 200, license_usage = 200, license_time_series = 200, credit_summary = 200, alerts_by_severity = 200, alerts_by_policy_type = 200, alerts_by_policy = 200, audit_log = 200 }
      pseudonymized_users   = var.pseudonymize_users
    }
    cloud_accounts = {
      total                 = length(local.account_lines)
      enabled               = length([for a in local.account_lines : a if a.enabled])
      disabled              = length([for a in local.account_lines : a if !a.enabled])
      by_cloud_type         = local.count_by.cloud
      enabled_by_cloud_type = { for k, v in { for a in local.account_lines : a.cloud_type => a... if a.enabled } : k => length(v) }
      by_account_type       = { for k, v in { for a in local.account_lines : a.account_type => a... } : k => length(v) }
      by_status             = { for k, v in { for a in local.account_lines : a.status => a... } : k => length(v) }
      by_protection_mode    = { for k, v in { for a in local.account_lines : a.protection_mode => a... } : k => length(v) }
      child_accounts_total  = sum([for a in local.account_lines : a.number_of_child_accounts])
      storage_scan_enabled  = length([for a in local.account_lines : a if a.storage_scan_enabled])
      added_last_30d        = length([for a in local.account_lines : a if a.added_on_ms > local.now_epoch_ms - 30 * local.ms_per_day])
      ungrouped             = length([for a in local.account_lines : a if !a.in_account_group])
      with_inventory        = length(local.account_lines)
      resources_total       = local.resources_total
    }
    account_groups = { total = 3, auto_created = 1, with_alert_rules = 2 }
    users = {
      total                       = length(local.users)
      enabled                     = length([for u in local.users : u if u.enabled])
      disabled                    = length([for u in local.users : u if !u.enabled])
      service_accounts            = length([for u in local.users : u if u.account_type == "SERVICE_ACCOUNT"])
      human_total                 = length(local.human_users)
      human_enabled               = length([for u in local.human_users : u if u.enabled])
      human_active_7d             = local.users_active_7d
      human_active_30d            = local.users_active_30d
      human_active_90d            = local.users_active_90d
      human_inactive_90d_plus     = length([for u in local.human_users : u if u.login_bucket == "90d_plus"])
      human_never_logged_in       = length([for u in local.human_users : u if u.login_bucket == "never"])
      admins                      = length([for u in local.users : u if u.is_admin])
      days_since_last_human_login = length(local.human_login_ts) > 0 ? max(0, (local.now_epoch_ms - max(local.human_login_ts...)) / local.ms_per_day) : null
      by_login_bucket             = { for b in ["7d", "30d", "90d", "90d_plus", "never"] : b => length([for u in local.human_users : u if u.login_bucket == b]) }
      by_account_type             = { for k, v in { for u in local.users : lower(u.account_type) => u... } : k => length(v) }
      by_default_role_type        = { for k, v in { for u in local.users : u.default_role_type => u... } : k => length(v) }
    }
    roles             = { total = 9, custom = 1, by_role_type = { "System Admin" = 1, "Account Group Admin" = 1, "Account Group Read Only" = 1, "Developer" = 1, "Build and Deploy Security" = 1, "Cloud Provisioning Admin" = 1, "NetSecOps" = 1, "Account and Cloud Provisioning Admin" = 1, "ACME FinOps" = 1 } }
    permission_groups = { total = 12, custom = 1 }
    policies = {
      total                  = 1320
      enabled                = 905 + (local.day % 4)
      disabled               = 415 - (local.day % 4)
      custom                 = length(local.policy_lines)
      custom_enabled         = length([for p in local.policy_lines : p if p.enabled])
      system_default         = 1320 - length(local.policy_lines)
      system_default_enabled = 901
      remediable_enabled     = 388
      with_open_alerts       = 61 + (local.run % 5)
      open_alerts_sum        = local.alerts_open
      enabled_by_severity    = { critical = 48, high = 312, medium = 401, low = 120, informational = 24 }
      enabled_by_type        = { config = 744, network = 61, audit_event = 58, anomaly = 22, iam = 10, data = 6, workload_vulnerability = 4 }
      enabled_by_cloud_type  = { aws = 411, azure = 262, gcp = 168, oci = 22, alibaba_cloud = 12, all = 30 }
      custom_by_type         = { for k, v in { for p in local.policy_lines : p.policy_type => p... } : k => length(v) }
    }
    alert_rules = {
      total                 = length(local.alert_rule_lines)
      enabled               = length([for r in local.alert_rule_lines : r if r.enabled])
      disabled              = length([for r in local.alert_rule_lines : r if !r.enabled])
      scan_all              = 1
      with_open_alerts      = 3
      policies_attached_sum = sum([for r in local.alert_rule_lines : r.policies_count])
      open_alerts_sum       = sum([for r in local.alert_rule_lines : r.open_alerts_count])
    }
    alerts = {
      opened_24h          = 6 + (local.run % 9)
      opened_7d           = 61 + (local.run % 20)
      resolved_7d         = local.resolved_7d
      dismissed_7d        = 3 + (local.run % 4)
      snoozed_7d          = 1
      open                = local.alerts_open
      open_policies       = 64
      open_by_severity    = { critical = floor(local.alerts_open * 0.06), high = floor(local.alerts_open * 0.3), medium = floor(local.alerts_open * 0.44), low = floor(local.alerts_open * 0.17), informational = floor(local.alerts_open * 0.03) }
      open_by_policy_type = { config = floor(local.alerts_open * 0.82), network = floor(local.alerts_open * 0.08), audit_event = floor(local.alerts_open * 0.06), anomaly = floor(local.alerts_open * 0.04) }
      top_policies = [
        { policy_id = "p1", policy_name = "AWS S3 bucket publicly readable", severity = "high", policy_type = "config", cloud_type = "aws", alert_count = 38 + (local.run % 6), remediable = true },
        { policy_id = "p2", policy_name = "Azure storage account logging disabled", severity = "medium", policy_type = "config", cloud_type = "azure", alert_count = 31, remediable = true },
        { policy_id = "p3", policy_name = "GCP VM instance with public IP", severity = "medium", policy_type = "config", cloud_type = "gcp", alert_count = 24, remediable = false },
        { policy_id = "p4", policy_name = "AWS security group allows all traffic on SSH", severity = "high", policy_type = "config", cloud_type = "aws", alert_count = 19, remediable = true },
        { policy_id = "p5", policy_name = "ACME - Egress to sanctioned country", severity = "critical", policy_type = "network", cloud_type = "all", alert_count = 4 + (local.run % 3), remediable = false },
      ]
    }
    integrations = {
      total     = length(local.integration_lines)
      enabled   = length(local.integration_lines)
      disabled  = 0
      valid     = length([for g in local.integration_lines : g if g.valid])
      invalid   = length([for g in local.integration_lines : g if !g.valid])
      by_type   = { for k, v in { for g in local.integration_lines : g.integration_type => g... } : k => length(v) }
      by_status = { for k, v in { for g in local.integration_lines : g.status => g... } : k => length(v) }
    }
    notification_templates = { total = 1, enabled = 1 }
    compliance_standards   = { total = 46, custom = 1, system_default = 45, custom_policies_assigned_sum = 24 }
    reports                = { total = 2, by_type = { compliance = 1, inventory_overview = 1 }, by_status = { ready = 2 } }
    saved_searches         = { saved = 7, recent = 40 + (local.run % 10) }
    resource_lists         = { total = 2, by_type = { tag = 2 } }
    collections            = { total = 0 }
    trusted_ips            = { login_allowlists = 1, alert_allowlists = 0 }
    enterprise_settings = {
      session_timeout_minutes              = 60
      access_key_max_validity_days         = 90
      audit_logs_enabled                   = true
      apply_default_policies_enabled       = true
      require_alert_dismissal_note         = true
      user_attribution_in_notification     = false
      alarm_enabled                        = true
      audit_log_siem_integrations          = 1
      default_policies_enabled_by_severity = { critical = true, high = true, medium = true, low = false, informational = false }
    }
    anomaly_settings = { network_policies = 0, ueba_policies = 0 }
    inventory = {
      timestamp_ms        = local.now_epoch_ms - 1800000
      total_resources     = local.resources_total
      passed_resources    = local.resources_total - local.resources_failed
      failed_resources    = local.resources_failed
      unscanned_resources = 12
      pass_rate_pct       = 100 * (local.resources_total - local.resources_failed) / local.resources_total
      failed_by_severity  = { critical = floor(local.resources_failed * 0.05), high = floor(local.resources_failed * 0.25), medium = floor(local.resources_failed * 0.45), low = floor(local.resources_failed * 0.2), informational = floor(local.resources_failed * 0.05) }
      vulnerable_by_severity = { critical = 3, high = 21, medium = 77, low = 140 }
      by_cloud_type = {
        for ct, accs in { for a in local.account_lines : a.cloud_type => a... } :
        ct => {
          total_resources     = sum([for a in accs : a.resources_total])
          passed_resources    = sum([for a in accs : a.resources_total - a.resources_failed])
          failed_resources    = sum([for a in accs : a.resources_failed])
          unscanned_resources = 0
        }
      }
    }
    license = {
      available_as_of_ms     = local.now_epoch_ms - 3600000
      plan_type              = "ENTERPRISE"
      workloads_purchased    = local.purchased
      usage_total            = local.usage_total
      usage_window_days      = 7
      utilization_pct        = local.util_pct
      usage_by_cloud_type    = { for ct, accs in { for a in local.account_lines : a.cloud_type => a... } : ct => sum([for a in accs : a.license_workloads]) }
      usage_by_resource_type = { vm = floor(local.usage_total * 0.5), serverless = floor(local.usage_total * 0.1), container = floor(local.usage_total * 0.25), paas = floor(local.usage_total * 0.1), iam = floor(local.usage_total * 0.05) }
      accounts_reported      = length(local.account_lines)
      credits                = { purchased = 2000, used = local.usage_total, utilization_pct = local.util_pct }
      trend = {
        days        = 30
        points      = 30
        first_total = local.license_points[0].total
        last_total  = local.license_points[29].total
        change_pct  = 100 * (local.license_points[29].total - local.license_points[0].total) / local.license_points[0].total
        time_unit   = "day"
      }
      time_series = local.license_points
    }
    activity = {
      window_hours         = 24
      events_total         = 140 + (local.run % 30)
      logins               = 9 + (local.run % 5)
      failed_events        = local.run % 3
      distinct_users       = 5 + (local.run % 3)
      distinct_login_users = 4 + (local.run % 2)
      by_action_type       = { login = 9 + (local.run % 5), read = 110 + (local.run % 20), update = 14, create = 4, delete = 1 + (local.run % 2) }
      events_by_user       = { "alice.admin@acme.example" = 61, "svc-terraform" = 48, "bob.secops@acme.example" = 22, "carol.cloud@acme.example" = 9 }
    }
    scores = {
      adoption_score            = min(100, floor(sum(values(local.adoption_components)) + 0.5))
      adoption_points_by_signal = local.adoption_components
      risk_score                = min(100, sum(values(local.risk_components)))
      risk_points_by_signal     = local.risk_components
      risk_flags                = sort([for k, v in local.risk_components : k if v > 0])
    }
  }

  reports_dir = startswith(var.reports_dir, "/") ? var.reports_dir : abspath("${path.module}/${var.reports_dir}")

  jsonl = {
    cloud_accounts = "${join("\n", [for l in local.account_lines : jsonencode(l)])}\n"
    users          = "${join("\n", [for l in local.users : jsonencode(l)])}\n"
    policies       = "${join("\n", [for l in local.policy_lines : jsonencode(l)])}\n"
    alert_rules    = "${join("\n", [for l in local.alert_rule_lines : jsonencode(l)])}\n"
    integrations   = "${join("\n", [for l in local.integration_lines : jsonencode(l)])}\n"
  }
}

resource "local_sensitive_file" "summary" {
  filename             = "${local.reports_dir}/prisma_summary.json"
  content              = "${jsonencode(local.summary)}\n"
  file_permission      = var.file_permission
  directory_permission = "0755"
}

resource "local_sensitive_file" "cloud_accounts" {
  filename             = "${local.reports_dir}/prisma_cloud_accounts.jsonl"
  content              = local.jsonl.cloud_accounts
  file_permission      = var.file_permission
  directory_permission = "0755"
}

resource "local_sensitive_file" "users" {
  filename             = "${local.reports_dir}/prisma_users.jsonl"
  content              = local.jsonl.users
  file_permission      = var.file_permission
  directory_permission = "0755"
}

resource "local_sensitive_file" "policies" {
  filename             = "${local.reports_dir}/prisma_policies.jsonl"
  content              = local.jsonl.policies
  file_permission      = var.file_permission
  directory_permission = "0755"
}

resource "local_sensitive_file" "alert_rules" {
  filename             = "${local.reports_dir}/prisma_alert_rules.jsonl"
  content              = local.jsonl.alert_rules
  file_permission      = var.file_permission
  directory_permission = "0755"
}

resource "local_sensitive_file" "integrations" {
  filename             = "${local.reports_dir}/prisma_integrations.jsonl"
  content              = local.jsonl.integrations
  file_permission      = var.file_permission
  directory_permission = "0755"
}

output "snapshot" {
  value = {
    timestamp        = local.now_rfc3339
    run              = local.run
    cloud_accounts   = length(local.account_lines)
    users_active_30d = local.users_active_30d
    alerts_open      = local.alerts_open
    license_usage    = local.usage_total
    risk_flags       = local.summary.scores.risk_flags
  }
}
