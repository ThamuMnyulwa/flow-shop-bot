"""Scheduled work (E12). An external scheduler calls POST /jobs/run, because services that scale to zero cannot
keep a timer running. Running it twice is harmless: every step is a guarded update."""

from sqlalchemy.orm import Session

from flowshop.services import orders


def run_all(db: Session) -> dict[str, list[str]]:
    reminded = orders.send_payment_reminders(db)
    released = orders.release_overdue(db)
    return {"reminded": [o.reference for o in reminded], "released": [o.reference for o in released]}
