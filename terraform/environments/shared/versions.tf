terraform {
  required_version = "~> 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
  }

  # State stays on this machine (git-ignored). Move to a GCS backend once more than one person runs Terraform.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Sign in once with: gcloud auth application-default login
provider "google" {
  project = var.project_id
  region  = var.region
}
