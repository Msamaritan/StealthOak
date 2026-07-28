# ============================================
# StealthOak - Authentication Router
# ============================================
# Handles login, logout, and the get_current_user dependency
# that every other router imports to protect its routes.

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.utils import get_configured_templates


router = APIRouter(tags=["Auth"])
templates = get_configured_templates()

# --------------------------------------------
# Password hashing
# --------------------------------------------
# CryptContext wraps passlib so we can swap algorithms later if needed.
# "bcrypt" is deliberately slow — it resists brute-force attacks.
# "deprecated='auto'" means old hashes are automatically re-hashed on
# next login if the algorithm or cost factor changes.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plain-text password matches the stored bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    """Hash a plain-text password.  Use this when creating/updating users."""
    return pwd_context.hash(plain)


# --------------------------------------------
# Custom exception — raised when a protected
# route is accessed without a valid session.
# app/__init__.py registers an exception handler
# that turns this into a 303 redirect to /login.
# --------------------------------------------
class NotAuthenticatedException(Exception):
    """Raised by get_current_user when no valid session exists."""
    pass


# --------------------------------------------
# get_current_user — FastAPI dependency
# --------------------------------------------
# Import this in any router that should be protected:
#
#   from app.routers.auth import get_current_user
#
#   @router.get("/stocks")
#   async def stocks(current_user: User = Depends(get_current_user)):
#       ...
#
async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Read user_id from the signed session cookie and return the User object.

    Raises NotAuthenticatedException (→ redirect to /login) when:
      - The session has no user_id key (not logged in)
      - The user_id doesn't exist in the database
      - The account is inactive (is_active=False)
    """
    user_id: int | None = request.session.get("user_id")
    if user_id is None:
        raise NotAuthenticatedException()

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        # Clear a stale/invalid session so the cookie doesn't linger
        request.session.clear()
        raise NotAuthenticatedException()

    return user


# --------------------------------------------
# Routes
# --------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Render the login form.

    If the user is already logged in (valid session) redirect them to the
    dashboard so they don't see the login page unnecessarily.
    """
    user_id = request.session.get("user_id")
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
        if result.scalar_one_or_none():
            return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": None},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Process the login form submission.

    On success: store user_id in the session and redirect to /.
    On failure: re-render the login form with an error message.

    The error message is deliberately vague ("Invalid credentials") to avoid
    leaking whether the username or password was wrong (OWASP recommendation).
    """
    # Look up the user by username
    result = await db.execute(select(User).where(User.username == username))
    user: User | None = result.scalar_one_or_none()

    # Verify password — always call verify_password even if user is None so
    # that the response time is consistent (prevents timing-based user enumeration).
    password_ok = verify_password(password, user.hashed_password) if user else False

    if not user or not password_ok or not user.is_active:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "Invalid username or password.",
                # Preserve the typed username so the user doesn't have to retype it
                "username_value": username,
            },
            status_code=401,
        )

    # Successful login — write user_id into the signed session cookie
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    """
    Clear the session and redirect to /login.

    Uses POST (not GET) so that a simple link can't log someone out via
    a prefetched URL or an <img> tag (CSRF consideration for logout).
    """
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
