# Runs with mocked providers: no Google Cloud or Neon account, no cost.  terraform test

mock_provider "google" {
  mock_data "google_project" {
    defaults = {
      number = "123456789012"
    }
  }
}
mock_provider "random" {}

variables {
  name            = "floww-shop-test"
  project_id      = "floww-shop"
  database_url    = "postgresql://neondb_owner:pw@ep-test-pooler.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require"
  neon_project_id = "divine-term-00000000"
}

run "prod_has_no_test_features" {
  command = apply

  variables {
    environment = "production"
  }

  assert {
    condition = alltrue([
      for e in google_cloud_run_v2_service.this.template[0].containers[0].env :
      e.value == "false" if e.name == "FLOWSHOP_ALLOW_TIME_TRAVEL"
    ])
    error_message = "The test clock must be off in production."
  }
  assert {
    condition     = google_cloud_run_v2_job.migrate.template[0].template[0].containers[0].args[2] == "flowshop migrate"
    error_message = "Production deploys must never load sample data."
  }
  assert {
    condition     = google_cloud_run_v2_service.this.deletion_protection == true
    error_message = "Prod must be protected from accidental deletion by default."
  }
}

run "scales_to_zero_and_never_wakes_the_database" {
  command = apply

  variables {
    environment = "dev"
  }

  assert {
    condition     = google_cloud_run_v2_service.this.template[0].scaling[0].min_instance_count == 0
    error_message = "The service should scale to zero by default."
  }
  assert {
    condition     = google_cloud_run_v2_service.this.template[0].containers[0].resources[0].cpu_idle == true
    error_message = "CPU must only be billed while handling requests."
  }
  assert {
    condition     = google_cloud_run_v2_service.this.template[0].containers[0].startup_probe[0].http_get[0].path == "/healthz"
    error_message = "Probes must use /healthz, which doesn't touch the database."
  }
}

run "secrets_stay_in_secret_manager" {
  command = apply

  variables {
    environment = "dev"
    secrets     = { FLOWSHOP_WA_TOKEN = "secret-token" }
  }

  assert {
    condition = alltrue([
      for e in google_cloud_run_v2_service.this.template[0].containers[0].env :
      length(e.value_source) == 1 && e.value == null
      if contains(["FLOWSHOP_DATABASE_URL", "FLOWSHOP_SECRET_KEY", "FLOWSHOP_JOBS_TOKEN", "FLOWSHOP_WA_TOKEN"], e.name)
    ])
    error_message = "Secrets must come from Secret Manager, never plain environment values."
  }
  assert {
    condition     = length(google_secret_manager_secret.this) == 5
    error_message = "Expected the four built-in secrets plus the WhatsApp token."
  }
}

run "scheduler_calls_this_environments_service" {
  command = apply

  variables {
    environment = "dev"
  }

  assert {
    condition     = google_cloud_scheduler_job.jobs.http_target[0].uri == "https://floww-shop-test-123456789012.europe-west2.run.app/jobs/run"
    error_message = "The scheduler must call this environment's own service."
  }
  assert {
    condition     = google_cloud_scheduler_job.jobs.http_target[0].headers["X-Jobs-Token"] == random_password.jobs_token.result
    error_message = "The scheduler must send the service's jobs token."
  }
  assert {
    condition     = google_storage_bucket.files.public_access_prevention == "enforced"
    error_message = "The files bucket holds proofs of payment and must never be public."
  }
}

run "uses_the_given_neon_database" {
  command = apply

  variables {
    environment     = "production"
    database_url    = "postgresql://neondb_owner:pw@ep-console-made-pooler.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require"
    neon_project_id = "quiet-sound-91322992"
  }

  assert {
    condition     = google_secret_manager_secret_version.this["FLOWSHOP_DATABASE_URL"].secret_data == var.database_url
    error_message = "The service must use the given database's connection string."
  }
  assert {
    condition     = output.neon_project_id == "quiet-sound-91322992"
    error_message = "Backups must target this environment's Neon project."
  }
}

run "rejects_a_non_postgres_url" {
  command = plan

  variables {
    environment  = "dev"
    database_url = "mysql://nope"
  }

  expect_failures = [var.database_url]
}

run "rejects_unknown_environment" {
  command = plan

  variables {
    environment = "staging"
  }

  expect_failures = [var.environment]
}
