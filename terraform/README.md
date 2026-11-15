# Infrastructure

Everything the FLOWW shop runs on is defined here: the database, the servers and the scheduled jobs, for dev and prod.

```
terraform/
├── modules/environment/     one environment: Neon database, Render web service + disk, jobs cron, secrets
│   └── tests/               mock-provider tests: no accounts, no cost (terraform test)
└── environments/
    ├── dev/                 develop branch, sample data, test clock, simulator
    └── prod/                main branch, real data
```

Each environment has its own Neon project and its own Terraform state, so a change to dev can't touch prod.

## What gets created

| Resource | Dev | Prod |
| --- | --- | --- |
| Neon project, Frankfurt, PostgreSQL 16 | `floww-shop-dev` | `floww-shop-prod` |
| Render web service, Docker, starter | `floww-shop-dev`, 1 GB disk | `floww-shop-prod`, 5 GB disk |
| Render cron job, every 15 minutes | `floww-shop-dev-jobs` | `floww-shop-prod-jobs` |
| Secrets: session key, jobs token, first admin password | generated | generated |

Deploys don't happen on git push. `scripts/deploy.sh` runs them, so every deploy is tested and verified (see [docs/deploy-render.md](../docs/deploy-render.md)).

## First run

1. **API keys.** Never put them in a file in git.

   ```sh
   export RENDER_API_KEY=...      # Render → Account settings → API keys
   export RENDER_OWNER_ID=...     # Render → Workspace settings (starts with tea- or usr-)
   export NEON_API_KEY=...        # Neon → Account settings → API keys
   ```

2. **Render access to GitHub.** Connect GitHub to Render once in the dashboard, so Render can read the repository.

3. **Dev first.**

   ```sh
   cd terraform/environments/dev
   cp terraform.tfvars.example terraform.tfvars   # edit if needed
   terraform init
   terraform plan          # read it
   terraform apply
   terraform output -raw admin_password           # sign in as admin@floww.local
   ```

4. **Then prod**, the same way, in `terraform/environments/prod`. Prod starts empty. After the first deploy, create the products and admin from the Render shell:

   ```sh
   flowshop seed --no-orders     # FLOWSHOP_ADMIN_PASSWORD is already set by Terraform
   ```

## Changing infrastructure

Edit the module or an environment, then run `terraform plan` and `terraform apply` in that environment. Do dev first.

Before pushing, check:

```sh
terraform fmt -recursive
(cd modules/environment && terraform init -backend=false && terraform test)
```

## Things to know

- **State holds secrets**: the database password and the generated keys. It stays on your machine (`terraform.tfstate`, git-ignored). Back it up. If more than one person will run Terraform, move it to a remote backend; see `versions.tf`.
- **The service address** is assumed to be `https://<name>.onrender.com`. If Render gives a different address, because the name is taken, set `base_url` in `terraform.tfvars`.
- **Neon's free plan** pauses an idle database, and keeps up to 6 hours of history for restores. Before go-live, consider the paid plan for prod, and raise `database_history_seconds`.
- **Not yet applied against real accounts.** `terraform validate` and the mock tests pass against the providers' real schemas: render-oss/render 1.9, kislerdm/neon 0.18.
