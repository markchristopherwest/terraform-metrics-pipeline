############################################################################
# Read-only inventory through the PaloAltoNetworks/prismacloud provider.
# Every block here is a data source: nothing in the tenant is ever changed.
# Each is wrapped in try() in locals.tf so a disabled block yields [] / null.
############################################################################

# --- Footprint ------------------------------------------------------------

data "prismacloud_cloud_accounts" "all" {}

data "prismacloud_account_groups" "all" {}

# --- People & access ------------------------------------------------------

data "prismacloud_user_profiles" "all" {
  count = var.collect.users ? 1 : 0
}

data "prismacloud_user_roles" "all" {
  count = var.collect.roles ? 1 : 0
}

data "prismacloud_permission_groups" "all" {
  count = var.collect.permission_groups ? 1 : 0
}

# --- Detection content ----------------------------------------------------

data "prismacloud_policies" "all" {
  count = var.collect.policies ? 1 : 0
  # No filters: we want the whole catalogue (enabled + disabled, default + custom).
}

data "prismacloud_alert_rules" "all" {
  count = var.collect.alert_rules ? 1 : 0
}

# Cheap alert-volume windows: limit = 1 keeps the payload tiny, `total`
# still carries the server-side totalRows for the filter/time-range.
data "prismacloud_alerts" "windows" {
  for_each = var.collect.alerts ? local.alert_windows : {}

  limit = 1

  time_range {
    relative {
      amount = each.value.amount
      unit   = each.value.unit
    }
  }

  filters {
    name  = "alert.status"
    value = each.value.status
  }
}

# --- Operational wiring ---------------------------------------------------

data "prismacloud_integrations" "all" {
  count = var.collect.integrations ? 1 : 0
}

data "prismacloud_notification_templates" "all" {
  count = var.collect.notification_templates ? 1 : 0
}

data "prismacloud_compliance_standards" "all" {
  count = var.collect.compliance ? 1 : 0
}

data "prismacloud_reports" "all" {
  count = var.collect.reports ? 1 : 0
}

data "prismacloud_rql_historic_searches" "saved" {
  count  = var.collect.saved_searches ? 1 : 0
  filter = "saved"
  limit  = 1000
}

data "prismacloud_rql_historic_searches" "recent" {
  count  = var.collect.saved_searches ? 1 : 0
  filter = "recent"
  limit  = 1000
}

data "prismacloud_resource_lists" "all" {
  count = var.collect.resource_lists ? 1 : 0
}

data "prismacloud_collections" "all" {
  count = var.collect.collections ? 1 : 0
}

data "prismacloud_trusted_login_ips" "all" {
  count = var.collect.trusted_ips ? 1 : 0
}

data "prismacloud_trusted_alert_ips" "all" {
  count = var.collect.trusted_ips ? 1 : 0
}

data "prismacloud_enterprise_settings" "current" {
  count = var.collect.enterprise_settings ? 1 : 0
}

data "prismacloud_anomaly_settings" "network" {
  count = var.collect.anomaly_settings ? 1 : 0
  type  = "Network"
}

data "prismacloud_anomaly_settings" "ueba" {
  count = var.collect.anomaly_settings ? 1 : 0
  type  = "UEBA"
}
