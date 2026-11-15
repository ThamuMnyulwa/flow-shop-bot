output "url" {
  description = "Public address of the web service."
  value       = local.base_url
}

output "web_service_id" {
  description = "Render service id, used by scripts/deploy.sh to trigger and watch deploys."
  value       = render_web_service.this.id
}

output "neon_project_id" {
  description = "Neon project id, used by scripts/deploy.sh to make a backup branch before a prod deploy."
  value       = neon_project.this.id
}

output "neon_branch_id" {
  description = "The database branch the service uses."
  value       = neon_project.this.default_branch_id
}

output "admin_password" {
  description = "Password for admin@floww.local. Show it with: terraform output -raw admin_password"
  value       = random_password.admin.result
  sensitive   = true
}

output "database_url" {
  description = "Connection string, for running migrations or a restore by hand."
  value       = neon_project.this.connection_uri
  sensitive   = true
}
