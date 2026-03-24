# ============================================
# StealthOak - Routers Package
# ============================================

from fastapi import APIRouter

from app.routers.dashboard import router as dashboard_router
from app.routers.stocks import router as stocks_router
from app.routers.mutualfunds import router as mutualfunds_router


# Main router that combines all sub-routers
router = APIRouter()

# Include all routers
router.include_router(dashboard_router)
router.include_router(stocks_router)
router.include_router(mutualfunds_router)

__all__ = ["router"]
