# ============================================
# StealthOak - Database Setup
# ============================================

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from config import settings


# --------------------------------------------
# 1. DATABASE ENGINE
# --------------------------------------------
# The engine is the starting point for any SQLAlchemy application.
# It manages the connection pool to the database. 
# Connection manager between python and SQLite.

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,  # Log SQL statements when debug=True
)


# --------------------------------------------
# 2. SESSION FACTORY
# --------------------------------------------
# Sessions are how we interact with the database.
# This factory creates new sessions when needed.

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep data accessible after commit
    autocommit=False,        # We control when to commit
    autoflush=False,         # We control when to flush
)


# --------------------------------------------
# 3. BASE MODEL CLASS
# --------------------------------------------
# All our models (Portfolio, Holding, etc.) will inherit from this.
# SQLAlchemy uses this to track all models and create tables.

class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# --------------------------------------------
# 4. DEPENDENCY INJECTION
# --------------------------------------------
# FastAPI will use this to provide database sessions to routes.
# The session is automatically closed after each request.

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    
    Usage in routes:
        @app.get("/stocks")
        async def get_stocks(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()  # Commit if no errors
        except Exception:
            await session.rollback()  # Rollback on error
            raise


# --------------------------------------------
# 5. DATABASE INITIALIZATION
# --------------------------------------------
# Creates all tables defined by our models.
# Called once when the app starts.

async def init_db() -> None:
    """
    Create all database tables.
    
    This is called on app startup.
    Safe to call multiple times - only creates missing tables.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """
    Close database connections.
    
    Called on app shutdown for clean exit.
    """
    await engine.dispose()
