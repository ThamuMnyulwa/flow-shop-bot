variable "project_id" {
  description = "Google Cloud project that holds both environments (the same one as in environments/shared)."
  type        = string
}

variable "region" {
  description = "Google Cloud region, next to Neon's Frankfurt region."
  type        = string
  default     = "europe-west3"
}

variable "cors_origins" {
  description = "Website origins allowed to read the product API, comma separated."
  type        = string
  default     = ""
}

variable "secrets" {
  description = "Further secret settings, e.g. WhatsApp credentials or FLOWSHOP_SENTRY_DSN. Set in terraform.tfvars."
  type        = map(string)
  default     = {}
  sensitive   = true
}
