# Infrastructure

Everything the FLOWW shop runs on is defined here. The app runs on Google Cloud Run in London and the database on Neon, for dev and prod. Both environments live in the Google Cloud project **`oceanhub-dev`**.

```
terraform/
├── modules/environment/     one environment: Neon database, Cloud Run service + migration job, files bucket,
│   │                        secrets, service account, scheduled jobs
│   └── tests/               mock-provider tests: no accounts, no cost (terraform test)
└── environments/
    ├── shared/              Google Cloud services, the image registry, an optional budget alert
    ├── dev/                 sample data, test clock, simulator
    └── prod/                real data
```

Terraform state is kept in the `oceanhub-dev-tfstate` bucket, under `floww-shop/<environment>`. The bucket is private and keeps old versions. The state holds secrets.

## What gets created

| Resource | Shared | Dev | Prod |
| --- | --- | --- | --- |
| Artifact Registry `floww-shop` | ✓ | | |
| Cloud Run service, 1 vCPU / 512 MB, scales to zero | | `floww-shop-dev` | `floww-shop-prod` |
| Cloud Run job for migrations | | `floww-shop-dev-migrate` | `floww-shop-prod-migrate` |
| Cloud Storage bucket, private | | `oceanhub-dev-floww-shop-dev-files` | `oceanhub-dev-floww-shop-prod-files` |
| Secret Manager: database URL, session key, jobs token, admin password, WhatsApp keys | | ✓ | ✓ |
| Service account with access only to its own secrets and bucket | | ✓ | ✓ |
| Cloud Scheduler: reminders and the 48-hour release | | hourly | every 15 minutes |
| Neon project, London, PostgreSQL | | `floww-shop-dev`, created by Terraform | `quiet-sound-91322992`, created in the Neon console |

**Images:** Terraform creates the services with a placeholder image. `scripts/deploy.sh` sets the real one, and Terraform leaves it alone afterwards.

**Shared project:** every resource is labelled `app=floww-shop`, and the budget alert counts only those, so the other apps in `oceanhub-dev` aren't included. Removing FLOWW never turns off the Google services the other apps use.

## First run

```sh
gcloud auth application-default login          # Terraform's Google sign-in
export NEON_API_KEY=...                        # Neon console → Account settings → API keys

cd terraform/environments/shared
cp terraform.tfvars.example terraform.tfvars   # project_id = "oceanhub-dev"; billing_account for a budget alert
terraform init && terraform plan && terraform apply

cd ../dev
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform plan && terraform apply

cd ../prod
cp terraform.tfvars.example terraform.tfvars   # paste the prod database's POOLED string after resetting its password
terraform init && terraform plan && terraform apply
```

Then deploy with `scripts/deploy.sh dev` and `scripts/deploy.sh prod` (see [docs/deploy.md](../docs/deploy.md)).

## Moving prod to its own project later

Recommended before real customers. `oceanhub-dev` is a development project shared with other apps, and prod holds personal information under POPIA.

1. Create a project, for example `floww-shop-prod`, and link billing to it.
2. In `environments/prod`, set `project_id` to the new project, and set the backend bucket to a state bucket in that project.
3. Let prod's Cloud Run service agent read images from the shared registry. Grant `roles/artifactregistry.reader` to `service-<prod project number>@serverless-robot-prod.iam.gserviceaccount.com` on the `floww-shop` repository.
4. Run `terraform apply`, then `scripts/deploy.sh prod`.

## Changing infrastructure

Edit the module or an environment, then run `terraform plan` and `terraform apply` in that environment. Do dev before prod. Before pushing, check:

```sh
terraform fmt -recursive
(cd modules/environment && terraform init -backend=false && terraform test)
```

## Things to know

- **Deletion protection:** prod has it on for the service and job, and the files bucket isn't force-deleted. Dev has it off, so it can be rebuilt freely.
- **Scheduler token:** Cloud Scheduler sends the jobs token in the `X-Jobs-Token` header, so it's visible to anyone who can view Scheduler jobs in the project. It only allows triggering the reminders and the 48-hour release, nothing else.
- **Neon's free plan** suspends idle compute and keeps 6 hours of history. Prod's database was created in the Neon console, so its plan, restore window and settings are managed there, not by Terraform. Put it on Launch before go-live, with a 7-day restore window.
- **The prod database password** lives in `terraform.tfvars`, which isn't committed. It's also in Terraform state, in the private state bucket, and in Secret Manager. To change it, reset it in Neon, update `terraform.tfvars`, run `terraform apply`, then redeploy.
- **Neon Auth** is turned on in the prod Neon project but not used. Staff sign in through the app, and customers are identified by their WhatsApp number. It can be switched off in the Neon console.
- **Tested so far:**
  - `terraform validate` and the mock tests pass against Google provider 8.11 and Neon provider 0.18.
  - `terraform plan` for `shared` against `oceanhub-dev` shows 8 additions and nothing changed or deleted.
  - Nothing has been applied yet.
