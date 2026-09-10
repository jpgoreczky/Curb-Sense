resource "oci_identity_compartment" "app" {
  compartment_id = var.tenancy_ocid
  name           = var.compartment_name
  description    = "Curb Sense application resources (prod + staging compute, networking)."
  enable_delete  = true
}