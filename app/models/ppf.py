# ============================================
# StealthOak - PPF Models
# ============================================

from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PPFBalance(Base):
    """
    Container for a PPF account.

    Invested and current values are derived from PPFTransaction records:
      invested_amount = sum of Deposit transactions
      current_value   = sum of Deposit + Interest transactions
    """

    __tablename__ = "ppf_balances"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Primary PPF",
        comment="Display label for this PPF account"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Last modification time"
    )

    transactions: Mapped[List["PPFTransaction"]] = relationship(
        "PPFTransaction",
        back_populates="ppf_balance",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def invested_amount(self) -> float:
        """Sum of all Deposit transactions."""
        return sum(t.amount for t in self.transactions if t.transaction_type == "deposit")

    @property
    def current_value(self) -> float:
        """Sum of all Deposit + Interest transactions."""
        return sum(t.amount for t in self.transactions)

    def __repr__(self) -> str:
        return f"<PPFBalance(id={self.id}, name='{self.name}')>"


class PPFTransaction(Base):
    """
    A single PPF entry: either a Deposit (principal) or an Interest credit.
    """

    __tablename__ = "ppf_transactions"

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
        comment="Unique identifier"
    )

    ppf_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ppf_balances.id", ondelete="CASCADE"),
        nullable=False,
        comment="PPF account this transaction belongs to"
    )

    transaction_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'deposit' or 'interest'"
    )

    amount: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Transaction amount in ₹"
    )

    transaction_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="Date of transaction"
    )

    note: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Optional note"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        comment="When this record was created"
    )

    ppf_balance: Mapped["PPFBalance"] = relationship(
        "PPFBalance",
        back_populates="transactions",
    )

    def __repr__(self) -> str:
        return (
            f"<PPFTransaction(id={self.id}, type='{self.transaction_type}', "
            f"amount={self.amount}, date={self.transaction_date})>"
        )
