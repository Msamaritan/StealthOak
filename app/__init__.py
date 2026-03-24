# ============================================
# StealthOak - Application Factory
# ============================================

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from app.database import init_db, close_db
from app.routers import router


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
    
    # ----- STATIC FILES -----
    # Serve CSS, JS, images from /static URL
    app.mount(
        "/static",
        StaticFiles(directory="app/static"),
        name="static"
    )
    
    # ----- ROUTERS -----
    # Include all route handlers
    app.include_router(router)
    
    return app


# Create the app instance
app = create_app()
