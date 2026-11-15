# Prod: real customers and real stock. Deploys only through scripts/deploy.sh prod, after a database backup.

module "environment" {
  source = "../../modules/environment"

  environment       = "production"
  name              = "floww-shop-prod"
  repo_url          = var.repo_url
  branch            = "main"
  auto_deploy       = false
  disk_size_gb      = 5
  base_url          = var.base_url
  cors_origins      = var.cors_origins
  allow_time_travel = false
  seed_on_start     = false

  extra_env_vars = merge(
    {
      FLOWSHOP_CHANNEL            = var.whatsapp_live ? "whatsapp" : "simulator"
      FLOWSHOP_WA_BUSINESS_NUMBER = var.wa_business_number
    },
    var.extra_env_vars,
  )
}
