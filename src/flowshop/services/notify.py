"""Sending to customers and alerting staff.

Free-form messages go out only within 24 hours of the customer's last message. Later messages use an
approved template, or are skipped and flagged to staff when no template fits.
"""

import logging
import smtplib
from datetime import timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowshop import clock
from flowshop.channels import get_channel
from flowshop.channels.base import OutMessage
from flowshop.channels.base import template as template_message
from flowshop.channels.base import text as text_message
from flowshop.config import get_settings
from flowshop.models import Conversation, Customer, Direction, Message, Notification, Staff

log = logging.getLogger(__name__)
WINDOW = timedelta(hours=24)


class OutsideWindow(Exception):
    pass


def conversation_for(db: Session, customer: Customer) -> Conversation:
    conv = db.scalar(select(Conversation).where(Conversation.customer_id == customer.id))
    if conv is None:
        conv = Conversation(customer_id=customer.id, data={}, last_activity_at=clock.now(db))
        db.add(conv)
        db.flush()
    return conv


def in_window(db: Session, conv: Conversation) -> bool:
    return conv.last_inbound_at is not None and clock.now(db) - conv.last_inbound_at < WINDOW


def send(db: Session, conv: Conversation, message: OutMessage, sender: str = "bot",
         staff: Staff | None = None) -> Message:
    if message.kind != "template" and not in_window(db, conv):
        raise OutsideWindow("More than 24 hours since the customer's last message: use a template.")
    stored = Message(conversation_id=conv.id, direction=Direction.OUT, sender=sender,
                     staff_id=staff.id if staff else None, kind=message.kind, text=message.text,
                     payload=message.to_payload(), created_at=clock.now(db))
    db.add(stored)
    db.flush()
    try:
        external_id = get_channel().send(conv.customer.wa_id, message)
    except Exception as exc:  # keep the record, show the failure in the inbox
        log.exception("send failed for conversation %s", conv.id)
        stored.payload = {**stored.payload, "error": str(exc)[:500]}
    else:
        stored.external_id = external_id
    conv.last_activity_at = clock.now(db)
    db.flush()
    return stored


def customer(db: Session, cust: Customer, text: str, template: str | None = None,
             params: list[str] | None = None) -> Message | None:
    """Tell a customer about their order: free text in the window, otherwise the named template (L2)."""
    conv = conversation_for(db, cust)
    if in_window(db, conv):
        return send(db, conv, text_message(text))
    if template:
        settings = get_settings()
        name = {"order_update": settings.wa_template_order_update,
                "payment_reminder": settings.wa_template_payment_reminder}[template]
        return send(db, conv, template_message(name, params or [], text))
    staff(db, "unsent", f"Could not message {cust.wa_id} (outside 24 hours): {text}", f"/inbox/{conv.id}")
    return None


def staff(db: Session, kind: str, text: str, link: str = "") -> Notification:
    """Staff alert (A5, S5): always shown on the admin page, and emailed when SMTP is configured."""
    note = Notification(kind=kind, text=text, link=link, created_at=clock.now(db))
    db.add(note)
    db.flush()
    _email(text, link)
    return note


def _email(text: str, link: str) -> None:
    s = get_settings()
    if not (s.smtp_host and s.alert_email_to and s.alert_email_from):
        return
    msg = EmailMessage()
    msg["Subject"] = f"FLOWW shop: {text[:70]}"
    msg["From"] = s.alert_email_from
    msg["To"] = s.alert_email_to
    msg.set_content(f"{text}\n\n{s.base_url}{link}")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except Exception:
        log.exception("alert email failed")
