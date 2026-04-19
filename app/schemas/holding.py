# ============================================
# StealthOak - Holding Schemas
# ============================================

from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, ConfigDict, field_validator


# --------------------------------------------
# CREATE SCHEMA
# --------------------------------------------
# Used when: User adds a new stock or mutual fund
# Endpoint: POST /api/stocks, POST /api/mutualfunds

class HoldingCreate(BaseModel):
    """Schema for creating a new holding."""
    
    symbol: str = Field(
        ...,
        min_length=1,
        max_length=50,
        examples=["INFY", "120503"],
        description="Stock symbol (INFY) or MF scheme code (120503)"
    )
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        examples=["Infosys Limited", "Axis Bluechip Fund - Direct Growth"],
        description="Full name of the stock or fund"
    )
    
    asset_type: Literal["stock", "mutual_fund"] = Field(
        ...,
        description="Type of asset"
    )
    
    exchange: Optional[str] = Field(
        default=None,
        max_length=10,
        examples=["NSE", "BSE"],
        description="Exchange for stocks (NSE/BSE), NULL for mutual funds"
    )
    
    quantity: float = Field(
        ...,
        gt=0,  # Must be greater than 0
        examples=[50, 120.5],
        description="Number of shares or MF units"
    )
    
    avg_price: float = Field(
        ...,
        gt=0,
        examples=[1400.50, 45.20],
        description="Average buy price (stock) or NAV (MF)"
    )
    
    portfolio_id: Optional[int] = Field(
        default=None,
        description="Portfolio ID (auto-assigned if not provided)"
    )
    
    # --------------------------------------------
    # VALIDATORS
    # --------------------------------------------
    
    @field_validator("symbol")
    @classmethod
    def symbol_uppercase(cls, v: str) -> str:
        """Convert stock symbols to uppercase."""
        return v.upper().strip()
    
    @field_validator("exchange")
    @classmethod
    def exchange_uppercase(cls, v: Optional[str]) -> Optional[str]:
        """Convert exchange to uppercase if provided."""
        if v is not None:
            return v.upper().strip()
        return v
    
    @field_validator("asset_type", mode="after")
    @classmethod
    def validate_exchange_for_stocks(cls, v: str, info) -> str:
        """Stocks should have exchange, MFs should not."""
        # Note: Cross-field validation happens at model level
        return v


# --------------------------------------------
# UPDATE SCHEMA
# --------------------------------------------
# Used when: User modifies holding details
# Endpoint: PATCH /api/stocks/{id}, PATCH /api/mutualfunds/{id}

class HoldingUpdate(BaseModel):
    """Schema for updating a holding. All fields optional."""
    
    name: Optional[str] = Field(default=None, max_length=200)
    quantity: Optional[float] = Field(default=None, gt=0)
    avg_price: Optional[float] = Field(default=None, gt=0)
    exchange: Optional[str] = Field(default=None, max_length=10)


# --------------------------------------------
# RESPONSE SCHEMA
# --------------------------------------------
# Used when: Returning holding data without live prices
# Endpoint: GET /api/stocks, GET /api/mutualfunds

class HoldingResponse(BaseModel):
    """Schema for holding response (without live price)."""
    
    id: int
    symbol: str
    name: str
    asset_type: str
    exchange: Optional[str]
    quantity: float
    avg_price: float
    invested_value: float  # Computed: quantity * avg_price
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------
# RESPONSE WITH LIVE PRICE
# --------------------------------------------
# Used when: Dashboard view with real-time prices
# Endpoint: GET / (dashboard)

class HoldingWithPrice(BaseModel):
    """Schema for holding with live price data."""
    
    id: int
    symbol: str
    name: str
    asset_type: str
    exchange: Optional[str]
    quantity: float
    avg_price: float
    
    # Computed from database
    invested_value: float
    
    # Fetched from external API
    current_price: Optional[float] = None
    current_value: Optional[float] = None
    pnl: Optional[float] = None           # Profit/Loss in ₹
    pnl_percent: Optional[float] = None   # Profit/Loss in %
    day_change: Optional[float] = None    # Today's change in ₹
    day_change_percent: Optional[float] = None
    
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------
# MF SEARCH RESULT
# --------------------------------------------
# Used when: Displaying MF search results
# Endpoint: GET /api/mutualfunds/search?q=axis

class MFSearchResult(BaseModel):
    """Schema for mutual fund search result from mfapi.in."""
    
    scheme_code: int = Field(alias="schemeCode")
    scheme_name: str = Field(alias="schemeName")
    
    model_config = ConfigDict(populate_by_name=True)
