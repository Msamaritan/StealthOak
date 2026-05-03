"""
Money Flow Router - API and HTML endpoints for Bank → Broker → Investment tracking
"""

import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.moneyflow import BankTransfer, BrokerCredit, MoneyFlowInvestment
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
    IdleBreakdown,
)

router = APIRouter(prefix="/moneyflow", tags=["Money Flow"])


# ============================================
# Template Setup
# ============================================

from config import settings
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


# ============================================
# HTML Routes
# ============================================

@router.get("", response_class=HTMLResponse)
async def moneyflow_page(
    request: Request,
    session: AsyncSession = Depends(get_db),
    month: Optional[str] = Query(default=None, description="Filter by month: YYYY-MM")
):
    """
    Main Money Flow page - Kanban board view
    """
    # Build date filter if month is provided
    date_filter_start = None
    date_filter_end = None
    
    if month:
        try:
            year, mon = map(int, month.split("-"))
            date_filter_start = dt.date(year, mon, 1)
            # Last day of month
            if mon == 12:
                date_filter_end = dt.date(year + 1, 1, 1)
            else:
                date_filter_end = dt.date(year, mon + 1, 1)
        except ValueError:
            pass  # Invalid format, ignore filter

    # Fetch bank transfers with related data
    bank_query = (
        select(BankTransfer)
        .options(
            selectinload(BankTransfer.broker_credits)
            .selectinload(BrokerCredit.investments)
        )
        .order_by(BankTransfer.date.desc())
    )
    
    if date_filter_start and date_filter_end:
        bank_query = bank_query.where(
            BankTransfer.date >= date_filter_start,
            BankTransfer.date < date_filter_end
        )
    
    result = await session.execute(bank_query)
    bank_transfers = result.scalars().all()

    # Get filtered bank IDs for broker query
    filtered_bank_ids = [bt.id for bt in bank_transfers]

    # Fetch broker credits linked to filtered bank transfers
    if filtered_bank_ids:
        broker_query = (
            select(BrokerCredit)
            .options(selectinload(BrokerCredit.investments))
            .where(BrokerCredit.bank_transfer_id.in_(filtered_bank_ids))
            .order_by(BrokerCredit.date.desc())
        )
    elif date_filter_start and date_filter_end:
        # Month filter active but no bank transfers found
        broker_query = (
            select(BrokerCredit)
            .where(BrokerCredit.id == -1)  # Return nothing
        )
    else:
        # No filter - get all
        broker_query = (
            select(BrokerCredit)
            .options(selectinload(BrokerCredit.investments))
            .order_by(BrokerCredit.date.desc())
        )
    
    result = await session.execute(broker_query)
    broker_credits = result.scalars().all()

    # Get filtered broker IDs for investment query
    filtered_broker_ids = [bc.id for bc in broker_credits]

    # Fetch investments linked to filtered broker credits
    if filtered_broker_ids:
        investment_query = (
            select(MoneyFlowInvestment)
            .where(MoneyFlowInvestment.broker_credit_id.in_(filtered_broker_ids))
            .order_by(MoneyFlowInvestment.date.desc())
        )
    elif date_filter_start and date_filter_end:
        # Month filter active but no broker credits found
        investment_query = (
            select(MoneyFlowInvestment)
            .where(MoneyFlowInvestment.id == -1)  # Return nothing
        )
    else:
        # No filter - get all
        investment_query = (
            select(MoneyFlowInvestment)
            .order_by(MoneyFlowInvestment.date.desc())
        )
    
    result = await session.execute(investment_query)
    investments = result.scalars().all()

    # Calculate summary WITH the same filters
    summary = await _calculate_summary(session, date_filter_start, date_filter_end)

    # Get available months for filter dropdown
    months_query = (
        select(
            func.strftime('%Y-%m', BankTransfer.date).label('month')
        )
        .distinct()
        .order_by(func.strftime('%Y-%m', BankTransfer.date).desc())
    )
    result = await session.execute(months_query)
    available_months = [row[0] for row in result.fetchall()]

    context = {
        "request": request,
        "bank_transfers": bank_transfers,
        "broker_credits": broker_credits,
        "investments": investments,
        "summary": summary,
        "available_months": available_months,
        "selected_month": month,
        "banks": ["SBI", "HDFC", "ICICI"],  # Configurable later
        "brokers": ["Zerodha", "Kite", "Coin"],
        "savings": ["PPF", "NPS", "EPF"],
    }

    return templates.TemplateResponse("moneyflow/list.html", context)


# ============================================
# API: Bank Transfers
# ============================================

@router.post("/api/bank-transfers", response_model=BankTransferResponse)
async def create_bank_transfer(
    data: BankTransferCreate,
    session: AsyncSession = Depends(get_db)
):
    """Create a new bank transfer"""
    transfer = BankTransfer(
        date=data.date,
        amount=data.amount,
        source_bank=data.source_bank,
        notes=data.notes
    )
    session.add(transfer)
    await session.commit()
    await session.refresh(transfer)
    
    return BankTransferResponse(
        id=transfer.id,
        date=transfer.date,
        amount=transfer.amount,
        source_bank=transfer.source_bank,
        notes=transfer.notes,
        created_at=transfer.created_at,
        allocated_amount=0.0,
        idle_amount=transfer.amount
    )


@router.get("/api/bank-transfers", response_model=list[BankTransferResponse])
async def list_bank_transfers(
    session: AsyncSession = Depends(get_db),
    with_idle_only: bool = Query(default=False, description="Only show transfers with idle amount")
):
    """List all bank transfers"""
    query = (
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits))
        .order_by(BankTransfer.date.desc())
    )
    result = await session.execute(query)
    transfers = result.scalars().all()

    response = []
    for t in transfers:
        resp = BankTransferResponse(
            id=t.id,
            date=t.date,
            amount=t.amount,
            source_bank=t.source_bank,
            notes=t.notes,
            created_at=t.created_at,
            allocated_amount=t.allocated_amount,
            idle_amount=t.idle_amount
        )
        if with_idle_only and resp.idle_amount <= 0:
            continue
        response.append(resp)

    return response


@router.get("/api/bank-transfers/{transfer_id}", response_model=BankTransferResponse)
async def get_bank_transfer(
    transfer_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Get a specific bank transfer"""
    query = (
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits))
        .where(BankTransfer.id == transfer_id)
    )
    result = await session.execute(query)
    transfer = result.scalar_one_or_none()

    if not transfer:
        raise HTTPException(status_code=404, detail="Bank transfer not found")

    return BankTransferResponse(
        id=transfer.id,
        date=transfer.date,
        amount=transfer.amount,
        source_bank=transfer.source_bank,
        notes=transfer.notes,
        created_at=transfer.created_at,
        allocated_amount=transfer.allocated_amount,
        idle_amount=transfer.idle_amount
    )


@router.put("/api/bank-transfers/{transfer_id}", response_model=BankTransferResponse)
async def update_bank_transfer(
    transfer_id: int,
    data: BankTransferUpdate,
    session: AsyncSession = Depends(get_db)
):
    """Update a bank transfer"""
    query = (
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits))
        .where(BankTransfer.id == transfer_id)
    )
    result = await session.execute(query)
    transfer = result.scalar_one_or_none()

    if not transfer:
        raise HTTPException(status_code=404, detail="Bank transfer not found")

    # Update fields if provided
    if data.date is not None:
        transfer.date = data.date
    if data.amount is not None:
        # Validate: new amount must be >= allocated amount
        if data.amount < transfer.allocated_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Amount cannot be less than allocated amount (₹{transfer.allocated_amount})"
            )
        transfer.amount = data.amount
    if data.source_bank is not None:
        transfer.source_bank = data.source_bank
    if data.notes is not None:
        transfer.notes = data.notes

    await session.commit()
    await session.refresh(transfer)

    return BankTransferResponse(
        id=transfer.id,
        date=transfer.date,
        amount=transfer.amount,
        source_bank=transfer.source_bank,
        notes=transfer.notes,
        created_at=transfer.created_at,
        allocated_amount=transfer.allocated_amount,
        idle_amount=transfer.idle_amount
    )


@router.delete("/api/bank-transfers/{transfer_id}")
async def delete_bank_transfer(
    transfer_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Delete a bank transfer (cascades to broker credits and investments)"""
    query = select(BankTransfer).where(BankTransfer.id == transfer_id)
    result = await session.execute(query)
    transfer = result.scalar_one_or_none()

    if not transfer:
        raise HTTPException(status_code=404, detail="Bank transfer not found")

    await session.delete(transfer)
    await session.commit()

    return {"message": "Bank transfer deleted", "id": transfer_id}


# ============================================
# API: Broker Credits
# ============================================

@router.post("/api/broker-credits", response_model=BrokerCreditResponse)
async def create_broker_credit(
    data: BrokerCreditCreate,
    session: AsyncSession = Depends(get_db)
):
    """Create a new broker credit (allocate from bank transfer)"""
    # Validate bank transfer exists and has enough idle amount
    query = (
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits))
        .where(BankTransfer.id == data.bank_transfer_id)
    )
    result = await session.execute(query)
    bank_transfer = result.scalar_one_or_none()

    if not bank_transfer:
        raise HTTPException(status_code=404, detail="Bank transfer not found")

    if data.amount > bank_transfer.idle_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds available idle amount (₹{bank_transfer.idle_amount})"
        )

    credit = BrokerCredit(
        bank_transfer_id=data.bank_transfer_id,
        date=data.date,
        amount=data.amount,
        destination=data.destination,
        destination_type=data.destination_type,
        notes=data.notes
    )
    session.add(credit)
    await session.commit()
    await session.refresh(credit)

    return BrokerCreditResponse(
        id=credit.id,
        bank_transfer_id=credit.bank_transfer_id,
        date=credit.date,
        amount=credit.amount,
        destination=credit.destination,
        destination_type=credit.destination_type,
        notes=credit.notes,
        created_at=credit.created_at,
        invested_amount=0.0,
        idle_amount=credit.amount if credit.destination_type == "broker" else 0.0,
        is_complete=credit.destination_type == "savings",
        source_bank=bank_transfer.source_bank,
        source_date=bank_transfer.date
    )


@router.get("/api/broker-credits", response_model=list[BrokerCreditResponse])
async def list_broker_credits(
    session: AsyncSession = Depends(get_db),
    with_idle_only: bool = Query(default=False, description="Only show credits with idle amount"),
    destination_type: Optional[str] = Query(default=None, description="Filter by type: broker or savings")
):
    """List all broker credits"""
    query = (
        select(BrokerCredit)
        .options(
            selectinload(BrokerCredit.investments),
            selectinload(BrokerCredit.bank_transfer)
        )
        .order_by(BrokerCredit.date.desc())
    )
    
    if destination_type:
        query = query.where(BrokerCredit.destination_type == destination_type)

    result = await session.execute(query)
    credits = result.scalars().all()

    response = []
    for c in credits:
        resp = BrokerCreditResponse(
            id=c.id,
            bank_transfer_id=c.bank_transfer_id,
            date=c.date,
            amount=c.amount,
            destination=c.destination,
            destination_type=c.destination_type,
            notes=c.notes,
            created_at=c.created_at,
            invested_amount=c.invested_amount,
            idle_amount=c.idle_amount,
            is_complete=c.is_complete,
            source_bank=c.bank_transfer.source_bank if c.bank_transfer else None,
            source_date=c.bank_transfer.date if c.bank_transfer else None
        )
        if with_idle_only and resp.idle_amount <= 0:
            continue
        response.append(resp)

    return response


@router.get("/api/broker-credits/{credit_id}", response_model=BrokerCreditResponse)
async def get_broker_credit(
    credit_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Get a specific broker credit"""
    query = (
        select(BrokerCredit)
        .options(
            selectinload(BrokerCredit.investments),
            selectinload(BrokerCredit.bank_transfer)
        )
        .where(BrokerCredit.id == credit_id)
    )
    result = await session.execute(query)
    credit = result.scalar_one_or_none()

    if not credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")

    return BrokerCreditResponse(
        id=credit.id,
        bank_transfer_id=credit.bank_transfer_id,
        date=credit.date,
        amount=credit.amount,
        destination=credit.destination,
        destination_type=credit.destination_type,
        notes=credit.notes,
        created_at=credit.created_at,
        invested_amount=credit.invested_amount,
        idle_amount=credit.idle_amount,
        is_complete=credit.is_complete,
        source_bank=credit.bank_transfer.source_bank if credit.bank_transfer else None,
        source_date=credit.bank_transfer.date if credit.bank_transfer else None
    )


@router.put("/api/broker-credits/{credit_id}", response_model=BrokerCreditResponse)
async def update_broker_credit(
    credit_id: int,
    data: BrokerCreditUpdate,
    session: AsyncSession = Depends(get_db)
):
    """Update a broker credit"""
    query = (
        select(BrokerCredit)
        .options(
            selectinload(BrokerCredit.investments),
            selectinload(BrokerCredit.bank_transfer)
        )
        .where(BrokerCredit.id == credit_id)
    )
    result = await session.execute(query)
    credit = result.scalar_one_or_none()

    if not credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")

    if data.date is not None:
        credit.date = data.date
    if data.amount is not None:
        # Validate: new amount must be >= invested amount
        if data.amount < credit.invested_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Amount cannot be less than invested amount (₹{credit.invested_amount})"
            )
        credit.amount = data.amount
    if data.destination is not None:
        credit.destination = data.destination
    if data.destination_type is not None:
        credit.destination_type = data.destination_type
    if data.notes is not None:
        credit.notes = data.notes

    await session.commit()
    await session.refresh(credit)

    return BrokerCreditResponse(
        id=credit.id,
        bank_transfer_id=credit.bank_transfer_id,
        date=credit.date,
        amount=credit.amount,
        destination=credit.destination,
        destination_type=credit.destination_type,
        notes=credit.notes,
        created_at=credit.created_at,
        invested_amount=credit.invested_amount,
        idle_amount=credit.idle_amount,
        is_complete=credit.is_complete,
        source_bank=credit.bank_transfer.source_bank if credit.bank_transfer else None,
        source_date=credit.bank_transfer.date if credit.bank_transfer else None
    )


@router.delete("/api/broker-credits/{credit_id}")
async def delete_broker_credit(
    credit_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Delete a broker credit (cascades to investments)"""
    query = select(BrokerCredit).where(BrokerCredit.id == credit_id)
    result = await session.execute(query)
    credit = result.scalar_one_or_none()

    if not credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")

    await session.delete(credit)
    await session.commit()

    return {"message": "Broker credit deleted", "id": credit_id}


# ============================================
# API: Investments
# ============================================

@router.post("/api/investments", response_model=MoneyFlowInvestmentResponse)
async def create_investment(
    data: MoneyFlowInvestmentCreate,
    session: AsyncSession = Depends(get_db)
):
    """Create a new investment (from broker credit)"""
    # Validate broker credit exists and has enough idle amount
    query = (
        select(BrokerCredit)
        .options(selectinload(BrokerCredit.investments))
        .where(BrokerCredit.id == data.broker_credit_id)
    )
    result = await session.execute(query)
    broker_credit = result.scalar_one_or_none()

    if not broker_credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")

    if broker_credit.destination_type == "savings":
        raise HTTPException(
            status_code=400,
            detail="Cannot create investments for savings type (PPF/NPS)"
        )

    if data.amount > broker_credit.idle_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Amount exceeds available idle amount (₹{broker_credit.idle_amount})"
        )

    investment = MoneyFlowInvestment(
        broker_credit_id=data.broker_credit_id,
        date=data.date,
        amount=data.amount,
        holding_name=data.holding_name,
        holding_id=data.holding_id,
        notes=data.notes
    )
    session.add(investment)
    await session.commit()
    await session.refresh(investment)

    return MoneyFlowInvestmentResponse(
        id=investment.id,
        broker_credit_id=investment.broker_credit_id,
        date=investment.date,
        amount=investment.amount,
        holding_name=investment.holding_name,
        holding_id=investment.holding_id,
        notes=investment.notes,
        created_at=investment.created_at,
        broker_destination=broker_credit.destination,
        broker_date=broker_credit.date
    )


@router.get("/api/investments", response_model=list[MoneyFlowInvestmentResponse])
async def list_investments(
    session: AsyncSession = Depends(get_db)
):
    """List all investments"""
    query = (
        select(MoneyFlowInvestment)
        .options(selectinload(MoneyFlowInvestment.broker_credit))
        .order_by(MoneyFlowInvestment.date.desc())
    )
    result = await session.execute(query)
    investments = result.scalars().all()

    return [
        MoneyFlowInvestmentResponse(
            id=inv.id,
            broker_credit_id=inv.broker_credit_id,
            date=inv.date,
            amount=inv.amount,
            holding_name=inv.holding_name,
            holding_id=inv.holding_id,
            notes=inv.notes,
            created_at=inv.created_at,
            broker_destination=inv.broker_credit.destination if inv.broker_credit else None,
            broker_date=inv.broker_credit.date if inv.broker_credit else None
        )
        for inv in investments
    ]


@router.get("/api/investments/{investment_id}", response_model=MoneyFlowInvestmentResponse)
async def get_investment(
    investment_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Get a specific investment"""
    query = (
        select(MoneyFlowInvestment)
        .options(selectinload(MoneyFlowInvestment.broker_credit))
        .where(MoneyFlowInvestment.id == investment_id)
    )
    result = await session.execute(query)
    investment = result.scalar_one_or_none()

    if not investment:
        raise HTTPException(status_code=404, detail="Investment not found")

    return MoneyFlowInvestmentResponse(
        id=investment.id,
        broker_credit_id=investment.broker_credit_id,
        date=investment.date,
        amount=investment.amount,
        holding_name=investment.holding_name,
        holding_id=investment.holding_id,
        notes=investment.notes,
        created_at=investment.created_at,
        broker_destination=investment.broker_credit.destination if investment.broker_credit else None,
        broker_date=investment.broker_credit.date if investment.broker_credit else None
    )


@router.put("/api/investments/{investment_id}", response_model=MoneyFlowInvestmentResponse)
async def update_investment(
    investment_id: int,
    data: MoneyFlowInvestmentUpdate,
    session: AsyncSession = Depends(get_db)
):
    """Update an investment"""
    query = (
        select(MoneyFlowInvestment)
        .options(selectinload(MoneyFlowInvestment.broker_credit))
        .where(MoneyFlowInvestment.id == investment_id)
    )
    result = await session.execute(query)
    investment = result.scalar_one_or_none()

    if not investment:
        raise HTTPException(status_code=404, detail="Investment not found")

    if data.date is not None:
        investment.date = data.date
    if data.amount is not None:
        investment.amount = data.amount
    if data.holding_name is not None:
        investment.holding_name = data.holding_name
    if data.holding_id is not None:
        investment.holding_id = data.holding_id
    if data.notes is not None:
        investment.notes = data.notes

    await session.commit()
    await session.refresh(investment)

    return MoneyFlowInvestmentResponse(
        id=investment.id,
        broker_credit_id=investment.broker_credit_id,
        date=investment.date,
        amount=investment.amount,
        holding_name=investment.holding_name,
        holding_id=investment.holding_id,
        notes=investment.notes,
        created_at=investment.created_at,
        broker_destination=investment.broker_credit.destination if investment.broker_credit else None,
        broker_date=investment.broker_credit.date if investment.broker_credit else None
    )


@router.delete("/api/investments/{investment_id}")
async def delete_investment(
    investment_id: int,
    session: AsyncSession = Depends(get_db)
):
    """Delete an investment"""
    query = select(MoneyFlowInvestment).where(MoneyFlowInvestment.id == investment_id)
    result = await session.execute(query)
    investment = result.scalar_one_or_none()

    if not investment:
        raise HTTPException(status_code=404, detail="Investment not found")

    await session.delete(investment)
    await session.commit()

    return {"message": "Investment deleted", "id": investment_id}


# ============================================
# API: Summary
# ============================================

@router.get("/api/summary", response_model=MoneyFlowSummary)
async def get_summary(
    session: AsyncSession = Depends(get_db),
    month: Optional[str] = Query(default=None, description="Filter by month: YYYY-MM")
):
    """Get money flow summary statistics"""
    date_start = None
    date_end = None

    if month:
        try:
            year, mon = map(int, month.split("-"))
            date_start = dt.date(year, mon, 1)
            if mon == 12:
                date_end = dt.date(year + 1, 1, 1)
            else:
                date_end = dt.date(year, mon + 1, 1)
        except ValueError:
            pass  # Invalid month format, ignore filter
    return await _calculate_summary(session, date_start, date_end)


async def _calculate_summary(session: AsyncSession, date_start: dt.date = None, date_end: dt.date = None) -> MoneyFlowSummary:
    """Helper function to calculate summary statistics with optional date filtering"""
    
    # Fetch all data with relationships
    bank_query = (
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits).selectinload(BrokerCredit.investments))
    )

    if date_start and date_end:
        bank_query = bank_query.where(
            BankTransfer.date >= date_start,
            BankTransfer.date < date_end
        )

    result = await session.execute(bank_query)
    bank_transfers = result.scalars().all()

    # Get broker credit IDs from filtered bank transfers
    filter_bank_ids = [bt.id for bt in bank_transfers]

    broker_query = (
        select(BrokerCredit)
        .options(selectinload(BrokerCredit.investments))
    )
    if filter_bank_ids:
        broker_query = broker_query.where(BrokerCredit.bank_transfer_id.in_(filter_bank_ids))
    elif date_start and date_end:
        # If no bank transfers in date range, return empty
        broker_query = broker_query.where(BrokerCredit.id == -1)  # No results

    result = await session.execute(broker_query)
    broker_credits = result.scalars().all()

    # Get investment IDs from filtered broker credits
    filter_broker_ids = [bc.id for bc in broker_credits]

    investment_query = select(MoneyFlowInvestment)
    if filter_broker_ids:
        investment_query = investment_query.where(MoneyFlowInvestment.broker_credit_id.in_(filter_broker_ids))
    elif date_start and date_end:
        # If no broker credits in date range, return empty
        investment_query = investment_query.where(MoneyFlowInvestment.id == -1)  # No results

    result = await session.execute(investment_query)
    investments = result.scalars().all()

    # Calculate totals
    total_bank = sum(bt.amount for bt in bank_transfers)
    total_broker = sum(bc.amount for bc in broker_credits)
    total_invested = sum(inv.amount for inv in investments)

    # Calculate idle amounts
    idle_at_bank = sum(bt.idle_amount for bt in bank_transfers)
    idle_at_broker = sum(bc.idle_amount for bc in broker_credits)

    # Build breakdowns
    bank_idle_breakdown = [
        IdleBreakdown(
            id=bt.id,
            date=bt.date,
            source=bt.source_bank,
            total_amount=bt.amount,
            idle_amount=bt.idle_amount
        )
        for bt in bank_transfers
        if bt.idle_amount > 0
    ]

    broker_idle_breakdown = [
        IdleBreakdown(
            id=bc.id,
            date=bc.date,
            source=bc.destination,
            total_amount=bc.amount,
            idle_amount=bc.idle_amount
        )
        for bc in broker_credits
        if bc.idle_amount > 0
    ]

    return MoneyFlowSummary(
        total_bank_transfers=total_bank,
        total_broker_credits=total_broker,
        total_invested=total_invested,
        idle_at_bank=idle_at_bank,
        idle_at_broker=idle_at_broker,
        bank_idle_breakdown=bank_idle_breakdown,
        broker_idle_breakdown=broker_idle_breakdown,
        bank_transfer_count=len(bank_transfers),
        broker_credit_count=len(broker_credits),
        investment_count=len(investments)
    )
