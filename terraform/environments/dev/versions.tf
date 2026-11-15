terraform {
  required_version = "~> 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # State lives in the project's Terraform bucket, in its own folder per environment. It holds secrets, so only
  # people with access to that bucket can read it. Create the bucket first if a new project doesn't have one.
  backend "gcs" {
    bucket = "oceanhub-dev-tfstate"
    prefix = "floww-shop/dev"
  }
}

# Credentials come from your machine, never from files in git:
#   gcloud auth application-default login     (Google Cloud)
provider "google" {
  project = var.project_id
  region  = var.region
}
