"""
Insurance models for policy metadata and premium payment tracking.
"""

import datetime as dt
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InsurancePolicy(Base):
    """Master record for an insurance policy (LIC, health, etc.)."""

    __tablename__ = "insurance_policies"

    ## Core Identity fields
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    policy_category: Mapped[str] = mapped_column(
        String(20), nullable=False, default="other"
    )  # lic / health / general / other

    ## Classification fields
    policy_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="traditional"
    )  # term / ulip / endowment / family_floater / etc.
    policy_number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    ## Coverage details
    insured_person: Mapped[str] = mapped_column(String(100), nullable=False)
    nominee: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    ## Lifecycle fields
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)

    ## Premium details
    premium_amount: Mapped[float] = mapped_column(Float, nullable=False)
    premium_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="yearly"
    )  # monthly / quarterly / half_yearly / yearly / single

    sum_assured: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    tax_section: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    ## Status fields
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    premium_payments: Mapped[List["InsurancePremiumPayment"]] = relationship(
        "InsurancePremiumPayment",
        back_populates="policy",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    @property
    def total_premium_paid(self) -> float:
        return sum(p.amount for p in self.premium_payments)

    @property
    def last_payment_date(self) -> Optional[dt.date]:
        if not self.premium_payments:
            return None
        return max(p.payment_date for p in self.premium_payments)

    @property
    def policy_term_years(self) -> Optional[int]:
        """Policy term in whole years, derived from start and maturity dates."""
        if not self.start_date or not self.maturity_date:
            return None

        years = self.maturity_date.year - self.start_date.year
        before_anniversary = (self.maturity_date.month, self.maturity_date.day) < (
            self.start_date.month,
            self.start_date.day,
        )
        if before_anniversary:
            years -= 1
        return max(years, 0)

    @property
    def total_premium_for_term(self) -> Optional[float]:
        """Estimated total premium payable over full policy term."""
        term_years = self.policy_term_years
        if term_years is None:
            return None

        multiplier_by_frequency = {
            "single": 1,
            "yearly": max(term_years, 1),
            "half_yearly": max(term_years, 1) * 2,
            "quarterly": max(term_years, 1) * 4,
            "monthly": max(term_years, 1) * 12,
        }

        installments = multiplier_by_frequency.get(self.premium_frequency, max(term_years, 1))
        return round(self.premium_amount * installments, 2)

    @property
    def remaining_premium_for_term(self) -> Optional[float]:
        """Estimated remaining premium amount for full policy term."""
        total_term = self.total_premium_for_term
        if total_term is None:
            return None
        return round(max(total_term - self.total_premium_paid, 0.0), 2)

    def __repr__(self) -> str:
        return f"<InsurancePolicy {self.provider}:{self.policy_name}>"


class InsurancePremiumPayment(Base):
    """Payment log for each insurance policy."""

    __tablename__ = "insurance_premium_payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(
        ForeignKey("insurance_policies.id", ondelete="CASCADE"), nullable=False
    )
    payment_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_mode: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    reference_no: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    tax_claim_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    policy: Mapped["InsurancePolicy"] = relationship(
        "InsurancePolicy",
        back_populates="premium_payments",
    )

    def __repr__(self) -> str:
        return f"<InsurancePremiumPayment policy_id={self.policy_id} amount={self.amount}>"
