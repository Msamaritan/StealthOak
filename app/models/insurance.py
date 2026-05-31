"""
Insurance models for policy metadata and premium payment tracking.
"""

import datetime as dt
import calendar
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
    policy_term: Mapped[Optional[int]] = mapped_column(nullable=True)  # in years

    ## Premium details
    premium_amount: Mapped[float] = mapped_column(Float, nullable=False)
    premium_frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="yearly"
    )  # monthly / quarterly / half_yearly / yearly / single
    last_premium_payment_date: Mapped[Optional[dt.date]] = mapped_column(Date, nullable=True)
    total_premium_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    sum_assured: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    maturity_benefit_value: Mapped[Optional[float]] = mapped_column(
        "current_value", Float, nullable=True
    )
    compute_investment_gain: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

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
        """Total premium amount for full policy term as entered by user."""
        return self.total_premium_amount

    @property
    def remaining_premium_for_term(self) -> Optional[float]:
        """Remaining premium amount for full policy term."""
        total_term = self.total_premium_for_term
        if total_term is None:
            return None
        return round(max(total_term - self.total_premium_paid, 0.0), 2)

    @property
    def investment_gain_percent(self) -> Optional[float]:
        """Gain percentage from investment base to maturity benefit value."""
        if not self.compute_investment_gain:
            return None

        if self.maturity_benefit_value is None:
            return None

        # Use full-term premium as primary base to avoid inflated gains when
        # only a few payments are logged; fall back to paid amount if needed.
        base_amount = self.total_premium_amount or self.total_premium_paid
        if base_amount is None or base_amount <= 0:
            return None

        gain_pct = ((self.maturity_benefit_value - base_amount) / base_amount) * 100.0
        return round(gain_pct, 2)

    @staticmethod
    def _add_months(date_value: dt.date, months: int) -> dt.date:
        """
        Add months safely while preserving day where possible.
        31-Jan + 1 month -> Feb has no 31st, so it becomes 28-Feb (or 29-Feb in leap year).
        This avoids invalid dates and crashes.
        """
        year = date_value.year + (date_value.month - 1 + months) // 12
        month = (date_value.month - 1 + months) % 12 + 1
        day = min(date_value.day, calendar.monthrange(year, month)[1])
        return dt.date(year, month, day)

    @property
    def next_premium_date(self) -> Optional[dt.date]:
        """Next premium date computed from start date schedule and frequency."""
        if self.premium_frequency == "single":
            return None

        if not self.start_date:
            return None

        month_increment = {
            "monthly": 1,
            "quarterly": 3,
            "half_yearly": 6,
            "yearly": 12,
        }.get(self.premium_frequency)

        if month_increment is None:
            return None

        today = dt.date.today()
        next_date = self.start_date
        while next_date < today:
            next_date = self._add_months(next_date, month_increment)

        if self.maturity_date and next_date > self.maturity_date:
            return None

        return next_date

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
