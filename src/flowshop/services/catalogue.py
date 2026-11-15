import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from flowshop.models import Category, Product, ProductStatus

VISIBLE = (ProductStatus.ON_SALE, ProductStatus.LAUNCHING_SOON)
CODE_PATTERN = re.compile(r"\[?\b([A-Z]{2,5}-\d{1,4})\b\]?", re.IGNORECASE)


def visible_products(db: Session, category_id: int | None = None) -> list[Product]:
    stmt = select(Product).where(Product.status.in_(VISIBLE))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    return list(db.scalars(stmt.order_by(Product.sort_order, Product.name)))


def categories_with_products(db: Session) -> list[Category]:
    stmt = (select(Category).join(Product).where(Product.status.in_(VISIBLE)).group_by(Category.id)
            .order_by(Category.sort_order, Category.name))
    return list(db.scalars(stmt))


def search(db: Session, text: str, limit: int = 10) -> list[Product]:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3]
    if not words:
        return []
    conditions = [or_(func.lower(Product.name).contains(w), func.lower(Product.description).contains(w))
                  for w in words]
    stmt = select(Product).where(Product.status.in_(VISIBLE), or_(*conditions)).order_by(Product.name).limit(limit)
    return list(db.scalars(stmt))


def by_code(db: Session, text: str) -> Product | None:
    match = CODE_PATTERN.search(text)
    if not match:
        return None
    return db.scalar(select(Product).where(func.upper(Product.code) == match.group(1).upper(),
                                           Product.status.in_(VISIBLE)))


def availability_label(product: Product) -> str:
    if product.status == ProductStatus.LAUNCHING_SOON:
        return "Launching soon"
    if product.available <= 0:
        return "Sold out"
    return f"{product.available} available"
