############################################
# Prisma Cloud connection
############################################

variable "prismacloud_url" {
  description = "Prisma Cloud API host WITHOUT protocol (console app.* -> api.*), e.g. api.prismacloud.io, api2.eu.prismacloud.io. Env: PRISMACLOUD_URL / TF_VAR_prismacloud_url."
  type        = string

  validation {
    condition     = !startswith(var.prismacloud_url, "http://") && !startswith(var.prismacloud_url, "https://")
    error_message = "prismacloud_url must be a bare host name (api.prismacloud.io), not a URL."
  }
}

variable "prismacloud_username" {
  description = "Prisma Cloud access key ID."
  type        = string
  sensitive   = true
}

variable "prismacloud_password" {
  description = "Prisma Cloud secret key."
  type        = string
  sensitive   = true
}

variable "prismacloud_customer_name" {
  description = "Tenant / customer name. Only needed when the access key can see several tenants."
  type        = string
  default     = null
}

variable "tenant_label" {
  description = "Free-form label stamped on every report line (becomes the `tenant` label in Loki/Prometheus). Use the customer name."
  type        = string
  default     = "prisma-cloud"
}

variable "provider_timeout" {
  description = "Per-request timeout (seconds) for the prismacloud provider."
  type        = number
  default     = 180
}

variable "provider_max_retries" {
  description = "How many 429 retries the prismacloud provider may spend PER RUN (the SDK decrements a shared counter). Raise for large tenants."
  type        = number
  default     = 40
}

variable "provider_retry_max_delay" {
  description = "Upper bound (seconds) for the provider's exponential back-off between retries."
  type        = number
  default     = 64
}

############################################
# Output
############################################

variable "reports_dir" {
  description = "Directory that receives the JSON reports. Relative paths are resolved against this module."
  type        = string
  default     = "../reports"
}

variable "file_permission" {
  description = "Mode for the generated report files."
  type        = string
  default     = "0644"
}

variable "interval_hint_seconds" {
  description = "How often the scheduler runs this module. Only recorded in the summary (used by the dashboards to judge staleness)."
  type        = number
  default     = 300
}

############################################
# What to collect
############################################

variable "collect" {
  description = "Toggle individual provider data sources. Everything defaults to on except APIs that are not present on every tenant."
  type = object({
    users                  = optional(bool, true)
    roles                  = optional(bool, true)
    permission_groups      = optional(bool, true)
    policies               = optional(bool, true)
    alert_rules            = optional(bool, true)
    alerts                 = optional(bool, true)
    integrations           = optional(bool, true)
    notification_templates = optional(bool, true)
    compliance             = optional(bool, true)
    reports                = optional(bool, true)
    saved_searches         = optional(bool, true)
    resource_lists         = optional(bool, true)
    trusted_ips            = optional(bool, true)
    enterprise_settings    = optional(bool, true)
    collections            = optional(bool, false) # /entitlement/api/v1/collection - newer tenants only
    anomaly_settings       = optional(bool, false) # Network + UEBA anomaly policies (2 extra calls)
  })
  default = {}
}

variable "api_enrichment" {
  description = <<-EOT
    Also call the Prisma Cloud REST API directly (hashicorp/http) for data the
    Terraform provider does not expose: cloud account health (/cloud), asset
    inventory (/v3/inventory), licence usage & credits (/license/api/*), open
    alerts by severity/type (/alert/v1/*) and audit-log activity (/audit/redlock).
    Turn off to run with the prismacloud provider only.
  EOT
  type        = bool
  default     = true
}

variable "license_usage_days" {
  description = "Averaging window (days) for the current licence usage snapshot."
  type        = number
  default     = 7
}

variable "license_trend_days" {
  description = "How many days of daily licence usage history to pull for the trend."
  type        = number
  default     = 30
}

variable "activity_window_hours" {
  description = "Audit-log look-back window (hours) for the activity section."
  type        = number
  default     = 24
}

variable "top_n" {
  description = "Size of top-N lists (alert-generating policies, most active users)."
  type        = number
  default     = 15
}

variable "pseudonymize_users" {
  description = "Replace user names / e-mails with a short SHA-256 prefix in every report."
  type        = bool
  default     = false
}

############################################
# Scoring (post-sales health heuristics)
############################################

variable "adoption_weights" {
  description = "Points awarded per adoption signal (sums to 100 by default). Edit to match your success-plan."
  type = object({
    all_accounts_healthy      = optional(number, 10)
    multi_cloud               = optional(number, 5)
    integration_valid         = optional(number, 15)
    alert_rule_enabled        = optional(number, 15)
    custom_policy             = optional(number, 10)
    custom_compliance         = optional(number, 5)
    saved_search              = optional(number, 5)
    scheduled_report          = optional(number, 5)
    two_active_users_30d      = optional(number, 15)
    audit_or_siem_enabled     = optional(number, 5)
    license_utilization_50pct = optional(number, 10)
  })
  default = {}
}

variable "risk_weights" {
  description = "Points added per churn-risk signal (0 = healthy, 100 = maximum risk)."
  type = object({
    no_human_login_30d      = optional(number, 30)
    single_active_user_30d  = optional(number, 15)
    accounts_disabled       = optional(number, 10)
    integrations_broken     = optional(number, 10)
    no_alert_rules          = optional(number, 15)
    alerts_open_no_activity = optional(number, 10)
    license_utilization_low = optional(number, 10)
  })
  default = {}
}
