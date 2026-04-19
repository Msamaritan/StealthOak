"""
SyncLog model - Track synchronization history
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class SyncLog(Base):
    """
    Stores logs of synchronization events.
    
    Used to track when data was last synced, what was synced, and if there were any errors.
    """
    
    __tablename__ = "sync_logs"
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )
    
    # Sync Details Attributes
    sync_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Type of sync: 'holdings', 'trades', 'orders', 'full', etc."
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'started', 'success', 'failed', 'partial'"
    )

    # Results Attributes
    records_fetched: Mapped[Optional[int]] = mapped_column(
        Integer,
        default = 0,
        nullable=True,
        comment="Number of records fetched during this sync event"
    )
    records_created: Mapped[Optional[int]] = mapped_column(
        Integer,
        default = 0,
        nullable=True,
        comment="Number of records created during this sync event"
    )
    records_updated: Mapped[Optional[int]] = mapped_column(
        Integer,
        default = 0,
        nullable=True,
        comment="Number of records updated during this sync event"
    )
    records_skipped: Mapped[Optional[int]] = mapped_column(
        Integer,
        default = 0,
        nullable=True,
        comment="Number of records skipped during this sync event"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Additional info about the sync event (e.g. error details)"
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="When the sync event started"
    )

    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="When the sync event completed"
    )

    def __repr__(self):
        return f"<SyncLog {self.sync_type} {self.status}>"