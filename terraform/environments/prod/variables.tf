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

variable "base_url" {
  description = "Public address, e.g. https://shop-api.floww.co.za once a custom domain is set. Empty uses onrender.com."
  type        = string
  default     = ""
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
