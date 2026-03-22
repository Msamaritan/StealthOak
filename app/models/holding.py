# ============================================
# StealthOak - Holding Model
# ============================================

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.portfolio import Portfolio
    from app.models.transaction import Transaction


class Holding(Base):
    """
    Represents a stock or mutual fund holding.
    
    Examples:
        - 50 shares of INFY at avg price ₹1400
        - 120.5 units of Axis Bluechip at avg NAV ₹45.20
    
    Holdings belong to a portfolio.
    Holdings can have multiple transactions (buy/sell history).
    """
    
    __tablename__ = "holdings"
    
    # --------------------------------------------
    # COLUMNS
    # --------------------------------------------
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )
    
    # Foreign key linking to portfolio
    portfolio_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("portfolios.id", ondelete="CASCADE"),
        nullable=False,
        comment="Which portfolio this belongs to"
    )
    
    symbol: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Stock symbol (INFY) or MF scheme code (120503)"
    )
    
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Full name: 'Infosys Limited' or 'Axis Bluechip Fund'"
    )
    
    asset_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'stock' or 'mutual_fund'"
    )
    
    exchange: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment="'NSE' or 'BSE' for stocks, NULL for mutual funds"
    )
    
    quantity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Number of shares or MF units"
    )
    
    avg_price: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Average buy price (stock) or NAV (MF)"
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        comment="When holding was first added"
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last modification time"
    )
    
    # --------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------
    
    # Many holdings belong to one portfolio
    portfolio: Mapped["Portfolio"] = relationship(
        "Portfolio",
        back_populates="holdings"
    )
    
    # One holding has many transactions (Phase 2+)
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction",
        back_populates="holding",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # --------------------------------------------
    # METHODS
    # --------------------------------------------
    
    @property
    def invested_value(self) -> float:
        """Total amount invested in this holding."""
        return self.quantity * self.avg_price
    
    def __repr__(self) -> str:
        return f"<Holding(id={self.id}, symbol='{self.symbol}', qty={self.quantity})>"
