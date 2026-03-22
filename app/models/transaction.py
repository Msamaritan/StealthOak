# ============================================
# StealthOak - Transaction Model
# ============================================

from datetime import date as date_type, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Float, Integer, Date, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.holding import Holding


class Transaction(Base):
    """
    Represents a buy or sell transaction.
    
    Examples:
        - BUY 50 INFY at ₹1400 on 2024-01-15
        - SELL 20 INFY at ₹1600 on 2024-06-20
    
    Used in Phase 2+ for:
        - Transaction history
        - SIP auto-tracking
        - XIRR calculation
    """
    
    __tablename__ = "transactions"
    
    # --------------------------------------------
    # COLUMNS
    # --------------------------------------------
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )
    
    holding_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("holdings.id", ondelete="CASCADE"),
        nullable=False,
        comment="Which holding this transaction belongs to"
    )
    
    type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="'BUY' or 'SELL'"
    )
    
    transaction_date: Mapped[date_type] = mapped_column(
        Date,
        nullable=False,
        comment="Transaction date"
    )
    
    quantity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Number of shares/units"
    )
    
    price: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Price per share/unit at transaction time"
    )
    
    notes: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Optional notes about the transaction"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        comment="When this record was created"
    )
    
    # --------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------
    
    # Many transactions belong to one holding
    holding: Mapped["Holding"] = relationship(
        "Holding",
        back_populates="transactions"
    )
    
    # --------------------------------------------
    # METHODS
    # --------------------------------------------
    
    @property
    def value(self) -> float:
        """Total value of this transaction."""
        return self.quantity * self.price
    
    def __repr__(self) -> str:
        return f"<Transaction(id={self.id}, type='{self.type}', qty={self.quantity}, price={self.price})>"
