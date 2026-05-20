"""Dashboard overview endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from src.routers._admin_deps import verify_admin_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

@router.get("/api/admin/dashboard/summary")
async def dashboard_summary(
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Aggregated dashboard overview — tenant counts, pipeline runs, error rate."""
    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            # Tenant counts
            tenant_count_row = await conn.fetchrow(
                "SELECT COUNT(*) as total FROM tenants WHERE status = 'active'"
            )
            tenant_today_row = await conn.fetchrow(
                "SELECT COUNT(*) as total FROM tenants WHERE created_at >= CURRENT_DATE"
            )

            # Pipeline runs today — naive count from pipeline_states
            pipeline_total = 0
            pipeline_failed = 0
            pipeline_running = 0
            try:
                pipeline_total_row = await conn.fetchrow(
                    "SELECT COUNT(*) as total FROM pipeline_states WHERE created_at >= CURRENT_DATE"
                )
                pipeline_total = pipeline_total_row["total"] if pipeline_total_row else 0
            except Exception as exc:
                logger.warning(
                    "admin dashboard pipeline count query failed: %s",
                    str(exc)[:200],
                )

            # Recent errors from error_logs
            error_rows = await conn.fetch(
                """
                SELECT id, tenant_id, scenario, error_code, message, created_at
                FROM error_logs
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            recent_errors = []
            for e in error_rows:
                recent_errors.append({
                    "id": str(e["id"]),
                    "tenant_id": e["tenant_id"],
                    "scenario": e["scenario"],
                    "error_code": e["error_code"],
                    "message": e["message"][:150] if e["message"] else "",
                    "created_at": e["created_at"].isoformat() if e["created_at"] else None,
                })

            # Error rate (24h)
            error_rate_24h = 0.0
            try:
                total_24h_row = await conn.fetchrow(
                    "SELECT COUNT(*) as total FROM pipeline_states WHERE created_at >= NOW() - INTERVAL '24 hours'"
                )
                # degraded states are tracked in memory — approximate from error_logs
                error_24h_row = await conn.fetchrow(
                    "SELECT COUNT(DISTINCT tenant_id) as total FROM error_logs WHERE created_at >= NOW() - INTERVAL '24 hours'"
                )
                total_24h = total_24h_row["total"] if total_24h_row else 0
                error_24h = error_24h_row["total"] if error_24h_row else 0
                if total_24h > 0:
                    error_rate_24h = round(error_24h / total_24h, 4)
            except Exception as exc:
                logger.warning(
                    "admin dashboard error rate query failed: %s",
                    str(exc)[:200],
                )

            return {
                "tenant_count": tenant_count_row["total"] if tenant_count_row else 0,
                "tenant_count_today": tenant_today_row["total"] if tenant_today_row else 0,
                "pipeline_runs_today": {
                    "total": pipeline_total,
                    "success": pipeline_total - pipeline_failed - pipeline_running,
                    "failed": pipeline_failed,
                    "running": pipeline_running,
                },
                "error_rate_24h": error_rate_24h,
                "recent_errors": recent_errors,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("dashboard_summary_error error=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to load dashboard")


# ═══════════════════════════════════════════════════════════════════
# System Logs
# ═══════════════════════════════════════════════════════════════════
