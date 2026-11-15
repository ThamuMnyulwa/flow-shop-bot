"""FLOWW shop: WhatsApp ordering and stock management."""

import argparse
import getpass
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="flowshop")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="run the web service")
    serve.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    serve.add_argument("--reload", action="store_true")
    sub.add_parser("migrate", help="apply database migrations")
    seed = sub.add_parser("seed", help="load sample data")
    seed.add_argument("--no-orders", action="store_true", help="catalogue and staff account only")
    staff = sub.add_parser("create-staff", help="add a staff account")
    staff.add_argument("email")
    staff.add_argument("name")
    staff.add_argument("--admin", action="store_true")
    sub.add_parser("run-jobs", help="run scheduled work once: payment reminders and the 48-hour release")
    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn

        uvicorn.run("flowshop.app:app", host=args.host, port=args.port, reload=args.reload, proxy_headers=True,
                    forwarded_allow_ips="*")
    elif args.command == "migrate":
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(os.path.join(os.getcwd(), "alembic.ini")), "head")
    elif args.command == "seed":
        from flowshop.config import get_settings
        from flowshop.db import session_scope
        from flowshop.seed import seed_all

        password = os.environ.get("FLOWSHOP_ADMIN_PASSWORD", "")
        env = get_settings().env
        # Anywhere reachable from the internet, the first admin needs a real password, never the default.
        if env != "local" and len(password) < 12:
            sys.exit(f"In {env}, set FLOWSHOP_ADMIN_PASSWORD (12+ characters) before seeding.")
        if env == "production" and not args.no_orders:
            sys.exit("Test orders are never loaded in production. Use seed --no-orders.")
        with session_scope() as db:
            seed_all(db, with_orders=not args.no_orders, admin_password=password or "floww-admin")
        shown = "the password you set" if password else "floww-admin (change it)"
        print(f"Seeded. Admin sign-in: admin@floww.local / {shown}. Collection code: FLOWW2026")
    elif args.command == "create-staff":
        from flowshop import clock
        from flowshop.auth import hash_password
        from flowshop.db import session_scope
        from flowshop.models import Staff

        password = getpass.getpass("Password: ")
        if len(password) < 10:
            sys.exit("Use at least 10 characters.")
        with session_scope() as db:
            db.add(Staff(email=args.email.lower(), name=args.name, password_hash=hash_password(password),
                         is_admin=args.admin, created_at=clock.now(db)))
        print(f"Created {args.email}")
    elif args.command == "run-jobs":
        from flowshop.db import session_scope
        from flowshop.jobs import run_all

        with session_scope() as db:
            print(run_all(db))
