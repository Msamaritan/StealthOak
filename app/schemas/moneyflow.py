"""
Money Flow Schemas - Validation for Bank → Broker → Investment flow
"""

import datetime as dt
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict


# ============================================
# Bank Transfer Schemas
# ============================================

class BankTransferCreate(BaseModel):
    """Schema for creating a new bank transfer"""
    date: dt.date
    amount: float = Field(gt=0, description="Amount must be positive")
    source_bank: str = Field(min_length=1, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=255)


class BankTransferUpdate(BaseModel):
    """Schema for updating a bank transfer (all fields optional)"""
    date: Optional[dt.date] = None
    amount: Optional[float] = Field(default=None, gt=0)
    source_bank: Optional[str] = Field(default=None, min_length=1, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=255)


class BankTransferResponse(BaseModel):
    """Schema for bank transfer response with computed fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    amount: float
    source_bank: str
    notes: Optional[str]
    created_at: dt.datetime
    allocated_amount: float  # Computed property
    idle_amount: float  # Computed property


class BankTransferBrief(BaseModel):
    """Brief schema for dropdowns/selection"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    amount: float
    source_bank: str
    idle_amount: float


# ============================================
# Broker Credit Schemas
# ============================================

class BrokerCreditCreate(BaseModel):
    """Schema for creating a new broker credit"""
    bank_transfer_id: int
    date: dt.date
    amount: float = Field(gt=0, description="Amount must be positive")
    destination: str = Field(min_length=1, max_length=50)
    destination_type: str = Field(
        default="broker",
        pattern="^(broker|savings)$",
        description="Either 'broker' or 'savings'"
    )
    notes: Optional[str] = Field(default=None, max_length=255)


class BrokerCreditUpdate(BaseModel):
    """Schema for updating a broker credit (all fields optional)"""
    date: Optional[dt.date] = None
    amount: Optional[float] = Field(default=None, gt=0)
    destination: Optional[str] = Field(default=None, min_length=1, max_length=50)
    destination_type: Optional[str] = Field(
        default=None,
        pattern="^(broker|savings)$"
    )
    notes: Optional[str] = Field(default=None, max_length=255)


class BrokerCreditResponse(BaseModel):
    """Schema for broker credit response with computed fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    bank_transfer_id: int
    date: dt.date
    amount: float
    destination: str
    destination_type: str
    notes: Optional[str]
    created_at: dt.datetime
    invested_amount: float  # Computed property
    idle_amount: float  # Computed property
    is_complete: bool  # Computed property

    # Include parent info for UI display
    source_bank: Optional[str] = None
    source_date: Optional[dt.date] = None


class BrokerCreditBrief(BaseModel):
    """Brief schema for dropdowns/selection"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    date: dt.date
    amount: float
    destination: str
    destination_type: str
    idle_amount: float


# ============================================
# Investment Schemas
# ============================================

class MoneyFlowInvestmentCreate(BaseModel):
    """Schema for creating a new investment"""
    broker_credit_id: int
    date: dt.date
    amount: float = Field(gt=0, description="Amount must be positive")
    holding_name: str = Field(min_length=1, max_length=100)
    holding_id: Optional[int] = None  # Optional link to Holding table
    notes: Optional[str] = Field(default=None, max_length=255)


class MoneyFlowInvestmentUpdate(BaseModel):
    """Schema for updating an investment (all fields optional)"""
    date: Optional[dt.date] = None
    amount: Optional[float] = Field(default=None, gt=0)
    holding_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    holding_id: Optional[int] = None
    notes: Optional[str] = Field(default=None, max_length=255)


class MoneyFlowInvestmentResponse(BaseModel):
    """Schema for investment response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    broker_credit_id: int
    date: dt.date
    amount: float
    holding_name: str
    holding_id: Optional[int]
    notes: Optional[str]
    created_at: dt.datetime

    # Include parent info for UI display
    broker_destination: Optional[str] = None
    broker_date: Optional[dt.date] = None


# ============================================
# Summary / Stats Schemas
# ============================================

class IdleBreakdown(BaseModel):
    """Breakdown of idle amount by source"""
    id: int
    date: dt.date
    source: str  # Bank name or Broker name
    total_amount: float
    idle_amount: float


class MoneyFlowSummary(BaseModel):
    """Summary statistics for the money flow dashboard"""
    # Totals
    total_bank_transfers: float
    total_broker_credits: float
    total_invested: float

    # Idle amounts
    idle_at_bank: float
    idle_at_broker: float

    # Breakdowns
    bank_idle_breakdown: List[IdleBreakdown]
    broker_idle_breakdown: List[IdleBreakdown]

    # Counts
    bank_transfer_count: int
    broker_credit_count: int
    investment_count: int


# ============================================
# Full Response with Nested Data (for UI)
# ============================================

class MoneyFlowFullResponse(BaseModel):
    """Complete money flow data for the Kanban board"""
    bank_transfers: List[BankTransferResponse]
    broker_credits: List[BrokerCreditResponse]
    investments: List[MoneyFlowInvestmentResponse]
    summary: MoneyFlowSummary
