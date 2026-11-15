# Prod: real customers and real stock. Deployed only with scripts/deploy.sh prod, after a database backup.

module "environment" {
  source = "../../modules/environment"

  environment         = "production"
  name                = "floww-shop-prod"
  project_id          = var.project_id
  region              = var.region
  database_url        = var.database_url # the Neon project created in the console
  neon_project_id     = var.neon_project_id
  base_url            = var.base_url
  cors_origins        = var.cors_origins
  allow_time_travel   = false
  seed_on_deploy      = false
  min_instances       = var.min_instances
  max_instances       = 3
  jobs_schedule       = "*/15 * * * *"
  deletion_protection = true

  settings = {
    FLOWSHOP_CHANNEL            = var.whatsapp_live ? "whatsapp" : "simulator"
    FLOWSHOP_WA_BUSINESS_NUMBER = var.wa_business_number
  }
  secrets = var.secrets
}
