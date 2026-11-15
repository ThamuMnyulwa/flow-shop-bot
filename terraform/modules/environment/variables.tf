variable "environment" {
  description = "Which environment this is. Sets FLOWSHOP_ENV and the guard rails that go with it."
  type        = string

  validation {
    condition     = contains(["dev", "production"], var.environment)
    error_message = "environment must be \"dev\" or \"production\"."
  }
}

variable "name" {
  description = "Base name for the Render services and the Neon project, e.g. floww-shop-dev."
  type        = string
}

variable "repo_url" {
  description = "GitHub repository Render builds from."
  type        = string
}

variable "branch" {
  description = "Git branch this environment deploys from."
  type        = string
}

variable "auto_deploy" {
  description = "Deploy on every push to the branch. Off in both environments: deploys go through scripts/deploy.sh."
  type        = bool
}

variable "region" {
  description = "Render region. Frankfurt is nearest to South Africa and to Neon's Frankfurt region."
  type        = string
  default     = "frankfurt"
}

variable "neon_region" {
  description = "Neon region for the database."
  type        = string
  default     = "aws-eu-central-1"
}

variable "plan" {
  description = "Render instance plan for the web service. A disk needs a paid plan."
  type        = string
  default     = "starter"
}

variable "disk_size_gb" {
  description = "Disk for product photos and proof-of-payment files."
  type        = number
  default     = 1
}

variable "database_history_seconds" {
  description = "How far back Neon can restore the database. The free plan allows up to 6 hours."
  type        = number
  default     = 21600
}

variable "base_url" {
  description = "Public address of the web service. Leave empty for https://<name>.onrender.com."
  type        = string
  default     = ""
}

variable "cors_origins" {
  description = "Website origins allowed to read the product API, comma separated."
  type        = string
  default     = ""
}

variable "allow_time_travel" {
  description = "The test clock. Never on in production."
  type        = bool
  default     = false
}

variable "seed_on_start" {
  description = "Load sample products, a test admin and test orders on start. Dev only."
  type        = bool
  default     = false
}

variable "jobs_schedule" {
  description = "Cron schedule for payment reminders and the 48-hour release."
  type        = string
  default     = "*/15 * * * *"
}

variable "extra_env_vars" {
  description = "Further settings, such as the WhatsApp channel and its credentials. Values are secret."
  type        = map(string)
  default     = {}
  sensitive   = true
}
