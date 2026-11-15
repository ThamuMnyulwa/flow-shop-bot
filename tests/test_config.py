import pytest

from flowshop.config import Settings


@pytest.mark.parametrize("given", [
    "postgres://u:p@ep-x.eu-central-1.aws.neon.tech/flowshop?sslmode=require",
    "postgresql://u:p@ep-x.eu-central-1.aws.neon.tech/flowshop?sslmode=require",
    "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/flowshop?sslmode=require",
])
def test_database_url_accepted_as_neon_shows_it(given):
    url = Settings(database_url=given).database_url
    assert url == "postgresql+psycopg://u:p@ep-x.eu-central-1.aws.neon.tech/flowshop?sslmode=require"


def test_environment_banner():
    from fastapi.testclient import TestClient

    from flowshop.app import app
    from flowshop.config import get_settings

    settings = get_settings()
    original = settings.env
    try:
        with TestClient(app) as c:
            settings.env = "dev"
            assert "DEV: test data" in c.get("/admin/login").text
            settings.env = "production"
            assert "test data" not in c.get("/admin/login").text
    finally:
        settings.env = original


def test_prepared_statements_off_through_neon_pooler(monkeypatch):
    from flowshop import db

    seen = {}
    monkeypatch.setattr(db, "create_engine", lambda url, **kw: seen.setdefault(url, kw))
    pooled = "postgresql+psycopg://u:p@ep-x-pooler.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require"
    direct = "postgresql+psycopg://u:p@ep-x.c-2.eu-west-2.aws.neon.tech/neondb?sslmode=require"
    db._make_engine(pooled)
    db._make_engine(direct)
    assert seen[pooled]["connect_args"] == {"prepare_threshold": None}
    assert seen[direct]["connect_args"] == {}
