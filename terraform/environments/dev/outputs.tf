output "url" {
  description = "Public address of the service."
  value       = module.environment.url
}

output "web_service_id" {
  description = "Render service id, read by scripts/deploy.sh."
  value       = module.environment.web_service_id
}

output "neon_project_id" {
  description = "Neon project id, read by scripts/deploy.sh."
  value       = module.environment.neon_project_id
}

output "neon_branch_id" {
  description = "The database branch the service uses, read by scripts/deploy.sh."
  value       = module.environment.neon_branch_id
}

output "admin_password" {
  description = "Password for admin@floww.local: terraform output -raw admin_password"
  value       = module.environment.admin_password
  sensitive   = true
}
