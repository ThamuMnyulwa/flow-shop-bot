"""Admin page, inbox, public API, webhook and jobs endpoint."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from flowshop.app import app
from flowshop.config import get_settings
from flowshop.db import new_session
from flowshop.models import Conversation, ConversationMode, Message, Order, OrderStatus, Product
from tests.helpers import SimCustomer, csrf, texts

ADDRESS = "14 Jacaranda Street, Melville, Johannesburg, 2092"


@pytest.fixture
def client(shop):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def staff_client(client):
    token = csrf(client)
    r = client.post("/admin/login", data={"csrf": token, "email": "admin@floww.local", "password": "floww-admin",
                                          "next": "/admin"}, follow_redirects=False)
    assert r.status_code == 303
    client.headers["X-CSRF-Token"] = csrf_after_login(client)
    return client


def csrf_after_login(client):
    page = client.get("/admin").text
    marker = 'name="csrf" content="'
    start = page.index(marker) + len(marker)
    return page[start:page.index('"', start)]


def place_order(client, wa="27820000001"):
    c = SimCustomer(client, wa)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("2")
    c.tap("Checkout")
    c.tap("Delivery")
    c.say(ADDRESS)
    c.tap("Confirm order")
    s = new_session()
    order = s.scalar(select(Order).order_by(Order.id.desc()))
    s.close()
    return c, order


# ----- sign-in and protection ----------------------------------------------------

def test_admin_requires_sign_in(client):
    r = client.get("/admin/orders", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/admin/login")


def test_wrong_password_refused(client):
    r = client.post("/admin/login", data={"csrf": csrf(client), "email": "admin@floww.local", "password": "nope"})
    assert r.status_code == 401


def test_post_without_csrf_refused(staff_client):
    staff_client.headers.pop("X-CSRF-Token")
    r = staff_client.post("/admin/settings", data={"delivery_fee_cents": "0"})
    assert r.status_code == 403


def test_every_admin_page_renders(staff_client):
    place_order(staff_client)
    s = new_session()
    pid = s.scalar(select(Product.id))
    oid = s.scalar(select(Order.id))
    cid = s.scalar(select(Conversation.id))
    s.close()
    for path in ["/admin", "/admin/orders", "/admin/orders?status=attention", "/admin/orders?status=paid",
                 "/admin/orders/new", f"/admin/orders/{oid}", "/admin/products", "/admin/products/new",
                 f"/admin/products/{pid}", "/admin/settings", "/admin/staff", "/admin/reports",
                 "/admin/notifications", "/inbox", f"/inbox/{cid}", f"/inbox/{cid}/messages", "/simulator"]:
        r = staff_client.get(path)
        assert r.status_code == 200, (path, r.text[:300])


# ----- phase 1: staff change stock, the website API shows it --------------------------------

def test_stock_change_shows_on_public_api_at_once(staff_client):
    s = new_session()
    hw = s.scalar(select(Product).where(Product.code == "HW-01"))
    s.close()
    r = staff_client.post(f"/admin/products/{hw.id}/stock", data={"on_hand": "4", "note": "count"},
                          follow_redirects=False)
    assert r.status_code == 303
    api = staff_client.get("/api/products/HW-01").json()
    assert api["available"] == 4 and api["orderable"] is True
    assert api["order_url"].startswith("https://wa.me/") and "%5BHW-01%5D" in api["order_url"]


def test_public_api_lists_visible_products_only(staff_client):
    s = new_session()
    nb = s.scalar(select(Product).where(Product.code == "NB-01"))
    s.close()
    staff_client.post(f"/admin/products/{nb.id}", data={"code": "NB-01", "name": "Notebook", "price": "100",
                                                         "status": "hidden", "low_stock_threshold": "2"})
    codes = {p["code"]: p for p in staff_client.get("/api/products").json()["products"]}
    assert "NB-01" not in codes
    assert codes["MG-01"]["status"] == "launching_soon" and codes["MG-01"]["orderable"] is False
    assert staff_client.get("/api/products/NB-01").status_code == 404


def test_cors_allows_the_website_only_for_reads(client):
    r = client.get("/api/products", headers={"Origin": "http://localhost:8888"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:8888"
    r = client.get("/api/products", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_shop_info_for_disclosures(client):
    info = client.get("/api/shop").json()
    assert info["delivery_fee_cents"] == 20000 and info["payment_methods"] == ["EFT"]


def test_add_product_and_validation(staff_client):
    r = staff_client.post("/admin/products", data={"code": "hw-02", "name": "Headwrap Kente", "price": "120.50",
                                                    "status": "on_sale", "category": "Fashion", "on_hand": "5"},
                          follow_redirects=False)
    assert r.status_code == 303
    p = staff_client.get("/api/products/HW-02").json()
    assert p["price_cents"] == 12050 and p["available"] == 5
    r = staff_client.post("/admin/products", data={"code": "HW-03", "name": "A name that is far too long for WA",
                                                    "price": "100", "status": "on_sale"})
    assert "24 characters" in r.text


# ----- orders on the admin page ---------------------------------------------------

def test_staff_mark_paid_then_dispatch(staff_client):
    c, order = place_order(staff_client)
    r = staff_client.post(f"/admin/orders/{order.id}/dispatch", follow_redirects=True)
    assert "cannot become dispatched" in r.text  # P4: not before payment
    staff_client.post(f"/admin/orders/{order.id}/paid")
    assert "We received payment" in c.last_bot()["text"]
    staff_client.post(f"/admin/orders/{order.id}/dispatch")
    s = new_session()
    o = s.get(Order, order.id)
    assert o.status == OrderStatus.DISPATCHED
    assert [e.staff.name for e in o.events if e.staff] == ["Admin", "Admin"]  # A6
    assert s.scalar(select(Product).where(Product.code == "HW-01")).on_hand == 8
    s.close()


def test_staff_created_order(staff_client):
    s = new_session()
    hw = s.scalar(select(Product).where(Product.code == "HW-01"))
    s.close()
    r = staff_client.post("/admin/orders/new", data={"wa_id": "082 555 1234", "name": "Phone Customer",
                                                      f"qty_{hw.id}": "3", "fulfilment": "delivery",
                                                      "address": ADDRESS, "draft_key": "abc"}, follow_redirects=True)
    assert "Created FLW-" in r.text
    s = new_session()
    o = s.scalar(select(Order))
    assert o.customer.wa_id == "27825551234" and o.created_by_staff_id is not None
    s.close()


def test_return_is_written_off(staff_client):
    _, order = place_order(staff_client)
    staff_client.post(f"/admin/orders/{order.id}/paid")
    staff_client.post(f"/admin/orders/{order.id}/dispatch")
    s = new_session()
    hw = s.scalar(select(Product).where(Product.code == "HW-01"))
    s.close()
    r = staff_client.post(f"/admin/orders/{order.id}/returns", data={"product_id": hw.id, "quantity": "1",
                                                                       "reason": "Torn seam", "refund": "100"},
                          follow_redirects=True)
    assert "Return recorded" in r.text
    s = new_session()
    assert s.get(Product, hw.id).on_hand == 8  # not added back to sellable stock
    s.close()


def test_proof_files_need_sign_in(staff_client, client):
    c, order = place_order(staff_client)
    c.send_file()
    s = new_session()
    proof_id = s.get(Order, order.id).proofs[0].id
    s.close()
    assert staff_client.get(f"/admin/proofs/{proof_id}").status_code == 200
    with TestClient(app) as anon:
        assert anon.get(f"/admin/proofs/{proof_id}", follow_redirects=False).status_code == 303
        assert anon.get("/api/images/proofs/x.jpg").status_code == 404


def test_settings_change_collection_code(staff_client):
    r = staff_client.post("/admin/settings", data={"collection_code": "newcode9", "delivery_fee_cents": "250",
                                                   "free_delivery_over_cents": "1000"}, follow_redirects=True)
    assert "Settings saved" in r.text
    assert staff_client.get("/api/shop").json()["delivery_fee_cents"] == 25000
    c = SimCustomer(staff_client, "27820000005")
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("I have a code")
    assert "isn't valid" in texts(c.say("FLOWW2026"))  # the old code no longer works
    c.tap("Try again")
    assert "Collection from our office" in texts(c.say("NEWCODE9"))


# ----- inbox (I1, I2) ---------------------------------------------------------------

def test_inbox_reply_and_hand_back(staff_client):
    c = SimCustomer(staff_client)
    c.say("I want to speak to someone")
    s = new_session()
    conv = s.scalar(select(Conversation))
    s.close()
    assert "waiting since" in staff_client.get("/inbox").text
    staff_client.post(f"/inbox/{conv.id}/reply", data={"body": "Hi Thandi, how can I help?"})
    msgs = c.messages()
    assert msgs[-1]["text"] == "Hi Thandi, how can I help?" and msgs[-1]["staff"] == "Admin"  # I3
    s = new_session()
    conv = s.get(Conversation, conv.id)
    assert conv.mode == ConversationMode.HUMAN and conv.waiting_since is None
    s.close()
    staff_client.post(f"/inbox/{conv.id}/bot")
    assert "back with the FLOWW assistant" in c.last_bot()["text"]
    assert "Welcome" in texts(c.say("hi"))


def test_inbox_blocks_free_text_after_24_hours(staff_client, db):
    from datetime import timedelta

    from flowshop import clock

    c = SimCustomer(staff_client)
    c.say("talk to a person")
    clock.advance(db, timedelta(hours=25))
    db.commit()
    s = new_session()
    conv = s.scalar(select(Conversation))
    s.close()
    r = staff_client.post(f"/inbox/{conv.id}/reply", data={"body": "Sorry for the wait"}, follow_redirects=True)
    assert "approved template" in r.text


# ----- webhook (L1) and jobs (E12) ---------------------------------------------------

def signed(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook_rejects_bad_signature(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "wa_app_secret", "s3cret")
    r = client.post("/webhook", content=b'{"entry":[]}', headers={"X-Hub-Signature-256": "sha256=00"})
    assert r.status_code == 401


def test_webhook_processes_signed_message(client, monkeypatch):
    from flowshop.channels import webhook as wh

    monkeypatch.setattr(get_settings(), "wa_app_secret", "s3cret")
    body = json.dumps(wh.build_text_payload("27820000009", "Real Customer", "wamid.REAL1", "hi", 1)).encode()
    r = client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signed(body, "s3cret"),
                                                        "Content-Type": "application/json"})
    assert r.status_code == 200
    client.post("/webhook", content=body, headers={"X-Hub-Signature-256": signed(body, "s3cret")})  # retried
    s = new_session()
    assert len(s.scalars(select(Message).where(Message.direction == "out")).all()) == 1
    s.close()


def test_webhook_verification_handshake(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "wa_verify_token", "verify-me")
    ok = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "verify-me",
                                        "hub.challenge": "12345"})
    assert ok.status_code == 200 and ok.text == "12345"
    bad = client.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"})
    assert bad.status_code == 403


def test_status_updates_are_ignored(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "wa_app_secret", "s3cret")
    body = json.dumps({"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid.X", "status": "read"}]}}]}]})
    r = client.post("/webhook", content=body.encode(),
                    headers={"X-Hub-Signature-256": signed(body.encode(), "s3cret")})
    assert r.status_code == 200


def test_jobs_endpoint_needs_token(client):
    assert client.post("/jobs/run").status_code == 401
    r = client.post("/jobs/run", headers={"Authorization": "Bearer test-jobs-token"})
    assert r.status_code == 200 and r.json() == {"reminded": [], "released": []}


def test_time_travel_button_releases_overdue(staff_client):
    c, order = place_order(staff_client)
    r = staff_client.post("/admin/clock", data={"hours": "49"}, follow_redirects=True)
    assert "Stock released: 1" in r.text
    assert "no longer held" in c.last_bot()["text"]
    staff_client.post("/admin/clock", data={"reset": "true"})


def test_health(client):
    assert client.get("/healthz").json() == {"ok": True}


# ----- product photos -------------------------------------------------------------

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")


def upload_photo(staff_client, code, data=PNG, name="photo.png", content_type="image/png"):
    s = new_session()
    pid = s.scalar(select(Product.id).where(Product.code == code))
    s.close()
    return staff_client.post(f"/admin/products/{pid}/image", files={"image": (name, data, content_type)},
                             follow_redirects=True)


def test_photo_upload_shows_in_chat_api_and_admin(staff_client):
    assert "Photo saved" in upload_photo(staff_client, "HW-01").text
    api = staff_client.get("/api/products/HW-01").json()
    assert api["image_url"].startswith("http") and "/api/images/products/" in api["image_url"]
    path = "/api/images/" + api["image_url"].split("/api/images/")[1]
    img = staff_client.get(path)
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content == PNG
    assert 'class="thumb" src="/api/images/products/' in staff_client.get("/admin/products").text

    c = SimCustomer(staff_client)
    out = c.say("[HW-01]")
    product_msg = out[-1]
    assert product_msg["payload"]["image_path"] == path and "*Headwrap*" in product_msg["text"]
    assert [b["title"] for b in product_msg["payload"]["buttons"]] == ["Add to order", "Other products"]
    c.tap("Add to order")  # the buttons under the photo still work


def test_product_without_photo_is_plain_text(staff_client):
    c = SimCustomer(staff_client)
    out = c.say("[NB-01]")
    assert out[-1]["payload"]["image_path"] == ""


def test_photo_upload_rejects_non_images(staff_client):
    r = upload_photo(staff_client, "HW-01", data=b"<svg>not a photo</svg>", name="x.png")
    assert "Use a JPEG or PNG photo" in r.text
    assert staff_client.get("/api/products/HW-01").json()["image_url"] is None


def test_photo_shown_when_item_added_and_in_one_item_summary(staff_client):
    upload_photo(staff_client, "HW-01")
    c = SimCustomer(staff_client)
    c.say("[HW-01]")
    c.tap("Add to order")
    added = c.tap("2")[-1]
    assert "Added 2 × Headwrap" in added["text"] and added["payload"]["image_path"].startswith("/api/images/")
    c.tap("Checkout")
    c.tap("Delivery")
    summary = c.say("14 Jacaranda Street, Melville, Johannesburg, 2092")[-1]
    assert "Order summary" in summary["text"] and summary["payload"]["image_path"]


def test_multi_item_summary_is_text_only(staff_client):
    upload_photo(staff_client, "HW-01")
    c = SimCustomer(staff_client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Add more")
    c.tap("Notebook")
    c.tap("Add to order")
    assert c.tap("1")[-1]["payload"]["image_path"] == ""  # the notebook has no photo
    c.tap("Checkout")
    c.tap("Delivery")
    summary = c.say("14 Jacaranda Street, Melville, Johannesburg, 2092")[-1]
    assert summary["payload"]["image_path"] == ""
