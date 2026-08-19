############################################################################
# The deliverable: JSON files in var.reports_dir.
#
#   prisma_summary.json         one JSON object (single line) - tenant totals
#   prisma_cloud_accounts.jsonl one JSON object per cloud account
#   prisma_users.jsonl          one per user profile
#   prisma_policies.jsonl       one per CUSTOM policy
#   prisma_alert_rules.jsonl    one per alert rule
#   prisma_integrations.jsonl   one per integration
#
# Why local_sensitive_file instead of local_file: identical behaviour
# (delete + re-create on every content change) but Terraform redacts the
# content in plan/apply output. Every run rewrites every file (the
# "@timestamp" changes), so without redaction each apply would print the
# whole JSON twice per file into the scheduler logs.
#
# Every line ends with "\n" - tail-based shippers (Promtail / Alloy) only
# forward complete lines. "@timestamp" sorts first in jsonencode() output,
# so the first bytes of a file always differ between runs (Alloy compares a
# 1 KiB signature to decide whether a re-created file is "the same").
############################################################################

locals {
  # Relative paths are anchored to this module so `terraform -chdir=terraform apply`
  # and the container (which mounts the module at /terraform) behave the same.
  reports_dir = startswith(var.reports_dir, "/") ? var.reports_dir : abspath("${path.module}/${var.reports_dir}")

  # JSON Lines encoder: empty list -> empty file.
  jsonl = {
    cloud_accounts = length(local.account_lines) > 0 ? "${join("\n", [for l in local.account_lines : jsonencode(l)])}\n" : ""
    users          = length(local.users) > 0 ? "${join("\n", [for l in local.users : jsonencode(l)])}\n" : ""
    policies       = length(local.policy_lines) > 0 ? "${join("\n", [for l in local.policy_lines : jsonencode(l)])}\n" : ""
    alert_rules    = length(local.alert_rule_lines) > 0 ? "${join("\n", [for l in local.alert_rule_lines : jsonencode(l)])}\n" : ""
    integrations   = length(local.integration_lines) > 0 ? "${join("\n", [for l in local.integration_lines : jsonencode(l)])}\n" : ""
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
