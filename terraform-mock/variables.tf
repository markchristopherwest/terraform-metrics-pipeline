variable "tenant_label" {
  description = "Label stamped on every line (same role as in the real module)."
  type        = string
  default     = "demo-tenant"
}

variable "reports_dir" {
  description = "Where to write the reports (relative paths are anchored to this module)."
  type        = string
  default     = "../reports"
}

variable "interval_hint_seconds" {
  description = "Scheduler interval; also the 'run' granularity of the synthetic data."
  type        = number
  default     = 300
}

variable "seed" {
  description = "Changes the synthetic tenant entirely."
  type        = string
  default     = "prisma-demo"
}

variable "file_permission" {
  type    = string
  default = "0644"
}

# Accepted so the scheduler can pass the same TF_VAR_* set to both modules.
variable "prismacloud_url" {
  type    = string
  default = "api.mock.prismacloud.io"
}
variable "prismacloud_username" {
  type      = string
  default   = "mock"
  sensitive = true
}
variable "prismacloud_password" {
  type      = string
  default   = "mock"
  sensitive = true
}
variable "prismacloud_customer_name" {
  type    = string
  default = null
}
variable "api_enrichment" {
  type    = bool
  default = true
}
variable "pseudonymize_users" {
  type    = bool
  default = false
}
