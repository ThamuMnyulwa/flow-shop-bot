"""Behaviour the Cloud Run deployment relies on."""

from fastapi.testclient import TestClient

from flowshop.app import app
from flowshop.config import get_settings


def test_healthz_never_touches_the_database(monkeypatch, shop):
    """Health checks and uptime monitors must not wake Neon, or scale-to-zero never happens."""
    import flowshop.db as db

    def no_db(*args, **kwargs):
        raise AssertionError("/healthz opened a database session")

    monkeypatch.setattr(db, "session_scope", no_db)
    monkeypatch.setattr(get_settings(), "version", "abc1234")
    with TestClient(app) as c:
        assert c.get("/healthz").json() == {"ok": True, "version": "abc1234"}


def test_healthz_db_checks_the_database(shop):
    with TestClient(app) as c:
        assert c.get("/healthz/db").json()["ok"] is True


def test_gcs_storage_round_trip(monkeypatch):
    import types

    from flowshop import storage

    blobs = {}

    class Blob:
        def __init__(self, key):
            self.key = key

        def upload_from_string(self, data, content_type):
            blobs[self.key] = (data, content_type)

        def download_as_bytes(self):
            return blobs[self.key][0]

    class Bucket:
        def __init__(self, name):
            self.name = name

        def blob(self, key):
            return Blob(key)

    import google.cloud.storage as real_gcs

    monkeypatch.setattr(real_gcs, "Client", lambda: types.SimpleNamespace(bucket=Bucket))

    gcs = storage.GCSStorage("floww-shop-dev-files")
    key = gcs.put("proofs", b"%PDF proof", "application/pdf")
    assert key.startswith("proofs/") and key.endswith(".pdf")
    assert blobs[key] == (b"%PDF proof", "application/pdf")
    assert gcs.get(key) == b"%PDF proof"
