import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from flowshop.auth import LoginRequired
from flowshop.config import get_settings
from flowshop.web import admin, api, inbox, simulator, webhook

HERE = Path(__file__).parent


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format='{"time":"%(asctime)s","level":"%(levelname)s",'
                        '"logger":"%(name)s","message":"%(message)s"}')
    if settings.sentry_dsn:
        import sentry_sdk  # optional dependency: uv add sentry-sdk

        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env)
    if settings.env == "production" and settings.secret_key == "dev-only-change-me":
        raise RuntimeError("Set FLOWSHOP_SECRET_KEY in production.")
    if settings.env == "production" and settings.allow_time_travel:
        raise RuntimeError("Time travel must be off in production.")

    _check_storage(settings)

    app = FastAPI(title="FLOWW shop", docs_url="/api/docs" if settings.env != "production" else None,
                  redoc_url=None)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="floww_session",
                       max_age=12 * 3600, same_site="lax", https_only=settings.base_url.startswith("https"))
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_methods=["GET"],
                       allow_headers=[])
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    app.include_router(api.router)
    app.include_router(webhook.router)
    app.include_router(admin.router)
    app.include_router(inbox.router)
    app.include_router(simulator.router)

    @app.exception_handler(LoginRequired)
    async def to_login(request: Request, exc: LoginRequired):
        if request.headers.get("hx-request"):
            return RedirectResponse("/admin/login", status_code=200, headers={"HX-Redirect": "/admin/login"})
        return RedirectResponse(f"/admin/login?next={request.url.path}", status_code=303)

    @app.get("/")
    def home():
        return RedirectResponse("/admin")

    @app.get("/healthz")
    def health():
        """Liveness, without touching the database, so health checks and uptime monitors never keep Neon awake.
        `version` is the commit built into the image; scripts/deploy.sh checks it after each deploy."""
        return {"ok": True, "version": settings.version}

    @app.get("/healthz/db")
    def health_db():
        from sqlalchemy import text

        from flowshop.db import session_scope

        with session_scope() as db:
            db.execute(text("SELECT 1"))
        return {"ok": True, "version": settings.version}

    return app


def _check_storage(settings) -> None:
    """Fail at start-up if file storage isn't writable, instead of losing the first photo or proof of payment."""
    if settings.storage_backend != "local":
        return
    root = Path(settings.storage_dir)
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-check"
        probe.write_text("ok")
        probe.unlink()
    except OSError as exc:
        raise RuntimeError(f"File storage at {root} is not writable: {exc}") from exc


app = create_app()
