resource "oci_core_vcn" "main" {
  compartment_id = oci_identity_compartment.app.id
  cidr_block     = "10.0.0.0/16"
  display_name   = "curb-sense-vcn"
  dns_label      = "curbsense"
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = oci_identity_compartment.app.id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "curb-sense-igw"
  enabled        = true
}

resource "oci_core_route_table" "main" {
  compartment_id = oci_identity_compartment.app.id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "curb-sense-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

resource "oci_core_security_list" "main" {
  compartment_id = oci_identity_compartment.app.id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "curb-sense-seclist"

  # SSH access
  ingress_security_rules {
    protocol = "6" # TCP
    source   = "0.0.0.0/0"
    tcp_options {
      min = 22
      max = 22
    }
  }

  # Staging API port
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8001
      max = 8001
    }
  }

  # Prod API port
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options {
      min = 8000
      max = 8000
    }
  }

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_subnet" "main" {
  compartment_id             = oci_identity_compartment.app.id
  vcn_id                     = oci_core_vcn.main.id
  cidr_block                 = "10.0.1.0/24"
  display_name               = "curb-sense-subnet"
  dns_label                  = "curbsub"
  route_table_id             = oci_core_route_table.main.id
  security_list_ids          = [oci_core_security_list.main.id]
  prohibit_public_ip_on_vnic = false
}