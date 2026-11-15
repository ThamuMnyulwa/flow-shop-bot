# Deploy to Render and Neon

Production runs the Docker image on Render (Frankfurt region) with PostgreSQL on Neon. Staging is a second Render service on a Neon branch. The same image also runs on Google Cloud Run, AWS or Azure. Nothing in the code depends on Render.

## What you need

- A Neon project: a `main` branch for production and a `staging` branch for staging.
- A Render account connected to this GitHub repository.
- An S3-compatible bucket for product images and proof-of-payment files, for example Cloudflare R2 or AWS S3. Render's disk is wiped on every deploy, so files can't live on the server.

## Steps

1. **Database.** In Neon, copy the pooled connection string. Change the scheme to `postgresql+psycopg://` and keep `?sslmode=require` on the end.
2. **Blueprint.** In Render, choose **New → Blueprint** and pick this repository. Render reads `render.yaml` and creates:
   - the web service
   - a cron job that calls `/jobs/run` every 15 minutes
3. **Settings.** Fill in the values Render asks for:

   | Setting | Value |
   | --- | --- |
   | `FLOWSHOP_DATABASE_URL` | the Neon string from step 1 |
   | `FLOWSHOP_BASE_URL` | the service's public URL, for example `https://floww-shop.onrender.com` |
   | `FLOWSHOP_CORS_ORIGINS` | the Netlify site's URL |
   | `FLOWSHOP_S3_BUCKET`, `FLOWSHOP_S3_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | the bucket and its credentials |
   | `FLOWSHOP_WA_BUSINESS_NUMBER` | the WhatsApp number in international form, without the plus |

   On the cron job, set the same `FLOWSHOP_BASE_URL`, and copy `FLOWSHOP_JOBS_TOKEN` from the web service.
4. **First admin.** Open the web service's shell and run:

   ```sh
   FLOWSHOP_ADMIN_PASSWORD='a long password' flowshop seed --no-orders
   ```

   This loads the four launch products and the admin account. It refuses to load test orders in production.
5. **Settings page.** Sign in and set the real bank details, office address, returns link and collection code.
6. **Staff accounts.** Add one account per staff member on the Staff page.

## Checks before customers use it

- [ ] `/healthz` returns `{"ok": true}`.
- [ ] The Netlify site shows live stock, and changing a quantity on the admin page shows up there within 30 seconds.
- [ ] A test order in the simulator reserves stock. The **+49 h** button doesn't exist in production, so check the release on staging, which has `FLOWSHOP_ALLOW_TIME_TRAVEL=true`.
- [ ] **Backup restore tested:** create a Neon branch from a point in time, point staging at it and sign in. Do this before go-live.
- [ ] Error alerts work: set `FLOWSHOP_SENTRY_DSN` and trigger a test error.
- [ ] An uptime check (for example UptimeRobot) watches `/healthz`.

## Release steps

1. Make and test the change locally. CI must pass.
2. Deploy to staging, and check it there with staff if the change affects them.
3. Back up production by creating a Neon branch named after the release.
4. Deploy production. Migrations run when the container starts.
5. If something goes wrong:
   - In Render, roll back to the previous deploy.
   - If a migration was the problem, point production at the backup branch.

## Costs

The Render starter plan is about $7 a month. The Neon free plan pauses an idle database, and the first request after a pause is slow. Before go-live, either move to Neon's paid plan, or add a 5-minute uptime ping to `/healthz` to keep it awake.
