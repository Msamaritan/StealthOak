# ============================================
# StealthOak - Schemas Package
# ============================================

# Export all schemas for easy importing
# Usage: from app.schemas import HoldingCreate, HoldingResponse

from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioUpdate,
    PortfolioResponse,
)

from app.schemas.holding import (
    HoldingCreate,
    HoldingUpdate,
    HoldingResponse,
    HoldingWithPrice,
)

from app.schemas.moneyflow import (
    BankTransferCreate,
    BankTransferUpdate,
    BankTransferResponse,
    BankTransferBrief,
    BrokerCreditCreate,
    BrokerCreditUpdate,
    BrokerCreditResponse,
    BrokerCreditBrief,
    MoneyFlowInvestmentCreate,
    MoneyFlowInvestmentUpdate,
    MoneyFlowInvestmentResponse,
    MoneyFlowSummary,
    MoneyFlowFullResponse,
)

__all__ = [
    # Portfolio
    "PortfolioCreate",
    "PortfolioUpdate", 
    "PortfolioResponse",
    # Holding
    "HoldingCreate",
    "HoldingUpdate",
    "HoldingResponse",
    "HoldingWithPrice",
    # Money Flow
    "BankTransferCreate",
    "BankTransferUpdate",
    "BankTransferResponse",
    "BankTransferBrief",
    "BrokerCreditCreate",
    "BrokerCreditUpdate",
    "BrokerCreditResponse",
    "BrokerCreditBrief",
    "MoneyFlowInvestmentCreate",
    "MoneyFlowInvestmentUpdate",
    "MoneyFlowInvestmentResponse",
    "MoneyFlowSummary",
    "MoneyFlowFullResponse",
]
