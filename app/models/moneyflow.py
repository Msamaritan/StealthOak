"""
Money Flow Models - Track money from Bank → Broker → Investments
"""

import datetime as dt
from typing import Optional, List
from sqlalchemy import String, Float, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BankTransfer(Base):
    """
    Level 1: Money transferred to investment bank account
    Example: Salary account → SBI (investment account)
    """
    __tablename__ = "bank_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    source_bank: Mapped[str] = mapped_column(String(50), nullable=False)  # "SBI", "HDFC"
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship: One BankTransfer → Many BrokerCredits
    broker_credits: Mapped[List["BrokerCredit"]] = relationship(
        "BrokerCredit",
        back_populates="bank_transfer",
        cascade="all, delete-orphan"
    )

    @property
    def allocated_amount(self) -> float:
        """Sum of all broker credits linked to this transfer"""
        return sum(bc.amount for bc in self.broker_credits)

    @property
    def idle_amount(self) -> float:
        """Amount not yet allocated to any broker"""
        return self.amount - self.allocated_amount

    def __repr__(self) -> str:
        return f"<BankTransfer {self.source_bank} ₹{self.amount} on {self.date}>"


class BrokerCredit(Base):
    """
    Level 2: Money moved to broker/savings account
    Example: SBI → Zerodha or SBI → PPF
    """
    __tablename__ = "broker_credits"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_transfer_id: Mapped[int] = mapped_column(
        ForeignKey("bank_transfers.id", ondelete="CASCADE"),
        nullable=False
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    destination: Mapped[str] = mapped_column(String(50), nullable=False)  # "Zerodha", "Groww", "PPF"
    destination_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="broker"
    )  # "broker" or "savings"
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship: Many BrokerCredits → One BankTransfer
    bank_transfer: Mapped["BankTransfer"] = relationship(
        "BankTransfer",
        back_populates="broker_credits"
    )

    # Relationship: One BrokerCredit → Many Investments
    investments: Mapped[List["MoneyFlowInvestment"]] = relationship(
        "MoneyFlowInvestment",
        back_populates="broker_credit",
        cascade="all, delete-orphan"
    )

    @property
    def invested_amount(self) -> float:
        """Sum of all investments linked to this credit"""
        return sum(inv.amount for inv in self.investments)

    @property
    def idle_amount(self) -> float:
        """Amount not yet invested"""
        # For savings (PPF/NPS), no sub-investments needed
        if self.destination_type == "savings":
            return 0.0
        return self.amount - self.invested_amount

    @property
    def is_complete(self) -> bool:
        """Check if fully invested or is a savings type"""
        return self.destination_type == "savings" or self.idle_amount == 0

    def __repr__(self) -> str:
        return f"<BrokerCredit {self.destination} ₹{self.amount} on {self.date}>"


class MoneyFlowInvestment(Base):
    """
    Level 3: Actual investment in stocks/MFs
    Example: Zerodha → HDFC Flexi Cap MF
    
    Note: Named MoneyFlowInvestment to avoid confusion with 
    potential Investment model elsewhere
    """
    __tablename__ = "moneyflow_investments"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_credit_id: Mapped[int] = mapped_column(
        ForeignKey("broker_credits.id", ondelete="CASCADE"),
        nullable=False
    )
    # Optional link to existing Holding (for future integration)
    holding_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("holdings.id", ondelete="SET NULL"),
        nullable=True
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    holding_name: Mapped[str] = mapped_column(String(100), nullable=False)  # "HDFC Flexi Cap"
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship: Many Investments → One BrokerCredit
    broker_credit: Mapped["BrokerCredit"] = relationship(
        "BrokerCredit",
        back_populates="investments"
    )

    # Optional: Link to actual Holding
    # holding: Mapped[Optional["Holding"]] = relationship("Holding")

    def __repr__(self) -> str:
        return f"<MoneyFlowInvestment {self.holding_name} ₹{self.amount} on {self.date}>"
