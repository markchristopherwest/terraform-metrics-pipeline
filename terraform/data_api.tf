############################################################################
# Direct REST calls (hashicorp/http) for data the provider does not expose.
# All of them are optional (var.api_enrichment) and soft-fail: a non-200 or
# unparsable answer just leaves the matching summary section null, the run
# still succeeds. Only the login is a hard failure (bad credentials).
#
# Everything is a read (GET, or POST against read-only "search" endpoints).
############################################################################

locals {
  api_enabled = var.api_enrichment
  api_base    = "https://${trimsuffix(var.prismacloud_url, "/")}"

  api_json_headers = {
    "Content-Type" = "application/json"
    "Accept"       = "application/json; charset=UTF-8"
  }

  # JWT from POST /login (valid 10 minutes - plenty for one plan/apply).
  api_token = try(jsondecode(data.http.login[0].response_body).token, "")

  api_auth_headers = merge(local.api_json_headers, {
    "x-redlock-auth" = local.api_token
  })

  # Cloud types present in the tenant, lower-cased, for the licence queries.
  api_cloud_types = distinct([for a in local.raw_accounts : lower(a.cloud_type) if a.cloud_type != null && a.cloud_type != ""])
}

# --- Auth ------------------------------------------------------------------

data "http" "login" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/login"
  method = "POST"

  request_headers = local.api_json_headers
  # customerName only when set (null attributes are dropped by the filter)
  request_body = jsonencode({
    for k, v in {
      username     = var.prismacloud_username
      password     = var.prismacloud_password
      customerName = var.prismacloud_customer_name
    } : k => v if v != null
  })

  request_timeout_ms = 30000

  retry {
    attempts     = 3
    min_delay_ms = 1000
    max_delay_ms = 5000
  }

  lifecycle {
    postcondition {
      condition     = self.status_code == 200
      error_message = "Prisma Cloud login failed (HTTP ${self.status_code}). Check PRISMACLOUD_URL / access key / secret key / customer name."
    }
  }
}

# --- Cloud accounts (rich list view: enabled, status, protection mode ...) ---

data "http" "cloud_accounts" {
  count = local.api_enabled ? 1 : 0

  url                = "${local.api_base}/cloud?excludeAccountGroupDetails=false&includePendingAccounts=true"
  method             = "GET"
  request_headers    = local.api_auth_headers
  request_timeout_ms = 60000

  retry {
    attempts     = 2
    min_delay_ms = 1000
    max_delay_ms = 4000
  }
}

# --- Asset inventory (tenant summary grouped by cloud type, and by account) ---

data "http" "inventory" {
  count = local.api_enabled ? 1 : 0

  url                = "${local.api_base}/v3/inventory?groupBy=cloud.type"
  method             = "GET"
  request_headers    = local.api_auth_headers
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

data "http" "inventory_by_account" {
  count = local.api_enabled ? 1 : 0

  url                = "${local.api_base}/v3/inventory?groupBy=cloud.account"
  method             = "GET"
  request_headers    = local.api_auth_headers
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

# --- Licence usage (workloads / credits) ------------------------------------

data "http" "license_usage" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/license/api/v2/usage"
  method = "POST"

  request_headers = local.api_auth_headers
  request_body = jsonencode({
    accountIds = []
    cloudTypes = local.api_cloud_types
    timeRange = {
      type  = "relative"
      value = { amount = var.license_usage_days, unit = "day" }
    }
    limit  = 1000
    offset = 0
  })
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

data "http" "license_time_series" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/license/api/v2/time_series"
  method = "POST"

  request_headers = local.api_auth_headers
  request_body = jsonencode({
    accountIds = []
    cloudTypes = local.api_cloud_types
    timeRange = {
      type  = "relative"
      value = { amount = var.license_trend_days, unit = "day" }
    }
  })
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

# Credit-based licences only; returns 4xx elsewhere (soft-fail).
data "http" "credit_summary" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/license/api/v1/credit-allocation-rule-summary"
  method = "POST"

  request_headers = local.api_auth_headers
  request_body = jsonencode({
    timeRange = {
      type  = "relative"
      value = { amount = 1, unit = "month" }
    }
  })
  request_timeout_ms = 60000
}

# --- Open alerts by severity / policy type, and top alert-generating policies ---

locals {
  api_open_alert_filter = [{ name = "alert.status", operator = "=", value = "open" }]
  api_all_time          = { type = "to_now", value = "epoch" }
}

data "http" "alerts_by_severity" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/alert/v1/aggregate"
  method = "POST"

  request_headers = local.api_auth_headers
  request_body = jsonencode({
    groupBy   = "policy.severity"
    filters   = local.api_open_alert_filter
    timeRange = local.api_all_time
    size      = 50
  })
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

data "http" "alerts_by_policy_type" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/alert/v1/aggregate"
  method = "POST"

  request_headers = local.api_auth_headers
  request_body = jsonencode({
    groupBy   = "policy.type"
    filters   = local.api_open_alert_filter
    timeRange = local.api_all_time
    size      = 50
  })
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

data "http" "alerts_by_policy" {
  count = local.api_enabled ? 1 : 0

  url    = "${local.api_base}/alert/v1/policy"
  method = "POST"

  request_headers = local.api_auth_headers
  request_body = jsonencode({
    filters   = local.api_open_alert_filter
    timeRange = local.api_all_time
    size      = 200
  })
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}

# --- Audit log: is anybody actually using the console? ----------------------

data "http" "audit_log" {
  count = local.api_enabled ? 1 : 0

  url                = "${local.api_base}/audit/redlock?timeType=relative&timeAmount=${var.activity_window_hours}&timeUnit=hour"
  method             = "GET"
  request_headers    = local.api_auth_headers
  request_timeout_ms = 90000

  retry {
    attempts     = 2
    min_delay_ms = 2000
    max_delay_ms = 6000
  }
}
