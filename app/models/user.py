# ============================================
# StealthOak - User Model
# ============================================

import datetime as dt
from typing import Optional

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    """
    Represents a logged-in user of StealthOak.

    All financial data (portfolios, insurance, moneyflow, etc.)
    is linked to a user via a user_id foreign key on the root tables.

    Columns:
        username        Unique login name (case-sensitive)
        hashed_password bcrypt hash — the plain password is never stored
        display_name    Friendly name shown in the sidebar (e.g. "Manoj")
        is_active       False = account disabled, cannot log in
        is_admin        True = can access /admin/users to manage users
        kite_api_key    Per-user Zerodha Kite API key (nullable)
        kite_api_secret Per-user Zerodha Kite API secret (nullable)
        created_at      Timestamp when the account was created
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    username: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        comment="Unique login name",
    )

    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="bcrypt hash of the password — never store plain text",
    )

    display_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Friendly name shown in the UI",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="False = account disabled",
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True = can manage users at /admin/users",
    )

    # Per-user Kite Connect credentials (nullable — not every user uses Kite)
    kite_api_key: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Zerodha Kite API key",
    )

    kite_api_secret: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Zerodha Kite API secret",
    )

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="Account creation timestamp",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
