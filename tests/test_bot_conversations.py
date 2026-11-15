"""E7: whole bot conversations through the simulator channel, from first message to confirmed order."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from flowshop.app import app
from flowshop.db import new_session
from flowshop.models import Conversation, ConversationMode, Message, Order, OrderStatus, Product
from tests.helpers import SimCustomer, csrf, texts

ADDRESS = "14 Jacaranda Street, Melville, Johannesburg, 2092"


@pytest.fixture
def client(shop):
    with TestClient(app) as c:
        yield c


def product(code):
    s = new_session()
    try:
        return s.scalar(select(Product).where(Product.code == code))
    finally:
        s.close()


def orders_for(wa_id):
    s = new_session()
    try:
        return s.scalars(select(Order).join(Order.customer).where(Order.customer.has(wa_id=wa_id))).all()
    finally:
        s.close()


def test_browse_to_confirmed_order_within_ten_messages(client):
    c = SimCustomer(client)
    out = c.say("hi")
    assert "Welcome to FLOWW" in texts(out)
    out = c.tap("Browse products")
    browse = out[-1]
    assert browse["kind"] == "carousel"  # swipeable cards with photos, no category step
    cards = browse["payload"]["cards"]
    assert [c["body"].split(" · ")[0] for c in cards] == ["*Headwrap*", "*Notebook*", "*Shea Butter Cream*",
                                                          "*FLOWW Mug*"]
    assert "10 available" in cards[0]["body"] and cards[0]["image_path"]  # placeholder until a photo is uploaded
    assert [b["title"] for b in cards[3]["buttons"]] == ["More info"]  # the mug can't be ordered yet
    c.tap_card("Headwrap", "Add to order")
    out = c.tap("2")
    assert "Headwrap × 2: R200" in texts(out)
    out = c.tap("Checkout")
    assert "Delivery costs R200" in texts(out)
    c.tap("Delivery")
    out = c.say(ADDRESS)
    summary = texts(out)
    assert "Total: R400" in summary and "3 working days" in summary and "Returns:" in summary
    out = c.tap("Confirm order")
    text = texts(out)
    assert "is confirmed" in text and "R400" in text and "Reference: *FLW-" in text
    assert product("HW-01").reserved == 2
    bot_messages = [m for m in c.messages() if m["direction"] == "out"]
    assert len(bot_messages) <= 10


def test_website_link_starts_with_the_product(client):
    c = SimCustomer(client)
    out = c.say("Hi, I'd like to order Notebook [NB-01]")
    assert "*Notebook* · R100" in texts(out)
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("Delivery")
    c.say(ADDRESS)
    c.tap("Confirm order")
    assert len([m for m in c.messages() if m["direction"] == "out"]) <= 7


def test_search_by_name_shows_price_and_availability(client):
    c = SimCustomer(client)
    out = c.say("do you have shea butter?")
    # One match opens the product straight away: price, live availability and the add button.
    assert "*Shea Butter Cream* · R100" in texts(out) and "10 available" in texts(out)
    assert "Add to order" in [b["title"] for b in out[-1]["payload"]["buttons"]]


def test_search_with_several_matches_shows_cards(client):
    c = SimCustomer(client)
    out = c.say("floww")  # the notebook and the mug both mention FLOWW
    assert out[-1]["kind"] == "carousel" and len(out[-1]["payload"]["cards"]) == 2


def test_more_info_on_a_launching_soon_card(client):
    c = SimCustomer(client)
    c.say("hi")
    c.tap("Browse products")
    out = c.tap_card("FLOWW Mug", "More info")
    assert "can't take orders" in texts(out)


def test_launching_soon_is_shown_but_not_orderable(client):
    c = SimCustomer(client)
    out = c.say("[MG-01]")
    assert "Launching soon" in texts(out) and "can't take orders" in texts(out)
    assert "Add to order" not in [b["title"] for b in out[-1]["payload"]["buttons"]]


def test_quantity_above_stock_is_refused(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    out = c.say("11")
    assert "only 10 Headwrap available" in texts(out)


def test_edit_and_remove_items(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("2")
    c.tap("Add more")
    c.tap_card("Notebook", "Add to order")
    out = c.tap("1")
    assert "Products: R300" in texts(out)
    c.tap("Edit order")
    c.tap("Headwrap")
    c.tap("Change quantity")
    out = c.tap("3")
    assert "Headwrap × 3" in texts(out) and "Products: R400" in texts(out)
    c.tap("Edit order")
    c.tap("Notebook")
    out = c.tap("Remove")
    assert "Notebook" not in texts(out) and "Products: R300" in texts(out)


def test_free_delivery_above_r1000(client):
    c = SimCustomer(client)
    s = new_session()
    s.get(Product, product("HW-01").id).price_cents = 60000
    s.commit()
    s.close()
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("2")
    c.tap("Checkout")
    c.tap("Delivery")
    out = c.say(ADDRESS)
    assert "Delivery: free" in texts(out) and "Total: R1 200" in texts(out)


def test_collection_with_valid_code(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("I have a code")
    out = c.say("floww2026")
    summary = texts(out)
    assert "Collection from our office" in summary and "Total: R100" in summary
    assert "address" in summary.lower() and "once you've paid" in summary
    c.tap("Confirm order")
    (order,) = orders_for(c.wa_id)
    assert order.fulfilment.value == "collection" and order.delivery_fee_cents == 0


def test_wrong_code_offers_delivery_and_locks_after_three(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("I have a code")
    for attempt in ("WRONG1", "WRONG2"):
        out = c.say(attempt)
        assert "isn't valid" in texts(out) and "deliver" in texts(out)
        c.tap("Try again")
    out = c.say("WRONG3")
    assert "Try again" not in [b["title"] for b in out[-1]["payload"]["buttons"]]
    out = c.tap("Cancel")
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    out = c.tap("Checkout")
    assert [b["title"] for b in out[-1]["payload"]["buttons"]] == ["Delivery"]  # locked: delivery only


def test_no_code_set_means_no_collection(client, db):
    from flowshop.services import settings

    settings.put(db, "collection_code", "")
    db.commit()
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("I have a code")
    out = c.say("FLOWW2026")
    assert "isn't valid" in texts(out)


def test_double_tap_confirm_creates_one_order(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("Delivery")
    c.say(ADDRESS)
    c.tap("Confirm order")
    c.tap("Confirm order")
    assert len(orders_for(c.wa_id)) == 1
    assert product("HW-01").reserved == 1


def test_someone_else_buys_the_last_units_first(client):
    a, b = SimCustomer(client), SimCustomer(client, "27820000002", "Sipho Test")
    for who, qty in ((a, "8"), (b, "5")):
        who.say("[HW-01]")
        who.tap("Add to order")
        who.say(qty)
        who.tap("Checkout")
        who.tap("Delivery")
        who.say(ADDRESS)
    a.tap("Confirm order")
    out = b.tap("Confirm order")
    assert "only 2 Headwrap left" in texts(out)
    assert "Headwrap × 2" in texts(out)  # the bot offers what is left
    b.tap("Confirm order")
    assert product("HW-01").reserved == 10


def test_proof_of_payment_then_staff_mark_paid(client, shop):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("1")
    c.tap("Checkout")
    c.tap("Delivery")
    c.say(ADDRESS)
    c.tap("Confirm order")
    out = c.send_file()
    assert "received your proof of payment" in texts(out)
    (order,) = orders_for(c.wa_id)
    assert order.status == OrderStatus.PROOF_RECEIVED
    s = new_session()
    from flowshop.services import orders

    o = s.get(Order, order.id)
    orders.mark_paid(s, o, s.get(type(shop["staff"]), shop["staff"].id))
    s.commit()
    s.close()
    assert "We received payment" in c.last_bot()["text"]


def test_ask_for_a_person_hands_off_and_bot_goes_quiet(client):
    c = SimCustomer(client)
    out = c.say("can I talk to a person please")
    assert "passing you to our team" in texts(out)
    assert c.say("hello?") == []  # the bot stays quiet while staff have the chat
    s = new_session()
    conv = s.scalar(select(Conversation))
    assert conv.mode == ConversationMode.HUMAN and conv.waiting_since is not None
    s.close()


def test_two_misunderstood_messages_hand_off(client):
    c = SimCustomer(client)
    out = c.say("qwertyuiop")
    assert "didn't catch that" in texts(out)
    out = c.say("zxcvbnm asdf")
    assert "passing you to our team" in texts(out)


def test_my_order_and_cancel_in_chat(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("3")
    c.tap("Checkout")
    c.tap("Delivery")
    c.say(ADDRESS)
    c.tap("Confirm order")
    out = c.say("my order")
    assert "waiting for payment of R500" in texts(out)
    c.tap("Cancel order")
    out = c.tap("Yes, cancel")
    assert "has been cancelled" in texts(out)
    assert product("HW-01").reserved == 0


def test_conversation_state_survives_restart(client):
    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("2")
    with TestClient(app) as fresh:  # a new process sees the same state from PostgreSQL
        c.client = fresh
        c.token = csrf(fresh)
        out = c.tap("Checkout")
    assert "Delivery costs" in texts(out)


def test_idle_draft_expires(client, db):
    from datetime import timedelta

    from flowshop import clock

    c = SimCustomer(client)
    c.say("[HW-01]")
    c.tap("Add to order")
    c.tap("2")
    clock.advance(db, timedelta(hours=25))
    db.commit()
    out = c.say("hi")
    assert "Welcome" in texts(out)
    assert "View my order" not in [b["title"] for b in out[-1]["payload"]["buttons"]]


def test_duplicate_delivery_is_processed_once(client):
    from flowshop.channels import webhook as wh

    c = SimCustomer(client)
    payload = wh.build_text_payload(c.wa_id, c.name, "wamid.DUPLICATE", "hi", 1700000000)
    from flowshop.bot.engine import handle_inbound

    s = new_session()
    assert handle_inbound(s, wh.parse(payload)[0]) is True
    s.commit()
    assert handle_inbound(s, wh.parse(payload)[0]) is False
    s.commit()
    assert s.scalar(select(Message).where(Message.external_id == "wamid.DUPLICATE")) is not None
    assert len([m for m in c.messages() if m["direction"] == "out"]) == 1
    s.close()


def test_marketing_opt_in_is_separate(client):
    c = SimCustomer(client)
    out = c.say("SUBSCRIBE")
    assert "subscribed" in texts(out)
    out = c.say("STOP")
    assert "won't receive" in texts(out)


def test_malformed_button_id_returns_to_menu(client):
    c = SimCustomer(client)
    c._post("/simulator/reply", json={"wa_id": c.wa_id, "name": c.name, "reply_id": "prod:not-a-number",
                                      "title": "x"})
    assert "Welcome" in c.last_bot()["text"]


def test_simulator_off_when_whatsapp_is_live(client, monkeypatch):
    from flowshop.config import get_settings

    monkeypatch.setattr(get_settings(), "channel", "whatsapp")
    assert client.get("/simulator").status_code == 404
