import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from flowshop.models import Product, ProductStatus

VISIBLE = (ProductStatus.ON_SALE, ProductStatus.LAUNCHING_SOON)
CODE_PATTERN = re.compile(r"\[?\b([A-Z]{2,5}-\d{1,4})\b\]?", re.IGNORECASE)


def visible_products(db: Session, category_id: int | None = None) -> list[Product]:
    stmt = select(Product).where(Product.status.in_(VISIBLE))
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    return list(db.scalars(stmt.order_by(Product.sort_order, Product.name)))


STOP_WORDS = {
    "the", "and", "you", "your", "have", "has", "any", "for", "with", "what", "how", "much", "does", "can", "are",
    "want", "would", "like", "please", "need", "looking", "some", "this", "that", "there", "stock", "price", "cost",
    "buy", "order", "sell", "selling", "available", "get", "hello", "thanks",
}


def search(db: Session, text: str, limit: int = 10) -> list[Product]:
    """Name matches rank above description matches; filler words are ignored."""
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3 and w not in STOP_WORDS]
    if not words:
        return []
    conditions = [or_(func.lower(Product.name).contains(w), func.lower(Product.description).contains(w))
                  for w in words]
    candidates = db.scalars(select(Product).where(Product.status.in_(VISIBLE), or_(*conditions))).all()

    def score(p: Product) -> tuple[int, int, str]:
        name, desc = p.name.lower(), p.description.lower()
        return (-sum(w in name for w in words), -sum(w in desc for w in words), p.name)

    return sorted(candidates, key=score)[:limit]


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
