"""Session login: dependencies that identify the user, and the /login and /logout routes.

current_user   -- the logged-in User or None; also stored on request.state.user for templates
require_user   -- any active user; HTML requests redirect to /login, /api requests get 401
require_staff  -- staff only; 403 otherwise
"""

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from slim_lab_portal.db import get_db
from slim_lab_portal.models import User
from slim_lab_portal.security import csrf_protect, verify_password
from slim_lab_portal.web import render

SESSION_USER_KEY = "user_id"


class LoginRequired(Exception):
    """Raised by require_user; handled in main.py (redirect for HTML, 401 for /api)."""


class StaffRequired(Exception):
    """Raised by require_staff; handled in main.py (403)."""


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User | None:
    user = None
    raw_id = request.session.get(SESSION_USER_KEY)
    if raw_id:
        try:
            user = db.get(User, uuid.UUID(raw_id))
        except ValueError:
            user = None
        if user is None or not user.is_active:
            request.session.pop(SESSION_USER_KEY, None)
            user = None
    request.state.user = user
    return user


def require_user(user: Annotated[User | None, Depends(current_user)]) -> User:
    if user is None:
        raise LoginRequired
    return user


def require_staff(user: Annotated[User, Depends(require_user)]) -> User:
    if not user.is_staff:
        raise StaffRequired
    return user


CurrentUser = Annotated[User | None, Depends(current_user)]
RequireUser = Annotated[User, Depends(require_user)]
RequireStaff = Annotated[User, Depends(require_staff)]

router = APIRouter(dependencies=[Depends(csrf_protect)])


def _safe_next(next_url: str | None) -> str:
    # Only same-site absolute paths; "//evil.example" and "/\evil" are protocol-relative tricks.
    if next_url and next_url.startswith("/") and not next_url.startswith(("//", "/\\")):
        return next_url
    return "/"


@router.get("/login", name="login")
def login_form(request: Request, user: CurrentUser, next: str | None = None):
    if user is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    return render(request, "login.html", {"next": _safe_next(next)})


@router.post("/login")
def login(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/",
):
    user = db.scalars(select(User).where(User.email == email.strip().lower())).first()
    ok = verify_password(password, user.password_hash if user else None)
    if not ok or user is None or not user.is_active:
        return render(
            request,
            "login.html",
            {"error": "Invalid email or password.", "next": _safe_next(next), "email": email},
            status_code=401,
        )
    # New session on login: drops any pre-login state and rotates the CSRF token.
    request.session.clear()
    request.session[SESSION_USER_KEY] = str(user.id)
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/logout", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(request.url_for("login").path, status_code=303)


def login_redirect(request: Request) -> RedirectResponse:
    target = request.url.path
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(f"/login?next={quote(target, safe='')}", status_code=303)
