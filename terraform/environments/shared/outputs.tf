output "registry" {
  description = "Where scripts/deploy.sh pushes images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "project_id" {
  description = "Google Cloud project."
  value       = var.project_id
}
