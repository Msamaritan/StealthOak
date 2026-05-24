"""
Money Flow Router - API and HTML endpoints for Bank → Broker → Investment tracking
"""

import asyncio
import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.moneyflow import BankTransfer, BrokerCredit, MoneyFlowInvestment, ActiveSIP
from app.services.price_fetcher import price_fetcher
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
    ActiveSIPCreate,
    ActiveSIPUpdate,
    ActiveSIPResponse,
    RunSIPsRequest,
    RunCoinSIPsRequest,
    RunZerodhaSIPsRequest,
    RunSIPsResponse,
)

router = APIRouter(prefix="/moneyflow", tags=["Money Flow"])


# ============================================
# Template Setup
# ============================================

from config import settings
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


WEEKDAY_NAMES = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}


def _adjust_for_weekend(date: dt.date) -> dt.date:
    """
    If date falls on Saturday (5) or Sunday (6), move to next Monday.
    Market doesn't function on weekends, so we shift execution to following Monday.
    Returns the adjusted date.
    """
    weekday = date.weekday()  # 0=Monday, 6=Sunday
    if weekday == 5:  # Saturday
        return date + dt.timedelta(days=2)
    elif weekday == 6:  # Sunday
        return date + dt.timedelta(days=1)
    return date


def _is_sip_due(sip: ActiveSIP, execution_date: dt.date) -> bool:
    if not sip.is_active:
        return False

    # Adjust execution_date if it falls on weekend
    adjusted_execution_date = _adjust_for_weekend(execution_date)

    if sip.frequency == "monthly":
        due_day = sip.monthly_day or 1
        due_date = _adjust_for_weekend(dt.date(execution_date.year, execution_date.month, due_day))
        if adjusted_execution_date != due_date:
            return False
        # Check if already executed this month
        if sip.last_executed_on and sip.last_executed_on.year == execution_date.year and sip.last_executed_on.month == execution_date.month:
            return False
        return True

    if sip.frequency == "weekly":
        expected_day = sip.weekday or "Thursday"
        if WEEKDAY_NAMES.get(adjusted_execution_date.weekday()) != expected_day:
            return False
        if sip.last_executed_on == execution_date:
            return False
        return True

    if sip.frequency == "Particular Dates":
        if not sip.execution_dates:
            return False
        dates_list = [int(d.strip()) for d in sip.execution_dates.split(',') if d.strip()]
        if adjusted_execution_date.day not in dates_list:
            return False
        # Check if already executed this month
        if sip.last_executed_on and sip.last_executed_on.year == execution_date.year and sip.last_executed_on.month == execution_date.month:
            return False
        return True

    return False


async def _existing_sip_allocated_holdings(
    session: AsyncSession,
    broker_name: str,
    execution_date: dt.date,
) -> set[str]:
    """
    Return holding names that already have SIP-generated allocations for a broker/date.
    This checks only auto SIP notes, so manual investments are not blocked.
    """
    result = await session.execute(
        select(func.distinct(MoneyFlowInvestment.holding_name))
        .select_from(MoneyFlowInvestment)
        .join(BrokerCredit, MoneyFlowInvestment.broker_credit_id == BrokerCredit.id)
        .where(
            MoneyFlowInvestment.date == execution_date,
            func.lower(BrokerCredit.destination) == broker_name.lower(),
            BrokerCredit.destination_type == "broker",
            func.lower(func.coalesce(MoneyFlowInvestment.notes, "")).like("%sip allocation%"),
        )
    )
    return {row[0] for row in result.fetchall() if row[0]}


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

    # Active SIPs for dropdown sections
    sip_query = (
        select(ActiveSIP)
        .where(ActiveSIP.is_active == True)
        .order_by(ActiveSIP.broker_name.asc(), ActiveSIP.holding_name.asc())
    )
    result = await session.execute(sip_query)
    active_sips = result.scalars().all()

    zerodha_sips = [sip for sip in active_sips if sip.broker_name.lower() == "zerodha"]
    coin_sips = [sip for sip in active_sips if sip.broker_name.lower() == "coin"]
    active_sip_brokers = {sip.broker_name for sip in active_sips}
    active_sip_brokers_lower = {sip.broker_name.strip().lower() for sip in active_sips}
    today = dt.date.today()
    due_sip_brokers_today_lower = {
        sip.broker_name.strip().lower()
        for sip in active_sips
        if _is_sip_due(sip, today)
    }

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
        "zerodha_sips": zerodha_sips,
        "coin_sips": coin_sips,
        "active_sip_brokers": active_sip_brokers,
        "active_sip_brokers_lower": active_sip_brokers_lower,
        "due_sip_brokers_today_lower": due_sip_brokers_today_lower,
        "current_month": today.strftime("%Y-%m"),
    }

    return templates.TemplateResponse("moneyflow/list.html", context)


# ============================================
# API: Active SIPs
# ============================================

@router.get("/api/sips", response_model=list[ActiveSIPResponse])
async def list_active_sips(
    session: AsyncSession = Depends(get_db),
    broker_name: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True)
):
    query = select(ActiveSIP).order_by(ActiveSIP.broker_name.asc(), ActiveSIP.holding_name.asc())
    if active_only:
        query = query.where(ActiveSIP.is_active == True)
    if broker_name:
        query = query.where(func.lower(ActiveSIP.broker_name) == broker_name.lower())

    result = await session.execute(query)
    return result.scalars().all()


@router.post("/api/sips", response_model=ActiveSIPResponse)
async def create_active_sip(
    data: ActiveSIPCreate,
    session: AsyncSession = Depends(get_db)
):
    if data.frequency == "weekly" and not data.weekday:
        raise HTTPException(status_code=400, detail="weekday is required for weekly SIP")
    if data.frequency == "monthly" and not data.monthly_day:
        raise HTTPException(status_code=400, detail="monthly_day is required for monthly SIP")
    if data.frequency == "Particular Dates" and not data.execution_dates:
        raise HTTPException(status_code=400, detail="execution_dates is required for Particular Dates SIP")

    weekday = data.weekday if data.frequency == "weekly" else None
    monthly_day = data.monthly_day if data.frequency == "monthly" else None
    execution_dates = data.execution_dates if data.frequency == "Particular Dates" else None

    sip = ActiveSIP(
        broker_name=data.broker_name,
        holding_name=data.holding_name,
        frequency=data.frequency,
        weekday=weekday,
        monthly_day=monthly_day,
        execution_dates=execution_dates,
        amount=data.amount,
        notes=data.notes,
        is_active=True,
    )
    session.add(sip)
    await session.commit()
    await session.refresh(sip)
    return sip


@router.put("/api/sips/{sip_id}", response_model=ActiveSIPResponse)
async def update_active_sip(
    sip_id: int,
    data: ActiveSIPUpdate,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(select(ActiveSIP).where(ActiveSIP.id == sip_id))
    sip = result.scalar_one_or_none()
    if not sip:
        raise HTTPException(status_code=404, detail="SIP not found")

    if data.broker_name is not None:
        sip.broker_name = data.broker_name
    if data.holding_name is not None:
        sip.holding_name = data.holding_name
    if data.frequency is not None:
        sip.frequency = data.frequency
    if data.weekday is not None:
        sip.weekday = data.weekday
    if data.monthly_day is not None:
        sip.monthly_day = data.monthly_day
    if data.execution_dates is not None:
        sip.execution_dates = data.execution_dates
    if data.amount is not None:
        sip.amount = data.amount
    if data.is_active is not None:
        sip.is_active = data.is_active
    if data.notes is not None:
        sip.notes = data.notes

    if sip.frequency == "weekly" and not sip.weekday:
        raise HTTPException(status_code=400, detail="weekday is required for weekly SIP")
    if sip.frequency == "monthly" and not sip.monthly_day:
        raise HTTPException(status_code=400, detail="monthly_day is required for monthly SIP")
    if sip.frequency == "Particular Dates" and not sip.execution_dates:
        raise HTTPException(status_code=400, detail="execution_dates is required for Particular Dates SIP")

    # Keep only relevant scheduling fields for selected frequency.
    if sip.frequency == "weekly":
        sip.monthly_day = None
        sip.execution_dates = None
    elif sip.frequency == "monthly":
        sip.weekday = None
        sip.execution_dates = None
    elif sip.frequency == "Particular Dates":
        sip.weekday = None
        sip.monthly_day = None

    await session.commit()
    await session.refresh(sip)
    return sip


@router.delete("/api/sips/{sip_id}")
async def delete_active_sip(
    sip_id: int,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(select(ActiveSIP).where(ActiveSIP.id == sip_id))
    sip = result.scalar_one_or_none()
    if not sip:
        raise HTTPException(status_code=404, detail="SIP not found")

    await session.delete(sip)
    await session.commit()
    return {"message": "SIP deleted", "id": sip_id}


@router.get("/api/sips/due", response_model=list[ActiveSIPResponse])
async def list_due_sips(
    broker_name: str,
    execution_date: dt.date,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(
        select(ActiveSIP)
        .where(
            ActiveSIP.is_active == True,
            func.lower(ActiveSIP.broker_name) == broker_name.lower()
        )
        .order_by(ActiveSIP.holding_name.asc())
    )
    sips = result.scalars().all()
    existing_holdings = await _existing_sip_allocated_holdings(session, broker_name, execution_date)
    return [
        sip
        for sip in sips
        if _is_sip_due(sip, execution_date) and sip.holding_name not in existing_holdings
    ]


@router.post("/api/sips/run", response_model=RunSIPsResponse)
async def run_due_sips(
    data: RunSIPsRequest,
    session: AsyncSession = Depends(get_db)
):
    result = await session.execute(
        select(BrokerCredit)
        .options(selectinload(BrokerCredit.investments))
        .where(BrokerCredit.id == data.broker_credit_id)
    )
    broker_credit = result.scalar_one_or_none()
    if not broker_credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")
    if broker_credit.destination_type != "broker":
        raise HTTPException(status_code=400, detail="SIPs can only run against broker credits")
    if broker_credit.destination.strip().lower() != "zerodha":
        raise HTTPException(status_code=400, detail="Broker-credit SIP run is supported only for Zerodha")

    result = await session.execute(
        select(ActiveSIP)
        .where(
            ActiveSIP.is_active == True,
            func.lower(ActiveSIP.broker_name) == broker_credit.destination.lower()
        )
        .order_by(ActiveSIP.created_at.asc())
    )
    sips = result.scalars().all()
    due_sips = [sip for sip in sips if _is_sip_due(sip, data.execution_date)]
    existing_holdings = await _existing_sip_allocated_holdings(
        session,
        broker_credit.destination,
        data.execution_date,
    )

    remaining = broker_credit.idle_amount
    allocated_holdings: list[str] = []
    skipped_holdings: list[str] = []
    total_allocated = 0.0

    for sip in due_sips:
        if sip.holding_name in existing_holdings:
            skipped_holdings.append(sip.holding_name)
            continue
        if sip.amount <= remaining:
            inv = MoneyFlowInvestment(
                broker_credit_id=broker_credit.id,
                date=data.execution_date,
                amount=sip.amount,
                holding_name=sip.holding_name,
                notes=f"SIP allocation ({sip.frequency})"
            )
            session.add(inv)
            remaining -= sip.amount
            total_allocated += sip.amount
            allocated_holdings.append(sip.holding_name)
            existing_holdings.add(sip.holding_name)
            sip.last_executed_on = data.execution_date
        else:
            skipped_holdings.append(sip.holding_name)

    await session.commit()

    return RunSIPsResponse(
        broker_credit_id=broker_credit.id,
        execution_date=data.execution_date,
        total_allocated=total_allocated,
        allocated_count=len(allocated_holdings),
        skipped_count=len(skipped_holdings),
        allocated_holdings=allocated_holdings,
        skipped_holdings=skipped_holdings,
    )


@router.post("/api/sips/run-coin", response_model=RunSIPsResponse)
async def run_coin_sips(
    data: RunCoinSIPsRequest,
    session: AsyncSession = Depends(get_db)
):
    try:
        year, month = map(int, data.sip_month.split("-"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sip_month format; expected YYYY-MM")

    month_start = dt.date(year, month, 1)
    month_end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)

    result = await session.execute(
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits).selectinload(BrokerCredit.investments))
        .where(BankTransfer.id == data.bank_transfer_id)
    )
    bank_transfer = result.scalar_one_or_none()
    if not bank_transfer:
        raise HTTPException(status_code=404, detail="Bank transfer not found")

    if not (month_start <= bank_transfer.date < month_end):
        raise HTTPException(status_code=400, detail="Selected bank transfer is not in the selected SIP month")

    # CHECK FOR DUPLICATE RUN: Detect if this month's SIPs were already executed
    result = await session.execute(
        select(func.count(MoneyFlowInvestment.id))
        .select_from(MoneyFlowInvestment)
        .join(BrokerCredit, MoneyFlowInvestment.broker_credit_id == BrokerCredit.id)
        .where(
            MoneyFlowInvestment.date >= month_start,
            MoneyFlowInvestment.date < month_end,
            func.lower(BrokerCredit.destination) == "coin",
            BrokerCredit.destination_type == "broker",
            func.lower(func.coalesce(MoneyFlowInvestment.notes, "")).like("%coin sip allocation%"),
        )
    )
    existing_run_count = result.scalar() or 0
    if existing_run_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Coin SIPs for {data.sip_month} have already been executed. Please select a different month."
        )

    # Fetch all active Coin SIPs
    result = await session.execute(
        select(ActiveSIP)
        .where(
            ActiveSIP.is_active == True,
            func.lower(ActiveSIP.broker_name) == "coin"
        )
        .order_by(ActiveSIP.holding_name.asc())
    )
    sips = result.scalars().all()

    if not sips:
        raise HTTPException(status_code=400, detail="No active Coin SIPs found")

    # Generate all execution dates for the month
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    all_dates = []
    for day in range(1, days_in_month + 1):
        all_dates.append(dt.date(year, month, day))

    # Aggregate SIPs by fund across all execution dates in the month
    # Structure: {holding_name: {"amount": total, "dates": [date1, date2, ...], "sip": SIP object}}
    fund_aggregates: dict = {}

    for execution_date in all_dates:
        for sip in sips:
            # Check if this SIP is due on this execution_date
            if not _is_sip_due(sip, execution_date):
                continue
            
            # Get adjusted date (in case weekend shifted to Monday)
            adjusted_date = _adjust_for_weekend(execution_date)
            
            # Skip if already in aggregates (to avoid counting same SIP twice on same date)
            if sip.holding_name in fund_aggregates and adjusted_date in fund_aggregates[sip.holding_name]["dates"]:
                continue
            
            # Initialize fund aggregate if not present
            if sip.holding_name not in fund_aggregates:
                fund_aggregates[sip.holding_name] = {
                    "amount": 0,
                    "dates": [],
                    "sip": sip,
                    "frequency": sip.frequency
                }
            
            # Add this execution to the aggregate (with adjusted date)
            fund_aggregates[sip.holding_name]["amount"] += sip.amount
            fund_aggregates[sip.holding_name]["dates"].append(adjusted_date)

    if not fund_aggregates:
        raise HTTPException(
            status_code=400,
            detail="No Coin SIPs are due for the selected month. Check your SIP frequency settings."
        )

    # Check if we have enough idle amount for all aggregated allocations
    total_allocated = sum(data["amount"] for data in fund_aggregates.values())
    if total_allocated > bank_transfer.idle_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient idle amount (₹{bank_transfer.idle_amount}) for all due Coin SIPs (₹{total_allocated} needed)"
        )

    # Create one broker credit for the month
    coin_credit = BrokerCredit(
        bank_transfer_id=bank_transfer.id,
        date=month_start,  # Use month start date
        amount=total_allocated,
        destination="Coin",
        destination_type="broker",
        notes=f"Auto-created for Coin SIP run ({data.sip_month}) - Aggregated monthly batch - {len(fund_aggregates)} funds"
    )
    session.add(coin_credit)
    await session.flush()

    # Create one investment per fund with aggregated amount and execution dates
    allocated_holdings: list[str] = []
    for holding_name, data_info in fund_aggregates.items():
        dates_str = ", ".join(d.isoformat() for d in sorted(data_info["dates"]))
        inv = MoneyFlowInvestment(
            broker_credit_id=coin_credit.id,
            date=month_start,
            amount=data_info["amount"],
            holding_name=holding_name,
            notes=f"Coin SIP allocation ({data_info['frequency']}) - Dates: {dates_str}"
        )
        session.add(inv)
        allocated_holdings.append(holding_name)
        
        # Update last_executed_on for the SIP (use the last execution date in the month)
        sip = data_info["sip"]
        sip.last_executed_on = max(data_info["dates"])

    await session.commit()

    return RunSIPsResponse(
        broker_credit_id=coin_credit.id,
        execution_date=month_start,
        total_allocated=total_allocated,
        allocated_count=len(allocated_holdings),
        skipped_count=0,
        allocated_holdings=allocated_holdings,
        skipped_holdings=[],
    )


@router.post("/api/sips/run-zerodha", response_model=RunSIPsResponse)
async def run_zerodha_sips(
    data: RunZerodhaSIPsRequest,
    session: AsyncSession = Depends(get_db)
):
    """Run Zerodha SIPs for a month - aggregates all due SIPs into one transaction per fund."""
    try:
        year, month = map(int, data.sip_month.split("-"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid sip_month format; expected YYYY-MM")

    month_start = dt.date(year, month, 1)
    month_end = dt.date(year + 1, 1, 1) if month == 12 else dt.date(year, month + 1, 1)

    result = await session.execute(
        select(BrokerCredit)
        .options(selectinload(BrokerCredit.investments))
        .where(BrokerCredit.id == data.broker_credit_id)
    )
    broker_credit = result.scalar_one_or_none()
    if not broker_credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")

    if not (month_start <= broker_credit.date < month_end):
        raise HTTPException(status_code=400, detail="Selected broker credit is not in the selected SIP month")

    # CHECK FOR DUPLICATE RUN: Detect if Zerodha SIPs were already executed for this month
    result = await session.execute(
        select(func.count(MoneyFlowInvestment.id))
        .select_from(MoneyFlowInvestment)
        .where(
            MoneyFlowInvestment.broker_credit_id == broker_credit.id,
            MoneyFlowInvestment.date >= month_start,
            MoneyFlowInvestment.date < month_end,
            func.lower(func.coalesce(MoneyFlowInvestment.notes, "")).like("%zerodha sip allocation%"),
        )
    )
    existing_run_count = result.scalar() or 0
    if existing_run_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Zerodha SIPs for {data.sip_month} have already been executed for this broker credit. Please select a different month or broker credit."
        )

    # Fetch all active Zerodha SIPs
    result = await session.execute(
        select(ActiveSIP)
        .where(
            ActiveSIP.is_active == True,
            func.lower(ActiveSIP.broker_name) == "zerodha"
        )
        .order_by(ActiveSIP.holding_name.asc())
    )
    sips = result.scalars().all()

    if not sips:
        raise HTTPException(status_code=400, detail="No active Zerodha SIPs found")

    # Generate all execution dates for the month
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    all_dates = []
    for day in range(1, days_in_month + 1):
        all_dates.append(dt.date(year, month, day))

    # Aggregate SIPs by fund across all execution dates in the month
    fund_aggregates: dict = {}

    for execution_date in all_dates:
        for sip in sips:
            # Check if this SIP is due on this execution_date
            if not _is_sip_due(sip, execution_date):
                continue
            
            # Get adjusted date (in case weekend shifted to Monday)
            adjusted_date = _adjust_for_weekend(execution_date)
            
            # Skip if already in aggregates (to avoid counting same SIP twice on same date)
            if sip.holding_name in fund_aggregates and adjusted_date in fund_aggregates[sip.holding_name]["dates"]:
                continue
            
            # Initialize fund aggregate if not present
            if sip.holding_name not in fund_aggregates:
                fund_aggregates[sip.holding_name] = {
                    "amount": 0,
                    "dates": [],
                    "sip": sip,
                    "frequency": sip.frequency
                }
            
            # Add this execution to the aggregate (with adjusted date)
            fund_aggregates[sip.holding_name]["amount"] += sip.amount
            fund_aggregates[sip.holding_name]["dates"].append(adjusted_date)

    if not fund_aggregates:
        raise HTTPException(
            status_code=400,
            detail="No Zerodha SIPs are due for the selected month. Check your SIP frequency settings."
        )

    # Check if we have enough idle amount for all aggregated allocations
    total_allocated = sum(data_info["amount"] for data_info in fund_aggregates.values())
    if total_allocated > broker_credit.idle_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient idle amount (₹{broker_credit.idle_amount}) for all due Zerodha SIPs (₹{total_allocated} needed)"
        )

    # Create investments under the existing broker credit (dated on 1st of month)
    allocated_holdings: list[str] = []
    for holding_name, data_info in fund_aggregates.items():
        dates_str = ", ".join(d.isoformat() for d in sorted(data_info["dates"]))
        inv = MoneyFlowInvestment(
            broker_credit_id=broker_credit.id,
            date=month_start,  # Use month start date like Coin does
            amount=data_info["amount"],
            holding_name=holding_name,
            notes=f"Zerodha SIP allocation ({data_info['frequency']}) - Dates: {dates_str}"
        )
        session.add(inv)
        allocated_holdings.append(holding_name)
        
        # Update last_executed_on for the SIP (use the last execution date in the month)
        sip = data_info["sip"]
        sip.last_executed_on = max(data_info["dates"])

    await session.commit()

    return RunSIPsResponse(
        broker_credit_id=broker_credit.id,
        execution_date=month_start,
        total_allocated=total_allocated,
        allocated_count=len(allocated_holdings),
        skipped_count=0,
        allocated_holdings=allocated_holdings,
        skipped_holdings=[],
    )


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
    with_idle_only: bool = Query(default=False, description="Only show transfers with idle amount"),
    month: Optional[str] = Query(default=None, description="Filter by month: YYYY-MM")
):
    """List all bank transfers"""
    query = (
        select(BankTransfer)
        .options(selectinload(BankTransfer.broker_credits))
        .order_by(BankTransfer.date.desc())
    )

    if month:
        try:
            year, mon = map(int, month.split("-"))
            start = dt.date(year, mon, 1)
            end = dt.date(year + 1, 1, 1) if mon == 12 else dt.date(year, mon + 1, 1)
            query = query.where(BankTransfer.date >= start, BankTransfer.date < end)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid month format. Use YYYY-MM")

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
    destination_type: Optional[str] = Query(default=None, description="Filter by type: broker or savings"),
    month: Optional[str] = Query(default=None, description="Filter by month (YYYY-MM format)"),
    broker: Optional[str] = Query(default=None, description="Filter by broker destination (Zerodha, Coin, etc.)")
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
    
    if month:
        try:
            year, month_num = map(int, month.split("-"))
            month_start = dt.date(year, month_num, 1)
            month_end = dt.date(year + 1, 1, 1) if month_num == 12 else dt.date(year, month_num + 1, 1)
            query = query.where(BrokerCredit.date >= month_start, BrokerCredit.date < month_end)
        except (ValueError, IndexError):
            pass  # Ignore invalid month format
    
    if broker:
        query = query.where(func.lower(BrokerCredit.destination) == broker.lower())

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
    """
    Delete a broker credit (cascades to investments).
    Also resets last_executed_on for any SIPs that were executed via this credit.
    """
    # Fetch the broker credit with investments
    query = (
        select(BrokerCredit)
        .options(selectinload(BrokerCredit.investments))
        .where(BrokerCredit.id == credit_id)
    )
    result = await session.execute(query)
    credit = result.scalar_one_or_none()

    if not credit:
        raise HTTPException(status_code=404, detail="Broker credit not found")

    # Check if this is an auto-created SIP broker credit
    is_sip_credit = credit.notes and "Auto-created for" in credit.notes and "SIP run" in credit.notes
    
    # If it is, reset last_executed_on for the SIPs that were executed
    if is_sip_credit:
        holding_names_in_credit = {inv.holding_name for inv in credit.investments}
        
        if holding_names_in_credit:
            # Find all SIPs that match this broker and holding names
            result = await session.execute(
                select(ActiveSIP).where(
                    func.lower(ActiveSIP.broker_name) == credit.destination.lower(),
                    ActiveSIP.holding_name.in_(holding_names_in_credit)
                )
            )
            sips_to_reset = result.scalars().all()
            
            # Reset their last_executed_on since the execution is being deleted
            for sip in sips_to_reset:
                sip.last_executed_on = None

    # Explicitly delete child investments first to avoid orphan rows
    # when DB-level cascades are not enforced.
    for investment in list(credit.investments):
        await session.delete(investment)

    # Delete the broker credit (which cascades to investments)
    await session.delete(credit)
    await session.commit()

    return {"message": "Broker credit deleted", "id": credit_id}


# ============================================
# API: Asset Search & Historical Price
# ============================================

@router.get("/api/assets/search")
async def search_assets(q: str = Query(default="")):
    """Search both stocks and mutual funds for moneyflow investment selection."""
    query = (q or "").strip()
    if len(query) < 2:
        return []

    stock_task = price_fetcher.search_stocks(query)
    mf_task = price_fetcher.search_mutual_funds(query) if len(query) >= 3 else asyncio.sleep(0, result=[])
    stock_results, mf_results = await asyncio.gather(stock_task, mf_task)

    combined = []

    for stock in stock_results[:8]:
        symbol = stock.get("symbol")
        exchange = stock.get("exchange", "NSE")
        name = stock.get("name") or symbol
        combined.append(
            {
                "asset_type": "stock",
                "holding_name": name,
                "display_name": f"{symbol} - {name} ({exchange})",
                "symbol": symbol,
                "exchange": exchange,
            }
        )

    for fund in mf_results[:8]:
        scheme_code = str(fund.get("scheme_code") or "")
        scheme_name = fund.get("scheme_name") or scheme_code
        combined.append(
            {
                "asset_type": "mutual_fund",
                "holding_name": scheme_name,
                "display_name": f"{scheme_name} (Code: {scheme_code})",
                "scheme_code": scheme_code,
            }
        )

    return combined[:16]


@router.get("/api/assets/historical-price")
async def get_historical_asset_price(
    asset_type: str,
    target_date: dt.date,
    symbol: Optional[str] = None,
    exchange: str = "NSE",
    scheme_code: Optional[str] = None,
):
    """Return 1-unit historical price on or before target_date with fallback."""
    normalized_type = asset_type.strip().lower()

    if normalized_type == "stock":
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required for stock")

        result = await price_fetcher.get_stock_price_on_or_before(
            symbol=symbol.strip().upper(),
            exchange=exchange.strip().upper() if exchange else "NSE",
            target_date=target_date,
        )

        if not result:
            raise HTTPException(status_code=404, detail="No historical stock price found for selected date")

        return {
            "asset_type": "stock",
            "unit_price": result["price"],
            "price_date": result["price_date"],
            "requested_date": result["requested_date"],
            "is_fallback": result["is_fallback"],
            "display_name": f"{result['symbol']} ({result['exchange']})",
        }

    if normalized_type in {"mutual_fund", "mutual fund", "mf"}:
        if not scheme_code:
            raise HTTPException(status_code=400, detail="scheme_code is required for mutual fund")

        result = await price_fetcher.get_mf_nav_on_or_before(
            scheme_code=scheme_code.strip(),
            target_date=target_date,
        )

        if not result:
            raise HTTPException(status_code=404, detail="No historical NAV found for selected date")

        return {
            "asset_type": "mutual_fund",
            "unit_price": result["price"],
            "price_date": result["price_date"],
            "requested_date": result["requested_date"],
            "is_fallback": result["is_fallback"],
            "display_name": result.get("scheme_name") or result["scheme_code"],
        }

    raise HTTPException(status_code=400, detail="asset_type must be 'stock' or 'mutual_fund'")


# ============================================
# API: Investments
# ============================================

@router.post("/api/investments", response_model=MoneyFlowInvestmentResponse)
async def create_investment(
    data: MoneyFlowInvestmentCreate,
    session: AsyncSession = Depends(get_db)
):
    """Create a new investment from broker credit or direct bank transfer (PPF)."""
    broker_credit = None

    if data.broker_credit_id:
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
    elif data.bank_transfer_id:
        transfer_query = (
            select(BankTransfer)
            .options(selectinload(BankTransfer.broker_credits))
            .where(BankTransfer.id == data.bank_transfer_id)
        )
        result = await session.execute(transfer_query)
        bank_transfer = result.scalar_one_or_none()

        if not bank_transfer:
            raise HTTPException(status_code=404, detail="Bank transfer not found")

        if data.amount > bank_transfer.idle_amount:
            raise HTTPException(
                status_code=400,
                detail=f"Amount exceeds available idle amount (₹{bank_transfer.idle_amount})"
            )

        # Bridge the bank transfer to investments without exposing savings in the broker card flow.
        broker_credit = BrokerCredit(
            bank_transfer_id=bank_transfer.id,
            date=data.date,
            amount=data.amount,
            destination="PPF",
            destination_type="savings",
            notes=data.notes or "Direct PPF investment from bank transfer",
        )
        session.add(broker_credit)
        await session.flush()
    else:
        raise HTTPException(
            status_code=400,
            detail="Either broker_credit_id or bank_transfer_id is required"
        )

    investment = MoneyFlowInvestment(
        broker_credit_id=broker_credit.id,
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
    total_broker = sum(bc.amount for bc in broker_credits if bc.destination_type == "broker")
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
