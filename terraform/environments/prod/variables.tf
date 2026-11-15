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

variable "base_url" {
  description = "Public address once a custom domain is mapped, e.g. https://shop-api.floww.co.za. Empty uses Cloud Run's."
  type        = string
  default     = ""
}

variable "min_instances" {
  description = "0 scales to zero (cheapest). 1 keeps an instance warm for fast first replies, about $10-14 a month."
  type        = number
  default     = 0
}

variable "database_history_seconds" {
  description = "Neon restore window. 21600 (6 hours) on the free plan; up to 604800 (7 days) on Launch."
  type        = number
  default     = 21600
}

variable "whatsapp_live" {
  description = "Switch prod from the simulator to the real WhatsApp number (docs/go-live-whatsapp.md)."
  type        = bool
  default     = false
}

variable "wa_business_number" {
  description = "The business WhatsApp number in international form without the plus, for the website's links."
  type        = string
  default     = "27000000000"
}
