import os

TEST_DB = os.environ.get("FLOWSHOP_TEST_DATABASE_URL", "postgresql+psycopg://localhost/flowshop_test")
os.environ["FLOWSHOP_DATABASE_URL"] = TEST_DB
os.environ["FLOWSHOP_ALLOW_TIME_TRAVEL"] = "true"
os.environ["FLOWSHOP_CHANNEL"] = "simulator"
os.environ["FLOWSHOP_JOBS_TOKEN"] = "test-jobs-token"
os.environ["FLOWSHOP_SMTP_HOST"] = ""
os.environ.setdefault("FLOWSHOP_STORAGE_DIR", "/tmp/flowshop-test-storage")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from flowshop import db as dbmod  # noqa: E402
from flowshop.channels import set_channel  # noqa: E402
from flowshop.channels.simulator import SimulatorChannel  # noqa: E402
from flowshop.db import Base  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(__file__))


@pytest.fixture(scope="session", autouse=True)
def migrated():
    engine = create_engine(TEST_DB)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    engine.dispose()
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    command.upgrade(cfg, "head")  # the tests run on the real migrations (E5)
    dbmod.reset_engine(TEST_DB)
    yield


class RecordingChannel(SimulatorChannel):
    def __init__(self):
        self.sent = []

    def send(self, to, message):
        super().send(to, message)
        self.sent.append((to, message))
        return f"sim.{len(self.sent)}"


@pytest.fixture(autouse=True)
def clean(migrated):
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with dbmod.get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    channel = RecordingChannel()
    set_channel(channel)
    yield channel
    set_channel(None)


@pytest.fixture
def channel(clean):
    return clean


@pytest.fixture
def db():
    session = dbmod.new_session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def shop(db):
    """The launch catalogue and an admin, committed so other sessions can see them."""
    from flowshop.seed import seed_catalogue, seed_staff
    from flowshop.services import settings

    products = seed_catalogue(db)
    staff = seed_staff(db)
    settings.put(db, "collection_code", "FLOWW2026")
    db.commit()
    return {"products": {p.code: p for p in products}, "staff": staff}
