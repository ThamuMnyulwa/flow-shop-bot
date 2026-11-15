# Deploy: dev and prod

There are two environments, each with its own server, database, files and scheduled jobs.

| | Dev | Prod |
| --- | --- | --- |
| Purpose | Try changes, with you and staff, before customers see them | Real customers, real stock |
| Git branch | `develop`, deployed on every push | `main`, deployed only when you press **Deploy** |
| Render services | `floww-shop-dev` + `floww-shop-dev-jobs` | `floww-shop-prod` + `floww-shop-prod-jobs` |
| Database | Neon branch `dev` | Neon branch `main` |
| Data | Sample products, a test admin and test orders, loaded on start | Real data only |
| WhatsApp | Simulator, later a Meta test number | Simulator until go-live, then the business number |
| Test clock | On | Off |
| Banner | Blue "DEV: test data" on every page | None |

**Never copy prod data into dev.** Customer names, numbers and addresses are personal information under POPIA. Dev always runs on sample data.

## How a change reaches customers

1. Work on a feature branch, and run the tests locally.
2. Merge it into `develop`. Render deploys dev on its own.
3. Check the change on dev, with staff if it affects them.
4. Merge `develop` into `main`.
5. Back up prod: in Neon, create a branch from `main` named after the release, for example `backup-2026-11-20`.
6. In Render, open `floww-shop-prod` and press **Manual Deploy → Deploy latest commit**. Migrations run when it starts.
7. If something goes wrong:
   - In Render, roll back to the previous deploy.
   - If a migration was the problem, point prod at the backup branch.

## First-time setup

### 1. Neon (database)

1. Create a project in the **Frankfurt** region (AWS eu-central-1).
2. The project starts with a `main` branch, which is prod. Add a second branch called `dev`.
3. Copy each branch's pooled connection string. Paste it exactly as Neon shows it. The service accepts `postgres://` and `postgresql://`.

### 2. GitHub

The `develop` branch must exist, because Render's dev service deploys from it. It is already pushed.

### 3. Render (servers)

1. **New → Blueprint**, then pick the `flow-shop-bot` repository. Render reads `render.yaml` and creates all four services, with a disk for each web service.
2. Fill in the values Render asks for:

   | Setting | Dev | Prod |
   | --- | --- | --- |
   | `FLOWSHOP_DATABASE_URL` | Neon `dev` string | Neon `main` string |
   | `FLOWSHOP_BASE_URL` | `https://floww-shop-dev.onrender.com` | `https://floww-shop-prod.onrender.com`, or a custom domain |
   | `FLOWSHOP_CORS_ORIGINS` | the Netlify preview URL | the live Netlify site |
   | `FLOWSHOP_WA_BUSINESS_NUMBER` | — | the WhatsApp number, without the plus |

   On each jobs service, set `FLOWSHOP_BASE_URL` to the matching web service's URL. The jobs token is linked automatically.
3. **Dev** loads sample data on its own. Sign in as `admin@floww.local`. The password is the generated `FLOWSHOP_ADMIN_PASSWORD` in the dev service's **Environment** tab.
4. **Prod** starts empty. Open the prod service's **Shell** tab and run:

   ```sh
   FLOWSHOP_ADMIN_PASSWORD='a long password you choose' flowshop seed --no-orders
   ```

   This loads the four launch products and the admin account. It refuses to load test orders.
5. **On prod,** sign in, change the password, then set the real bank details, office address, returns link and collection code. Add one staff account per person.

### 4. Checks before customers use prod

- [ ] `/healthz` returns `{"ok": true}` on both environments.
- [ ] On dev: a test order reserves stock, and the **+49 h** button releases it.
- [ ] On dev: a product photo upload survives a redeploy, which proves the disk works.
- [ ] **Backup restore tested:** restore a Neon backup branch into dev's place, sign in, then point dev back.
- [ ] Error alerts work: set `FLOWSHOP_SENTRY_DSN` on prod and trigger a test error.
- [ ] An uptime check (for example UptimeRobot, free) watches prod's `/healthz` every 5 minutes. This also keeps Neon's free plan from pausing the database.

## Costs

| Item | Dev | Prod |
| --- | --- | --- |
| Render web service, starter | about $7 a month | about $7 a month |
| Render cron job | about $1 a month | about $1 a month |
| Render disk | 1 GB, about $0.25 | 5 GB, about $1.25 |
| Neon | Free plan covers both branches to start | — |

That comes to about $18 a month for both environments. Running dev only while you use it, or putting dev on Render's free plan without a disk, halves that. On the free plan, uploaded files on dev disappear on each deploy.

## Running without Render

The same image runs on any server with Docker. See [self-hosting with Docker](self-host-docker.md).
