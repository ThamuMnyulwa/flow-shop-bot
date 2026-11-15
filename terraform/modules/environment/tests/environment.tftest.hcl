# Runs with mocked providers: no Render or Neon account, no cost.  terraform test

mock_provider "render" {}
mock_provider "neon" {
  mock_resource "neon_project" {
    defaults = {
      connection_uri_pooler = "postgresql://flowshop:pw@ep-x-pooler.eu-central-1.aws.neon.tech/flowshop?sslmode=require"
    }
  }
}
mock_provider "random" {}

variables {
  name     = "floww-shop-test"
  repo_url = "https://github.com/ThamuMnyulwa/flow-shop-bot"
}

run "prod_has_no_test_features" {
  command = apply

  variables {
    environment = "production"
    branch      = "main"
    auto_deploy = false
  }

  assert {
    condition     = render_web_service.this.env_vars["FLOWSHOP_ALLOW_TIME_TRAVEL"].value == "false"
    error_message = "The test clock must be off in production."
  }
  assert {
    condition     = render_web_service.this.env_vars["FLOWSHOP_SEED_ON_START"].value == "false"
    error_message = "Production must never load sample data."
  }
  assert {
    condition     = render_web_service.this.runtime_source.docker.auto_deploy == false
    error_message = "Prod deploys only through scripts/deploy.sh."
  }
  assert {
    condition     = render_web_service.this.env_vars["FLOWSHOP_ENV"].value == "production"
    error_message = "FLOWSHOP_ENV must be production."
  }
}

run "cron_and_web_share_the_jobs_token" {
  command = apply

  variables {
    environment = "dev"
    branch      = "develop"
    auto_deploy = true
  }

  assert {
    condition     = render_cron_job.jobs.env_vars["FLOWSHOP_JOBS_TOKEN"].value == render_web_service.this.env_vars["FLOWSHOP_JOBS_TOKEN"].value
    error_message = "The jobs cron must use the web service's token."
  }
  assert {
    condition     = render_cron_job.jobs.env_vars["FLOWSHOP_BASE_URL"].value == "https://floww-shop-test.onrender.com"
    error_message = "The cron must call this environment's own service."
  }
  assert {
    condition     = render_web_service.this.disk.mount_path == "/var/data" && render_web_service.this.env_vars["FLOWSHOP_STORAGE_DIR"].value == "/var/data/storage"
    error_message = "Files must be stored on the disk, or they vanish on every deploy."
  }
}

run "rejects_unknown_environment" {
  command = plan

  variables {
    environment = "staging"
    branch      = "develop"
    auto_deploy = true
  }

  expect_failures = [var.environment]
}
