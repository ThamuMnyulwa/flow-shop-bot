# One FLOWW shop environment: its own database, web service with a disk, and scheduled jobs.

locals {
  base_url     = var.base_url != "" ? var.base_url : "https://${var.name}.onrender.com"
  storage_path = "/var/data"
}

# ---------- database ----------

resource "neon_project" "this" {
  name                      = var.name
  region_id                 = var.neon_region
  pg_version                = 16
  history_retention_seconds = var.database_history_seconds

  branch {
    name          = "main"
    database_name = "flowshop"
    role_name     = "flowshop"
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

# ---------- web service ----------

resource "render_web_service" "this" {
  name              = var.name
  plan              = var.plan
  region            = var.region
  health_check_path = "/healthz"

  runtime_source = {
    docker = {
      repo_url        = var.repo_url
      branch          = var.branch
      auto_deploy     = var.auto_deploy
      dockerfile_path = "./Dockerfile"
      context         = "."
    }
  }

  disk = {
    name       = "${var.name}-files"
    mount_path = local.storage_path
    size_gb    = var.disk_size_gb
  }

  env_vars = merge(
    {
      FLOWSHOP_ENV               = { value = var.environment }
      FLOWSHOP_DATABASE_URL      = { value = neon_project.this.connection_uri_pooler }
      FLOWSHOP_SECRET_KEY        = { value = random_password.secret_key.result }
      FLOWSHOP_JOBS_TOKEN        = { value = random_password.jobs_token.result }
      FLOWSHOP_ADMIN_PASSWORD    = { value = random_password.admin.result }
      FLOWSHOP_BASE_URL          = { value = local.base_url }
      FLOWSHOP_STORAGE_DIR       = { value = "${local.storage_path}/storage" }
      FLOWSHOP_ALLOW_TIME_TRAVEL = { value = tostring(var.allow_time_travel) }
      FLOWSHOP_SEED_ON_START     = { value = tostring(var.seed_on_start) }
      FLOWSHOP_CORS_ORIGINS      = { value = var.cors_origins }
    },
    { for key, value in nonsensitive(var.extra_env_vars) : key => { value = sensitive(value) } },
  )
}

# ---------- scheduled jobs (E12) ----------

resource "render_cron_job" "jobs" {
  name     = "${var.name}-jobs"
  plan     = "starter"
  region   = var.region
  schedule = var.jobs_schedule

  # A tiny job: no build, just one authenticated call to the web service.
  runtime_source = {
    native_runtime = {
      repo_url      = var.repo_url
      branch        = var.branch
      auto_deploy   = var.auto_deploy
      runtime       = "python"
      build_command = "true"
    }
  }

  start_command = "python -c \"import os,urllib.request as u; r=u.Request(os.environ['FLOWSHOP_BASE_URL']+'/jobs/run', method='POST', headers={'Authorization':'Bearer '+os.environ['FLOWSHOP_JOBS_TOKEN']}); print(u.urlopen(r).read())\""

  env_vars = {
    FLOWSHOP_BASE_URL   = { value = local.base_url }
    FLOWSHOP_JOBS_TOKEN = { value = random_password.jobs_token.result }
  }
}
