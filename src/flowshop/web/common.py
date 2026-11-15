from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flowshop import clock
from flowshop.auth import csrf_token
from flowshop.config import get_settings
from flowshop.models import Conversation, ConversationMode, Notification, Staff
from flowshop.money import rand

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.filters["rand"] = rand
templates.env.filters["status"] = lambda s: (s.value if hasattr(s, "value") else str(s)).replace("_", " ")


def _local(moment, fmt="%d %b %H:%M"):
    return moment.astimezone(clock.SA_TZ).strftime(fmt) if moment else ""


templates.env.filters["local"] = _local


def render(request: Request, name: str, db: Session, staff: Staff | None = None, status_code: int = 200, **ctx):
    settings = get_settings()
    base = {
        "request": request,
        "staff": staff,
        "csrf": csrf_token(request),
        "env": settings.env,
        "time_travel": settings.allow_time_travel,
        "now": clock.now(db),
        "flash": request.session.pop("flash", None),
    }
    if staff is not None:
        base["unread"] = db.scalar(select(func.count(Notification.id)).where(Notification.read.is_(False)))
        base["waiting"] = db.scalar(select(func.count(Conversation.id)).where(
            Conversation.mode == ConversationMode.HUMAN, Conversation.waiting_since.is_not(None)))
    return templates.TemplateResponse(request, name, {**base, **ctx}, status_code=status_code)


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session["flash"] = {"message": message, "kind": kind}
