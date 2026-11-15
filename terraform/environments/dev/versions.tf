terraform {
  required_version = "~> 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.18"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State stays on this machine, one file per environment, never committed: it holds secrets.
  # Move to a GCS backend once more than one person runs Terraform.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Credentials come from your machine, never from files in git:
#   gcloud auth application-default login     (Google Cloud)
#   export NEON_API_KEY=...                   (Neon console → Account settings → API keys)
provider "google" {
  project = var.project_id
  region  = var.region
}

provider "neon" {}
