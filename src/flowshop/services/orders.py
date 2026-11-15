"""The order lifecycle. Every status change is a guarded update, so two actors cannot both win a race."""

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from flowshop import clock
from flowshop.models import (
    Customer,
    Fulfilment,
    Order,
    OrderEvent,
    OrderItem,
    OrderStatus,
    PaymentProof,
    Product,
    Staff,
)
from flowshop.money import order_reference, rand
from flowshop.services import notify, settings, stock

S = OrderStatus
UNPAID = (S.PENDING_PAYMENT, S.PROOF_RECEIVED, S.PAYMENT_OVERDUE)
OPEN = (*UNPAID, S.PAID, S.DISPATCHED)


class OrderError(Exception):
    pass


class InvalidTransition(OrderError):
    pass


@dataclass
class QuoteLine:
    product: Product
    quantity: int

    @property
    def line_cents(self) -> int:
        return self.product.price_cents * self.quantity


@dataclass
class Quote:
    lines: list[QuoteLine] = field(default_factory=list)
    fulfilment: Fulfilment | None = None
    delivery_fee_cents: int = 0

    @property
    def subtotal_cents(self) -> int:
        return sum(line.line_cents for line in self.lines)

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.delivery_fee_cents


def quote(db: Session, cart: dict[int, int], fulfilment: Fulfilment | None) -> Quote:
    """Prices always come from the database, never from message content."""
    q = Quote(fulfilment=fulfilment)
    if cart:
        products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(cart)))}
        q.lines = [QuoteLine(products[pid], qty) for pid, qty in cart.items() if pid in products and qty > 0]
    if fulfilment == Fulfilment.DELIVERY:
        q.delivery_fee_cents = settings.delivery_fee_for(db, q.subtotal_cents)
    return q


def _lines(order: Order) -> list[tuple[int, int]]:
    return [(item.product_id, item.quantity) for item in order.items]


def _event(db: Session, order: Order, from_status, to_status, actor: str, staff: Staff | None, note="") -> None:
    db.add(OrderEvent(order_id=order.id, from_status=from_status, to_status=to_status, actor=actor,
                      staff_id=staff.id if staff else None, note=note, created_at=clock.now(db)))


def _move(db: Session, order: Order, allowed: tuple[OrderStatus, ...], to: OrderStatus, actor: str,
          staff: Staff | None = None, note: str = "", **fields) -> OrderStatus:
    """Change status only if the order is still in an allowed status. Returns the previous status."""
    db.flush()
    previous = db.scalar(
        select(Order.status).where(Order.id == order.id, Order.status.in_(allowed)).with_for_update()
    )
    if previous is None:
        db.refresh(order)
        raise InvalidTransition(f"Order {order.reference} is {order.status.value.replace('_', ' ')}, "
                                f"so it cannot become {to.value.replace('_', ' ')}.")
    db.execute(update(Order).where(Order.id == order.id).values(status=to, **fields)
               .execution_options(synchronize_session=False))
    _event(db, order, previous.value, to.value, actor, staff, note)
    db.flush()
    db.refresh(order)
    return previous


def confirm(db: Session, customer: Customer, cart: dict[int, int], fulfilment: Fulfilment, address: str,
            idempotency_key: str, staff: Staff | None = None) -> Order:
    """Create the order and reserve its stock in one transaction (S3). Confirming twice returns the same order."""
    existing = db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
    if existing is not None:
        return existing
    q = quote(db, cart, fulfilment)
    if not q.lines:
        raise OrderError("The order is empty.")
    now = clock.now(db)
    try:
        with db.begin_nested():
            order = Order(
                idempotency_key=idempotency_key, customer_id=customer.id, status=S.PENDING_PAYMENT,
                fulfilment=fulfilment, address=address if fulfilment == Fulfilment.DELIVERY else "",
                subtotal_cents=q.subtotal_cents, delivery_fee_cents=q.delivery_fee_cents,
                confirmed_at=now, created_by_staff_id=staff.id if staff else None,
            )
            db.add(order)
            db.flush()
            order.reference = order_reference(order.id)
            for line in q.lines:
                db.add(OrderItem(order_id=order.id, product_id=line.product.id, name=line.product.name,
                                 unit_price_cents=line.product.price_cents, quantity=line.quantity))
            db.flush()
            stock.reserve(db, [(line.product.id, line.quantity) for line in q.lines], order.id)
            order.stock_reserved = True
            _event(db, order, None, S.PENDING_PAYMENT.value, "staff" if staff else "customer", staff)
            db.flush()
    except IntegrityError:
        # Another request confirmed the same draft first.
        existing = db.scalar(select(Order).where(Order.idempotency_key == idempotency_key))
        if existing is None:
            raise
        return existing
    notify.staff(db, "new_order", f"New order {order.reference}: {rand(order.total_cents)}, "
                 f"{fulfilment.value}.", f"/admin/orders/{order.id}")
    return order


def record_proof(db: Session, order: Order, storage_key: str, content_type: str) -> None:
    """The customer sent proof of payment. An order with proof never expires (P3)."""
    db.add(PaymentProof(order_id=order.id, storage_key=storage_key, content_type=content_type,
                        created_at=clock.now(db)))
    if order.status in (S.PENDING_PAYMENT, S.PAYMENT_OVERDUE):
        _move(db, order, (S.PENDING_PAYMENT, S.PAYMENT_OVERDUE), S.PROOF_RECEIVED, "customer",
              proof_received_at=clock.now(db))
    notify.staff(db, "proof", f"Proof of payment for {order.reference} ({rand(order.total_cents)}). "
                 "Check the bank, then mark it paid.", f"/admin/orders/{order.id}")


def mark_paid(db: Session, order: Order, staff: Staff) -> None:
    now = clock.now(db)
    days = int(settings.get(db, "dispatch_working_days"))
    dispatch_by = clock.add_working_days(now, days) if order.fulfilment == Fulfilment.DELIVERY else None
    _move(db, order, UNPAID, S.PAID, "staff", staff, paid_at=now, dispatch_by=dispatch_by)
    if not order.stock_reserved:
        _try_reserve_again(db, order)
    if order.fulfilment == Fulfilment.DELIVERY:
        text = (f"Thank you! We received payment for order {order.reference}. "
                f"It will be sent by {dispatch_by:%A %d %B}.")
    else:
        text = (f"Thank you! We received payment for order {order.reference}. "
                f"You can collect it at: {settings.get(db, 'office_address')}. Please bring your order reference.")
    notify.customer(db, order.customer, text, template="order_update", params=[order.reference, "paid"])


def _try_reserve_again(db: Session, order: Order) -> None:
    """A late payment on an overdue order: reserve again if possible, otherwise flag for staff (P6)."""
    try:
        stock.reserve(db, _lines(order), order.id, require_on_sale=False)
    except stock.InsufficientStock as exc:
        order.needs_attention = True
        order.attention_reason = f"Paid after stock was released, and stock is now short: {exc}"
        notify.staff(db, "attention", f"Order {order.reference} is paid but stock is short. "
                     "Resolve with the customer.", f"/admin/orders/{order.id}")
    else:
        order.stock_reserved = True
        order.needs_attention = False
        order.attention_reason = ""
    db.flush()


def retry_reservation(db: Session, order: Order, staff: Staff) -> bool:
    if order.stock_reserved or order.status != S.PAID:
        return order.stock_reserved
    _try_reserve_again(db, order)
    _event(db, order, order.status.value, order.status.value, "staff", staff,
           "Stock reserved again" if order.stock_reserved else "Reservation retry failed")
    return order.stock_reserved


def _require_stock(order: Order) -> None:
    if not order.stock_reserved:
        raise OrderError(f"Order {order.reference} has no stock reserved. Fix the stock first.")


def dispatch(db: Session, order: Order, staff: Staff) -> None:
    """Only a paid order can be dispatched (P4). Stock leaves on-hand now (S4)."""
    if order.fulfilment != Fulfilment.DELIVERY:
        raise OrderError("This order is for collection, so mark it as collected.")
    _require_stock(order)
    _move(db, order, (S.PAID,), S.DISPATCHED, "staff", staff, dispatched_at=clock.now(db))
    stock.ship(db, _lines(order), order.id, staff.id)
    notify.customer(db, order.customer, f"Your order {order.reference} is on its way.",
                    template="order_update", params=[order.reference, "dispatched"])


def collect(db: Session, order: Order, staff: Staff) -> None:
    if order.fulfilment != Fulfilment.COLLECTION:
        raise OrderError("This order is for delivery, so mark it as dispatched.")
    _require_stock(order)
    _move(db, order, (S.PAID,), S.COLLECTED, "staff", staff, collected_at=clock.now(db))
    stock.ship(db, _lines(order), order.id, staff.id)


def deliver(db: Session, order: Order, staff: Staff) -> None:
    _move(db, order, (S.DISPATCHED,), S.DELIVERED, "staff", staff, delivered_at=clock.now(db))


def cancel(db: Session, order: Order, actor: str, staff: Staff | None = None, reason: str = "") -> None:
    """Cancel before dispatch. A paid order that is cancelled needs a refund, recorded by staff."""
    previous = _move(db, order, (*UNPAID, S.PAID), S.CANCELLED, actor, staff, reason,
                     cancelled_at=clock.now(db))
    if order.stock_reserved:
        stock.release(db, _lines(order), order.id, note=f"cancelled by {actor}")
        order.stock_reserved = False
    if previous == S.PAID:
        order.needs_attention = True
        order.attention_reason = "Cancelled after payment: refund due."
        notify.staff(db, "attention", f"Order {order.reference} was cancelled after payment. A refund is due.",
                     f"/admin/orders/{order.id}")
    db.flush()
    notify.customer(db, order.customer, f"Your order {order.reference} has been cancelled.",
                    template="order_update", params=[order.reference, "cancelled"])


def record_refund(db: Session, order: Order, staff: Staff, note: str) -> None:
    order.refund_note = note
    order.needs_attention = False
    order.attention_reason = ""
    _event(db, order, order.status.value, order.status.value, "staff", staff, f"Refund: {note}")
    db.flush()


def release_overdue(db: Session) -> list[Order]:
    """48 hours without proof of payment: release the stock, keep the order open for a late payment (P3)."""
    now = clock.now(db)
    cutoff = now - timedelta(hours=int(settings.get(db, "payment_hours")))
    due = db.scalars(select(Order).where(Order.status == S.PENDING_PAYMENT, Order.confirmed_at <= cutoff)
                     .options(selectinload(Order.items)).order_by(Order.id)).all()
    released = []
    for order in due:
        try:
            _move(db, order, (S.PENDING_PAYMENT,), S.PAYMENT_OVERDUE, "system", overdue_at=now,
                  stock_reserved=False)
        except InvalidTransition:
            continue  # paid or proof arrived in the meantime
        stock.release(db, _lines(order), order.id, note="48 hours without proof of payment")
        notify.customer(
            db, order.customer,
            f"We haven't received payment for order {order.reference}, so the items are no longer held for you. "
            "If you pay now, send the proof here and we'll reserve them again if they're still in stock.",
            template="order_update", params=[order.reference, "payment overdue"],
        )
        released.append(order)
    return released


def send_payment_reminders(db: Session) -> list[Order]:
    """Remind the customer before the stock is released (P5)."""
    hours = int(settings.get(db, "payment_hours")) - int(settings.get(db, "reminder_hours"))
    now = clock.now(db)
    cutoff = now - timedelta(hours=hours)
    due = db.scalars(select(Order).where(Order.status == S.PENDING_PAYMENT, Order.confirmed_at <= cutoff,
                                         Order.reminder_sent_at.is_(None))).all()
    sent = []
    for order in due:
        claimed = db.execute(
            update(Order).where(Order.id == order.id, Order.reminder_sent_at.is_(None)).values(reminder_sent_at=now)
            .execution_options(synchronize_session=False)
        ).rowcount
        if not claimed:
            continue
        db.refresh(order)
        left = int(settings.get(db, "reminder_hours"))
        notify.customer(
            db, order.customer,
            f"Reminder: order {order.reference} ({rand(order.total_cents)}) is held for you for about {left} more "
            "hours. Send your proof of payment here when you've paid.",
            template="payment_reminder", params=[order.reference, rand(order.total_cents)],
        )
        sent.append(order)
    return sent


def open_orders_for(db: Session, customer: Customer) -> list[Order]:
    return list(db.scalars(select(Order).where(Order.customer_id == customer.id, Order.status.in_(OPEN))
                           .order_by(Order.id.desc())))


def latest_awaiting_payment(db: Session, customer: Customer) -> Order | None:
    return db.scalar(select(Order).where(Order.customer_id == customer.id, Order.status.in_(UNPAID))
                     .order_by(Order.id.desc()).limit(1))
