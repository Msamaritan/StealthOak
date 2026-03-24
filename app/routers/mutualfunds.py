# ============================================
# StealthOak - Mutual Funds Router
# ============================================

from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Holding, Portfolio
from app.schemas import HoldingCreate
from app.services.price_fetcher import price_fetcher
from app.services.portfolio_stats import portfolio_stats


router = APIRouter(prefix="/mutualfunds", tags=["Mutual Funds"])

templates = Jinja2Templates(directory="app/templates")


# ----------------------------------------
# HTML PAGES
# ----------------------------------------

@router.get("", response_class=HTMLResponse)
async def mutualfunds_list_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Mutual funds listing page.
    """
    result = await db.execute(
        select(Holding).where(Holding.asset_type == "mutual_fund")
    )
    holdings: List[Holding] = list(result.scalars().all())
    
    enriched = []
    if holdings:
        enriched = await portfolio_stats.enrich_holdings_with_prices(holdings)
    
    return templates.TemplateResponse(
        "mutualfunds/list.html",
        {
            "request": request,
            "mutual_funds": enriched,
        }
    )


@router.get("/add", response_class=HTMLResponse)
async def add_mutualfund_page(request: Request):
    """
    Add mutual fund form page with search functionality.
    """
    return templates.TemplateResponse(
        "mutualfunds/add.html",
        {"request": request}
    )


# ----------------------------------------
# API ENDPOINTS
# ----------------------------------------

@router.get("/api/search")
async def search_mutual_funds(q: str = ""):
    """
    Search mutual funds by name.
    
    Query Params:
        q: Search query (e.g., "axis bluechip")
    
    Returns:
        List of matching funds with scheme_code and scheme_name
    """
    if not q or len(q) < 3:
        return []
    
    results = await price_fetcher.search_mutual_funds(q)
    return results


@router.post("/api", status_code=status.HTTP_201_CREATED)
async def create_mutualfund(
    mf_data: HoldingCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new mutual fund holding.
    
    Request Body:
        {
            "symbol": "120503",
            "name": "Axis Bluechip Fund - Direct Growth",
            "asset_type": "mutual_fund",
            "quantity": 120.5,
            "avg_price": 45.20
        }
    """
    if mf_data.asset_type != "mutual_fund":
        raise HTTPException(
            status_code=400,
            detail="Asset type must be 'mutual_fund'"
        )
    
    # Get or create default portfolio
    result = await db.execute(
        select(Portfolio).where(Portfolio.owner == "Self")
    )
    portfolio = result.scalar_one_or_none()
    
    if not portfolio:
        portfolio = Portfolio(name="Main Portfolio", owner="Self")
        db.add(portfolio)
        await db.flush()
    
    holding = Holding(
        portfolio_id=portfolio.id,
        symbol=mf_data.symbol,
        name=mf_data.name,
        asset_type=mf_data.asset_type,
        exchange=None,  # MFs don't have exchange
        quantity=mf_data.quantity,
        avg_price=mf_data.avg_price,
    )
    
    db.add(holding)
    await db.flush()
    
    return {
        "message": "Mutual fund added successfully",
        "id": holding.id,
        "scheme_code": holding.symbol,
    }


@router.post("/add", response_class=HTMLResponse)
async def create_mutualfund_form(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle mutual fund form submission.
    """
    form = await request.form()
    
    scheme_code = form.get("scheme_code", "").strip()
    name = form.get("name", "").strip()
    quantity = form.get("quantity", "")
    avg_price = form.get("avg_price", "")
    
    errors = []
    if not scheme_code:
        errors.append("Scheme code is required")
    if not name:
        errors.append("Fund name is required")
    
    try:
        quantity = float(quantity)
        if quantity <= 0:
            errors.append("Units must be greater than 0")
    except ValueError:
        errors.append("Invalid units")
    
    try:
        avg_price = float(avg_price)
        if avg_price <= 0:
            errors.append("Average NAV must be greater than 0")
    except ValueError:
        errors.append("Invalid average NAV")
    
    if errors:
        return templates.TemplateResponse(
            "mutualfunds/add.html",
            {
                "request": request,
                "errors": errors,
                "form_data": {
                    "scheme_code": scheme_code,
                    "name": name,
                    "quantity": form.get("quantity"),
                    "avg_price": form.get("avg_price"),
                },
            }
        )
    
    # Get or create default portfolio
    result = await db.execute(
        select(Portfolio).where(Portfolio.owner == "Self")
    )
    portfolio = result.scalar_one_or_none()
    
    if not portfolio:
        portfolio = Portfolio(name="Main Portfolio", owner="Self")
        db.add(portfolio)
        await db.flush()
    
    holding = Holding(
        portfolio_id=portfolio.id,
        symbol=scheme_code,
        name=name,
        asset_type="mutual_fund",
        exchange=None,
        quantity=quantity,
        avg_price=avg_price,
    )
    
    db.add(holding)
    
    return RedirectResponse(url="/mutualfunds", status_code=303)


@router.delete("/api/{holding_id}")
async def delete_mutualfund(
    holding_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a mutual fund holding.
    """
    result = await db.execute(
        select(Holding).where(
            Holding.id == holding_id,
            Holding.asset_type == "mutual_fund"
        )
    )
    holding = result.scalar_one_or_none()
    
    if not holding:
        raise HTTPException(
            status_code=404,
            detail="Mutual fund not found"
        )
    
    await db.delete(holding)
    
    return {"message": "Mutual fund deleted successfully", "id": holding_id}


@router.get("/api/{holding_id}/nav")
async def get_mf_nav(holding_id: int, db: AsyncSession = Depends(get_db)):
    """
    Fetch latest NAV for a specific mutual fund.
    """
    result = await db.execute(
        select(Holding).where(
            Holding.id == holding_id,
            Holding.asset_type == "mutual_fund"
        )
    )
    holding = result.scalar_one_or_none()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    
    nav_data = await price_fetcher.get_mf_nav(holding.symbol)
    
    if not nav_data:
        raise HTTPException(status_code=503, detail="Unable to fetch NAV")
    
    return nav_data
