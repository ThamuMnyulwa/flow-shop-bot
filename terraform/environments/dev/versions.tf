terraform {
  required_version = "~> 1.9"

  required_providers {
    render = {
      source  = "render-oss/render"
      version = "~> 1.9"
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

  # State stays on this machine for now, one file per environment, and is never committed (it holds secrets).
  # To share it later, move to a remote backend such as Terraform Cloud or an S3/R2 bucket.
  backend "local" {
    path = "terraform.tfstate"
  }
}

# Credentials come from the environment, never from files in git:
#   RENDER_API_KEY, RENDER_OWNER_ID  (Render dashboard → Account settings → API keys)
#   NEON_API_KEY                     (Neon console → Account settings → API keys)
provider "render" {
  # Don't block `terraform apply` while Render builds; scripts/deploy.sh watches deploys instead.
  wait_for_deploy_completion = false
}

provider "neon" {}
