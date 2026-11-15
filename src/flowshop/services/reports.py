"""Weekly report (A4) and the success metrics from the PRD, measured from the database."""

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flowshop import clock
from flowshop.models import Direction, Event, Message, Order, OrderEvent, OrderItem, OrderStatus

S = OrderStatus
SOLD = (S.PAID, S.DISPATCHED, S.COLLECTED, S.DELIVERED)


def weekly(db: Session, weeks: int = 8) -> list[dict]:
    now = clock.now(db)
    rows = []
    for i in range(weeks):
        end = now - timedelta(weeks=i)
        start = end - timedelta(weeks=1)
        in_week = (Order.paid_at >= start, Order.paid_at < end, Order.status.in_(SOLD))
        count, revenue = db.execute(select(func.count(Order.id), func.coalesce(
            func.sum(Order.subtotal_cents + Order.delivery_fee_cents), 0)).where(*in_week)).one()
        top = db.execute(
            select(OrderItem.name, func.sum(OrderItem.quantity).label("qty")).join(Order).where(*in_week)
            .group_by(OrderItem.name).order_by(func.sum(OrderItem.quantity).desc()).limit(3)
        ).all()
        rows.append({"start": start, "end": end, "orders": count, "revenue_cents": revenue,
                     "top": [(name, qty) for name, qty in top]})
    return rows


def metrics(db: Session) -> dict:
    confirmed = db.scalar(select(func.count(Order.id))) or 0
    sold = db.scalar(select(func.count(Order.id)).where(Order.status.in_(SOLD))) or 0
    handoffs = db.scalar(select(func.count(func.distinct(Event.conversation_id))).where(Event.kind == "handoff")) or 0
    bot_orders = db.scalar(select(func.count(Event.id)).where(Event.kind == "order_confirmed")) or 0
    bot_replies = db.scalar(select(func.count(Message.id)).where(Message.direction == Direction.OUT,
                                                                 Message.sender == "bot")) or 0
    refused = db.scalar(select(func.count(Event.id)).where(Event.kind == "refused_stock")) or 0
    # Dispatched before paid should always be zero; this checks the rule held.
    shipped_unpaid = db.scalar(select(func.count(Order.id)).where(
        Order.status.in_((S.DISPATCHED, S.COLLECTED, S.DELIVERED)), Order.paid_at.is_(None))) or 0
    late = 0
    for order in db.scalars(select(Order).where(Order.dispatched_at.is_not(None), Order.dispatch_by.is_not(None))):
        if clock.local_date(order.dispatched_at) > order.dispatch_by:
            late += 1
    proof_to_paid = db.execute(
        select(func.avg(func.extract("epoch", Order.paid_at - Order.proof_received_at)))
        .where(Order.paid_at.is_not(None), Order.proof_received_at.is_not(None))
    ).scalar()
    return {
        "orders_confirmed": confirmed,
        "orders_paid_or_sent": sold,
        "orders_from_bot": bot_orders,
        "conversations_handed_to_staff": handoffs,
        "bot_replies_per_bot_order": round(bot_replies / bot_orders, 1) if bot_orders else None,
        "stock_refusals": refused,
        "sent_before_payment": shipped_unpaid,
        "sent_after_dispatch_date": late,
        "average_hours_proof_to_paid": round(proof_to_paid / 3600, 1) if proof_to_paid else None,
        "status_changes_logged": db.scalar(select(func.count(OrderEvent.id))) or 0,
    }
