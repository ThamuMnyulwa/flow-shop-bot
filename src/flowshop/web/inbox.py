"""The shared inbox (I1 to I3): every conversation, waiting chats first, replies signed by the staff member."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from flowshop import clock
from flowshop.auth import current_staff, verify_csrf
from flowshop.bot.engine import return_to_bot
from flowshop.channels.base import text
from flowshop.db import get_db
from flowshop.models import Conversation, ConversationMode, Message, Order, Staff
from flowshop.services import notify
from flowshop.web.common import flash, render

router = APIRouter(prefix="/inbox", dependencies=[Depends(verify_csrf)])


@router.get("")
def inbox(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    convs = db.scalars(select(Conversation).options(selectinload(Conversation.customer))
                       .order_by(Conversation.waiting_since.asc().nulls_last(),
                                 Conversation.last_activity_at.desc()).limit(200)).all()
    last = {}
    for conv in convs:
        last[conv.id] = db.scalar(select(Message).where(Message.conversation_id == conv.id)
                                  .order_by(Message.id.desc()).limit(1))
    return render(request, "inbox.html", db, staff, convs=convs, last=last)


def _conversation(db: Session, conv_id: int) -> Conversation:
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404)
    return conv


@router.get("/{conv_id}")
def conversation(conv_id: int, request: Request, db: Session = Depends(get_db),
                 staff: Staff = Depends(current_staff)):
    conv = _conversation(db, conv_id)
    customer_orders = db.scalars(select(Order).where(Order.customer_id == conv.customer_id)
                                 .order_by(Order.id.desc()).limit(10)).all()
    return render(request, "conversation.html", db, staff, conv=conv, messages=_messages(db, conv),
                  orders=customer_orders, in_window=notify.in_window(db, conv))


@router.get("/{conv_id}/messages")
def conversation_messages(conv_id: int, request: Request, db: Session = Depends(get_db),
                          staff: Staff = Depends(current_staff)):
    """Polled by the page every few seconds so several staff see the same chat (I3)."""
    conv = _conversation(db, conv_id)
    return render(request, "_messages.html", db, staff, conv=conv, messages=_messages(db, conv))


def _messages(db: Session, conv: Conversation) -> list[Message]:
    rows = db.scalars(select(Message).where(Message.conversation_id == conv.id)
                      .options(selectinload(Message.staff)).order_by(Message.id.desc()).limit(200)).all()
    return list(reversed(rows))


@router.post("/{conv_id}/reply")
def reply(conv_id: int, request: Request, body: str = Form(...), db: Session = Depends(get_db),
          staff: Staff = Depends(current_staff)):
    conv = _conversation(db, conv_id)
    body = body.strip()
    if not body:
        return RedirectResponse(f"/inbox/{conv_id}", status_code=303)
    try:
        notify.send(db, conv, text(body), sender="staff", staff=staff)
    except notify.OutsideWindow:
        flash(request, "It's more than 24 hours since the customer's last message, so WhatsApp only allows an "
              "approved template. Ask them to message you, or wait for their reply.", "error")
        return RedirectResponse(f"/inbox/{conv_id}", status_code=303)
    # A staff reply takes over the chat, and the customer is no longer waiting.
    conv.mode = ConversationMode.HUMAN
    conv.waiting_since = None
    conv.last_activity_at = clock.now(db)
    return RedirectResponse(f"/inbox/{conv_id}", status_code=303)


@router.post("/{conv_id}/takeover")
def takeover(conv_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    conv = _conversation(db, conv_id)
    conv.mode = ConversationMode.HUMAN
    conv.handoff_reason = f"Taken over by {staff.name}"
    return RedirectResponse(f"/inbox/{conv_id}", status_code=303)


@router.post("/{conv_id}/bot")
def back_to_bot(conv_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    return_to_bot(db, _conversation(db, conv_id))
    return RedirectResponse(f"/inbox/{conv_id}", status_code=303)
