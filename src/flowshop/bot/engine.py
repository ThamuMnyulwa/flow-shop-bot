"""The ordering bot: a state machine whose state lives in PostgreSQL, so it survives restarts (B7).

The same code runs for the simulator and WhatsApp (B1). Flows aim for a confirmed order in 10 bot
messages or fewer.
"""

import logging
import re
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from flowshop import clock
from flowshop.bot import fallback
from flowshop.channels.base import InboundMessage, OutMessage, Row, buttons, menu_list, text
from flowshop.models import (
    Conversation,
    ConversationMode,
    Customer,
    Direction,
    Event,
    Fulfilment,
    Message,
    Order,
    OrderStatus,
    Product,
)
from flowshop.money import rand
from flowshop.services import catalogue, notify, orders, settings, stock
from flowshop.storage import get_storage

log = logging.getLogger(__name__)

HANDOFF_WORDS = re.compile(r"\b(human|person|agent|staff|someone|consultant|talk to|speak to|call me)\b", re.I)
GREETING_WORDS = re.compile(r"^\s*(hi|hello|hey|hallo|howzit|menu|start|sawubona|molo|dumela)\b", re.I)
ORDER_WORDS = re.compile(r"\b(my order|order status|status|where is my order)\b", re.I)
QUESTION = re.compile(r"\?|^\s*(is|are|do|does|can|could|will|would|how|what|when|where|which|why|who)\b", re.I)
PAGE_SIZE = 9  # nine products and a "More" row fit WhatsApp's ten-row list


def handle_inbound(db: Session, inbound: InboundMessage) -> bool:
    """Process one customer message exactly once (L1). Returns False for a duplicate delivery."""
    if db.scalar(select(Message.id).where(Message.external_id == inbound.message_id)) is not None:
        return False
    customer = db.scalar(select(Customer).where(Customer.wa_id == inbound.wa_id))
    if customer is None:
        customer = Customer(wa_id=inbound.wa_id, name=inbound.name, created_at=clock.now(db))
        db.add(customer)
        db.flush()
    elif inbound.name and not customer.name:
        customer.name = inbound.name
    conv = notify.conversation_for(db, customer)
    try:
        with db.begin_nested():
            db.add(Message(conversation_id=conv.id, direction=Direction.IN, sender="customer",
                           external_id=inbound.message_id or None, kind=inbound.kind, text=inbound.text,
                           payload={"reply_id": inbound.reply_id, "media_id": inbound.media_id,
                                    "mime_type": inbound.mime_type},
                           created_at=clock.now(db)))
            db.flush()
    except IntegrityError:
        return False  # the same message arrived twice at the same moment
    Bot(db, conv).handle(inbound)
    return True


class Bot:
    def __init__(self, db: Session, conv: Conversation):
        self.db = db
        self.conv = conv
        self.data = dict(conv.data or {})

    # ----- plumbing -------------------------------------------------------

    def say(self, message: OutMessage) -> None:
        notify.send(self.db, self.conv, message)

    def go(self, state: str) -> None:
        self.conv.state = state

    def save(self) -> None:
        self.conv.data = self.data  # reassign so the JSON column is marked changed
        self.conv.last_activity_at = clock.now(self.db)
        self.db.flush()

    @property
    def cart(self) -> dict[int, int]:
        return {int(k): v for k, v in self.data.get("cart", {}).items()}

    @cart.setter
    def cart(self, value: dict[int, int]) -> None:
        self.data["cart"] = {str(k): v for k, v in value.items() if v > 0}

    def event(self, kind: str, **data) -> None:
        self.db.add(Event(kind=kind, conversation_id=self.conv.id, data=data, created_at=clock.now(self.db)))

    # ----- entry ----------------------------------------------------------

    def handle(self, msg: InboundMessage) -> None:
        now = clock.now(self.db)
        idle = timedelta(hours=int(settings.get(self.db, "conversation_idle_hours")))
        previous_inbound = self.conv.last_inbound_at
        self.conv.last_inbound_at = now
        if previous_inbound and now - previous_inbound > idle and self.conv.state not in ("start", "awaiting_payment"):
            self.data = {}  # an abandoned draft expires (B7)
            self.go("start")

        if msg.kind in ("image", "document"):
            self.on_file(msg)
        elif self.conv.mode == ConversationMode.HUMAN:
            if self.conv.waiting_since is None:
                self.conv.waiting_since = now
        elif msg.kind == "reply":
            self.on_reply(msg.reply_id, msg.text)
        elif msg.kind == "text":
            self.on_text(msg.text.strip())
        else:
            self.say(text("Sorry, I can only read text, buttons, and photos or PDFs of your proof of payment."))
        self.save()

    # ----- files: proof of payment -----------------------------------------

    def on_file(self, msg: InboundMessage) -> None:
        order = orders.latest_awaiting_payment(self.db, self.conv.customer)
        if order is None:
            if self.conv.mode == ConversationMode.BOT:
                self.handoff("Sent a file with no unpaid order")
            elif self.conv.waiting_since is None:
                self.conv.waiting_since = clock.now(self.db)
            return
        from flowshop.channels import get_channel

        try:
            data, content_type = get_channel().fetch_media(msg.media_id)
            key = get_storage().put("proofs", data, content_type or msg.mime_type or "application/octet-stream")
        except Exception:
            log.exception("could not fetch proof of payment")
            notify.staff(self.db, "attention", f"A proof of payment for {order.reference} could not be downloaded.",
                         f"/inbox/{self.conv.id}")
            key, content_type = f"unavailable:{msg.media_id}", msg.mime_type
        orders.record_proof(self.db, order, key, content_type or msg.mime_type)
        if self.conv.mode == ConversationMode.BOT:
            self.say(text(f"Thank you! We've received your proof of payment for {order.reference}. "
                          "We'll confirm as soon as the money reflects in our account."))
            self.go("awaiting_payment")

    # ----- buttons and list replies ----------------------------------------

    def on_reply(self, reply_id: str, title: str) -> None:
        try:
            self._route_reply(reply_id)
        except ValueError:  # a malformed or stale button id
            self.main_menu()

    def _route_reply(self, reply_id: str) -> None:
        action, _, arg = reply_id.partition(":")
        self.conv.misunderstood_count = 0
        match action:
            case "menu":
                self.main_menu()
            case "browse":
                self.browse()
            case "human":
                self.handoff("Asked for a person")
            case "more":
                cat, _, offset = arg.partition(",")
                self.product_list(int(cat) if cat else None, int(offset))
            case "prod":
                self.product_view(int(arg))
            case "add":
                self.ask_quantity(int(arg))
            case "qty":
                self.set_quantity(int(arg))
            case "cart":
                self.show_cart()
            case "checkout":
                self.checkout()
            case "edit":
                self.edit_cart()
            case "item":
                self.item_options(int(arg))
            case "change":
                self.ask_quantity(int(arg), replace=True)
            case "remove":
                self.remove_item(int(arg))
            case "delivery":
                self.choose_delivery()
            case "code":
                self.ask_code()
            case "confirm":
                self.confirm()
            case "discard":
                self.discard()
            case "myorder":
                self.my_order()
            case "cancelorder":
                self.ask_cancel(int(arg))
            case "cancelyes":
                self.cancel_order(int(arg))
            case _:
                self.main_menu()

    # ----- free text ------------------------------------------------------

    def on_text(self, body: str) -> None:
        if not body:
            return
        if HANDOFF_WORDS.search(body):
            return self.handoff("Asked for a person")
        if (product := catalogue.by_code(self.db, body)) is not None:
            return self.product_view(product.id)  # the website's "Order on WhatsApp" link (W2)
        lowered = body.lower()
        if lowered in ("subscribe", "stop", "unsubscribe"):
            return self.marketing(lowered == "subscribe")
        state = self.conv.state
        if state == "ask_quantity" and body.isdigit():
            return self.set_quantity(int(body))
        if state == "enter_code":
            return self.check_code(body)
        if state == "ask_address":
            return self.take_address(body)
        if GREETING_WORDS.search(body):
            return self.main_menu()
        if ORDER_WORDS.search(body):
            return self.my_order()
        asked_ai = False
        if fallback.enabled() and QUESTION.search(body):
            # A real question goes to the assistant first; a bare product name is still a search.
            asked_ai = True
            if self.ai_answer(body):
                return
        found = catalogue.search(self.db, body)
        if found:
            self.conv.misunderstood_count = 0
            return self.list_products(found, "Here's what I found:")
        self.unmatched(body, asked_ai)

    def ai_answer(self, body: str) -> bool:
        answer = fallback.answer(self.db, self.conv, body)
        if answer is None:
            return False
        self.conv.misunderstood_count = 0
        self.event("ai_answer")
        self.say(buttons(answer, ("browse", "Browse products"), ("human", "Talk to a person")))
        return True

    def unmatched(self, body: str, asked_ai: bool = False) -> None:
        """Every message the menus cannot handle passes through here: the AI first when it is on, then staff."""
        if not asked_ai and self.ai_answer(body):
            return
        self.conv.misunderstood_count += 1
        if self.conv.misunderstood_count >= 2:
            return self.handoff("The bot did not understand twice")
        self.say(buttons("Sorry, I didn't catch that. You can browse our products, type a product name, "
                         "or talk to a person.",
                         ("browse", "Browse products"), ("myorder", "My order"), ("human", "Talk to a person")))

    # ----- menus ----------------------------------------------------------

    def main_menu(self) -> None:
        self.go("menu")
        name = self.conv.customer.name.split(" ")[0] if self.conv.customer.name else "there"
        cart_label = ("cart", "View my order") if self.cart else ("myorder", "My order")
        self.say(buttons(f"Hi {name}! Welcome to {settings.get(self.db, 'seller_name')}. "
                         "Browse our products, or type the name of what you're looking for.",
                         ("browse", "Browse products"), cart_label, ("human", "Talk to a person")))

    def browse(self) -> None:
        """Straight to the product list: with a small catalogue, a category step only costs a message."""
        self.product_list(None)

    def product_list(self, category_id: int | None, offset: int = 0) -> None:
        products = catalogue.visible_products(self.db, category_id)
        self.list_products(products, "Our products:", category_id, offset)

    def list_products(self, products: list[Product], intro: str, category_id: int | None = None,
                      offset: int = 0) -> None:
        if not products:
            return self.say(buttons("There's nothing to show here yet.", ("menu", "Main menu")))
        self.go("browse")
        page = products[offset:offset + PAGE_SIZE] if len(products) > 10 else products
        rows = [Row(f"prod:{p.id}", p.name, f"{rand(p.price_cents)} · {catalogue.availability_label(p)}")
                for p in page]
        if len(products) > 10 and offset + PAGE_SIZE < len(products):
            rows.append(Row(f"more:{category_id or ''},{offset + PAGE_SIZE}", "More products…"))
        self.say(menu_list(intro, rows, "View products"))

    def product_view(self, product_id: int) -> None:
        p = self.db.get(Product, product_id)
        if p is None or p.status.value == "hidden":
            return self.browse()
        self.data["product"] = p.id
        self.go("product")
        body = f"*{p.name}* · {rand(p.price_cents)}\n{p.description}\n\n{catalogue.availability_label(p)}"
        photo = catalogue.image(p)  # shown above the text, so the customer sees what they're buying
        if not p.orderable:
            return self.say(buttons(body + "\nWe can't take orders for it yet.",
                                    ("browse", "Other products"), ("menu", "Main menu"), image=photo))
        if p.available <= 0:
            return self.say(buttons(body, ("browse", "Other products"), ("human", "Talk to a person"), image=photo))
        self.say(buttons(body, (f"add:{p.id}", "Add to order"), ("browse", "Other products"), image=photo))

    # ----- building the order (B4) -----------------------------------------

    def ask_quantity(self, product_id: int, replace: bool = False) -> None:
        p = self.db.get(Product, product_id)
        if p is None or not p.orderable:
            return self.browse()
        in_cart = 0 if replace else self.cart.get(p.id, 0)
        can_add = p.available - in_cart
        if can_add <= 0:
            return self.say(buttons(f"Sorry, there's no more {p.name} available right now.",
                                    ("browse", "Other products"), ("cart", "View my order")))
        self.data["product"] = p.id
        self.data["replace"] = replace
        self.go("ask_quantity")
        rows = [Row(f"qty:{n}", str(n)) for n in range(1, min(can_add, 10) + 1)]
        self.say(menu_list(f"How many {p.name}? ({can_add} available)", rows, "Choose quantity"))

    def set_quantity(self, qty: int) -> None:
        pid = self.data.get("product")
        p = self.db.get(Product, pid) if pid else None
        if p is None or not p.orderable:
            return self.browse()
        cart = self.cart
        base = 0 if self.data.get("replace") else cart.get(p.id, 0)
        if qty <= 0:
            return self.say(text("Please choose a quantity of 1 or more."))
        if base + qty > p.available:
            self.event("refused_stock", product_id=p.id, requested=base + qty, available=p.available)
            return self.say(text(f"Sorry, only {p.available} {p.name} available. Please choose a smaller number."))
        cart[p.id] = base + qty
        self.cart = cart
        self.data.pop("replace", None)
        self.show_cart(prefix=f"Added {qty} × {p.name}.\n\n")

    def cart_lines(self) -> tuple[str, orders.Quote]:
        q = orders.quote(self.db, self.cart, None)
        lines = "\n".join(f"• {line.product.name} × {line.quantity}: {rand(line.line_cents)}" for line in q.lines)
        return lines, q

    def show_cart(self, prefix: str = "") -> None:
        if not self.cart:
            return self.say(buttons("Your order is empty.", ("browse", "Browse products"), ("menu", "Main menu")))
        self.go("cart")
        lines, q = self.cart_lines()
        self.say(buttons(f"{prefix}Your order:\n{lines}\nProducts: {rand(q.subtotal_cents)}",
                         ("browse", "Add more"), ("checkout", "Checkout"), ("edit", "Edit order")))

    def edit_cart(self) -> None:
        if not self.cart:
            return self.show_cart()
        self.go("edit")
        q = orders.quote(self.db, self.cart, None)
        rows = [Row(f"item:{line.product.id}", line.product.name[:24], f"Quantity {line.quantity}")
                for line in q.lines[:9]]
        rows.append(Row("cart:", "Done editing"))
        self.say(menu_list("Which item would you like to change?", rows, "Choose item"))

    def item_options(self, product_id: int) -> None:
        p = self.db.get(Product, product_id)
        if p is None or product_id not in self.cart:
            return self.show_cart()
        self.say(buttons(f"{p.name} × {self.cart[product_id]}",
                         (f"change:{p.id}", "Change quantity"), (f"remove:{p.id}", "Remove"), ("cart", "Back")))

    def remove_item(self, product_id: int) -> None:
        cart = self.cart
        cart.pop(product_id, None)
        self.cart = cart
        self.show_cart(prefix="Removed.\n\n")

    # ----- delivery or collection (B5, D2 to D4) ---------------------------

    def checkout(self) -> None:
        if not self.cart:
            return self.show_cart()
        self.go("fulfilment")
        fee = int(settings.get(self.db, "delivery_fee_cents"))
        free_over = int(settings.get(self.db, "free_delivery_over_cents"))
        options = [("delivery", "Delivery")]
        if not self.code_locked():
            options.append(("code", "I have a code"))
        self.say(buttons(f"Delivery costs {rand(fee)}, and it's free when your products total more than "
                         f"{rand(free_over)}.", *options))

    def code_locked(self) -> bool:
        until = self.conv.code_locked_until
        return until is not None and until > clock.now(self.db)

    def ask_code(self) -> None:
        if self.code_locked():
            return self.choose_delivery()
        self.go("enter_code")
        self.say(text("Please type your code."))

    def check_code(self, attempt: str) -> None:
        if self.code_locked():
            return self.choose_delivery()
        if settings.collection_code_matches(self.db, attempt):
            self.conv.code_failures = 0
            self.data["fulfilment"] = Fulfilment.COLLECTION.value
            self.data.pop("address", None)
            return self.summary()
        self.conv.code_failures += 1
        if self.conv.code_failures >= int(settings.get(self.db, "code_max_failures")):
            minutes = int(settings.get(self.db, "code_lock_minutes"))
            self.conv.code_locked_until = clock.now(self.db) + timedelta(minutes=minutes)
            self.conv.code_failures = 0
            self.event("code_locked")
            return self.say(buttons("That code isn't valid. We can deliver your order to you.",
                                    ("delivery", "Delivery"), ("discard", "Cancel")))
        self.say(buttons("That code isn't valid. We can deliver your order to you.",
                         ("delivery", "Delivery"), ("code", "Try again")))

    def choose_delivery(self) -> None:
        self.data["fulfilment"] = Fulfilment.DELIVERY.value
        if self.data.get("address"):
            return self.summary()
        self.go("ask_address")
        self.say(text("Please send your delivery address: street, suburb, city and postal code."))

    def take_address(self, body: str) -> None:
        if len(body) < 10 or not re.search(r"\d", body):
            return self.say(text("That address looks incomplete. Please include the street number, suburb, city "
                                 "and postal code."))
        self.data["address"] = body[:500]
        self.summary()

    # ----- summary and confirmation (B6, B9) -------------------------------

    def summary(self) -> None:
        fulfilment = Fulfilment(self.data.get("fulfilment", "delivery"))
        q = orders.quote(self.db, self.cart, fulfilment)
        if not q.lines:
            return self.show_cart()
        self.data["draft_key"] = self.data.get("draft_key") or uuid.uuid4().hex
        self.go("summary")
        lines = "\n".join(f"• {line.product.name} × {line.quantity}: {rand(line.line_cents)}" for line in q.lines)
        if fulfilment == Fulfilment.DELIVERY:
            fee = "free" if q.delivery_fee_cents == 0 else rand(q.delivery_fee_cents)
            how = f"Delivery: {fee}\nDeliver to: {self.data.get('address', '')}"
        else:
            how = "Collection from our office. We'll send the address once you've paid."
        days = settings.get(self.db, "dispatch_working_days")
        body = (f"*Order summary*\n{lines}\n{how}\n*Total: {rand(q.total_cents)}*\n\n"
                f"Payment by EFT. Paid orders are sent within {days} working days. "
                f"Returns: {settings.get(self.db, 'returns_url')}\nSeller: {settings.get(self.db, 'seller_name')}")
        self.say(buttons(body, ("confirm", "Confirm order"), ("edit", "Edit order"), ("discard", "Cancel")))

    def confirm(self) -> None:
        key = self.data.get("draft_key")
        if self.conv.state != "summary" or not key:
            existing = self.db.scalar(select(Order).where(Order.idempotency_key == (key or "")))
            if existing is None:
                return self.main_menu()  # a stale Confirm tap with no draft
        fulfilment = Fulfilment(self.data.get("fulfilment", "delivery"))
        try:
            order = orders.confirm(self.db, self.conv.customer, self.cart, fulfilment, self.data.get("address", ""),
                                   key)
        except stock.InsufficientStock as exc:
            cart = self.cart
            notes = []
            for s in exc.shortfalls:
                cart[s.product_id] = min(cart.get(s.product_id, 0), s.available)
                notes.append(f"only {s.available} {s.name} left" if s.available else f"{s.name} is sold out")
                self.event("refused_stock", product_id=s.product_id, requested=s.requested, available=s.available)
            self.cart = cart
            self.data["draft_key"] = uuid.uuid4().hex  # the order changed, so it is a new draft
            self.say(text(f"Sorry, someone ordered just before you: {', '.join(notes)}. I've updated your order."))
            return self.summary() if self.cart else self.show_cart()
        except orders.OrderError:
            return self.show_cart()
        self.event("order_confirmed", order_id=order.id)
        self.data = {}
        self.go("awaiting_payment")
        hours = settings.get(self.db, "payment_hours")
        self.say(text(f"Thank you! Order *{order.reference}* is confirmed.\n\n"
                      f"Please pay *{rand(order.total_cents)}* by EFT to:\n{settings.get(self.db, 'bank_details')}\n"
                      f"Reference: *{order.reference}*\n\n"
                      f"Then send a photo or PDF of your proof of payment here. We hold your items for {hours} hours."))

    def discard(self) -> None:
        self.data = {}
        self.say(buttons("No problem, I've cleared your order.", ("browse", "Browse products"),
                         ("menu", "Main menu")))
        self.go("menu")

    # ----- existing orders (B10) -------------------------------------------

    def my_order(self) -> None:
        if self.cart:
            return self.show_cart()
        open_orders = orders.open_orders_for(self.db, self.conv.customer)
        if not open_orders:
            return self.say(buttons("You have no open orders.", ("browse", "Browse products"),
                                    ("human", "Talk to a person")))
        order = open_orders[0]
        status = {
            OrderStatus.PENDING_PAYMENT: f"waiting for payment of {rand(order.total_cents)}",
            OrderStatus.PROOF_RECEIVED: "proof of payment received, we're checking the bank",
            OrderStatus.PAYMENT_OVERDUE: "payment overdue, items no longer held",
            OrderStatus.PAID: f"paid, to be sent by {order.dispatch_by:%d %B}" if order.dispatch_by else "paid",
            OrderStatus.DISPATCHED: "on its way",
        }[order.status]
        options = [("menu", "Main menu"), ("human", "Talk to a person")]
        if order.status in orders.UNPAID:
            options.insert(0, (f"cancelorder:{order.id}", "Cancel order"))
        self.say(buttons(f"Order {order.reference}: {status}.", *options))

    def ask_cancel(self, order_id: int) -> None:
        order = self.db.get(Order, order_id)
        if order is None or order.customer_id != self.conv.customer_id or order.status not in orders.UNPAID:
            return self.my_order()
        self.say(buttons(f"Cancel order {order.reference}?", (f"cancelyes:{order.id}", "Yes, cancel"),
                         ("myorder", "No, keep it")))

    def cancel_order(self, order_id: int) -> None:
        order = self.db.get(Order, order_id)
        if order is None or order.customer_id != self.conv.customer_id:
            return self.my_order()
        try:
            orders.cancel(self.db, order, "customer", reason="Cancelled by the customer in the chat")
        except orders.InvalidTransition:
            return self.say(buttons("This order can no longer be cancelled in the chat.",
                                    ("human", "Talk to a person"), ("menu", "Main menu")))
        self.go("menu")

    # ----- marketing consent (L3) ------------------------------------------

    def marketing(self, opt_in: bool) -> None:
        customer = self.conv.customer
        customer.marketing_opt_in = opt_in
        customer.marketing_opt_in_at = clock.now(self.db)
        self.say(text("You're subscribed to FLOWW news. Reply STOP any time." if opt_in
                      else "You won't receive FLOWW news. Reply SUBSCRIBE any time."))

    # ----- handoff (B8) ---------------------------------------------------

    def handoff(self, reason: str) -> None:
        self.conv.mode = ConversationMode.HUMAN
        self.conv.waiting_since = clock.now(self.db)
        self.conv.handoff_reason = reason
        self.conv.misunderstood_count = 0
        self.event("handoff", reason=reason)
        self.say(text("I'm passing you to our team. Someone will reply here as soon as they can."))
        notify.staff(self.db, "handoff", f"{self.conv.customer.name or self.conv.customer.wa_id} is waiting: {reason}.",
                     f"/inbox/{self.conv.id}")


def return_to_bot(db: Session, conv: Conversation) -> None:
    conv.mode = ConversationMode.BOT
    conv.waiting_since = None
    conv.handoff_reason = ""
    conv.state = "menu"
    conv.misunderstood_count = 0
    db.flush()
    if notify.in_window(db, conv):
        notify.send(db, conv, buttons("You're back with the FLOWW assistant.", ("browse", "Browse products"),
                                      ("myorder", "My order")))
