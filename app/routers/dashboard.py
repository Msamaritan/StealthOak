# ============================================
# StealthOak - Dashboard Router
# ============================================

from typing import List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Holding, Portfolio, User
from app.routers.auth import get_current_user
from app.services.portfolio_stats import portfolio_stats
from app.utils import get_configured_templates



router = APIRouter(tags=["Dashboard"])

# Templates directory
templates = get_configured_templates()


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Main dashboard page.
    
    Shows:
    - Total invested, current value, P&L
    - Asset allocation chart
    - Top holdings
    - Stocks table
    - Mutual funds table
    """
    # Get all holdings for the current user
    result = await db.execute(
        select(Holding)
        .join(Portfolio)
        .where(Portfolio.user_id == current_user.id)
    )
    holdings: List[Holding] = list(result.scalars().all())
    
    # If no holdings, show empty dashboard
    if not holdings:
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "current_user": current_user,
                "summary": None,
                "allocation": {"stock": 0, "mutual_fund": 0},
                "top_holdings": [],
                "stocks": [],
                "mutual_funds": [],
            }
        )
    
    # Enrich holdings with live prices
    enriched = await portfolio_stats.enrich_holdings_with_prices(holdings)
    
    # Calculate statistics
    summary = portfolio_stats.calculate_summary(enriched)
    allocation = portfolio_stats.calculate_asset_allocation(enriched)
    top_holdings = portfolio_stats.get_top_holdings(enriched, limit=5)
    
    # Separate stocks and mutual funds — sorted by current value desc for the dashboard cards
    def _sort_key(h):
        return h.current_value if h.current_value is not None else h.invested_value or 0

    all_stocks = sorted(
        [h for h in enriched if h.asset_type == "stock"],
        key=_sort_key,
        reverse=True,
    )
    all_mutual_funds = sorted(
        [h for h in enriched if h.asset_type == "mutual_fund"],
        key=_sort_key,
        reverse=True,
    )

    stocks = all_stocks[:5]
    mutual_funds = all_mutual_funds[:5]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "current_user": current_user,
            "summary": summary,
            "allocation": allocation,
            "top_holdings": top_holdings,
            "stocks": stocks,
            "mutual_funds": mutual_funds,
        }
    )


@router.get("/api/dashboard/stats")
async def dashboard_stats_api(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Dashboard statistics as JSON.
    
    Useful for:
    - AJAX refresh without page reload
    - Future mobile app
    """
    result = await db.execute(
        select(Holding)
        .join(Portfolio)
        .where(Portfolio.user_id == current_user.id)
    )
    holdings: List[Holding] = list(result.scalars().all())
    
    if not holdings:
        return {
            "summary": None,
            "allocation": {"stock": 0, "mutual_fund": 0},
            "holdings_count": 0,
        }
    
    enriched = await portfolio_stats.enrich_holdings_with_prices(holdings)
    summary = portfolio_stats.calculate_summary(enriched)
    allocation = portfolio_stats.calculate_asset_allocation(enriched)
    
    return {
        "summary": {
            "total_invested": summary.total_invested,
            "total_current_value": summary.total_current_value,
            "total_pnl": summary.total_pnl,
            "total_pnl_percent": summary.total_pnl_percent,
            "day_change": summary.day_change,
            "day_change_percent": summary.day_change_percent,
        },
        "allocation": allocation,
        "holdings_count": summary.holdings_count,
    }
