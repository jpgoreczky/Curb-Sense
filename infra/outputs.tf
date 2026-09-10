output "compartment_id" {
  value = oci_identity_compartment.app.id
}

output "prod_public_ip" {
  value = oci_core_instance.prod.public_ip
}

output "staging_public_ip" {
  value = oci_core_instance.staging.public_ip
}