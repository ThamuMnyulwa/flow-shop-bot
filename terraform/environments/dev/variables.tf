variable "repo_url" {
  description = "GitHub repository Render builds from."
  type        = string
  default     = "https://github.com/ThamuMnyulwa/flow-shop-bot"
}

variable "cors_origins" {
  description = "Website origins allowed to read the product API, comma separated."
  type        = string
  default     = ""
}

variable "extra_env_vars" {
  description = "Further secret settings, e.g. WhatsApp credentials or FLOWSHOP_SENTRY_DSN. Set in terraform.tfvars."
  type        = map(string)
  default     = {}
  sensitive   = true
}
