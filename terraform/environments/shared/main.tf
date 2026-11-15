# What dev and prod share: the Google Cloud services they use, the image registry, and a budget alert.
# Apply this first, then environments/dev and environments/prod.

locals {
  services = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "billingbudgets.googleapis.com",
  ])
}

resource "google_project_service" "this" {
  for_each = local.services

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# One registry for both environments: dev builds an image once, and prod runs that same image.
resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = "floww-shop"
  format        = "DOCKER"
  labels        = { app = "floww-shop" }
  description   = "FLOWW shop images, tagged with the git commit"

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 15
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "2592000s" # 30 days, except the 15 most recent kept above
    }
  }

  depends_on = [google_project_service.this]
}

data "google_project" "this" {
  project_id = var.project_id
}

resource "google_billing_budget" "monthly" {
  count = var.billing_account == "" ? 0 : 1

  billing_account = var.billing_account
  display_name    = "FLOWW shop monthly"

  # The project also hosts other apps, so the budget counts only resources labelled app=floww-shop.
  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
    labels = {
      app = "floww-shop"
    }
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.9
  }
  threshold_rules {
    threshold_percent = 1.0
  }

  depends_on = [google_project_service.this]
}
