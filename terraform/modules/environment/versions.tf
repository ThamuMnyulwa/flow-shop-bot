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
}
