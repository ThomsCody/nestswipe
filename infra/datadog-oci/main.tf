terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 8.1"
    }
  }
}

provider "oci" {
  config_file_profile = "DEFAULT"
  region              = "eu-paris-1"
}

variable "datadog_api_key" {
  description = "Datadog API key for ThomasDogFooding; supply through TF_VAR_datadog_api_key."
  type        = string
  sensitive   = true
}

variable "datadog_app_key" {
  description = "Datadog application key; supply through TF_VAR_datadog_app_key."
  type        = string
  sensitive   = true
}

module "datadog_oci" {
  # Published datadog-integration-v1.2.7 release, pinned to its immutable commit.
  source = "github.com/DataDog/oracle-cloud-integration//datadog-terraform-onboarding?ref=868f6db4251c1519e34c7c0f7505d9ef8d06c054"

  datadog_api_key = var.datadog_api_key
  datadog_app_key = var.datadog_app_key
  datadog_site    = "datadoghq.com"

  tenancy_ocid      = "ocid1.tenancy.oc1..aaaaaaaaf6usbj2lrvramp56lnuo6kgx7kipzegvkpwkrsp42z36k7gd3usq"
  current_user_ocid = "ocid1.user.oc1..aaaaaaaav5y4i3yorb5s4ftrq3jx4j24hf7p3elhejmsfvrtkmktses5xvga"

  config_file_profile       = "DEFAULT"
  logs_enabled              = true
  events_collection_enabled = true
  enable_regional_vaults    = true
}
