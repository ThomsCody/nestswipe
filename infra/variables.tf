# --- OCI Authentication ---

variable "tenancy_ocid" {
  description = "OCID of the OCI tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the OCI user"
  type        = string
}

variable "compartment_ocid" {
  description = "OCID of the compartment (use tenancy OCID for root compartment)"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the OCI API signing key"
  type        = string
}

variable "private_key_path" {
  description = "Path to the OCI API private key PEM file"
  type        = string
}

variable "private_key_password" {
  description = "Passphrase for the OCI API private key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "region" {
  description = "OCI region identifier"
  type        = string
  default     = "eu-paris-1"
}

# --- SSH ---

variable "ssh_public_key_path" {
  description = "Path to the SSH public key for instance access"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

# --- Instance ---

variable "instance_ocpus" {
  description = "Number of OCPUs for the A1 Flex instance"
  type        = number
  default     = 4
}

variable "instance_memory_gb" {
  description = "Memory in GB for the A1 Flex instance"
  type        = number
  default     = 24
}

variable "instance_display_name" {
  description = "Display name for the compute instance"
  type        = string
  default     = "nestswipe"
}
