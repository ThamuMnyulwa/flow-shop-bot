"""Phase 3: the Cloud API channel maps our messages onto PyWa, and the webhook parser reads Meta's JSON."""

from types import SimpleNamespace

import pytest
from pywa.types import Button, SectionList

from flowshop.channels import base, webhook
from flowshop.channels.whatsapp import WhatsAppChannel
from flowshop.config import Settings


class FakePyWa:
    def __init__(self):
        self.calls = []

    def send_message(self, **kwargs):
        self.calls.append(("send_message", kwargs))
        return SimpleNamespace(id="wamid.OUT1")

    def send_image(self, **kwargs):
        self.calls.append(("send_image", kwargs))
        return SimpleNamespace(id="wamid.OUT3")

    def send_template(self, **kwargs):
        self.calls.append(("send_template", kwargs))
        return SimpleNamespace(id="wamid.OUT2")

    def get_media_url(self, media_id):
        return SimpleNamespace(url=f"https://lookaside.example/{media_id}", mime_type="image/jpeg")

    def get_media_bytes(self, url):
        return b"jpeg-bytes"


@pytest.fixture
def wa():
    fake = FakePyWa()
    return WhatsAppChannel(Settings(wa_phone_id="1", wa_token="t", wa_template_language="en"), client=fake), fake


def test_text(wa):
    channel, fake = wa
    assert channel.send("27820000001", base.text("Hello")) == "wamid.OUT1"
    assert fake.calls[0] == ("send_message", {"to": "27820000001", "text": "Hello"})


def test_reply_buttons(wa):
    channel, fake = wa
    channel.send("2782", base.buttons("Pick", ("a", "One"), ("b", "Two")))
    sent = fake.calls[0][1]["buttons"]
    assert all(isinstance(b, Button) for b in sent) and [b.callback_data for b in sent] == ["a", "b"]


def test_buttons_under_a_product_photo(wa):
    channel, fake = wa
    photo = ("https://shop.example/api/images/products/a.png", "/api/images/products/a.png")
    channel.send("2782", base.buttons("*Headwrap* · R100", ("add:1", "Add to order"), image=photo))
    name, kwargs = fake.calls[0]
    assert name == "send_image" and kwargs["image"] == photo[0] and kwargs["caption"] == "*Headwrap* · R100"
    assert [b.callback_data for b in kwargs["buttons"]] == ["add:1"]


def test_list(wa):
    channel, fake = wa
    channel.send("2782", base.menu_list("Choose", [base.Row("prod:1", "Headwrap", "R100")], "View"))
    section_list = fake.calls[0][1]["buttons"]
    assert isinstance(section_list, SectionList) and section_list.button_title == "View"
    assert section_list.sections[0].rows[0].callback_data == "prod:1"


def test_template(wa):
    channel, fake = wa
    channel.send("2782", base.template("order_update", ["FLW-1010", "paid"], "preview"))
    name, kwargs = fake.calls[0]
    assert name == "send_template" and kwargs["name"] == "order_update"
    assert kwargs["params"] == [{"type": "body", "parameters": [{"type": "text", "text": "FLW-1010"},
                                                                {"type": "text", "text": "paid"}]}]


def test_media(wa):
    channel, _ = wa
    assert channel.fetch_media("MEDIA1") == (b"jpeg-bytes", "image/jpeg")


def test_whatsapp_limits_enforced():
    with pytest.raises(base.ChannelLimitError):
        base.buttons("x", ("1", "a"), ("2", "b"), ("3", "c"), ("4", "d"))
    with pytest.raises(base.ChannelLimitError):
        base.buttons("x", ("1", "A button title that is too long"))
    with pytest.raises(base.ChannelLimitError):
        base.menu_list("x", [base.Row(str(i), str(i)) for i in range(11)])


def test_parse_real_meta_payloads():
    """Shapes as Meta documents them: text, button reply, list reply, image, and a status update."""
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "27100000000", "phone_number_id": "PHONE"},
        "contacts": [{"profile": {"name": "Naledi"}, "wa_id": "27831234567"}],
        "messages": [
            {"from": "27831234567", "id": "wamid.A", "timestamp": "1731667200", "type": "text", "text": {"body": "hi"}},
            {"from": "27831234567", "id": "wamid.B", "timestamp": "1731667201", "type": "interactive",
             "interactive": {"type": "button_reply", "button_reply": {"id": "browse", "title": "Browse products"}}},
            {"from": "27831234567", "id": "wamid.C", "timestamp": "1731667202", "type": "interactive",
             "interactive": {"type": "list_reply", "list_reply": {"id": "prod:3", "title": "Notebook",
                                                                  "description": "R100"}}},
            {"from": "27831234567", "id": "wamid.D", "timestamp": "1731667203", "type": "image",
             "image": {"id": "MEDIA9", "mime_type": "image/jpeg", "sha256": "x"}},
            {"from": "27831234567", "id": "wamid.E", "timestamp": "1731667204", "type": "sticker",
             "sticker": {"id": "S1"}},
        ],
        "statuses": [{"id": "wamid.OUT", "status": "delivered"}],
    }
    payload = {"object": "whatsapp_business_account",
               "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": value}]}]}
    msgs = webhook.parse(payload)
    assert [m.kind for m in msgs] == ["text", "reply", "reply", "image", "unsupported"]
    assert msgs[0].name == "Naledi" and msgs[0].wa_id == "27831234567"
    assert msgs[1].reply_id == "browse" and msgs[2].reply_id == "prod:3"
    assert msgs[3].media_id == "MEDIA9"


def test_signature():
    body = b'{"a":1}'
    import hashlib
    import hmac

    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert webhook.verify_signature("secret", body, good)
    assert not webhook.verify_signature("secret", body + b" ", good)
    assert not webhook.verify_signature("", body, good)  # no secret configured: refuse everything
