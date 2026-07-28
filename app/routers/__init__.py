# ============================================
# StealthOak - Routers Package
# ============================================

from fastapi import APIRouter

from app.routers.dashboard import router as dashboard_router
from app.routers.stocks import router as stocks_router
from app.routers.mutualfunds import router as mutualfunds_router
from app.routers.kite import router as kite_router
from app.routers.moneyflow import router as moneyflow_router
from app.routers.wealth import router as wealth_router
from app.routers.insurance import router as insurance_router
from app.routers.admin import router as admin_router


# Main router that combines all sub-routers
router = APIRouter()

# Include all routers
router.include_router(dashboard_router)
router.include_router(stocks_router)
router.include_router(mutualfunds_router)
router.include_router(kite_router)
router.include_router(moneyflow_router)
router.include_router(wealth_router)
router.include_router(insurance_router)
router.include_router(admin_router)
__all__ = ["router"]
