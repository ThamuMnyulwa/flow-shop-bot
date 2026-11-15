"""Stock rules (S2 to S5). Every change is a conditional update plus a row in the stock movement log.

The database constraint `reserved <= on_hand` is the backstop: even a bug here cannot oversell.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowshop import clock
from flowshop.models import MovementReason, Product, ProductStatus, StockMovement


@dataclass(frozen=True)
class Shortfall:
    product_id: int
    name: str
    requested: int
    available: int


class InsufficientStock(Exception):
    def __init__(self, shortfalls: list[Shortfall]):
        self.shortfalls = shortfalls
        super().__init__(", ".join(f"{s.name}: {s.available} left, {s.requested} asked" for s in shortfalls))


class StockError(Exception):
    pass


def _expire(db: Session, product_id: int) -> None:
    obj = db.identity_map.get(db.identity_key(Product, product_id))
    if obj is not None:
        db.expire(obj)


def _log(db: Session, product_id: int, reason: MovementReason, d_on_hand=0, d_reserved=0, order_id=None,
         staff_id=None, note="") -> None:
    db.add(StockMovement(product_id=product_id, delta_on_hand=d_on_hand, delta_reserved=d_reserved,
                         reason=reason, order_id=order_id, staff_id=staff_id, note=note, created_at=clock.now(db)))


def _merge(lines: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: dict[int, int] = {}
    for product_id, qty in lines:
        if qty <= 0:
            raise ValueError("quantity must be positive")
        merged[product_id] = merged.get(product_id, 0) + qty
    return sorted(merged.items())  # fixed order avoids deadlocks between two orders


def reserve(db: Session, lines: Iterable[tuple[int, int]], order_id: int, require_on_sale: bool = True) -> None:
    """Reserve every line or none. Raises InsufficientStock and leaves stock untouched on any shortfall."""
    merged = _merge(lines)
    db.flush()
    shortfalls: list[Shortfall] = []
    with db.begin_nested() as sp:
        for product_id, qty in merged:
            stmt = (
                update(Product)
                .where(Product.id == product_id, Product.on_hand - Product.reserved >= qty)
                .values(reserved=Product.reserved + qty)
                .execution_options(synchronize_session=False)
            )
            if require_on_sale:
                stmt = stmt.where(Product.status == ProductStatus.ON_SALE)
            if db.execute(stmt).rowcount == 1:
                _log(db, product_id, MovementReason.RESERVE, d_reserved=qty, order_id=order_id)
            else:
                product = db.get(Product, product_id, populate_existing=True)
                available = 0 if product is None or (require_on_sale and not product.orderable) else product.available
                shortfalls.append(Shortfall(product_id, product.name if product else "?", qty, max(available, 0)))
        if shortfalls:
            sp.rollback()
    for product_id, _ in merged:
        _expire(db, product_id)
    if shortfalls:
        raise InsufficientStock(shortfalls)
    for product_id, _ in merged:
        check_low_stock(db, product_id)


def release(db: Session, lines: Iterable[tuple[int, int]], order_id: int, note: str = "") -> None:
    for product_id, qty in _merge(lines):
        db.execute(
            update(Product).where(Product.id == product_id).values(reserved=Product.reserved - qty)
            .execution_options(synchronize_session=False)
        )
        _log(db, product_id, MovementReason.RELEASE, d_reserved=-qty, order_id=order_id, note=note)
        _expire(db, product_id)
        check_low_stock(db, product_id)


def ship(db: Session, lines: Iterable[tuple[int, int]], order_id: int, staff_id: int | None) -> None:
    """Goods leave the building: take them off on-hand and off reserved (S4)."""
    for product_id, qty in _merge(lines):
        db.execute(
            update(Product).where(Product.id == product_id)
            .values(on_hand=Product.on_hand - qty, reserved=Product.reserved - qty)
            .execution_options(synchronize_session=False)
        )
        _log(db, product_id, MovementReason.SHIP, d_on_hand=-qty, d_reserved=-qty, order_id=order_id,
             staff_id=staff_id)
        _expire(db, product_id)


def set_on_hand(db: Session, product: Product, new_on_hand: int, staff_id: int | None, note: str,
                reason: MovementReason = MovementReason.ADJUSTMENT) -> None:
    """Staff count or adjustment. Refused if it would leave less on hand than is reserved."""
    if new_on_hand < 0:
        raise StockError("On-hand stock cannot be negative.")
    db.flush()
    current = db.get(Product, product.id, populate_existing=True, with_for_update=True)
    assert current is not None
    delta = new_on_hand - current.on_hand
    if delta == 0:
        return
    try:
        with db.begin_nested():
            current.on_hand = new_on_hand
            current.updated_at = clock.now(db)
            db.flush()
    except IntegrityError as exc:
        db.refresh(current)
        raise StockError(
            f"{current.reserved} units are reserved for open orders, so on-hand cannot go below that."
        ) from exc
    _log(db, product.id, reason, d_on_hand=delta, staff_id=staff_id, note=note)
    check_low_stock(db, product.id)


def check_low_stock(db: Session, product_id: int) -> None:
    """Alert staff once when a product sells out or falls to its low-stock level (S5)."""
    from flowshop.services import notify

    product = db.get(Product, product_id)
    if product is None or product.status == ProductStatus.HIDDEN:
        return
    low = product.available <= product.low_stock_threshold
    if low and not product.low_stock_alerted:
        product.low_stock_alerted = True
        what = "is sold out" if product.available <= 0 else f"is low: {product.available} available"
        notify.staff(db, "low_stock", f"{product.name} {what}.", f"/admin/products/{product.id}")
    elif not low and product.low_stock_alerted:
        product.low_stock_alerted = False
