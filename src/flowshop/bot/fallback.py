"""The one fallback step for messages the menus cannot handle.

With the AI assistant off, it returns None and the bot hands off to staff. With it on, the assistant
answers from the product database first (AI1).
"""

from sqlalchemy.orm import Session

from flowshop.config import get_settings
from flowshop.models import Conversation


def enabled() -> bool:
    settings = get_settings()
    return settings.ai_enabled and bool(settings.anthropic_api_key)


def answer(db: Session, conv: Conversation, question: str) -> str | None:
    if not enabled():
        return None
    from flowshop.bot import assistant

    return assistant.answer(db, conv, question)
