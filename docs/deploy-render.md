# Deploy: dev and prod

There are two environments. Each has its own server, database, files and scheduled jobs, all defined in [terraform/](../terraform/README.md).

| | Dev | Prod |
| --- | --- | --- |
| Purpose | Try changes with you and staff before customers see them | Real customers, real stock |
| Git branch | `develop` | `main` |
| Deployed by | `scripts/deploy.sh dev` | `scripts/deploy.sh prod` |
| Database | Its own Neon project, with sample data only | Its own Neon project, with real data |
| WhatsApp | Simulator, later a Meta test number | Simulator until go-live, then the business number |
| Test clock | On | Off |
| Banner | Blue "DEV: test data" on every page | None |

**Never copy prod data into dev.** Customer names, numbers and addresses are personal information under POPIA.

## Deploying

```sh
export RENDER_API_KEY=...   # both environments
export NEON_API_KEY=...     # prod: for the backup before each deploy

scripts/deploy.sh dev       # 1. test, push to develop, deploy dev, wait, verify
                            # 2. check the change on dev
scripts/deploy.sh prod      # 3. promote that same commit to prod
scripts/deploy.sh status    # what is running where
```

**`scripts/deploy.sh dev`:**
1. Refuses to run if there are uncommitted changes.
2. Runs lint and the tests.
3. Fast-forwards `develop` to your current commit.
4. Tells Render to deploy exactly that commit.
5. Waits until the deploy is live, and checks `/healthz` reports the commit.

**`scripts/deploy.sh prod`:**
1. Refuses unless dev is already running the same commit. Only what you checked on dev reaches customers.
2. Asks you to type `prod`.
3. Fast-forwards `main`.
4. Backs up the prod database as a Neon branch named `backup-<date>-<commit>`.
5. Deploys, waits, and verifies, as for dev.

**If a deploy goes wrong:**
- Run `scripts/deploy.sh rollback prod` (or `dev`) to put the previous live version back.
- If the bad version also changed the database, restore the backup branch in the Neon console.

Add `--dry-run` to any command to see what it would do without changing anything.

## First-time setup

Follow [terraform/README.md](../terraform/README.md):
1. Create API keys for Render and Neon.
2. Connect GitHub to Render.
3. Run `terraform apply` in `environments/dev`, then in `environments/prod`.
4. Deploy each environment with the script.

**Dev** loads sample data on its own. Sign in as `admin@floww.local`, with the password from `terraform output -raw admin_password`.

**Prod** starts empty. After its first deploy:
1. Open the Render shell for `floww-shop-prod` and run `flowshop seed --no-orders`.
2. Sign in and change the password.
3. Set the real bank details, office address, returns link and collection code.
4. Add one staff account per person.

## Checks before customers use prod

- [ ] `scripts/deploy.sh status` shows both environments running the same commit.
- [ ] On dev: a test order reserves stock, and the **+49 h** button releases it.
- [ ] On dev: a product photo survives a redeploy, which proves the disk works.
- [ ] A backup restore tested on Neon: create a branch from a backup and connect to it.
- [ ] Error alerts work: add `FLOWSHOP_SENTRY_DSN` to prod's `terraform.tfvars`, apply, then trigger a test error.
- [ ] An uptime check (for example UptimeRobot, free) watches prod's `/healthz` every 5 minutes.

## Costs

| Item | Dev | Prod |
| --- | --- | --- |
| Render web service, starter | about $7 a month | about $7 a month |
| Render cron job | about $1 a month | about $1 a month |
| Render disk | 1 GB, about $0.25 | 5 GB, about $1.25 |
| Neon | Free plan to start | Free plan to start; paid recommended before go-live |

The total is about $18 a month.

## Running without Render

The same image runs on any server with Docker. See [self-hosting with Docker](self-host-docker.md).
