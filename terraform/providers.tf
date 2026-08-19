provider "prismacloud" {
  url           = var.prismacloud_url
  username      = var.prismacloud_username
  password      = var.prismacloud_password
  customer_name = var.prismacloud_customer_name

  # Read-only inventory every few minutes: be generous with 429 handling.
  timeout         = var.provider_timeout
  max_retries     = var.provider_max_retries
  retry_max_delay = var.provider_retry_max_delay
  retry_type      = "exponential_backoff"
}

# hashicorp/local and hashicorp/http need no configuration.
