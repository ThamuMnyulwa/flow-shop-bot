# One image for every environment (E11): local, staging and production run this unchanged.
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
RUN useradd --create-home --uid 1000 app
WORKDIR /app
# Local file storage lives here. Creating it as the app user means a mounted volume inherits that owner.
RUN mkdir -p /app/var/storage && chown -R app:app /app/var
COPY --from=build --chown=app /app/.venv /app/.venv
COPY --chown=app src ./src
COPY --chown=app alembic.ini ./
COPY --chown=app migrations ./migrations
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8000
EXPOSE 8000
# The entrypoint fixes ownership of a mounted storage disk, then drops to the app user.
ENTRYPOINT ["docker-entrypoint.sh"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"
# Migrations run on start, so a deploy and its schema change go out together (E5).
# FLOWSHOP_SEED_ON_START=true (dev only) loads the sample catalogue, staff account and test orders; it is idempotent
# and refuses to run in production.
CMD ["sh", "-c", "flowshop migrate && if [ \"$FLOWSHOP_SEED_ON_START\" = true ]; then flowshop seed; fi && flowshop serve --host $HOST --port $PORT"]
