"""Service health status endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request

from src.routers._admin_deps import verify_admin_session
from src.routers.admin.logs import _health_history, _health_lock, run_health_checks

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

@router.get("/api/admin/health/status")
async def health_status(
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Return current service health status. Triggers an immediate check."""
    await run_health_checks()

    latest = _health_history[-1] if _health_history else {
        "checked_at": None,
        "services": {},
    }

    return {
        "checked_at": latest["checked_at"],
        "services": latest["services"],
    }


@router.get("/api/admin/health/history")
async def health_history(
    request: Request,
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Return recent health check history."""
    hours = max(1, min(72, int(request.query_params.get("hours", "24"))))
    entries_per_hour = 12  # 5-min intervals
    max_entries = hours * entries_per_hour

    async with _health_lock:
        history = list(_health_history[-max_entries:]) if _health_history else []

    return {
        "checks": history,
        "count": len(history),
    }
