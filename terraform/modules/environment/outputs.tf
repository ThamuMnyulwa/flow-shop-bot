output "url" {
  description = "Public address of the service."
  value       = local.base_url
}

output "run_url" {
  description = "Cloud Run's own address, which always works even with a custom domain."
  value       = local.run_url
}

output "service_name" {
  description = "Cloud Run service, updated by scripts/deploy.sh."
  value       = google_cloud_run_v2_service.this.name
}

output "migrate_job_name" {
  description = "Cloud Run job that runs migrations, executed by scripts/deploy.sh before each deploy."
  value       = google_cloud_run_v2_job.migrate.name
}

output "region" {
  description = "Google Cloud region."
  value       = var.region
}

output "project_id" {
  description = "Google Cloud project."
  value       = var.project_id
}

output "files_bucket" {
  description = "Cloud Storage bucket for photos and proofs of payment."
  value       = google_storage_bucket.files.name
}

output "neon_project_id" {
  description = "Neon project id, used by scripts/deploy.sh to make a backup branch before a prod deploy."
  value       = local.neon_project_id
}

output "admin_password" {
  description = "Password for admin@floww.local. Show it with: terraform output -raw admin_password"
  value       = random_password.admin.result
  sensitive   = true
}

output "database_url" {
  description = "Connection string, for a restore or a migration by hand."
  value       = local.database_url
  sensitive   = true
}
