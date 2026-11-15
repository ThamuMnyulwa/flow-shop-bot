# Dev: deployed with scripts/deploy.sh dev, from the `develop` branch, with sample data, the test clock and the
# simulator.
# Never holds real customer data.

module "environment" {
  source = "../../modules/environment"

  environment       = "dev"
  name              = "floww-shop-dev"
  repo_url          = var.repo_url
  branch            = "develop"
  auto_deploy       = false # every deploy goes through scripts/deploy.sh, which checks it
  disk_size_gb      = 1
  cors_origins      = var.cors_origins
  allow_time_travel = true
  seed_on_start     = true

  extra_env_vars = merge(
    {
      FLOWSHOP_CHANNEL            = "simulator"
      FLOWSHOP_WA_BUSINESS_NUMBER = "27000000000"
    },
    var.extra_env_vars,
  )
}
