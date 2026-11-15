variable "environment" {
  description = "Which environment this is. Sets FLOWSHOP_ENV and the guard rails that go with it."
  type        = string

  validation {
    condition     = contains(["dev", "production"], var.environment)
    error_message = "environment must be \"dev\" or \"production\"."
  }
}

variable "name" {
  description = "Base name for every resource in this environment, e.g. floww-shop-dev."
  type        = string
}

variable "project_id" {
  description = "Google Cloud project that holds both environments."
  type        = string
}

variable "region" {
  description = "Google Cloud region. London sits next to Neon's London region; a WhatsApp tap runs many queries."
  type        = string
  default     = "europe-west2"
}

variable "neon_region" {
  description = "Neon region for a database this module creates. Ignored when database_url is set."
  type        = string
  default     = "aws-eu-west-2"
}

variable "database_url" {
  description = "Use an existing Neon database (its pooled connection string) instead of creating a Neon project."
  type        = string
  default     = ""
  sensitive   = true
}

variable "neon_project_id" {
  description = "With database_url: the existing Neon project's id, for the backup before each prod deploy."
  type        = string
  default     = ""
}

variable "database_history_seconds" {
  description = "How far back Neon can restore the database. The free plan allows up to 6 hours; Launch up to 7 days."
  type        = number
  default     = 21600
}

variable "max_instances" {
  description = "Upper limit of Cloud Run instances, a cap on cost if something goes wrong."
  type        = number
  default     = 3
}

variable "min_instances" {
  description = "Instances kept warm. 0 scales to zero (cheapest); 1 avoids a slow first reply after a quiet spell."
  type        = number
  default     = 0
}

variable "jobs_schedule" {
  description = "Cron schedule for payment reminders and the 48-hour release (Africa/Johannesburg time)."
  type        = string
  default     = "*/15 * * * *"
}

variable "base_url" {
  description = "Public address, e.g. a custom domain. Leave empty for the Cloud Run address."
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

variable "seed_on_deploy" {
  description = "The migration job also loads sample products, a test admin and test orders. Dev only."
  type        = bool
  default     = false
}

variable "settings" {
  description = "Further non-secret settings, e.g. FLOWSHOP_CHANNEL and FLOWSHOP_WA_BUSINESS_NUMBER."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Further secret settings, e.g. WhatsApp credentials. Stored in Secret Manager."
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "deletion_protection" {
  description = "Stop Terraform from deleting the service, files and database by accident."
  type        = bool
  default     = true
}
