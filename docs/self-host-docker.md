# Running with Docker

There are two compose files:

| File | Use | Containers |
| --- | --- | --- |
| `docker-compose.yml` | Your own machine | `app`, `db`, `jobs` |
| `docker-compose.prod.yml` | A server, as an alternative to Google Cloud | `caddy`, `app`, `db`, `jobs`, `backup` |

Both use the same image that Cloud Run runs.

## On your machine

```sh
docker compose up --build
```

- **Admin page:** http://localhost:8000/admin. Sign in as `admin@floww.local` / `floww-admin`.
- **Simulator:** http://localhost:8000/simulator
- **Data:** sample data loads on start. The `jobs` container sends payment reminders and releases 48-hour holds every 15 minutes, as on the real servers.
- **Start over:** `docker compose down -v` deletes the database and files.

## On a server

Any Linux server with Docker works. A small VPS in Johannesburg or Cape Town keeps customer data in South Africa.

1. Point a domain at the server's IP address, for example `shop-api.floww.co.za`. Open ports 80 and 443.
2. Copy the repository to the server, then create the settings file:

   ```sh
   cp .env.prod.example .env.prod
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # run once per secret
   ```

   Fill in `SITE_DOMAIN`, `POSTGRES_PASSWORD`, `FLOWSHOP_SECRET_KEY`, `FLOWSHOP_JOBS_TOKEN`, `FLOWSHOP_ADMIN_PASSWORD` and `FLOWSHOP_CORS_ORIGINS`.
3. Start it, and create the first admin:

   ```sh
   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
   docker compose -f docker-compose.prod.yml --env-file .env.prod exec app flowshop seed --no-orders
   ```

4. Open `https://<your domain>/admin`. Caddy fetches the HTTPS certificate on the first request.

### What each container does

| Container | Job |
| --- | --- |
| `caddy` | HTTPS with an automatic certificate, and redirects plain HTTP to HTTPS |
| `app` | The service. It runs migrations on every start, and runs as an unprivileged user |
| `db` | PostgreSQL 16. Not reachable from the internet |
| `jobs` | Calls `/jobs/run` every 15 minutes: payment reminders and the 48-hour release |
| `backup` | A compressed database dump at 02:00 South African time, kept for 14 days |

### Updating

```sh
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup sh -c 'pg_dump --no-owner --clean --if-exists | gzip > /backups/before-update.sql.gz'
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

### Backups and restore

Backups are in the `backups` volume. Copy them off the server regularly, for example with a nightly `docker cp` or `rsync`, because a backup on the same disk doesn't survive losing that disk.

Restore a backup like this:

```sh
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup sh -c \
  'gunzip -c /backups/<file>.sql.gz | psql -q'
```

A restore was tested when this setup was built. Test it again before go-live, and every few months after that.
