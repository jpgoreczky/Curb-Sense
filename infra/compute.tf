data "oci_core_images" "ubuntu_arm" {
  compartment_id           = oci_identity_compartment.app.id
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "22.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}


resource "oci_core_instance" "prod" {
  compartment_id      = oci_identity_compartment.app.id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "curb-sense-prod"
  shape                = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.main.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPna2OVmjuI/xUtWyAbmr/W74gaU5sEkUp6XcVVSJBNy curb-sense-infra"
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }
}

resource "oci_core_instance" "staging" {
  compartment_id      = oci_identity_compartment.app.id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "curb-sense-staging"
  shape                = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = 1
    memory_in_gbs = 6
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.main.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPna2OVmjuI/xUtWyAbmr/W74gaU5sEkUp6XcVVSJBNy curb-sense-infra"
    user_data           = base64encode(file("${path.module}/cloud-init.yaml"))
  }
}

data "oci_identity_availability_domains" "ads" {
  compartment_id = oci_identity_compartment.app.id
}