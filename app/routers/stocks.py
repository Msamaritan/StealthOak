# ============================================
# StealthOak - Stocks Router
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


router = APIRouter(prefix="/stocks", tags=["Stocks"])

templates = Jinja2Templates(directory="app/templates")


# ----------------------------------------
# HTML PAGES
# ----------------------------------------

@router.get("", response_class=HTMLResponse)
async def stocks_list_page(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Stocks listing page.
    
    Shows all stocks with live prices.
    """
    # Query only stocks
    result = await db.execute(
        select(Holding).where(Holding.asset_type == "stock")
    )
    holdings: List[Holding] = list(result.scalars().all())
    
    # Enrich with live prices
    enriched = []
    if holdings:
        enriched = await portfolio_stats.enrich_holdings_with_prices(holdings)
    
    return templates.TemplateResponse(
        "stocks/list.html",
        {
            "request": request,
            "stocks": enriched,
        }
    )


@router.get("/add", response_class=HTMLResponse)
async def add_stock_page(request: Request):
    """
    Add stock form page.
    """
    return templates.TemplateResponse(
        "stocks/add.html",
        {"request": request}
    )


# ----------------------------------------
# API ENDPOINTS
# ----------------------------------------

@router.get("/api/search")
async def search_stocks(q: str = ""):
    """
    Search stocks by name or symbol.
    
    Example:
        GET /stocks/api/search?q=infosys
        GET /stocks/api/search?q=TCS
    
    Returns:
        [
            {"symbol": "INFY", "name": "Infosys Limited", "exchange": "NSE"},
            {"symbol": "INFY", "name": "Infosys Limited", "exchange": "BSE"},
        ]
    """
    if not q or len(q) < 2:
        return []
    
    results = await price_fetcher.search_stocks(q)
    return results

@router.post("/api", status_code=status.HTTP_201_CREATED)
async def create_stock(
    stock_data: HoldingCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new stock holding.
    
    Request Body:
        {
            "symbol": "INFY",
            "name": "Infosys Limited",
            "asset_type": "stock",
            "exchange": "NSE",
            "quantity": 50,
            "avg_price": 1400.50
        }
    """
    # Validate asset type
    if stock_data.asset_type != "stock":
        raise HTTPException(
            status_code=400,
            detail="Asset type must be 'stock'"
        )
    
    # Ensure exchange is provided for stocks
    if not stock_data.exchange:
        raise HTTPException(
            status_code=400,
            detail="Exchange (NSE/BSE) is required for stocks"
        )
    
    # Get or create default portfolio
    result = await db.execute(
        select(Portfolio).where(Portfolio.owner == "Self")
    )
    portfolio = result.scalar_one_or_none()
    
    if not portfolio:
        portfolio = Portfolio(name="Main Portfolio", owner="Self")
        db.add(portfolio)
        await db.flush()  # Get the ID
    
    # Create holding
    holding = Holding(
        portfolio_id=portfolio.id,
        symbol=stock_data.symbol,
        name=stock_data.name,
        asset_type=stock_data.asset_type,
        exchange=stock_data.exchange,
        quantity=stock_data.quantity,
        avg_price=stock_data.avg_price,
    )
    
    db.add(holding)
    await db.flush()
    
    return {
        "message": "Stock added successfully",
        "id": holding.id,
        "symbol": holding.symbol,
    }


@router.post("/add", response_class=HTMLResponse)
async def create_stock_form(
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Handle stock form submission (HTML form POST).
    
    Redirects to stocks list on success.
    """
    form = await request.form()
    
    # Extract form data
    symbol = form.get("symbol", "").strip().upper()
    name = form.get("name", "").strip()
    exchange = form.get("exchange", "").strip().upper()
    quantity = form.get("quantity", "")
    avg_price = form.get("avg_price", "")
    
    # Basic validation
    errors = []
    if not symbol:
        errors.append("Symbol is required")
    if not name:
        errors.append("Name is required")
    if not exchange:
        errors.append("Exchange is required")
    
    try:
        quantity = float(quantity)
        if quantity <= 0:
            errors.append("Quantity must be greater than 0")
    except ValueError:
        errors.append("Invalid quantity")
    
    try:
        avg_price = float(avg_price)
        if avg_price <= 0:
            errors.append("Average price must be greater than 0")
    except ValueError:
        errors.append("Invalid average price")
    
    if errors:
        return templates.TemplateResponse(
            "stocks/add.html",
            {
                "request": request,
                "errors": errors,
                "form_data": {
                    "symbol": symbol,
                    "name": name,
                    "exchange": exchange,
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
    
    # Create holding
    holding = Holding(
        portfolio_id=portfolio.id,
        symbol=symbol,
        name=name,
        asset_type="stock",
        exchange=exchange,
        quantity=quantity,
        avg_price=avg_price,
    )
    
    db.add(holding)
    
    # Redirect to stocks list
    return RedirectResponse(url="/stocks", status_code=303)


@router.delete("/api/{holding_id}")
async def delete_stock(
    holding_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a stock holding.
    """
    result = await db.execute(
        select(Holding).where(
            Holding.id == holding_id,
            Holding.asset_type == "stock"
        )
    )
    holding = result.scalar_one_or_none()
    
    if not holding:
        raise HTTPException(
            status_code=404,
            detail="Stock not found"
        )
    
    await db.delete(holding)
    
    return {"message": "Stock deleted successfully", "id": holding_id}


@router.get("/api/{holding_id}/price")
async def get_stock_price(holding_id: int, db: AsyncSession = Depends(get_db)):
    """
    Fetch live price for a specific stock.
    """
    result = await db.execute(
        select(Holding).where(
            Holding.id == holding_id,
            Holding.asset_type == "stock"
        )
    )
    holding = result.scalar_one_or_none()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Stock not found")
    
    price_data = await price_fetcher.get_stock_price(holding.symbol)
    
    if not price_data:
        raise HTTPException(status_code=503, detail="Unable to fetch price")
    
    return price_data
