# ============================================
# StealthOak - Portfolio Model
# ============================================

from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Avoid circular imports - only import for type checking
if TYPE_CHECKING:
    from app.models.holding import Holding


class Portfolio(Base):
    """
    Represents a portfolio owned by a person.
    
    Examples:
        - Your portfolio (owner="Self")
        - Mom's portfolio (owner="Mom")
    
    One portfolio has many holdings (stocks + mutual funds).
    """
    
    __tablename__ = "portfolios"
    
    # --------------------------------------------
    # COLUMNS
    # --------------------------------------------
    
    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )
    
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="Portfolio name, e.g., 'Main Portfolio'"
    )
    
    owner: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Self",
        comment="Who owns this: 'Self', 'Mom', etc."
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        comment="When portfolio was created"
    )
    
    # --------------------------------------------
    # RELATIONSHIPS
    # --------------------------------------------
    
    # One portfolio has many holdings
    holdings: Mapped[List["Holding"]] = relationship(
        "Holding",
        back_populates="portfolio",
        cascade="all, delete-orphan",  # Delete holdings when portfolio is deleted
        lazy="selectin"                # Efficient loading strategy
    )
    
    # --------------------------------------------
    # METHODS
    # --------------------------------------------
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        return f"<Portfolio(id={self.id}, name='{self.name}', owner='{self.owner}')>"
