terraform {
  # plantimestamp() (>= 1.5) gives every report line the same, plan-time-known
  # timestamp, and optional() object attributes need >= 1.3.
  required_version = ">= 1.5.0"

  required_providers {
    prismacloud = {
      source  = "PaloAltoNetworks/prismacloud"
      version = "~> 1.7"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
    http = {
      source  = "hashicorp/http"
      version = "~> 3.4"
    }
  }

  # Local state. The scheduler container passes
  #   terraform init -backend-config="path=/var/lib/prisma-reports/terraform.tfstate"
  # so state lives on a Docker volume instead of inside the checkout.
  # NOTE: state contains the API access key/JWT captured by the http data
  # sources (see README > Security notes) - keep it private.
  backend "local" {}
}
