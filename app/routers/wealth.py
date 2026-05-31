# ============================================
# StealthOak - Wealth Router
# ============================================

from datetime import date
from typing import Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Holding, PPFBalance, PPFTransaction
from app.services.portfolio_stats import portfolio_stats
from app.utils import get_configured_templates



router = APIRouter(prefix="/wealth", tags=["Wealth"])

templates = get_configured_templates()

# ETF symbols that should appear as Gold / Silver rows on the Wealth page
# rather than being lumped into the Stocks bucket. Add more as needed.
GOLD_ETF_SYMBOLS: frozenset[str] = frozenset({
    "GOLDBEES", "GOLDETF", "KOTAKGOLD", "AXISGOLD",
    "BSLGOLDETF", "HDFCMFGETF", "QGOLDHALF", "HDFC Gold ETF Fund of Fund - Direct Plan"
})

SILVER_ETF_SYMBOLS: frozenset[str] = frozenset({
    "SILVERBEES", "SILVETF", "SILVERETF", "SILVRETF", "ICICISILVE",
})


async def _get_or_create_ppf(db: AsyncSession) -> PPFBalance:
    result = await db.execute(
        select(PPFBalance).order_by(PPFBalance.id.asc()).limit(1)
    )
    ppf = result.scalar_one_or_none()
    if ppf is None:
        ppf = PPFBalance(name="Primary PPF")
        db.add(ppf)
        await db.flush()
    return ppf


async def _build_wealth_context(db: AsyncSession) -> Dict:
    result = await db.execute(select(Holding))
    holdings: List[Holding] = list(result.scalars().all())

    enriched = []
    if holdings:
        enriched = await portfolio_stats.enrich_holdings_with_prices(holdings)

    def _is_gold(h) -> bool:
        return (h.asset_type == "stock") and h.symbol.upper() in GOLD_ETF_SYMBOLS

    def _is_silver(h) -> bool:
        return (h.asset_type == "stock") and h.symbol.upper() in SILVER_ETF_SYMBOLS

    def _val(h) -> float:
        return h.current_value or h.invested_value

    stock_invested = sum(h.invested_value for h in enriched if h.asset_type == "stock" and not _is_gold(h) and not _is_silver(h))
    stock_current  = sum(_val(h)           for h in enriched if h.asset_type == "stock" and not _is_gold(h) and not _is_silver(h))

    gold_invested  = sum(h.invested_value  for h in enriched if _is_gold(h))
    gold_current   = sum(_val(h)           for h in enriched if _is_gold(h))

    silver_invested = sum(h.invested_value for h in enriched if _is_silver(h))
    silver_current  = sum(_val(h)          for h in enriched if _is_silver(h))

    mf_invested = sum(h.invested_value for h in enriched if h.asset_type == "mutual_fund")
    mf_current = sum(
        _val(h) for h in enriched if h.asset_type == "mutual_fund"
    )

    ppf = await _get_or_create_ppf(db)
    ppf_invested = ppf.invested_amount
    ppf_current = ppf.current_value

    total_invested = stock_invested + gold_invested + silver_invested + mf_invested + ppf_invested
    total_current  = stock_current  + gold_current  + silver_current  + mf_current  + ppf_current
    total_pnl = total_current - total_invested
    total_pnl_percent = round((total_pnl / total_invested * 100), 2) if total_invested > 0 else 0.0

    def _alloc(val: float) -> float:
        return round((val / total_invested * 100), 1) if total_invested > 0 else 0.0

    def _pnl_pct(current: float, invested: float) -> float:
        return round(((current - invested) / invested * 100), 2) if invested > 0 else 0.0

    def _row(label: str, invested: float, current: float) -> Dict:
        return {
            "asset": label,
            "invested": round(invested, 2),
            "current": round(current, 2),
            "pnl": round(current - invested, 2),
            "pnl_percent": _pnl_pct(current, invested),
            "alloc_percent": _alloc(invested),
        }

    ## Asset - Stocks
    asset_rows: List[Dict] = [_row("Stocks", stock_invested, stock_current)]

    ## Asset - Mutual Funds
    asset_rows.append(_row("Mutual Funds", mf_invested, mf_current))

    ## Assets - Gold / Silver (only if user has any)
    if gold_invested > 0 or gold_current > 0:
        asset_rows.append(_row("Gold", gold_invested, gold_current))

    if silver_invested > 0 or silver_current > 0:
        asset_rows.append(_row("Silver", silver_invested, silver_current))

    ## Asset - PPF
    asset_rows.append(_row("PPF", ppf_invested, ppf_current))

    return {
        "asset_rows": asset_rows,
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_percent": total_pnl_percent,
        "stock_alloc": _alloc(stock_invested),
        "gold_alloc": _alloc(gold_invested),
        "silver_alloc": _alloc(silver_invested),
        "mf_alloc": _alloc(mf_invested),
        "ppf_alloc": _alloc(ppf_invested),
    }


@router.get("", response_class=HTMLResponse)
async def wealth_page(request: Request, db: AsyncSession = Depends(get_db)):
    ctx = await _build_wealth_context(db)
    ctx["request"] = request
    return templates.TemplateResponse("wealth.html", ctx)


@router.post("/ppf/transaction")
async def add_ppf_transaction(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    transaction_type = (form.get("transaction_type") or "").strip().lower()
    amount_raw = form.get("amount", "0")
    date_raw = form.get("transaction_date", "")
    note = (form.get("note") or "").strip() or None

    errors: List[str] = []
    if transaction_type not in ("deposit", "interest"):
        errors.append("Transaction type must be Deposit or Interest")

    amount = 0.0
    try:
        amount = float(amount_raw)
        if amount <= 0:
            errors.append("Amount must be greater than 0")
    except (ValueError, TypeError):
        errors.append("Invalid amount")

    txn_date = None
    try:
        txn_date = date.fromisoformat(date_raw)
    except (ValueError, TypeError):
        errors.append("Invalid date")

    if errors:
        return JSONResponse({"success": False, "errors": errors}, status_code=400)

    ppf = await _get_or_create_ppf(db)
    txn = PPFTransaction(
        ppf_id=ppf.id,
        transaction_type=transaction_type,
        amount=amount,
        transaction_date=txn_date,
        note=note,
    )
    db.add(txn)
    return JSONResponse({"success": True})


@router.get("/ppf/transactions")
async def get_ppf_transactions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PPFBalance).order_by(PPFBalance.id.asc()).limit(1)
    )
    ppf = result.scalar_one_or_none()
    if not ppf or not ppf.transactions:
        return {"transactions": [], "invested": 0.0, "current": 0.0}

    txns = sorted(ppf.transactions, key=lambda t: t.transaction_date, reverse=True)
    return {
        "transactions": [
            {
                "id": t.id,
                "type": t.transaction_type,
                "amount": t.amount,
                "date": t.transaction_date.isoformat(),
                "note": t.note or "",
            }
            for t in txns
        ],
        "invested": round(ppf.invested_amount, 2),
        "current": round(ppf.current_value, 2),
    }
