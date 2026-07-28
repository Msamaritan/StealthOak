# ============================================
# StealthOak - Mutual Funds Router
# ============================================

from typing import List

from fastapi import APIRouter, Depends, Request, HTTPException, status, Body
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Holding, Portfolio, User
from app.routers.auth import get_current_user
from app.schemas import HoldingCreate
from app.services.price_fetcher import price_fetcher
from app.services.portfolio_stats import portfolio_stats
from app.utils import get_configured_templates



router = APIRouter(prefix="/mutualfunds", tags=["Mutual Funds"])

templates = get_configured_templates()


def _mutual_fund_market_cards() -> List[dict]:
    return [
        {
            "theme": "india",
            "title": "Indian Market",
            "picture_label": "Indian Market",
            "image_url": "/static/images/indian_market.jpg",
            "description": "Track AMFI schemes, live NAVs, and the holdings you already manage.",
            "cta": "Open Indian Mutual Funds",
            "href": "/mutualfunds/india",
        },
        {
            "theme": "foreign",
            "title": "Foreign Market",
            "picture_label": "Foreign Market",
            "image_url": "/static/images/foreign_market.jpg",
            "description": "A separate view for international funds, ETFs, and future cross-border support.",
            "cta": "Open Foreign Funds",
            "href": "/mutualfunds/foreign",
        },
    ]


def _render_market_selector(request: Request, current_user: User):
    return templates.TemplateResponse(
        "market_selector.html",
        {
            "request": request,
            "current_user": current_user,
            "page_title": "Mutual Fund Markets",
            "heading": "Mutual Funds",
            "description": "Choose the market you want to manage.",
            "cards": _mutual_fund_market_cards(),
        },
    )


def _render_foreign_market_page(request: Request, current_user: User):
    return templates.TemplateResponse(
        "market_placeholder.html",
        {
            "request": request,
            "current_user": current_user,
            "page_title": "Foreign Mutual Funds",
            "heading": "Foreign Mutual Funds",
            "description": "Template-only view for overseas fund holdings.",
            "back_url": "/mutualfunds",
            "placeholder_title": "Foreign fund page scaffolded",
            "placeholder_copy": "This page is ready for future foreign fund data, NAV fetching, and ETF support.",
            "features": [
                {
                    "label": "Funds",
                    "title": "International schemes",
                    "copy": "A dedicated holdings table can live here once foreign fund sources are wired up.",
                },
                {
                    "label": "ETFs",
                    "title": "Foreign ETFs",
                    "copy": "These can share the same layout as funds while keeping the market split clear.",
                },
                {
                    "label": "Watchlists",
                    "title": "Future expansion",
                    "copy": "You can extend the same market split when you add other overseas instruments.",
                },
            ],
        },
    )


# ----------------------------------------
# HTML PAGES
# ----------------------------------------

@router.get("", response_class=HTMLResponse)
async def mutualfunds_market_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Mutual funds market landing page."""
    return _render_market_selector(request, current_user)


@router.get("/india", response_class=HTMLResponse)
@router.get("/indian", response_class=HTMLResponse)
async def indian_mutualfunds_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Indian mutual funds listing page."""
    result = await db.execute(
        select(Holding)
        .join(Portfolio)
        .where(
            Holding.asset_type == "mutual_fund",
            Portfolio.user_id == current_user.id
        )
    )
    holdings: List[Holding] = list(result.scalars().all())
    
    enriched = []
    if holdings:
        enriched = await portfolio_stats.enrich_holdings_with_prices(holdings)
    
    return templates.TemplateResponse(
        "mutualfunds/list.html",
        {
            "request": request,
            "current_user": current_user,
            "mutual_funds": enriched,
        }
    )


@router.get("/foreign", response_class=HTMLResponse)
async def foreign_mutualfunds_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Foreign mutual funds landing page placeholder."""
    return _render_foreign_market_page(request, current_user)


@router.get("/add", response_class=HTMLResponse)
async def add_mutualfund_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """
    Add mutual fund form page with search functionality.
    """
    return templates.TemplateResponse(
        "mutualfunds/add.html",
        {
            "request": request,
            "current_user": current_user,
        }
    )

@router.get("/edit/{holding_id}", response_class=HTMLResponse)
async def edit_mutualfund_page(
    request: Request,
    holding_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Edit mutual fund form page."""
    result = await db.execute(
        select(Holding)
        .join(Portfolio)
        .where(
            Holding.id == holding_id,
            Holding.asset_type == "mutual_fund",
            Portfolio.user_id == current_user.id
        )
    )
    holding = result.scalar_one_or_none()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    
    return templates.TemplateResponse(
        "mutualfunds/edit.html",
        {
            "request": request,
            "current_user": current_user,
            "holding": holding,
        }
    )


@router.post("/edit/{holding_id}", response_class=HTMLResponse)
async def update_mutualfund_form(
    request: Request,
    holding_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Handle mutual fund edit form submission."""
    result = await db.execute(
        select(Holding)
        .join(Portfolio)
        .where(
            Holding.id == holding_id,
            Holding.asset_type == "mutual_fund",
            Portfolio.user_id == current_user.id
        )
    )
    holding = result.scalar_one_or_none()
    
    if not holding:
        raise HTTPException(status_code=404, detail="Mutual fund not found")
    
    form = await request.form()
    
    quantity = form.get("quantity", "")
    avg_price = form.get("avg_price", "")
    
    errors = []
    
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
            "mutualfunds/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "holding": holding,
                "errors": errors,
            }
        )
    
    # Update holding
    holding.quantity = quantity
    holding.avg_price = avg_price
    
    return RedirectResponse(url="/mutualfunds/india", status_code=303)


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
    current_user: User = Depends(get_current_user),
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
    
    # Get or create default portfolio for this user
    result = await db.execute(
        select(Portfolio).where(
            Portfolio.owner == "Self",
            Portfolio.user_id == current_user.id
        )
    )
    portfolio = result.scalar_one_or_none()
    
    if not portfolio:
        portfolio = Portfolio(
            name="Main Portfolio",
            owner="Self",
            user_id=current_user.id
        )
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
    
    return RedirectResponse(url="/mutualfunds/india", status_code=303)


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


@router.delete("/api")
async def delete_all_mutualfunds(
    db: AsyncSession = Depends(get_db)
):
    """
    Delete all mutual fund holdings.
    """
    result = await db.execute(
        select(Holding).where(Holding.asset_type == "mutual_fund")
    )
    holdings = list(result.scalars().all())

    deleted_count = len(holdings)
    for holding in holdings:
        await db.delete(holding)

    return {
        "message": "All mutual funds deleted successfully",
        "deleted": deleted_count,
    }


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


@router.post("/api/{holding_id}/resolve-scheme")
async def resolve_mf_scheme_manually(
    holding_id: int,
    scheme_code: str = Body(..., embed=True),
    scheme_name: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually resolve an unresolved MF holding by setting correct scheme code.
    Used when AMFI mapping did not auto-resolve.
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
    
    if not scheme_code or not scheme_code.strip().isdigit():
        raise HTTPException(status_code=400, detail="Invalid scheme code")

    # Preserve ISIN: if the current symbol is an ISIN (non-numeric), save it as isin before overwriting
    if holding.symbol and not holding.symbol.strip().isdigit():
        holding.isin = holding.symbol.strip()

    holding.symbol = scheme_code.strip()
    if scheme_name:
        holding.name = scheme_name.strip()
    
    await db.commit()
    
    return {
        "message": "Scheme code resolved successfully",
        "id": holding.id,
        "scheme_code": holding.symbol,
        "scheme_name": holding.name,
    }


@router.get("/api/search")
async def search_mf_schemes(q: str):
    """
    Search for mutual fund schemes by name from mfapi.
    """
    if len(q.strip()) < 3:
        return []
    
    try:
        schemes = await price_fetcher.search_mf_schemes(q)
        return schemes
    except Exception:
        return []
