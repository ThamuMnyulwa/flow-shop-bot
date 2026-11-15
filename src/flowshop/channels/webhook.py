"""Parse Meta's webhook JSON and verify its signature. The simulator sends the same JSON shape (M1)."""

import hashlib
import hmac
from typing import Any

from flowshop.channels.base import InboundMessage


def verify_signature(app_secret: str, body: bytes, header: str | None) -> bool:
    """Meta signs each webhook with HMAC-SHA256 of the raw body, sent as 'sha256=<hex>' (L1)."""
    if not app_secret or not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse(payload: dict[str, Any]) -> list[InboundMessage]:
    """Return the customer messages in a webhook. Delivery statuses and other updates are ignored."""
    found: list[InboundMessage] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            names = {c.get("wa_id") or c.get("user_id"): (c.get("profile") or {}).get("name", "")
                     for c in value.get("contacts", []) or []}
            for msg in value.get("messages", []) or []:
                found.append(_parse_message(msg, names))
    return found


def _parse_message(msg: dict[str, Any], names: dict[str, str]) -> InboundMessage:
    sender = msg.get("from") or msg.get("from_user_id") or ""
    base = dict(message_id=msg.get("id", ""), wa_id=sender, name=names.get(sender, ""),
                timestamp=int(msg.get("timestamp") or 0))
    kind = msg.get("type")
    if kind == "text":
        return InboundMessage(kind="text", text=(msg.get("text") or {}).get("body", ""), **base)
    if kind == "interactive":
        inter = msg.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        return InboundMessage(kind="reply", reply_id=reply.get("id", ""), text=reply.get("title", ""), **base)
    if kind == "button":  # quick reply on a template
        btn = msg.get("button") or {}
        return InboundMessage(kind="reply", reply_id=btn.get("payload", ""), text=btn.get("text", ""), **base)
    if kind in ("image", "document"):
        media = msg.get(kind) or {}
        return InboundMessage(kind=kind, media_id=media.get("id", ""), mime_type=media.get("mime_type", ""),
                              text=media.get("caption", ""), **base)
    return InboundMessage(kind="unsupported", text=kind or "", **base)


def build_text_payload(wa_id: str, name: str, message_id: str, body: str, timestamp: int) -> dict:
    return _wrap(wa_id, name, {"from": wa_id, "id": message_id, "timestamp": str(timestamp), "type": "text",
                               "text": {"body": body}})


def build_reply_payload(wa_id: str, name: str, message_id: str, reply_id: str, title: str, timestamp: int,
                        list_reply: bool) -> dict:
    key = "list_reply" if list_reply else "button_reply"
    return _wrap(wa_id, name, {"from": wa_id, "id": message_id, "timestamp": str(timestamp), "type": "interactive",
                               "interactive": {"type": key, key: {"id": reply_id, "title": title}}})


def build_media_payload(wa_id: str, name: str, message_id: str, kind: str, media_id: str, mime_type: str,
                        timestamp: int) -> dict:
    return _wrap(wa_id, name, {"from": wa_id, "id": message_id, "timestamp": str(timestamp), "type": kind,
                               kind: {"id": media_id, "mime_type": mime_type}})


def _wrap(wa_id: str, name: str, message: dict) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "SIMULATOR", "changes": [{"field": "messages", "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "SIMULATOR", "phone_number_id": "SIMULATOR"},
            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
            "messages": [message],
        }}]}],
    }
