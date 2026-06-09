"""Error log viewer endpoints."""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.routers._admin_deps import verify_admin_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

@router.get("/api/admin/logs")
async def list_logs(
    request: Request,
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """List error logs with pagination and filters."""
    page = max(1, int(request.query_params.get("page", "1")))
    limit = min(100, max(1, int(request.query_params.get("limit", "50"))))
    level = (request.query_params.get("level") or "").strip().upper()
    scenario = (request.query_params.get("scenario") or "").strip()
    tenant_filter = (request.query_params.get("tenant_id") or "").strip()
    from_dt = (request.query_params.get("from") or "").strip()
    to_dt = (request.query_params.get("to") or "").strip()

    offset = (page - 1) * limit

    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None

        conditions: list[str] = []
        params: list[Any] = []
        param_idx = 0

        if scenario:
            param_idx += 1
            conditions.append(f"scenario = ${param_idx}")
            params.append(scenario)

        if tenant_filter:
            param_idx += 1
            conditions.append(f"tenant_id = ${param_idx}")
            params.append(tenant_filter)

        if from_dt:
            param_idx += 1
            conditions.append(f"created_at >= ${param_idx}::timestamptz")
            params.append(from_dt)

        if to_dt:
            param_idx += 1
            conditions.append(f"created_at <= ${param_idx}::timestamptz")
            params.append(to_dt)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Count
        count_sql = f"SELECT COUNT(*) FROM error_logs {where_clause}"
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(count_sql, *params)
            total = count_row["count"] if count_row else 0

        # Fetch
        param_idx += 1
        fetch_sql = f"""
            SELECT id, tenant_id, scenario, error_code, message, created_at
            FROM error_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        fetch_params = params[:] + [limit, offset]
        async with pool.acquire() as conn:
            rows = await conn.fetch(fetch_sql, *fetch_params)

        items = []
        for r in rows:
            items.append({
                "id": str(r["id"]),
                "tenant_id": r["tenant_id"],
                "scenario": r["scenario"],
                "error_code": r["error_code"],
                "message": r["message"][:200] if r["message"] else "",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })

        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("list_logs_error error=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to list logs")


@router.get("/api/admin/logs/{log_id}")
async def get_log_detail(
    log_id: str,
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Get full log entry including traceback."""
    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, scenario, error_code, message, traceback, created_at
                FROM error_logs
                WHERE id = $1
                """,
                log_id,
            )

            if row is None:
                raise HTTPException(status_code=404, detail="Log entry not found")

            return {
                "id": str(row["id"]),
                "tenant_id": row["tenant_id"],
                "scenario": row["scenario"],
                "error_code": row["error_code"],
                "message": row["message"],
                "traceback": row["traceback"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_log_detail_error log_id=%s error=%s", log_id, str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to get log detail")


# ═══════════════════════════════════════════════════════════════════
# Background cleanup tasks (registered in api.py startup)
# ═══════════════════════════════════════════════════════════════════


async def cleanup_expired_sessions() -> None:
    """Delete expired admin sessions. Runs every hour."""
    try:
        from src.storage.db import get_pool, is_pg_available
        if not is_pg_available():
            return
        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM admin_sessions WHERE expires_at < NOW()"
            )
    except Exception as exc:
        logger.warning(
            "admin expired session cleanup failed: %s",
            str(exc)[:200],
        )


async def cleanup_old_logs() -> None:
    """Delete error_logs older than ADMIN_LOG_RETENTION_DAYS. Runs every hour."""
    import os
    retention_days = int(os.getenv("ADMIN_LOG_RETENTION_DAYS", "30"))
    if retention_days <= 0:
        return
    try:
        from src.storage.db import get_pool, is_pg_available
        if not is_pg_available():
            return
        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            # Delete in batches to avoid long table locks
            await conn.execute(
                f"""
                DELETE FROM error_logs
                WHERE id IN (
                    SELECT id FROM error_logs
                    WHERE created_at < NOW() - INTERVAL '{retention_days} days'
                    LIMIT 1000
                )
                """
            )
    except Exception as exc:
        logger.warning(
            "admin old log cleanup failed: %s",
            str(exc)[:200],
        )


# ═══════════════════════════════════════════════════════════════════
# System Health
# ═══════════════════════════════════════════════════════════════════

import asyncio as _asyncio

# In-memory health history (288 entries = 24h at 5-min intervals)
_health_history: list[dict[str, Any]] = []
_health_lock = _asyncio.Lock()


async def _check_single_service(name: str) -> dict[str, Any]:
    """Check a single external service. Returns {status, latency_ms}."""
    import time as _time

    start = _time.time()
    try:
        if name == "postgres":
            from src.storage.db import get_pool, is_pg_available
            if not is_pg_available():
                return {"status": "down", "latency_ms": 0}
            pool = await get_pool()
            assert pool is not None
            async with pool.acquire() as conn:
                await conn.fetchrow("SELECT 1")
        elif name == "deepseek":
            from src.tools.llm_client import LLMClient
            client = LLMClient(timeout=10.0)
            await client.ainvoke("", "hi")
        elif name == "poyo":
            import httpx
            from src.config import POYO_API_BASE_URL, POYO_API_KEY
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                resp = await http_client.get(
                    f"{POYO_API_BASE_URL}/v1/models",
                    headers={"Authorization": f"Bearer {POYO_API_KEY}"},
                )
                if resp.status_code >= 500:
                    raise Exception(f"POYO returned {resp.status_code}")
        elif name == "siliconflow":
            import httpx
            from src.config import SILICONFLOW_API_BASE, SILICONFLOW_API_KEY
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                resp = await http_client.get(
                    f"{SILICONFLOW_API_BASE}/models",
                    headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"},
                )
                if resp.status_code >= 500:
                    raise Exception(f"SiliconFlow returned {resp.status_code}")
        elif name == "remotion":
            from src.tools.remotion_renderer import RemotionRenderer
            result = RemotionRenderer().validate_environment()
            return {
                "status": "healthy" if result.get("available") else "down",
                "latency_ms": round((_time.time() - start) * 1000, 2),
                "available": result.get("available", False),
            }
        else:
            return {"status": "down", "latency_ms": 0}

        latency_ms = round((_time.time() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": latency_ms}
    except Exception:
        latency_ms = round((_time.time() - start) * 1000, 2)
        return {"status": "down", "latency_ms": latency_ms}


async def run_health_checks() -> None:
    """Run all health checks and store results. Called by background task."""
    from datetime import datetime as _dt

    services = {}
    for svc in ["postgres", "deepseek", "poyo", "siliconflow", "remotion"]:
        services[svc] = await _check_single_service(svc)

    entry = {
        "checked_at": _dt.now(UTC).isoformat(),
        "services": services,
    }

    async with _health_lock:
        _health_history.append(entry)
        if len(_health_history) > 288:
            _health_history.pop(0)
