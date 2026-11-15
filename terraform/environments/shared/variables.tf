variable "project_id" {
  description = "Google Cloud project that holds both environments."
  type        = string
}

variable "region" {
  description = "Google Cloud region for the image registry, next to the services."
  type        = string
  default     = "europe-west3"
}

variable "billing_account" {
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX) for a budget alert. Leave empty to skip the alert."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Email alerts at 50%, 90% and 100% of this monthly spend."
  type        = number
  default     = 30
}
