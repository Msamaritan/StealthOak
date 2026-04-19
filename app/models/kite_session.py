"""
KiteSession model - Store Zerodha authentication tokens
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class KiteSession(Base):
    """
    Stores Zerodha authentication tokens and related info.
    
    Used for API access to fetch live prices, place orders, etc.
    """
    
    __tablename__ = "kite_sessions"
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )
    
    # API Credentials Attributes
    api_key: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="API key obtained after login"
    )

    api_secret: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="API secret obtained after login"
    )
    
    access_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Access token obtained after exchanging request token"
    )

    # Session Info Attributes
    user_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="Zerodha user ID associated with this session"
    )

    login_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the user logged in and session was created"
    )

    # Status Attributes
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=False,
        comment="Whether this session is currently active"
    )
    
    # Timestamp Attributes    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        comment="When this session was created"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="When this session was last updated"
    )


    def __repr__(self):
        return f"<KiteSession user={self.user_id}, active={self.is_active}>"