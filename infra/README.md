# Nestswipe Infrastructure — Oracle Cloud Always Free

Terraform configuration to provision an **A1 Flex** (4 OCPU / 24 GB) instance on Oracle Cloud's Always Free tier, with full networking (VCN, public subnet, internet gateway) and Docker pre-installed.

## Prerequisites

### 1. Install tools

```bash
brew install terraform oci-cli
```

### 2. Configure OCI CLI

```bash
oci setup config
```

This generates:
- `~/.oci/config` — CLI config file
- `~/.oci/oci_api_key.pem` — Private API signing key
- `~/.oci/oci_api_key_public.pem` — Public key to upload

### 3. Upload the API public key

1. Go to **OCI Console > Profile (top-right) > My profile > API Keys > Add API Key**
2. Choose **Paste a public key** and paste the contents of `~/.oci/oci_api_key_public.pem`
3. Note the **fingerprint** shown after uploading

### 4. Collect OCIDs

| Value | Where to find it |
|-------|-----------------|
| Tenancy OCID | Profile > Tenancy: \<name\> > OCID |
| User OCID | Profile > My profile > OCID |
| Compartment OCID | Use the Tenancy OCID (root compartment) |
| Fingerprint | Profile > My profile > API Keys |
| Region | `eu-paris-1` (visible in the console URL) |

### 5. Create your tfvars file

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your actual OCIDs and paths
```

## Usage

```bash
cd infra

# Initialize Terraform (downloads OCI provider)
terraform init

# Preview what will be created
terraform plan

# Apply — creates all resources
terraform apply

# Get the public IP
terraform output public_ip

# Connect
ssh ubuntu@$(terraform output -raw public_ip)

# Verify Docker is running (may take 2-3 minutes after instance boot)
ssh ubuntu@$(terraform output -raw public_ip) "docker --version"
```

## What gets provisioned

- **VCN** (10.0.0.0/16) with DNS
- **Public subnet** (10.0.1.0/24)
- **Internet gateway** + route table
- **Security list** — ingress on ports 22, 80, 443; all egress
- **A1 Flex instance** — 4 OCPU, 24 GB RAM, 50 GB boot volume, Ubuntu 22.04 ARM
- **Public IP** assigned to instance

The cloud-init script automatically installs Docker CE and Docker Compose plugin on first boot.

## Teardown

```bash
terraform destroy
```

## Troubleshooting

- **"Out of host capacity"**: A1 instances are in high demand. Retry later or reduce OCPU/memory.
- **SSH timeout**: Wait 2-3 minutes after `terraform apply` for cloud-init to complete. Check that your SSH key path in `terraform.tfvars` is correct.
- **Docker not found**: Cloud-init may still be running. Check with `sudo cloud-init status --wait`.
