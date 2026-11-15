"""The public, read-only product API the website calls (W1, W2). Nothing here changes data."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from flowshop.config import get_settings
from flowshop.db import get_db
from flowshop.models import Product
from flowshop.services import catalogue, settings
from flowshop.storage import get_storage

router = APIRouter(prefix="/api", tags=["public"])
CACHE = "public, max-age=30"  # live enough for stock, light on the database


def whatsapp_link(product: Product) -> str:
    message = f"Hi, I'd like to order {product.name} [{product.code}]"
    return f"https://wa.me/{get_settings().wa_business_number}?text={quote(message)}"


def product_json(product: Product) -> dict:
    base = get_settings().base_url
    return {
        "code": product.code,
        "name": product.name,
        "description": product.description,
        "price_cents": product.price_cents,
        "currency": "ZAR",
        "status": product.status.value,
        "available": max(product.available, 0) if product.orderable else 0,
        "availability": catalogue.availability_label(product),
        "orderable": product.orderable and product.available > 0,
        "category": product.category.name if product.category else None,
        "image_url": f"{base}/api/images/{product.image_key}" if product.image_key else None,
        "order_url": whatsapp_link(product),
    }


@router.get("/products")
def list_products(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = CACHE
    return {"products": [product_json(p) for p in catalogue.visible_products(db)]}


@router.get("/products/{code}")
def get_product(code: str, response: Response, db: Session = Depends(get_db)):
    product = db.scalar(select(Product).where(Product.code == code.upper(), Product.status.in_(catalogue.VISIBLE)))
    if product is None:
        raise HTTPException(404, "No such product")
    response.headers["Cache-Control"] = CACHE
    return product_json(product)


@router.get("/shop")
def shop_info(response: Response, db: Session = Depends(get_db)):
    """Seller details and delivery fees for the website's disclosure pages (W3)."""
    response.headers["Cache-Control"] = "public, max-age=300"
    return {
        "seller_name": settings.get(db, "seller_name"),
        "delivery_fee_cents": settings.get(db, "delivery_fee_cents"),
        "free_delivery_over_cents": settings.get(db, "free_delivery_over_cents"),
        "dispatch_working_days": settings.get(db, "dispatch_working_days"),
        "returns_url": settings.get(db, "returns_url"),
        "payment_methods": ["EFT"],
    }


@router.get("/images/{key:path}")
def product_image(key: str, db: Session = Depends(get_db)):
    # Only product images are public. Proof-of-payment files are never served here.
    if not key.startswith("products/") or db.scalar(select(Product.id).where(Product.image_key == key)) is None:
        raise HTTPException(404)
    data = get_storage().get(key)
    media = "image/png" if key.endswith(".png") else "image/webp" if key.endswith(".webp") else "image/jpeg"
    return Response(data, media_type=media, headers={"Cache-Control": "public, max-age=86400"})
