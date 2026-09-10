terraform {
  required_version = ">= 1.7.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "oci" {
  # Reads auth details from ~/.oci/config (DEFAULT profile),
  # the same file `oci setup config` wrote in Step 3.
  # No credentials are hardcoded here or committed to the repo.
}