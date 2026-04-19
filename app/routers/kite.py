"""
Kite Router - Zerodha authentication routes
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from app.database import get_db
from app.models import KiteSession
from app.services.kite_service import init_kite_service, get_kite_service

router = APIRouter(prefix="/kite", tags=["Kite"])


async def _get_authenticated_kite(db: AsyncSession):
    """Return an authenticated Kite service from memory or persisted session."""
    kite = get_kite_service()
    if kite:
        return kite

    result = await db.execute(
        select(KiteSession)
        .where(KiteSession.is_active.is_(True))
        .order_by(KiteSession.updated_at.desc())
        .limit(1)
    )
    stored_session = result.scalar_one_or_none()

    if not stored_session or not stored_session.access_token:
        raise HTTPException(status_code=401, detail="Kite access token not available. Login again.")

    return init_kite_service(
        api_key=stored_session.api_key,
        api_secret=stored_session.api_secret,
        access_token=stored_session.access_token,
        disable_ssl=settings.kite_disable_ssl,
    )


@router.get("/login")
def kite_login():
    """Redirect user to Zerodha login page"""
    
    # Initialize KiteService (singleton)
    kite = init_kite_service(
        api_key=settings.kite_api_key,
        api_secret=settings.kite_api_secret,
        disable_ssl=settings.kite_disable_ssl,
    )
    
    # Get Zerodha login URL
    login_url = kite.get_login_url()
    print(f"[KITE] Redirecting to: {login_url}")
    
    return RedirectResponse(url=login_url)


@router.get("/callback")
async def kite_callback(
    request_token: str = None,
    status: str = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Zerodha OAuth callback"""
    
    # Check if login was successful
    if status != "success" or not request_token:
        print(f"[KITE] Login failed: status={status}")
        raise HTTPException(status_code=400, detail="Login failed")
    
    # Get existing KiteService instance
    kite = get_kite_service()
    if not kite:
        raise HTTPException(status_code=500, detail="KiteService not initialized")
    
    try:
        # Exchange request_token for access_token
        session = kite.generate_session(request_token)

        result = await db.execute(select(KiteSession).where(KiteSession.is_active.is_(True)))
        active_sessions = list(result.scalars().all())
        for active_session in active_sessions:
            active_session.is_active = False

        db.add(
            KiteSession(
                api_key=settings.kite_api_key,
                api_secret=settings.kite_api_secret,
                access_token=session.get("access_token"),
                user_id=session.get("user_id"),
                login_time=session.get("login_time"),
                is_active=True,
            )
        )

        holdings = kite.get_holdings()
        
        # Print to terminal for verification
        print("=" * 50)
        print("[KITE] Login successful!")
        print(f"  User ID    : {session.get('user_id')}")
        print(f"  User Name  : {session.get('user_name')}")
        print(f"  Email      : {session.get('email')}")
        print(f"  Access Token: {session.get('access_token')[:20]}...")
        print(f"  Holdings   : {len(holdings)} fetched")
        print("=" * 50)
        
        # Redirect to dashboard
        return RedirectResponse(url="/")
        
    except Exception as e:
        print(f"[KITE] Session generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/holdings")
async def kite_holdings(db: AsyncSession = Depends(get_db)):
    """Fetch holdings from Zerodha using the active access token."""
    kite = await _get_authenticated_kite(db)

    try:
        holdings = kite.get_holdings()
        return {
            "count": len(holdings),
            "holdings": holdings,
        }
    except Exception as e:
        print(f"[KITE] Holdings fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
