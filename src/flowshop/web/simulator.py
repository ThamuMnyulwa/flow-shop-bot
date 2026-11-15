"""The fake WhatsApp chat (M1, M2). It builds the same webhook JSON Meta sends and feeds it to the same handler."""

import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from flowshop.auth import LoginRequired, current_staff, verify_csrf
from flowshop.bot.engine import handle_inbound
from flowshop.channels import webhook as wh
from flowshop.config import get_settings
from flowshop.db import get_db
from flowshop.models import Conversation, Customer, Event, Message
from flowshop.storage import get_storage
from flowshop.web.common import render

router = APIRouter(prefix="/simulator", dependencies=[Depends(verify_csrf)])

TEST_CUSTOMERS = [("27820000001", "Thandi Test"), ("27820000002", "Sipho Test"), ("27820000003", "Lerato Test")]


def access(request: Request, db: Session = Depends(get_db)) -> None:
    """Open on a developer's machine; elsewhere only signed-in staff can play the customer."""
    if get_settings().env == "local":
        return
    try:
        current_staff(request, db)
    except LoginRequired:
        raise HTTPException(403, "Sign in to the admin page to use the simulator.") from None


def _feed(db: Session, payload: dict) -> None:
    for message in wh.parse(payload):
        handle_inbound(db, message)


def _ids() -> tuple[str, int]:
    return f"wamid.SIM{uuid.uuid4().hex}", int(time.time())


@router.get("")
def page(request: Request, wa: str = TEST_CUSTOMERS[0][0], db: Session = Depends(get_db), _=Depends(access)):
    customers = list(TEST_CUSTOMERS)
    known = {c[0] for c in customers}
    for c in db.scalars(select(Customer).where(Customer.wa_id.like("2782000%")).order_by(Customer.wa_id)):
        if c.wa_id not in known:
            customers.append((c.wa_id, c.name or c.wa_id))
    current = next((c for c in customers if c[0] == wa), (wa, f"Customer {wa[-4:]}"))
    return render(request, "simulator.html", db, customers=customers, current=current,
                  business=get_settings().wa_business_number)


class TextIn(BaseModel):
    wa_id: str
    name: str = ""
    text: str


class ReplyIn(BaseModel):
    wa_id: str
    name: str = ""
    reply_id: str
    title: str
    list_reply: bool = False


@router.post("/text")
def send_text(body: TextIn, db: Session = Depends(get_db), _=Depends(access)):
    message_id, ts = _ids()
    _feed(db, wh.build_text_payload(body.wa_id, body.name, message_id, body.text[:4096], ts))
    return {"ok": True}


@router.post("/reply")
def send_reply(body: ReplyIn, db: Session = Depends(get_db), _=Depends(access)):
    message_id, ts = _ids()
    _feed(db, wh.build_reply_payload(body.wa_id, body.name, message_id, body.reply_id, body.title, ts,
                                     body.list_reply))
    return {"ok": True}


@router.post("/file")
async def send_file(wa_id: str = Form(...), name: str = Form(""), file: UploadFile = File(...),
                    db: Session = Depends(get_db), _=Depends(access)):
    content_type = file.content_type or "application/octet-stream"
    if content_type not in ("image/jpeg", "image/png", "application/pdf"):
        raise HTTPException(400, "Send a JPEG, PNG or PDF, like WhatsApp would.")
    key = get_storage().put("sim-media", await file.read(), content_type)
    kind = "document" if content_type == "application/pdf" else "image"
    message_id, ts = _ids()
    _feed(db, wh.build_media_payload(wa_id, name, message_id, kind, f"sim-media:{key}", content_type, ts))
    return {"ok": True}


@router.get("/messages")
def messages(wa_id: str, after: int = 0, db: Session = Depends(get_db), _=Depends(access)):
    customer = db.scalar(select(Customer).where(Customer.wa_id == wa_id))
    if customer is None:
        return {"messages": [], "mode": "bot"}
    conv = db.scalar(select(Conversation).where(Conversation.customer_id == customer.id))
    if conv is None:
        return {"messages": [], "mode": "bot"}
    rows = db.scalars(select(Message).where(Message.conversation_id == conv.id, Message.id > after)
                      .order_by(Message.id)).all()
    return {
        "mode": conv.mode.value,
        "messages": [{"id": m.id, "direction": m.direction.value, "sender": m.sender, "kind": m.kind,
                      "text": m.text, "payload": m.payload, "staff": m.staff.name if m.staff else None,
                      "time": m.created_at.isoformat()} for m in rows],
    }


@router.post("/reset")
def reset(body: TextIn, db: Session = Depends(get_db), _=Depends(access)):
    """Start a test customer's chat again (M2). Their orders stay, so stock stays correct."""
    customer = db.scalar(select(Customer).where(Customer.wa_id == body.wa_id))
    if customer is not None:
        conv = db.scalar(select(Conversation).where(Conversation.customer_id == customer.id))
        if conv is not None:
            db.execute(delete(Event).where(Event.conversation_id == conv.id))
            db.execute(delete(Message).where(Message.conversation_id == conv.id))
            db.delete(conv)
    return {"ok": True}
