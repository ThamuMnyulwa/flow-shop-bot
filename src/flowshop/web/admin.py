"""The admin page (A1 to A7, D1, D2, R1): stock, orders, settings, staff and reports. Works on a phone."""

import time
import uuid
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from flowshop import clock
from flowshop.auth import admin_only, check_password, current_staff, hash_password, verify_csrf
from flowshop.db import get_db
from flowshop.jobs import run_all
from flowshop.models import (
    Category,
    Customer,
    Fulfilment,
    MovementReason,
    Notification,
    Order,
    OrderItem,
    OrderStatus,
    PaymentProof,
    Product,
    ProductStatus,
    Return,
    Staff,
    StockMovement,
)
from flowshop.money import parse_rand, rand
from flowshop.services import orders, settings, stock
from flowshop.storage import get_storage
from flowshop.web.common import flash, render

router = APIRouter(prefix="/admin", dependencies=[Depends(verify_csrf)])
S = OrderStatus

# A small in-memory brake on password guessing, per client address.
_failed_logins: dict[str, list[float]] = defaultdict(list)


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


# ----- sign-in ---------------------------------------------------------------

@router.get("/login")
def login_page(request: Request, db: Session = Depends(get_db), next: str = "/admin"):
    return render(request, "login.html", db, next=next if next.startswith("/") else "/admin")


@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), next: str = Form("/admin"),
          db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "?"
    recent = [t for t in _failed_logins[ip] if t > time.time() - 900]
    _failed_logins[ip] = recent
    if len(recent) >= 10:
        return render(request, "login.html", db, error="Too many attempts. Try again in 15 minutes.", next=next,
                      status_code=429)
    staff = db.scalar(select(Staff).where(func.lower(Staff.email) == email.strip().lower()))
    if staff is None or not staff.active or not check_password(password, staff.password_hash):
        recent.append(time.time())
        return render(request, "login.html", db, error="Wrong email or password.", next=next, status_code=401)
    request.session.clear()
    request.session["staff_id"] = staff.id
    return back(next if next.startswith("/") and not next.startswith("//") else "/admin")


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return back("/admin/login")


# ----- dashboard ---------------------------------------------------------------

@router.get("")
def dashboard(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    today = clock.local_date(clock.now(db))
    attention = db.scalars(select(Order).where(Order.needs_attention.is_(True)).order_by(Order.id)).all()
    to_check = db.scalars(select(Order).where(Order.status == S.PROOF_RECEIVED).order_by(Order.proof_received_at)).all()
    to_send = db.scalars(select(Order).where(Order.status == S.PAID).order_by(Order.dispatch_by, Order.id)).all()
    dispatch = [(o, clock.working_days_between(today, o.dispatch_by) if o.dispatch_by else None) for o in to_send]
    low = [p for p in db.scalars(select(Product).where(Product.status != ProductStatus.HIDDEN))
           if p.available <= p.low_stock_threshold]
    notes = db.scalars(select(Notification).order_by(Notification.id.desc()).limit(8)).all()
    return render(request, "dashboard.html", db, staff, attention=attention, to_check=to_check, dispatch=dispatch,
                  low=low, notes=notes)


@router.get("/notifications")
def notifications(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    notes = db.scalars(select(Notification).order_by(Notification.id.desc()).limit(100)).all()
    return render(request, "notifications.html", db, staff, notes=notes)


@router.post("/notifications/read")
def notifications_read(db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    for note in db.scalars(select(Notification).where(Notification.read.is_(False))):
        note.read = True
    return back("/admin/notifications")


# ----- products and stock (A2, S6) -------------------------------------------------

@router.get("/products")
def products(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    rows = db.scalars(select(Product).options(selectinload(Product.category))
                      .order_by(Product.sort_order, Product.name)).all()
    return render(request, "products.html", db, staff, products=rows)


@router.get("/products/new")
def product_new(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    return render(request, "product_form.html", db, staff, product=None, categories=_categories(db),
                  statuses=list(ProductStatus))


def _categories(db: Session) -> list[Category]:
    return list(db.scalars(select(Category).order_by(Category.sort_order, Category.name)))


def _category_id(db: Session, name: str) -> int | None:
    name = name.strip()[:24]
    if not name:
        return None
    cat = db.scalar(select(Category).where(func.lower(Category.name) == name.lower()))
    if cat is None:
        cat = Category(name=name)
        db.add(cat)
        db.flush()
    return cat.id


def _validate_product(code: str, name: str, description: str, price: str) -> tuple[str, int]:
    if not code.strip() or not name.strip():
        raise ValueError("Code and name are required.")
    if len(name) > 24:
        raise ValueError("WhatsApp shows at most 24 characters of a name.")
    if len(description) > 72:
        raise ValueError("WhatsApp shows at most 72 characters of a description.")
    try:
        cents = parse_rand(price)
    except ValueError:
        raise ValueError("Enter the price in rand, for example 100 or 99.50.") from None
    return code.strip().upper(), cents


@router.post("/products")
def product_create(request: Request, code: str = Form(...), name: str = Form(...), description: str = Form(""),
                   price: str = Form(...), category: str = Form(""), status: ProductStatus = Form(...),
                   on_hand: int = Form(0), low_stock_threshold: int = Form(2), db: Session = Depends(get_db),
                   staff: Staff = Depends(current_staff)):
    try:
        code, cents = _validate_product(code, name, description, price)
        if db.scalar(select(Product.id).where(Product.code == code)):
            raise ValueError(f"The code {code} is already used.")
    except ValueError as exc:
        flash(request, str(exc), "error")
        return back("/admin/products/new")
    product = Product(code=code, name=name.strip(), description=description.strip(), price_cents=cents,
                      status=status, category_id=_category_id(db, category), on_hand=0, reserved=0,
                      low_stock_threshold=low_stock_threshold, updated_at=clock.now(db))
    db.add(product)
    db.flush()
    if on_hand:
        stock.set_on_hand(db, product, on_hand, staff.id, "Opening stock", MovementReason.INITIAL)
    flash(request, f"Added {product.name}.")
    return back(f"/admin/products/{product.id}")


@router.get("/products/{product_id}")
def product_detail(product_id: int, request: Request, db: Session = Depends(get_db),
                   staff: Staff = Depends(current_staff)):
    product = db.get(Product, product_id) or _404()
    moves = db.scalars(select(StockMovement).where(StockMovement.product_id == product_id)
                       .options(selectinload(StockMovement.staff)).order_by(StockMovement.id.desc()).limit(50)).all()
    return render(request, "product_form.html", db, staff, product=product, categories=_categories(db),
                  statuses=list(ProductStatus), moves=moves)


@router.post("/products/{product_id}")
def product_update(product_id: int, request: Request, code: str = Form(...), name: str = Form(...),
                   description: str = Form(""), price: str = Form(...), category: str = Form(""),
                   status: ProductStatus = Form(...), low_stock_threshold: int = Form(2),
                   db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    product = db.get(Product, product_id) or _404()
    try:
        code, cents = _validate_product(code, name, description, price)
        clash = db.scalar(select(Product.id).where(Product.code == code, Product.id != product_id))
        if clash:
            raise ValueError(f"The code {code} is already used.")
    except ValueError as exc:
        flash(request, str(exc), "error")
        return back(f"/admin/products/{product_id}")
    product.code, product.name, product.description = code, name.strip(), description.strip()
    product.price_cents, product.status = cents, status
    product.category_id = _category_id(db, category)
    product.low_stock_threshold = low_stock_threshold
    product.updated_at = clock.now(db)
    db.flush()
    stock.check_low_stock(db, product.id)
    flash(request, "Saved. The website shows the change straight away.")
    return back(f"/admin/products/{product_id}")


@router.post("/products/{product_id}/stock")
def product_stock(product_id: int, request: Request, on_hand: int = Form(...), note: str = Form(...),
                  db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    product = db.get(Product, product_id) or _404()
    try:
        stock.set_on_hand(db, product, on_hand, staff.id, note.strip() or "Stock count")
    except stock.StockError as exc:
        flash(request, str(exc), "error")
    else:
        flash(request, f"{product.name}: {on_hand} on hand.")
    return back(f"/admin/products/{product_id}")


@router.post("/products/{product_id}/image")
async def product_image(product_id: int, request: Request, image: UploadFile = File(...),
                        db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    product = db.get(Product, product_id) or _404()
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        flash(request, "Use a JPEG, PNG or WebP image.", "error")
        return back(f"/admin/products/{product_id}")
    data = await image.read()
    if len(data) > 5 * 1024 * 1024:
        flash(request, "Images must be under 5 MB.", "error")
        return back(f"/admin/products/{product_id}")
    product.image_key = get_storage().put("products", data, image.content_type)
    product.updated_at = clock.now(db)
    flash(request, "Image updated.")
    return back(f"/admin/products/{product_id}")


# ----- orders (A3, A6, A7, D1, P2, P4, R1) ----------------------------------------------

@router.get("/orders")
def order_list(request: Request, status: str = "open", db: Session = Depends(get_db),
               staff: Staff = Depends(current_staff)):
    stmt = select(Order).options(selectinload(Order.customer)).order_by(Order.id.desc()).limit(200)
    if status == "open":
        stmt = stmt.where(Order.status.in_(orders.OPEN))
    elif status == "attention":
        stmt = stmt.where(Order.needs_attention.is_(True))
    elif status in {s.value for s in S}:
        stmt = stmt.where(Order.status == S(status))
    counts = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    return render(request, "orders.html", db, staff, orders=db.scalars(stmt).all(), current=status,
                  counts=counts, statuses=list(S))


@router.get("/orders/new")
def order_new(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    products_ = db.scalars(select(Product).where(Product.status == ProductStatus.ON_SALE)
                           .order_by(Product.sort_order)).all()
    return render(request, "order_new.html", db, staff, products=products_)


@router.post("/orders/new")
async def order_create(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    form = await request.form()
    wa_id = "".join(ch for ch in str(form.get("wa_id", "")) if ch.isdigit())
    if wa_id.startswith("0"):
        wa_id = "27" + wa_id[1:]
    if len(wa_id) < 10:
        flash(request, "Enter the customer's WhatsApp number, for example 0821234567.", "error")
        return back("/admin/orders/new")
    cart = {}
    for key, value in form.items():
        if key.startswith("qty_") and str(value).strip() and int(str(value)) > 0:
            cart[int(key[4:])] = int(str(value))
    fulfilment = Fulfilment(str(form.get("fulfilment", "delivery")))
    customer = db.scalar(select(Customer).where(Customer.wa_id == wa_id))
    if customer is None:
        customer = Customer(wa_id=wa_id, name=str(form.get("name", "")).strip(), created_at=clock.now(db))
        db.add(customer)
        db.flush()
    try:
        order = orders.confirm(db, customer, cart, fulfilment, str(form.get("address", "")).strip(),
                               str(form.get("draft_key") or uuid.uuid4().hex), staff=staff)
    except stock.InsufficientStock as exc:
        flash(request, f"Not enough stock: {exc}", "error")
        return back("/admin/orders/new")
    except orders.OrderError as exc:
        flash(request, str(exc), "error")
        return back("/admin/orders/new")
    flash(request, f"Created {order.reference}. Give the customer the bank details and this reference.")
    return back(f"/admin/orders/{order.id}")


@router.get("/orders/{order_id}")
def order_detail(order_id: int, request: Request, db: Session = Depends(get_db),
                 staff: Staff = Depends(current_staff)):
    order = db.scalar(select(Order).where(Order.id == order_id).options(
        selectinload(Order.items), selectinload(Order.events), selectinload(Order.proofs),
        selectinload(Order.customer))) or _404()
    returns = db.scalars(select(Return).where(Return.order_id == order_id).order_by(Return.id)).all()
    from flowshop.services.notify import conversation_for

    conv = conversation_for(db, order.customer)
    return render(request, "order_detail.html", db, staff, order=order, returns=returns, conv=conv)


@router.post("/orders/{order_id}/returns")
def order_return(order_id: int, request: Request, product_id: int = Form(...), quantity: int = Form(...),
                 reason: str = Form(...), refund: str = Form(...), db: Session = Depends(get_db),
                 staff: Staff = Depends(current_staff)):
    """Record a return (R1). The items are written off: logged, never added back to sellable stock."""
    order = db.get(Order, order_id) or _404()
    item = db.scalar(select(OrderItem).where(OrderItem.order_id == order_id, OrderItem.product_id == product_id))
    already = db.scalar(select(func.coalesce(func.sum(Return.quantity), 0)).where(
        Return.order_id == order_id, Return.product_id == product_id))
    if order.status not in (S.DISPATCHED, S.DELIVERED, S.COLLECTED) or item is None:
        flash(request, "Returns can only be recorded for items that were sent or collected.", "error")
        return back(f"/admin/orders/{order_id}")
    if quantity <= 0 or quantity + already > item.quantity or not reason.strip():
        flash(request, "Check the quantity and give a reason.", "error")
        return back(f"/admin/orders/{order_id}")
    try:
        refund_cents = parse_rand(refund)
    except ValueError:
        flash(request, "Enter the refund in rand.", "error")
        return back(f"/admin/orders/{order_id}")
    now = clock.now(db)
    db.add(Return(order_id=order_id, product_id=product_id, quantity=quantity, reason=reason.strip(),
                  refund_cents=refund_cents, staff_id=staff.id, created_at=now))
    db.add(StockMovement(product_id=product_id, reason=MovementReason.RETURN_WRITE_OFF, order_id=order_id,
                         staff_id=staff.id, note=f"{quantity} returned and written off: {reason.strip()}",
                         created_at=now))
    flash(request, f"Return recorded, refund {rand(refund_cents)}.")
    return back(f"/admin/orders/{order_id}")


@router.post("/orders/{order_id}/{action}")
def order_action(order_id: int, action: str, request: Request, note: str = Form(""),
                 db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    order = db.get(Order, order_id) or _404()
    actions = {
        "paid": lambda: orders.mark_paid(db, order, staff),
        "dispatch": lambda: orders.dispatch(db, order, staff),
        "collect": lambda: orders.collect(db, order, staff),
        "deliver": lambda: orders.deliver(db, order, staff),
        "cancel": lambda: orders.cancel(db, order, "staff", staff, note or "Cancelled by staff"),
        "retry": lambda: orders.retry_reservation(db, order, staff),
        "refund": lambda: orders.record_refund(db, order, staff, note or "Refunded"),
    }
    if action not in actions:
        raise HTTPException(404)
    try:
        actions[action]()
    except orders.OrderError as exc:
        flash(request, str(exc), "error")
    else:
        flash(request, f"{order.reference}: {order.status.value.replace('_', ' ')}.")
    return back(f"/admin/orders/{order_id}")


@router.get("/proofs/{proof_id}")
def proof_file(proof_id: int, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    """Proof-of-payment files are visible to signed-in staff only."""
    proof = db.get(PaymentProof, proof_id) or _404()
    if proof.storage_key.startswith("unavailable:"):
        raise HTTPException(404, "This file could not be downloaded from WhatsApp.")
    return Response(get_storage().get(proof.storage_key), media_type=proof.content_type,
                    headers={"Cache-Control": "private, no-store"})


# ----- settings (D2, D3) -----------------------------------------------------------------

MONEY_KEYS = ("delivery_fee_cents", "free_delivery_over_cents")


@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    values = {key: settings.get(db, key) for key in settings.LABELS}
    return render(request, "settings.html", db, staff, values=values, labels=settings.LABELS, money=MONEY_KEYS)


@router.post("/settings")
async def settings_save(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(admin_only)):
    form = await request.form()
    for key in settings.LABELS:
        if key not in form:
            continue
        raw = str(form[key]).strip()
        if key in MONEY_KEYS:
            try:
                settings.put(db, key, parse_rand(raw))
            except ValueError:
                flash(request, f"{settings.LABELS[key]}: enter an amount in rand.", "error")
                return back("/admin/settings")
        elif key == "collection_code":
            if raw and len(raw) < 6:
                flash(request, "Use a collection code of at least 6 characters, or leave it empty to turn "
                      "collection off.", "error")
                return back("/admin/settings")
            settings.put(db, key, raw.upper())
        else:
            settings.put(db, key, raw)
    flash(request, "Settings saved.")
    return back("/admin/settings")


# ----- staff accounts ---------------------------------------------------------------

@router.get("/staff")
def staff_page(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(admin_only)):
    return render(request, "staff.html", db, staff, people=db.scalars(select(Staff).order_by(Staff.name)).all())


@router.post("/staff")
def staff_create(request: Request, email: str = Form(...), name: str = Form(...), password: str = Form(...),
                 is_admin: bool = Form(False), db: Session = Depends(get_db), staff: Staff = Depends(admin_only)):
    if len(password) < 10:
        flash(request, "Passwords need at least 10 characters.", "error")
        return back("/admin/staff")
    if db.scalar(select(Staff.id).where(func.lower(Staff.email) == email.strip().lower())):
        flash(request, "That email already has an account.", "error")
        return back("/admin/staff")
    db.add(Staff(email=email.strip().lower(), name=name.strip(), password_hash=hash_password(password),
                 is_admin=is_admin, created_at=clock.now(db)))
    flash(request, f"Added {name}.")
    return back("/admin/staff")


@router.post("/staff/{staff_id}/toggle")
def staff_toggle(staff_id: int, request: Request, db: Session = Depends(get_db), staff: Staff = Depends(admin_only)):
    person = db.get(Staff, staff_id) or _404()
    if person.id == staff.id:
        flash(request, "You can't switch off your own account.", "error")
    else:
        person.active = not person.active
    return back("/admin/staff")


@router.post("/staff/{staff_id}/password")
def staff_password(staff_id: int, request: Request, password: str = Form(...), db: Session = Depends(get_db),
                   staff: Staff = Depends(current_staff)):
    if staff_id != staff.id and not staff.is_admin:
        raise HTTPException(403)
    if len(password) < 10:
        flash(request, "Passwords need at least 10 characters.", "error")
        return back("/admin/staff" if staff.is_admin else "/admin")
    person = db.get(Staff, staff_id) or _404()
    person.password_hash = hash_password(password)
    flash(request, "Password changed.")
    return back("/admin/staff" if staff.is_admin else "/admin")


# ----- report (A4) and success metrics -----------------------------------------------------

@router.get("/reports")
def reports(request: Request, db: Session = Depends(get_db), staff: Staff = Depends(current_staff)):
    from flowshop.services.reports import metrics, weekly

    return render(request, "reports.html", db, staff, weeks=weekly(db), metrics=metrics(db))


# ----- time travel for testing (E8) ------------------------------------------------------

@router.post("/clock")
def clock_move(request: Request, hours: int = Form(0), reset: bool = Form(False), db: Session = Depends(get_db),
               staff: Staff = Depends(current_staff)):
    try:
        if reset:
            clock.reset(db)
        elif hours:
            clock.advance(db, timedelta(hours=hours))
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    result = run_all(db)
    flash(request, f"Clock now {clock.now(db).astimezone(clock.SA_TZ):%a %d %b %H:%M}. Reminders sent: "
          f"{len(result['reminded'])}. Stock released: {len(result['released'])}.")
    referer = urlparse(request.headers.get("referer") or "")
    return back(referer.path if referer.path.startswith("/") and not referer.path.startswith("//") else "/admin")


def _404():
    raise HTTPException(404)
