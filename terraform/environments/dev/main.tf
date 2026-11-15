# Dev: sample data, the test clock and the simulator. Deployed with scripts/deploy.sh dev. Never holds real
# customer data.

module "environment" {
  source = "../../modules/environment"

  environment         = "dev"
  name                = "floww-shop-dev"
  project_id          = var.project_id
  region              = var.region
  database_url        = var.database_url # the Neon project created in the console
  neon_project_id     = var.neon_project_id
  cors_origins        = var.cors_origins
  allow_time_travel   = true
  seed_on_deploy      = true
  min_instances       = 0
  max_instances       = 2
  jobs_schedule       = "0 * * * *" # hourly: dev has no real orders, and Neon's free plan stays free
  deletion_protection = false       # dev can be torn down and rebuilt

  settings = {
    FLOWSHOP_CHANNEL            = "simulator"
    FLOWSHOP_WA_BUSINESS_NUMBER = "27000000000"
  }
  secrets = var.secrets
}
