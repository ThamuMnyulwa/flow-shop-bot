"""Business settings that staff change on the admin page (D2, D3)."""

import hmac
from typing import Any

from sqlalchemy.orm import Session

from flowshop.models import Setting

DEFAULTS: dict[str, Any] = {
    "delivery_fee_cents": 20000,
    "free_delivery_over_cents": 100000,  # free when the product total is above this
    "collection_code": "",  # empty means collection is off
    "bank_details": "Bank: [bank name]\nAccount name: FLOWW\nAccount number: [number]\nBranch code: [code]",
    "office_address": "[office address, shared only after payment]",
    "returns_url": "https://example.com/returns",
    "seller_name": "FLOWW",
    "dispatch_working_days": 3,
    "payment_hours": 48,
    "reminder_hours": 24,
    "conversation_idle_hours": 24,
    "code_max_failures": 3,
    "code_lock_minutes": 60,
}

LABELS = {
    "delivery_fee_cents": "Delivery fee",
    "free_delivery_over_cents": "Free delivery when products total more than",
    "collection_code": "Collection code",
    "bank_details": "Bank details sent to customers",
    "office_address": "Office address (sent only after payment)",
    "returns_url": "Returns policy link",
    "seller_name": "Seller name",
}


def get(db: Session, key: str) -> Any:
    row = db.get(Setting, key)
    return row.value if row is not None else DEFAULTS[key]


def put(db: Session, key: str, value: Any) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.flush()


def delivery_fee_for(db: Session, subtotal_cents: int) -> int:
    if subtotal_cents > int(get(db, "free_delivery_over_cents")):
        return 0
    return int(get(db, "delivery_fee_cents"))


def collection_code_matches(db: Session, attempt: str) -> bool:
    code = str(get(db, "collection_code")).strip()
    if not code:
        return False
    return hmac.compare_digest(code.upper().encode(), attempt.strip().upper().encode())
