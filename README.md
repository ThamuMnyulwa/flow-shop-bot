# FLOWW shop bot

WhatsApp ordering and stock management for the FLOWW shop. It is one FastAPI service with one PostgreSQL database, and it holds:

- stock and orders, with oversell protection
- a menu-driven ordering bot
- an admin page and a shared inbox for staff
- a fake WhatsApp chat for testing

The design is in [the PRD](docs/0_PRD%20WhatsApp%20ordering%20and%20stock%20management.md).

## Run it locally

**With Docker (one command):**

```sh
docker compose up --build
```

This starts the service, PostgreSQL and the scheduled-jobs container.

**Without Docker (uses a local PostgreSQL):**

```sh
createdb flowshop
cp .env.example .env    # then set FLOWSHOP_DATABASE_URL=postgresql+psycopg://localhost/flowshop
uv sync
uv run flowshop migrate
uv run flowshop seed
uv run flowshop serve --reload
```

Then open:

| Page | URL |
| --- | --- |
| Admin page | http://localhost:8000/admin (admin@floww.local / floww-admin) |
| Fake WhatsApp chat | http://localhost:8000/simulator |
| Shared inbox | http://localhost:8000/inbox |
| Product API for the website | http://localhost:8000/api/products |

The seed loads the four launch products at R100 with 10 units each, an admin account, two test orders and the collection code `FLOWW2026`.

**Moving time forward:** the yellow bar on the admin page moves the test clock, so you can check the 48-hour release and the dispatch dates in minutes. It is off in production.

## Tests

```sh
createdb flowshop_test
uv run pytest
```

The tests run against real PostgreSQL. They cover:

- Every stock rule, including two customers buying the last units at the same moment.
- Whole bot conversations through the simulator.
- The admin page, the inbox, the webhook and the jobs endpoint.

Set `FLOWSHOP_TEST_DATABASE_URL` to use another database.

## How it fits together

| Part | Code |
| --- | --- |
| Stock and order rules | `src/flowshop/services/stock.py`, `src/flowshop/services/orders.py` |
| Bot conversation, as a state machine stored in PostgreSQL | `src/flowshop/bot/engine.py` |
| Channel interface, shared by the simulator and WhatsApp | `src/flowshop/channels/` |
| Admin page, inbox and simulator | `src/flowshop/web/`, `src/flowshop/templates/` |
| AI assistant (phase 5, off by default) | `src/flowshop/bot/assistant.py` |
| Scheduled work: 48-hour release and payment reminders | `POST /jobs/run`, called every 15 minutes |
| Database migrations | `migrations/` (Alembic) |

## Order lifecycle

```
pending_payment ─proof─▶ proof_received ─staff verify─▶ paid ─▶ dispatched ─▶ delivered
      │                                                  └──▶ collected
      ├─48h, no proof─▶ payment_overdue ─late payment─▶ paid (stock reserved again if available)
      └─cancel─▶ cancelled
```

- Stock is reserved when the order is confirmed.
- Stock leaves on-hand at dispatch or collection.
- An order with proof of payment never expires.

## Guides

- [Deploy: dev and prod on Google Cloud Run and Neon](docs/deploy.md) (`scripts/deploy.sh dev|prod`)
- [Infrastructure as code](terraform/README.md)
- [Run with Docker, locally or on your own server](docs/self-host-docker.md)
- [Go live on WhatsApp](docs/go-live-whatsapp.md)
- [Connect the Netlify website](docs/website-integration.md)
