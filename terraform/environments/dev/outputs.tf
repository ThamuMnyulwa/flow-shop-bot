output "url" {
  description = "Public address of the service."
  value       = module.environment.url
}

output "run_url" {
  description = "Cloud Run's own address."
  value       = module.environment.run_url
}

output "service_name" {
  description = "Read by scripts/deploy.sh."
  value       = module.environment.service_name
}

output "migrate_job_name" {
  description = "Read by scripts/deploy.sh."
  value       = module.environment.migrate_job_name
}

output "region" {
  description = "Read by scripts/deploy.sh."
  value       = module.environment.region
}

output "project_id" {
  description = "Read by scripts/deploy.sh."
  value       = module.environment.project_id
}

output "neon_project_id" {
  description = "Read by scripts/deploy.sh for the pre-deploy backup."
  value       = module.environment.neon_project_id
}

output "admin_password" {
  description = "Password for admin@floww.local: terraform output -raw admin_password"
  value       = module.environment.admin_password
  sensitive   = true
}
