# ============================================
# StealthOak - Application Factory
# ============================================

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import settings
from app.database import init_db, close_db
from app.routers import router
from app.routers.auth import NotAuthenticatedException, router as auth_router
from app.utils import format_date_dd_mm_yyyy, format_indian_rupee


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    
    Startup:
        - Initialize database (create tables if not exist)
    
    Shutdown:
        - Close database connections
    """
    # ----- STARTUP -----
    print("🌳 StealthOak is starting...")
    await init_db()
    print("✅ Database initialized")
    
    yield  # App runs here
    
    # ----- SHUTDOWN -----
    print("🌳 StealthOak is shutting down...")
    await close_db()
    print("✅ Database connections closed")


def _format_indian_rupee(value):
    """
    Format amount to Indian rupee display format (x,xx,xx,xxx).
    Removes the leading ₹ if present and formats with proper commas.
    """
    if value is None or value == "":
        return "0.00"
    
    # Remove ₹ symbol if present
    value_str = str(value).replace("₹", "").strip()
    
    try:
        num = float(value_str)
    except (ValueError, TypeError):
        return "0.00"
    
    # Format to 2 decimal places
    formatted = f"{abs(num):.2f}"
    parts = formatted.split(".")
    int_part = parts[0]
    dec_part = parts[1]
    
    # Apply Indian numbering format
    if len(int_part) <= 3:
        return int_part + "." + dec_part
    
    last_three = int_part[-3:]
    remaining = int_part[:-3]
    result = ""
    for i, digit in enumerate(reversed(remaining)):
        if i > 0 and i % 2 == 0:
            result = "," + result
        result = digit + result
    
    return result + "," + last_three + "." + dec_part

def configure_jinja2_filters(env):
    """
    Register custom filters with Jinja2 environment.
    
    This centralizes all template filters for consistency across the app.
    """
    env.filters["format_date_dd_mm_yyyy"] = format_date_dd_mm_yyyy
    env.filters["format_indian_rupee"] = format_indian_rupee


def create_app() -> FastAPI:
    """
    Application factory.
    
    Creates and configures the FastAPI application.
    
    Returns:
        Configured FastAPI instance
    """
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="A privacy-first portfolio tracker for passive investors.",
        lifespan=lifespan,
    )

    # ----- SESSION MIDDLEWARE -----
    # Starlette's SessionMiddleware stores session data in a signed cookie.
    # The secret_key signs the cookie payload — anyone who knows it could
    # forge sessions, so override it in production via the
    # STEALTHOAK_SECRET_KEY environment variable.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="stealthoak_session",
        same_site="lax",   # Protects against CSRF for cross-site requests
        https_only=False,  # Set True in production when serving over HTTPS
    )

    # ----- EXCEPTION HANDLER -----
    # When get_current_user raises NotAuthenticatedException,
    # redirect the browser to /login instead of returning a JSON 500 error.
    @app.exception_handler(NotAuthenticatedException)
    async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
        return RedirectResponse(url="/login", status_code=303)

    # ----- STATIC FILES -----
    # Serve CSS, JS, images from /static URL
    app.mount(
        "/static",
        StaticFiles(directory="app/static"),
        name="static"
    )

    # ----- ROUTERS -----
    # Auth routes (/login, /logout) are public — included separately
    # so they are never wrapped by the get_current_user dependency.
    app.include_router(auth_router)
    # All other application routes
    app.include_router(router)

    return app


# Create the app instance
app = create_app()
