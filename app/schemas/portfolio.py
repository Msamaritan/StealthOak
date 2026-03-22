# ============================================
# StealthOak - Portfolio Schemas
# ============================================

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


# --------------------------------------------
# CREATE SCHEMA
# --------------------------------------------
# Used when: User creates a new portfolio
# Endpoint: POST /api/portfolios

class PortfolioCreate(BaseModel):
    """Schema for creating a new portfolio."""
    
    name: str = Field(
        ...,  # ... means required
        min_length=1,
        max_length=100,
        examples=["Main Portfolio"],
        description="Name of the portfolio"
    )
    
    owner: str = Field(
        default="Self",
        max_length=50,
        examples=["Self", "Mom"],
        description="Who owns this portfolio"
    )


# --------------------------------------------
# UPDATE SCHEMA
# --------------------------------------------
# Used when: User updates portfolio details
# Endpoint: PATCH /api/portfolios/{id}

class PortfolioUpdate(BaseModel):
    """Schema for updating a portfolio. All fields optional."""
    
    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100
    )
    
    owner: Optional[str] = Field(
        default=None,
        max_length=50
    )


# --------------------------------------------
# RESPONSE SCHEMA
# --------------------------------------------
# Used when: Returning portfolio data to client
# Endpoint: GET /api/portfolios, GET /api/portfolios/{id}

class PortfolioResponse(BaseModel):
    """Schema for portfolio response."""
    
    id: int
    name: str
    owner: str
    created_at: datetime
    
    # This allows Pydantic to read data from SQLAlchemy models
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------
# RESPONSE WITH HOLDINGS
# --------------------------------------------
# Used when: Need portfolio with all its holdings
# Endpoint: GET /api/portfolios/{id}/full

class PortfolioWithHoldings(BaseModel):
    """Portfolio with nested holdings list."""
    
    id: int
    name: str
    owner: str
    created_at: datetime
    holdings: List["HoldingResponse"] = []
    
    model_config = ConfigDict(from_attributes=True)


# Import here to avoid circular import
from app.schemas.holding import HoldingResponse
PortfolioWithHoldings.model_rebuild()
