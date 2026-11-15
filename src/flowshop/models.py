"""Database schema. The order lifecycle and stock rules are in the PRD section of the same name."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowshop.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def _enum(cls: type[StrEnum]) -> Enum:
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class ProductStatus(StrEnum):
    ON_SALE = "on_sale"
    LAUNCHING_SOON = "launching_soon"
    HIDDEN = "hidden"


class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PROOF_RECEIVED = "proof_received"
    PAYMENT_OVERDUE = "payment_overdue"
    PAID = "paid"
    DISPATCHED = "dispatched"
    COLLECTED = "collected"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Fulfilment(StrEnum):
    DELIVERY = "delivery"
    COLLECTION = "collection"


class MovementReason(StrEnum):
    INITIAL = "initial"
    ADJUSTMENT = "adjustment"
    RESERVE = "reserve"
    RELEASE = "release"
    SHIP = "ship"
    RETURN_WRITE_OFF = "return_write_off"


class ConversationMode(StrEnum):
    BOT = "bot"
    HUMAN = "human"


class Direction(StrEnum):
    IN = "in"
    OUT = "out"


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(24), unique=True)  # WhatsApp list row titles hold 24 characters
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("on_hand >= 0", name="on_hand_not_negative"),
        CheckConstraint("reserved >= 0", name="reserved_not_negative"),
        CheckConstraint("reserved <= on_hand", name="reserved_within_on_hand"),
        CheckConstraint("price_cents >= 0", name="price_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # used in website links, e.g. HW-01
    name: Mapped[str] = mapped_column(String(24))
    description: Mapped[str] = mapped_column(String(72), default="")  # WhatsApp list row descriptions hold 72
    price_cents: Mapped[int] = mapped_column(Integer)
    status: Mapped[ProductStatus] = mapped_column(_enum(ProductStatus), default=ProductStatus.ON_SALE)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    image_key: Mapped[str | None] = mapped_column(String(255))
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    low_stock_threshold: Mapped[int] = mapped_column(Integer, default=2)
    low_stock_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    category: Mapped[Category | None] = relationship(back_populates="products")

    @property
    def available(self) -> int:
        return self.on_hand - self.reserved

    @property
    def orderable(self) -> bool:
        return self.status == ProductStatus.ON_SALE


class StockMovement(Base):
    """Every stock change is one row, so quantities can be rebuilt from the log (A2)."""

    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    delta_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    delta_reserved: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[MovementReason] = mapped_column(_enum(MovementReason))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    product: Mapped[Product] = relationship()
    staff: Mapped[Staff | None] = relationship()


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    wa_id: Mapped[str] = mapped_column(String(32), unique=True)  # WhatsApp number in international form
    name: Mapped[str] = mapped_column(String(120), default="")
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("subtotal_cents >= 0 AND delivery_fee_cents >= 0", name="amounts_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str | None] = mapped_column(String(16), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus), index=True)
    fulfilment: Mapped[Fulfilment] = mapped_column(_enum(Fulfilment))
    address: Mapped[str] = mapped_column(Text, default="")
    subtotal_cents: Mapped[int] = mapped_column(Integer)
    delivery_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    stock_reserved: Mapped[bool] = mapped_column(Boolean, default=False)
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False)
    attention_reason: Mapped[str] = mapped_column(Text, default="")
    created_by_staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))

    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    proof_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    overdue_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_by: Mapped[date | None] = mapped_column(Date)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_note: Mapped[str] = mapped_column(Text, default="")

    customer: Mapped[Customer] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", order_by="OrderItem.id")
    events: Mapped[list["OrderEvent"]] = relationship(back_populates="order", order_by="OrderEvent.id")
    proofs: Mapped[list["PaymentProof"]] = relationship(back_populates="order", order_by="PaymentProof.id")

    @property
    def total_cents(self) -> int:
        return self.subtotal_cents + self.delivery_fee_cents


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="quantity_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    name: Mapped[str] = mapped_column(String(120))  # snapshot at order time
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()

    @property
    def line_cents(self) -> int:
        return self.unit_price_cents * self.quantity


class OrderEvent(Base):
    """Status history: who changed what and when (A6). Also the source for success metrics."""

    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(32))  # customer, staff, system
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="events")
    staff: Mapped[Staff | None] = relationship()


class PaymentProof(Base):
    __tablename__ = "payment_proofs"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship(back_populates="proofs")


class Return(Base):
    """A return against an order (R1). Returned items are written off, never added back to stock."""

    __tablename__ = "returns"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    refund_cents: Mapped[int] = mapped_column(Integer)
    staff_id: Mapped[int] = mapped_column(ForeignKey("staff.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    order: Mapped[Order] = relationship()
    product: Mapped[Product] = relationship()
    staff: Mapped[Staff] = relationship()


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), unique=True)
    mode: Mapped[ConversationMode] = mapped_column(_enum(ConversationMode), default=ConversationMode.BOT)
    state: Mapped[str] = mapped_column(String(32), default="start")
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    waiting_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    handoff_reason: Mapped[str] = mapped_column(Text, default="")
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    misunderstood_count: Mapped[int] = mapped_column(Integer, default=0)
    code_failures: Mapped[int] = mapped_column(Integer, default=0)
    code_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped[Customer] = relationship()
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation", order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"), index=True)
    direction: Mapped[Direction] = mapped_column(_enum(Direction))
    sender: Mapped[str] = mapped_column(String(16))  # customer, bot, staff, ai
    staff_id: Mapped[int | None] = mapped_column(ForeignKey("staff.id"))
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True)  # WhatsApp message id: dedupe (L1)
    kind: Mapped[str] = mapped_column(String(16))  # text, buttons, list, image, document, template, reply
    text: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    staff: Mapped[Staff | None] = relationship()


class Setting(Base):
    """Business settings staff can change: delivery fee, free-delivery threshold, collection code, bank details."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONType)


class Notification(Base):
    """A staff alert (A5, S5). Shown on the admin page and optionally emailed."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    link: Mapped[str] = mapped_column(String(255), default="")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Event(Base):
    """Analytics events for success metrics: handoffs, refusals, bot replies."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    conversation_id: Mapped[int | None] = mapped_column(ForeignKey("conversations.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
