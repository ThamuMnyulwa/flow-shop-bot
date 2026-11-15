"""Sample data (E2): the four FLOWW launch products at R100 with 10 units each, a staff account and test orders."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowshop import clock
from flowshop.auth import hash_password
from flowshop.models import Category, Customer, Fulfilment, MovementReason, Product, ProductStatus, Staff
from flowshop.services import orders, settings, stock

LAUNCH_CATALOGUE = [
    # code, name, description, category, status
    ("HW-01", "Headwrap", "Bold African print headwraps, made to crown every look.", "Fashion", ProductStatus.ON_SALE),
    ("NB-01", "Notebook", "A FLOWW notebook for the plans, the dreams and the lists.", "Stationery",
     ProductStatus.ON_SALE),
    ("SB-01", "Shea Butter Cream", "Rich, natural shea butter care for skin that glows.", "Skincare",
     ProductStatus.ON_SALE),
    ("MG-01", "FLOWW Mug", "Your morning reminder: bold, brave, beautiful.", "Home", ProductStatus.LAUNCHING_SOON),
]


def seed_catalogue(db: Session) -> list[Product]:
    products = []
    for i, (code, name, description, cat_name, status) in enumerate(LAUNCH_CATALOGUE):
        cat = db.scalar(select(Category).where(Category.name == cat_name))
        if cat is None:
            cat = Category(name=cat_name, sort_order=i)
            db.add(cat)
            db.flush()
        product = db.scalar(select(Product).where(Product.code == code))
        if product is None:
            product = Product(code=code, name=name, description=description, price_cents=10000, status=status,
                              category_id=cat.id, on_hand=0, reserved=0, sort_order=i, updated_at=clock.now(db))
            db.add(product)
            db.flush()
            stock.set_on_hand(db, product, 10, None, "Opening stock", MovementReason.INITIAL)
        products.append(product)
    return products


def seed_staff(db: Session, email: str = "admin@floww.local", password: str = "floww-admin") -> Staff:
    staff = db.scalar(select(Staff).where(Staff.email == email))
    if staff is None:
        staff = Staff(email=email, name="Admin", password_hash=hash_password(password), is_admin=True,
                      created_at=clock.now(db))
        db.add(staff)
        db.flush()
    return staff


def seed_all(db: Session, with_orders: bool = True) -> None:
    products = seed_catalogue(db)
    staff = seed_staff(db)
    if not settings.get(db, "collection_code"):
        settings.put(db, "collection_code", "FLOWW2026")
    if not with_orders or db.scalar(select(Customer).where(Customer.wa_id == "27820000001")):
        return
    headwrap, notebook, shea = products[0], products[1], products[2]
    thandi = Customer(wa_id="27820000001", name="Thandi Test", created_at=clock.now(db))
    sipho = Customer(wa_id="27820000002", name="Sipho Test", created_at=clock.now(db))
    db.add_all([thandi, sipho])
    db.flush()
    address = "12 Test Street, Braamfontein, Johannesburg, 2001"
    orders.confirm(db, thandi, {headwrap.id: 2}, Fulfilment.DELIVERY, address, uuid.uuid4().hex)
    paid = orders.confirm(db, sipho, {notebook.id: 1, shea.id: 1}, Fulfilment.COLLECTION, "", uuid.uuid4().hex)
    orders.mark_paid(db, paid, staff)
