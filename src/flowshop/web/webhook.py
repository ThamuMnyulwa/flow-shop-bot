"""The WhatsApp Cloud API webhook (L1) and the scheduled-jobs endpoint (E12)."""

import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

from flowshop.bot.engine import handle_inbound
from flowshop.channels import webhook as wh
from flowshop.channels.base import InboundMessage
from flowshop.config import get_settings
from flowshop.db import session_scope
from flowshop.jobs import run_all

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/webhook", response_class=PlainTextResponse)
def verify(mode: str = Query("", alias="hub.mode"), token: str = Query("", alias="hub.verify_token"),
           challenge: str = Query("", alias="hub.challenge")):
    expected = get_settings().wa_verify_token
    if mode == "subscribe" and expected and hmac.compare_digest(token, expected):
        return challenge
    raise HTTPException(403)


@router.post("/webhook")
async def receive(request: Request, background: BackgroundTasks,
                  x_hub_signature_256: str | None = Header(default=None)):
    body = await request.body()
    if not wh.verify_signature(get_settings().wa_app_secret, body, x_hub_signature_256):
        raise HTTPException(401, "bad signature")
    try:
        messages = wh.parse(json.loads(body))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(400, "bad payload") from None
    # Acknowledge Meta at once and process afterwards. Each message is processed once, keyed on its id.
    background.add_task(process, messages)
    return {"ok": True}


def process(messages: list[InboundMessage]) -> None:
    for message in messages:
        try:
            with session_scope() as db:
                handle_inbound(db, message)
        except Exception:
            log.exception("failed to handle message %s", message.message_id)


@router.post("/jobs/run")
def jobs(authorization: str = Header(default="")):
    token = get_settings().jobs_token
    if not token or not hmac.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401)
    with session_scope() as db:
        return run_all(db)
