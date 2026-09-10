variable "tenancy_ocid" {
  description = "OCID of the curb-sense tenancy (root compartment)."
  type        = string
}

variable "compartment_name" {
  description = "Name of the compartment holding all Curb Sense app resources."
  type        = string
  default     = "curb-sense-app"
}