"""Staff sign-in (A1): one account per staff member, hashed passwords, signed session cookies and CSRF tokens."""

import hmac
import secrets

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from flowshop.db import get_db
from flowshop.models import Staff


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


class LoginRequired(Exception):
    pass


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


async def verify_csrf(request: Request) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    sent = request.headers.get("x-csrf-token")
    if sent is None:
        form = await request.form()
        sent = form.get("csrf")
    expected = request.session.get("csrf", "")
    if not expected or not isinstance(sent, str) or not hmac.compare_digest(sent, expected):
        raise HTTPException(403, "The form expired. Go back, refresh the page and try again.")


def current_staff(request: Request, db: Session = Depends(get_db)) -> Staff:
    staff_id = request.session.get("staff_id")
    staff = db.get(Staff, staff_id) if staff_id else None
    if staff is None or not staff.active:
        request.session.pop("staff_id", None)
        raise LoginRequired()
    return staff


def admin_only(staff: Staff = Depends(current_staff)) -> Staff:
    if not staff.is_admin:
        raise HTTPException(403, "Only an admin can do this.")
    return staff
