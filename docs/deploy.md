# Deploy: dev and prod

The app runs on **Google Cloud Run** in London and scales to zero when idle. The database is on **Neon**, also in London. Each environment has its own service, database, files bucket, secrets and scheduled jobs, all defined in [terraform/](../terraform/README.md). Both environments are in the Google Cloud project `oceanhub-dev`.

| | Dev | Prod |
| --- | --- | --- |
| Purpose | Try changes with you and staff before customers see them | Real customers, real stock |
| Git branch | `develop` | `main` |
| Deployed by | `scripts/deploy.sh dev` | `scripts/deploy.sh prod` |
| Cloud Run service | `floww-shop-dev`, scales to zero, at most 2 instances | `floww-shop-prod`, scales to zero, at most 3 instances |
| Database | Neon project `floww-shop-dev` (London), free plan, sample data only | Neon project `quiet-sound-91322992` (London), real data |
| Scheduled jobs | Hourly | Every 15 minutes |
| WhatsApp | Simulator, later a Meta test number | Simulator until go-live, then the business number |
| Test clock | On | Off |
| Banner | Blue "DEV: test data" on every page | None |

**Never copy prod data into dev.** Customer names, numbers and addresses are personal information under POPIA.

## Deploying

```sh
gcloud auth login                                          # once
gcloud auth configure-docker europe-west2-docker.pkg.dev   # once
export NEON_API_KEY=...                                    # prod: for the backup before each deploy

scripts/deploy.sh dev       # 1. test, build, migrate, deploy dev, verify
                            # 2. check the change on dev
scripts/deploy.sh prod      # 3. promote the same image to prod
scripts/deploy.sh status    # what is running where
```

**`scripts/deploy.sh dev`:**
1. Refuses to run if there are uncommitted changes.
2. Runs lint and the tests.
3. Fast-forwards `develop` to your current commit.
4. Builds the image once, with the commit built in, and pushes it to Artifact Registry.
5. Runs the migration job. Dev's job also loads the sample data.
6. Points the service at the new image, then checks that `/healthz` reports the commit.

**`scripts/deploy.sh prod`:**
1. Refuses unless dev is already running the same commit. Prod gets **the same image** as dev, not a rebuild.
2. Asks you to type `prod`.
3. Fast-forwards `main`.
4. Backs up the prod database as a Neon branch named `backup-<date>-<commit>`.
5. Migrates, deploys and verifies, as for dev.

**If a deploy goes wrong:**
- If the migration fails, the service is never touched and keeps running the old version.
- `scripts/deploy.sh rollback prod` (or `dev`) sends all traffic back to the previous version within seconds. If the bad version also changed the database, restore the backup branch in the Neon console.

Add `--dry-run` to any command to see what it would do without changing anything.

## First-time setup

Follow [terraform/README.md](../terraform/README.md). In short:
1. Run `terraform apply` in `environments/shared`, then `dev`, then `prod`.
2. Run `scripts/deploy.sh dev`.
3. Run `scripts/deploy.sh prod`.

**Dev:** the first deploy loads sample data. Sign in as `admin@floww.local`, with the password from `terraform output -raw admin_password` in `environments/dev`.

**Prod** starts with the tables but no data. Load the four launch products and the admin account once:

```sh
gcloud run jobs execute floww-shop-prod-migrate --region europe-west2 --project oceanhub-dev \
  --args="sh,-c,flowshop migrate && flowshop seed --no-orders" --wait
```

Then on prod:
1. Sign in with the prod `admin_password` output, and change the password.
2. Set the real bank details, office address, returns link and collection code.
3. Add one staff account per person.

## How it scales to zero, and what that means

- **Idle:** when nobody uses the shop for about 15 minutes, Cloud Run stops the app, and Neon suspends the database after 5 minutes. You pay for neither while they're stopped.
- **First message after a quiet spell:** the app starts and the database wakes, which adds about 2–5 seconds. Messages after that are fast.
- **Health checks** (`/healthz`) never touch the database, so they don't keep it awake. `/healthz/db` checks the database when you need to.
- **Always fast:** set `min_instances = 1` in `environments/prod/terraform.tfvars` and apply. That costs about $10–14 a month.

## Checks before customers use prod

- [ ] `scripts/deploy.sh status` shows both environments running the same commit.
- [ ] On dev: a test order reserves stock, and the **+49 h** button releases it.
- [ ] On dev: a product photo uploads, and still shows after another deploy (Cloud Storage).
- [ ] The scheduled job runs: in Cloud Scheduler, `floww-shop-prod-jobs` shows "Success".
- [ ] A backup restore tested: in Neon, create a branch from a backup and connect to it.
- [ ] Error alerts work: add `FLOWSHOP_SENTRY_DSN` to prod's `secrets` in `terraform.tfvars`, apply, then trigger a test error.
- [ ] A budget alert is set: `billing_account` in `environments/shared/terraform.tfvars`.

## Expected costs

| Item | Dev | Prod |
| --- | --- | --- |
| Cloud Run, scales to zero | $0, within the free allowance | $0, within the free allowance |
| Neon | $0, free plan | About $8–12, Launch plan |
| Cloud Storage, Secret Manager, Artifact Registry, Scheduler | Under $1 | Under $1 |

The total is about **$10–15 a month**. One always-on prod instance adds about $10–14. WhatsApp message charges are separate.

## Running without Google Cloud

The same image runs on any server with Docker. See [self-hosting with Docker](self-host-docker.md).
