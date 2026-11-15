# One FLOWW shop environment on Google Cloud Run. Its database is a Neon project made in the Neon console;
# Terraform is given the connection string.
#
#   Neon (console) ──▶ DATABASE_URL secret ──▶ Cloud Run service (scales to zero) ◀── Cloud Scheduler (jobs)
#                                          └▶ Cloud Run job (migrations, once per deploy)
#   Cloud Storage bucket ◀── product photos and proof-of-payment files
#
# The container image is set by scripts/deploy.sh, not by Terraform: Terraform creates the service with a
# placeholder and then leaves the image alone.

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  # Cloud Run's address is predictable, so the service can be told its own URL before it exists.
  run_url  = "https://${var.name}-${data.google_project.this.number}.${var.region}.run.app"
  base_url = var.base_url != "" ? var.base_url : local.run_url

  placeholder_image = "us-docker.pkg.dev/cloudrun/container/hello"

  settings = merge(
    {
      FLOWSHOP_ENV               = var.environment
      FLOWSHOP_BASE_URL          = local.base_url
      FLOWSHOP_STORAGE_BACKEND   = "gcs"
      FLOWSHOP_GCS_BUCKET        = google_storage_bucket.files.name
      FLOWSHOP_MIGRATE_ON_START  = "false" # the migration job runs once per deploy instead
      FLOWSHOP_ALLOW_TIME_TRAVEL = tostring(var.allow_time_travel)
      FLOWSHOP_CORS_ORIGINS      = var.cors_origins
    },
    var.settings,
  )

  # Every secret becomes a Secret Manager secret and an environment variable of the same name.
  secret_values = merge(
    {
      FLOWSHOP_DATABASE_URL   = var.database_url
      FLOWSHOP_SECRET_KEY     = random_password.secret_key.result
      FLOWSHOP_JOBS_TOKEN     = random_password.jobs_token.result
      FLOWSHOP_ADMIN_PASSWORD = random_password.admin.result
    },
    var.secrets,
  )
  secret_names = toset(nonsensitive(keys(local.secret_values)))

  labels = {
    app         = "floww-shop"
    environment = var.environment == "production" ? "prod" : "dev"
  }
}

# ---------- secrets, generated once and kept in Terraform state ----------

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

resource "random_password" "jobs_token" {
  length  = 48
  special = false
}

resource "random_password" "admin" {
  length  = 24
  special = false
}

resource "google_secret_manager_secret" "this" {
  for_each = local.secret_names

  project   = var.project_id
  secret_id = "${var.name}-${lower(replace(each.key, "_", "-"))}"

  replication {
    auto {}
  }

  labels = local.labels
}

resource "google_secret_manager_secret_version" "this" {
  for_each = local.secret_names

  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = local.secret_values[each.key]
}

# ---------- identity: the service runs as its own account with only what it needs ----------

resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = var.name
  display_name = "FLOWW shop ${var.environment}"
}

resource "google_secret_manager_secret_iam_member" "runtime" {
  for_each = local.secret_names

  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

# ---------- files: product photos and proofs of payment ----------

resource "google_storage_bucket" "files" {
  project                     = var.project_id
  name                        = "${var.project_id}-${var.name}-files"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced" # photos are served through the app; proofs are staff-only
  force_destroy               = !var.deletion_protection

  labels = local.labels
}

resource "google_storage_bucket_iam_member" "runtime" {
  bucket = google_storage_bucket.files.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

# ---------- the web service ----------

resource "google_cloud_run_v2_service" "this" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  # Public without granting anything to allUsers: customers, the website and Meta's webhook must reach it,
  # and the app does its own sign-in for staff pages.
  invoker_iam_disabled = true

  template {
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 40
    timeout                          = "60s"

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = local.placeholder_image

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        cpu_idle          = true # request-based billing: CPU is only paid for while handling requests
        startup_cpu_boost = true # faster cold starts
      }

      dynamic "env" {
        for_each = local.settings
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_names
        content {
          name = env.value
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.this[env.value].secret_id
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 0
        period_seconds        = 2
        failure_threshold     = 15
        timeout_seconds       = 2
        http_get {
          path = "/healthz" # never touches the database, so probes don't keep Neon awake
        }
      }
    }
  }

  labels = local.labels

  depends_on = [google_secret_manager_secret_iam_member.runtime, google_secret_manager_secret_version.this]

  lifecycle {
    # scripts/deploy.sh owns the image; Terraform owns everything else.
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# ---------- migrations: a job that runs once per deploy, so cold starts stay fast ----------

resource "google_cloud_run_v2_job" "migrate" {
  project             = var.project_id
  name                = "${var.name}-migrate"
  location            = var.region
  deletion_protection = var.deletion_protection

  template {
    task_count = 1

    template {
      service_account = google_service_account.runtime.email
      max_retries     = 1
      timeout         = "600s"

      containers {
        image = local.placeholder_image
        # Dev also loads its sample data; prod never does (the seed command refuses in production anyway).
        args = ["sh", "-c", var.seed_on_deploy ? "flowshop migrate && flowshop seed" : "flowshop migrate"]

        env {
          name  = "FLOWSHOP_ENV"
          value = var.environment
        }

        dynamic "env" {
          for_each = toset(["FLOWSHOP_DATABASE_URL", "FLOWSHOP_ADMIN_PASSWORD"])
          content {
            name = env.value
            value_source {
              secret_key_ref {
                secret  = google_secret_manager_secret.this[env.value].secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  labels = local.labels

  depends_on = [google_secret_manager_secret_iam_member.runtime, google_secret_manager_secret_version.this]

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

# ---------- scheduled work: payment reminders and the 48-hour release (E12) ----------

resource "google_cloud_scheduler_job" "jobs" {
  project          = var.project_id
  region           = var.region
  name             = "${var.name}-jobs"
  schedule         = var.jobs_schedule
  time_zone        = "Africa/Johannesburg"
  attempt_deadline = "60s"

  http_target {
    http_method = "POST"
    uri         = "${local.run_url}/jobs/run"
    headers = {
      "X-Jobs-Token" = random_password.jobs_token.result
    }
  }

  retry_config {
    retry_count = 1
  }
}
