"""Phase 5: the AI assistant answers from the product data, and staff take over when it is unsure."""

import json
from types import SimpleNamespace

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

from flowshop.app import app
from flowshop.bot import assistant
from flowshop.config import get_settings
from tests.helpers import SimCustomer, texts


class FakeMessages:
    def __init__(self, reply=None, error=None, stop_reason="end_turn"):
        self.reply, self.error, self.stop_reason = reply, error, stop_reason
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        block = SimpleNamespace(type="text", text=json.dumps(self.reply))
        return SimpleNamespace(stop_reason=self.stop_reason, content=[block])


def fake_client(monkeypatch, **kwargs):
    messages = FakeMessages(**kwargs)
    monkeypatch.setattr(assistant, "_client", lambda: SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    return messages


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_enabled", True)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")


@pytest.fixture
def client(shop):
    with TestClient(app) as c:
        yield c


def test_confident_answer_is_sent(client, ai, monkeypatch):
    fake = fake_client(monkeypatch, reply={"answer": "Yes, the Shea Butter Cream is natural and costs R100.",
                                           "confident": True})
    c = SimCustomer(client)
    out = c.say("is it safe for sensitive skin and natural??")
    assert "Shea Butter Cream is natural" in texts(out)
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    data = call["messages"][0]["content"]
    assert '"price": "R100"' in data and "Headwrap" in data  # grounded in the live catalogue
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}  # stable prompt, cached


def test_unsure_answer_falls_back_to_staff(client, ai, monkeypatch):
    fake_client(monkeypatch, reply={"answer": "Not sure.", "confident": False})
    c = SimCustomer(client)
    assert "didn't catch that" in texts(c.say("can you recommend a good lawyer"))
    assert "passing you to our team" in texts(c.say("what about my tax return"))


def test_api_errors_hand_off_without_breaking_the_chat(client, ai, monkeypatch):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    fake_client(monkeypatch, error=anthropic.APIConnectionError(request=request))
    c = SimCustomer(client)
    assert "didn't catch that" in texts(c.say("qwerty question"))


def test_refusal_is_not_shown(client, ai, monkeypatch):
    fake_client(monkeypatch, reply={"answer": "x", "confident": True}, stop_reason="refusal")
    c = SimCustomer(client)
    assert "didn't catch that" in texts(c.say("something odd"))


def test_assistant_off_by_default(client, monkeypatch):
    fake = fake_client(monkeypatch, reply={"answer": "hi", "confident": True})
    c = SimCustomer(client)
    c.say("random words here")
    assert fake.calls == []


def test_menus_still_win_over_the_assistant(client, ai, monkeypatch):
    fake = fake_client(monkeypatch, reply={"answer": "x", "confident": True})
    c = SimCustomer(client)
    c.say("notebook")  # a product search the menus handle
    assert fake.calls == []
