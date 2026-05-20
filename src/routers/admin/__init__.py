"""Admin panel API router.

Mount point: /api/admin/* (mounted in src/api.py startup).

Re-assembles sub-routers into a single router for backward compatibility.
"""

from fastapi import APIRouter

from src.routers.admin.auth import router as auth_router
from src.routers.admin.common import _validate_tenant_id
from src.routers.admin.dashboard import router as dashboard_router
from src.routers.admin.health import router as health_router
from src.routers.admin.logs import (
    cleanup_expired_sessions,
    cleanup_old_logs,
    run_health_checks,
)
from src.routers.admin.logs import (
    router as logs_router,
)
from src.routers.admin.tenants import router as tenants_router

router = APIRouter(tags=["admin"])
router.include_router(auth_router)
router.include_router(tenants_router)
router.include_router(dashboard_router)
router.include_router(logs_router)
router.include_router(health_router)

__all__ = [
    "router",
    "_validate_tenant_id",
    "cleanup_expired_sessions",
    "cleanup_old_logs",
    "run_health_checks",
]
