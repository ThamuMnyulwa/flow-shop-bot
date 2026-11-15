"""E6: reserving, refusing an oversell (also under concurrency), releasing, the 48-hour rule, proof of payment,
late payment, double confirmation, and blocking dispatch before payment."""

import threading
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from flowshop import clock
from flowshop.db import new_session
from flowshop.jobs import run_all
from flowshop.models import (
    Customer,
    Fulfilment,
    MovementReason,
    Notification,
    Order,
    OrderStatus,
    Product,
    ProductStatus,
    StockMovement,
)
from flowshop.services import orders, stock

ADDRESS = "1 Main Road, Rosebank, Johannesburg, 2196"


def customer(db, wa_id="27821111111"):
    c = db.scalar(select(Customer).where(Customer.wa_id == wa_id))
    if c is None:
        c = Customer(wa_id=wa_id, name="Test", created_at=clock.now(db))
        db.add(c)
        db.flush()
    return c


def place(db, product, qty, cust=None, key=None, fulfilment=Fulfilment.DELIVERY):
    return orders.confirm(db, cust or customer(db), {product.id: qty}, fulfilment, ADDRESS, key or uuid.uuid4().hex)


def fresh(db, product):
    return db.get(Product, product.id, populate_existing=True)


def test_confirm_reserves_stock(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 3)
    hw = fresh(db, hw)
    assert (hw.on_hand, hw.reserved, hw.available) == (10, 3, 7)
    assert order.status == OrderStatus.PENDING_PAYMENT
    assert order.reference.startswith("FLW-")
    assert order.total_cents == 30000 + 20000  # R300 plus R200 delivery


def test_free_delivery_only_above_threshold(db, shop):
    hw = shop["products"]["HW-01"]
    hw.price_cents = 50000
    db.flush()
    assert place(db, hw, 2).delivery_fee_cents == 20000  # exactly R1 000 is not "more than"
    hw.price_cents = 50001
    db.flush()
    assert place(db, hw, 2).delivery_fee_cents == 0


def test_oversell_is_refused_and_nothing_changes(db, shop):
    hw, nb = shop["products"]["HW-01"], shop["products"]["NB-01"]
    with pytest.raises(stock.InsufficientStock) as exc:
        orders.confirm(db, customer(db), {nb.id: 2, hw.id: 11}, Fulfilment.DELIVERY, ADDRESS, "k1")
    assert exc.value.shortfalls[0].available == 10
    assert fresh(db, hw).reserved == 0
    assert fresh(db, nb).reserved == 0  # the line that fitted was rolled back too
    assert db.scalar(select(func.count(Order.id))) == 0


def test_launching_soon_cannot_be_ordered(db, shop):
    with pytest.raises(stock.InsufficientStock):
        place(db, shop["products"]["MG-01"], 1)


def test_concurrent_orders_cannot_both_take_the_last_units(shop):
    hw_id = shop["products"]["HW-01"].id
    results, barrier = [], threading.Barrier(2)

    def buy(wa_id):
        s = new_session()
        try:
            c = customer(s, wa_id)
            s.commit()
            barrier.wait()
            orders.confirm(s, c, {hw_id: 7}, Fulfilment.DELIVERY, ADDRESS, uuid.uuid4().hex)
            s.commit()
            results.append("ok")
        except stock.InsufficientStock:
            s.rollback()
            results.append("refused")
        finally:
            s.close()

    threads = [threading.Thread(target=buy, args=(f"2782000000{i}",)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == ["ok", "refused"]
    s = new_session()
    assert s.get(Product, hw_id).reserved == 7
    s.close()


def test_double_confirmation_returns_the_same_order(db, shop):
    hw = shop["products"]["HW-01"]
    c = customer(db)
    first = place(db, hw, 2, c, key="same-draft")
    second = place(db, hw, 2, c, key="same-draft")
    assert first.id == second.id
    assert fresh(db, hw).reserved == 2


def test_cancel_releases_reservation(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 4)
    orders.cancel(db, order, "customer")
    assert order.status == OrderStatus.CANCELLED
    assert fresh(db, hw).reserved == 0


def test_dispatch_blocked_before_payment(db, shop):
    order = place(db, shop["products"]["HW-01"], 1)
    with pytest.raises(orders.InvalidTransition):
        orders.dispatch(db, order, shop["staff"])


def test_dispatch_takes_stock_off_on_hand(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 2)
    orders.mark_paid(db, order, shop["staff"])
    orders.dispatch(db, order, shop["staff"])
    hw = fresh(db, hw)
    assert (hw.on_hand, hw.reserved) == (8, 0)
    orders.deliver(db, order, shop["staff"])
    assert fresh(db, hw).on_hand == 8  # delivery itself does not move stock


def test_collection_order_is_collected_not_dispatched(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 1, fulfilment=Fulfilment.COLLECTION)
    assert order.delivery_fee_cents == 0
    orders.mark_paid(db, order, shop["staff"])
    with pytest.raises(orders.OrderError):
        orders.dispatch(db, order, shop["staff"])
    orders.collect(db, order, shop["staff"])
    assert fresh(db, hw).on_hand == 9


def test_48_hours_without_proof_releases_stock_but_keeps_order(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 3)
    clock.advance(db, timedelta(hours=47))
    assert run_all(db)["released"] == []
    clock.advance(db, timedelta(hours=2))
    assert run_all(db)["released"] == [order.reference]
    db.refresh(order)
    assert order.status == OrderStatus.PAYMENT_OVERDUE
    assert not order.stock_reserved
    assert fresh(db, hw).reserved == 0
    assert run_all(db)["released"] == []  # running the job again changes nothing


def test_order_with_proof_never_expires(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 3)
    orders.record_proof(db, order, "proofs/x.jpg", "image/jpeg")
    clock.advance(db, timedelta(days=10))
    assert run_all(db)["released"] == []
    db.refresh(order)
    assert order.status == OrderStatus.PROOF_RECEIVED
    assert fresh(db, hw).reserved == 3


def test_late_payment_reserves_again(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 3)
    clock.advance(db, timedelta(hours=49))
    run_all(db)
    orders.mark_paid(db, order, shop["staff"])
    assert order.status == OrderStatus.PAID
    assert order.stock_reserved and not order.needs_attention
    assert fresh(db, hw).reserved == 3


def test_late_payment_with_stock_gone_is_flagged(db, shop):
    hw = shop["products"]["HW-01"]
    late = place(db, hw, 3)
    clock.advance(db, timedelta(hours=49))
    run_all(db)
    place(db, hw, 9, customer(db, "27829999999"))
    orders.mark_paid(db, late, shop["staff"])
    assert late.status == OrderStatus.PAID
    assert late.needs_attention and not late.stock_reserved
    with pytest.raises(orders.OrderError):
        orders.dispatch(db, late, shop["staff"])
    assert db.scalar(select(func.count(Notification.id)).where(Notification.kind == "attention")) == 1


def test_late_payment_reserves_even_if_product_now_launching_soon(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 1)
    clock.advance(db, timedelta(hours=49))
    run_all(db)
    hw.status = ProductStatus.LAUNCHING_SOON
    db.flush()
    orders.mark_paid(db, order, shop["staff"])
    assert order.stock_reserved  # the customer already bought it


def test_paid_and_expiry_race_only_one_wins(db, shop):
    order = place(db, shop["products"]["HW-01"], 1)
    orders.mark_paid(db, order, shop["staff"])
    clock.advance(db, timedelta(hours=49))
    assert run_all(db)["released"] == []
    assert order.status == OrderStatus.PAID


def test_reminder_sent_once_at_24_hours(db, shop):
    order = place(db, shop["products"]["HW-01"], 1)
    clock.advance(db, timedelta(hours=23))
    assert run_all(db)["reminded"] == []
    clock.advance(db, timedelta(hours=2))
    assert run_all(db)["reminded"] == [order.reference]
    assert run_all(db)["reminded"] == []


def test_cancel_after_payment_flags_refund(db, shop):
    hw = shop["products"]["HW-01"]
    order = place(db, hw, 2)
    orders.mark_paid(db, order, shop["staff"])
    orders.cancel(db, order, "staff", shop["staff"], "Customer changed their mind")
    assert order.needs_attention and "refund" in order.attention_reason.lower()
    assert fresh(db, hw).reserved == 0


def test_cannot_cancel_after_dispatch(db, shop):
    order = place(db, shop["products"]["HW-01"], 1)
    orders.mark_paid(db, order, shop["staff"])
    orders.dispatch(db, order, shop["staff"])
    with pytest.raises(orders.InvalidTransition):
        orders.cancel(db, order, "staff", shop["staff"])


def test_adjustment_cannot_go_below_reserved(db, shop):
    hw = shop["products"]["HW-01"]
    place(db, hw, 6)
    with pytest.raises(stock.StockError):
        stock.set_on_hand(db, fresh(db, hw), 5, shop["staff"].id, "count")
    stock.set_on_hand(db, fresh(db, hw), 6, shop["staff"].id, "count")
    assert fresh(db, hw).available == 0


def test_every_stock_change_is_logged_and_rebuilds_quantities(db, shop):
    hw = shop["products"]["HW-01"]
    a = place(db, hw, 2)
    b = place(db, hw, 3)
    orders.mark_paid(db, a, shop["staff"])
    orders.dispatch(db, a, shop["staff"])
    orders.cancel(db, b, "customer")
    stock.set_on_hand(db, fresh(db, hw), 12, shop["staff"].id, "delivery from supplier")
    on_hand, reserved = db.execute(
        select(func.sum(StockMovement.delta_on_hand), func.sum(StockMovement.delta_reserved))
        .where(StockMovement.product_id == hw.id)
    ).one()
    hw = fresh(db, hw)
    assert (on_hand, reserved) == (hw.on_hand, hw.reserved) == (12, 0)
    reasons = set(db.scalars(select(StockMovement.reason).where(StockMovement.product_id == hw.id)))
    assert reasons == {MovementReason.INITIAL, MovementReason.RESERVE, MovementReason.SHIP, MovementReason.RELEASE,
                       MovementReason.ADJUSTMENT}


def test_low_stock_alert_once(db, shop):
    hw = shop["products"]["HW-01"]
    place(db, hw, 8)
    place(db, hw, 1)
    count = db.scalar(select(func.count(Notification.id)).where(Notification.kind == "low_stock"))
    assert count == 1


def test_dispatch_by_skips_weekends_and_holidays(db):
    from datetime import UTC, date, datetime

    # Paid on Thursday 24 December 2026: Friday 25 and Saturday 26 are holidays, the 27th is a Sunday.
    paid = datetime(2026, 12, 24, 10, 0, tzinfo=UTC)
    assert clock.add_working_days(paid, 3) == date(2026, 12, 30)
