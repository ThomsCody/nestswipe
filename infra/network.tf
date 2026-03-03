# --- VCN ---

resource "oci_core_vcn" "nestswipe" {
  compartment_id = var.compartment_ocid
  cidr_blocks    = ["10.0.0.0/16"]
  display_name   = "nestswipe-vcn"
  dns_label      = "nestswipe"
}

# --- Internet Gateway ---

resource "oci_core_internet_gateway" "nestswipe" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.nestswipe.id
  display_name   = "nestswipe-igw"
  enabled        = true
}

# --- Route Table ---

resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.nestswipe.id
  display_name   = "nestswipe-public-rt"

  route_rules {
    network_entity_id = oci_core_internet_gateway.nestswipe.id
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
  }
}

# --- Security List ---

resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.nestswipe.id
  display_name   = "nestswipe-public-sl"

  # Allow all egress
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    stateless   = false
  }

  # SSH
  ingress_security_rules {
    protocol  = "6" # TCP
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 22
      max = 22
    }
  }

  # HTTP
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 80
      max = 80
    }
  }

  # HTTPS
  ingress_security_rules {
    protocol  = "6"
    source    = "0.0.0.0/0"
    stateless = false
    tcp_options {
      min = 443
      max = 443
    }
  }

  # ICMP (for path MTU discovery)
  ingress_security_rules {
    protocol  = "1" # ICMP
    source    = "0.0.0.0/0"
    stateless = false
    icmp_options {
      type = 3
      code = 4
    }
  }
}

# --- Public Subnet ---

resource "oci_core_subnet" "public" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.nestswipe.id
  cidr_block                 = "10.0.1.0/24"
  display_name               = "nestswipe-public-subnet"
  dns_label                  = "pub"
  route_table_id             = oci_core_route_table.public.id
  security_list_ids          = [oci_core_security_list.public.id]
  prohibit_public_ip_on_vnic = false
}
