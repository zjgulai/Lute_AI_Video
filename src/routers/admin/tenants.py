"""Tenant management endpoints."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from src.routers._admin_deps import verify_admin_session, verify_csrf_token
from src.routers.admin.common import _validate_tenant_id

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])
DEFAULT_API_KEY_TTL_DAYS = 90


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_api_key_expiry(raw_value: Any) -> datetime:
    now = datetime.now(UTC)
    if raw_value in (None, ""):
        return now + timedelta(days=DEFAULT_API_KEY_TTL_DAYS)
    if not isinstance(raw_value, str):
        raise HTTPException(status_code=422, detail="expires_at must be an ISO datetime")

    try:
        parsed = datetime.fromisoformat(raw_value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=422, detail="expires_at must be an ISO datetime")

    expires_at = _as_utc_datetime(parsed)
    if expires_at <= now:
        raise HTTPException(status_code=422, detail="expires_at must be in the future")
    return expires_at


@router.post("/api/admin/tenants")
async def create_tenant(
    request: Request,
    admin_id: str = Depends(verify_admin_session),
    _csrf: None = Depends(verify_csrf_token),
) -> dict[str, Any]:
    """Create a new tenant. Does NOT generate an API key — use
    POST /tenants/{tenant_id}/keys for that."""
    body = await request.json()
    tenant_id = (body.get("tenant_id") or "").strip().lower()
    display_name = (body.get("display_name") or "").strip()
    contact_email = (body.get("contact_email") or "").strip()

    if not tenant_id:
        raise HTTPException(status_code=422, detail="tenant_id is required")
    if not display_name:
        raise HTTPException(status_code=422, detail="display_name is required")

    _validate_tenant_id(tenant_id)

    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO tenants (tenant_id, display_name, contact_email)
                VALUES ($1, $2, $3)
                RETURNING id, tenant_id, display_name, contact_email,
                          status, created_at
                """,
                tenant_id,
                display_name,
                contact_email,
            )
    except Exception as exc:
        error_str = str(exc).lower()
        if "unique" in error_str or "duplicate" in error_str:
            raise HTTPException(
                status_code=409, detail="Tenant ID already exists"
            )
        if "violates" in error_str and "check" in error_str:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Invalid tenant_id format. Must be 3-32 characters, "
                    "lowercase alphanumeric with optional hyphens."
                ),
            )
        logger.error("create_tenant_error error=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to create tenant")

    return {
        "id": str(row["id"]),
        "tenant_id": row["tenant_id"],
        "display_name": row["display_name"],
        "contact_email": row["contact_email"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


@router.get("/api/admin/tenants")
async def list_tenants(
    request: Request,
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """List tenants with pagination and optional search."""
    page = max(1, int(request.query_params.get("page", "1")))
    limit = min(100, max(1, int(request.query_params.get("limit", "20"))))
    q = (request.query_params.get("q") or "").strip()
    status_filter = (request.query_params.get("status") or "all").strip().lower()

    offset = (page - 1) * limit

    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None

        # Build query conditions
        conditions = []
        params: list[Any] = []
        param_idx = 0

        if q:
            param_idx += 1
            conditions.append(
                f"(tenant_id ILIKE ${param_idx} OR display_name ILIKE ${param_idx})"
            )
            params.append(f"%{q}%")

        if status_filter in ("active", "disabled"):
            param_idx += 1
            conditions.append(f"status = ${param_idx}")
            params.append(status_filter)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # Count
        param_idx += 1
        count_sql = f"SELECT COUNT(*) FROM tenants {where_clause}"
        count_params = params[:]
        async with pool.acquire() as conn:
            count_row = await conn.fetchrow(count_sql, *count_params)
            total = count_row["count"] if count_row else 0

        # Fetch with key counts
        fetch_sql = f"""
            SELECT
                t.id, t.tenant_id, t.display_name, t.contact_email,
                t.status, t.created_at,
                COUNT(k.id) FILTER (WHERE k.revoked_at IS NULL) AS key_count,
                MAX(k.last_used_at) AS last_active
            FROM tenants t
            LEFT JOIN api_keys k ON t.tenant_id = k.tenant_id
            {where_clause}
            GROUP BY t.id
            ORDER BY t.created_at DESC
            LIMIT ${param_idx + 1} OFFSET ${param_idx + 2}
        """
        fetch_params = params[:] + [limit, offset]
        async with pool.acquire() as conn:
            rows = await conn.fetch(fetch_sql, *fetch_params)

        items = []
        for r in rows:
            items.append({
                "id": str(r["id"]),
                "tenant_id": r["tenant_id"],
                "display_name": r["display_name"],
                "contact_email": r["contact_email"],
                "status": r["status"],
                "key_count": r["key_count"] or 0,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "last_active": r["last_active"].isoformat() if r["last_active"] else None,
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
        logger.error("list_tenants_error error=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to list tenants")


@router.get("/api/admin/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Get tenant detail including API keys and recent pipeline activity."""
    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            # Tenant info
            tenant = await conn.fetchrow(
                """
                SELECT id, tenant_id, display_name, contact_email,
                       status, created_at
                FROM tenants
                WHERE tenant_id = $1
                """,
                tenant_id,
            )

            if tenant is None:
                raise HTTPException(status_code=404, detail="Tenant not found")

            # API keys
            key_rows = await conn.fetch(
                """
                SELECT id, key_hash, description, created_at, expires_at,
                       revoked_at, last_used_at
                FROM api_keys
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                """,
                tenant_id,
            )

            keys = []
            for k in key_rows:
                key_id = str(k["id"])
                key_hash = k["key_hash"]
                expires_at = (
                    _as_utc_datetime(k["expires_at"])
                    if k["expires_at"]
                    else None
                )
                status = "active"
                if k["revoked_at"]:
                    status = "revoked"
                elif expires_at and expires_at < datetime.now(UTC):
                    status = "expired"
                keys.append({
                    "id": key_id,
                    "key_preview": key_hash[:12] + "..." if key_hash else "unknown",
                    "label": k["description"] or "",
                    "status": status,
                    "created_at": k["created_at"].isoformat() if k["created_at"] else None,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                    "revoked_at": k["revoked_at"].isoformat() if k["revoked_at"] else None,
                    "last_used_at": k["last_used_at"].isoformat() if k["last_used_at"] else None,
                })

            # Recent pipeline runs from pipeline_states
            recent_runs = []
            try:
                run_rows = await conn.fetch(
                    """
                    SELECT label, config, created_at
                    FROM pipeline_states
                    WHERE config->>'tenant_id' = $1
                       OR label ILIKE $2
                    ORDER BY created_at DESC
                    LIMIT 20
                    """,
                    tenant_id,
                    f"%{tenant_id}%",
                )
                for r in run_rows:
                    config = r["config"] or {}
                    recent_runs.append({
                        "label": r["label"],
                        "scenario": config.get("scenario", "unknown") if isinstance(config, dict) else "unknown",
                        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                    })
            except Exception as exc:
                logger.warning(
                    "admin tenant recent runs query failed tenant_id=%s error=%s",
                    tenant_id,
                    str(exc)[:200],
                )

            return {
                "id": str(tenant["id"]),
                "tenant_id": tenant["tenant_id"],
                "display_name": tenant["display_name"],
                "contact_email": tenant["contact_email"],
                "status": tenant["status"],
                "created_at": tenant["created_at"].isoformat() if tenant["created_at"] else None,
                "keys": keys,
                "recent_runs": recent_runs,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("get_tenant_error tenant_id=%s error=%s", tenant_id, str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to get tenant")


@router.put("/api/admin/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str,
    request: Request,
    admin_id: str = Depends(verify_admin_session),
    _csrf: None = Depends(verify_csrf_token),
) -> dict[str, Any]:
    """Update tenant info or enable/disable. Disabling cascades to revoke all API keys."""
    body = await request.json()
    new_status = body.get("status")

    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            # Verify tenant exists
            existing = await conn.fetchrow(
                "SELECT id, tenant_id FROM tenants WHERE tenant_id = $1",
                tenant_id,
            )
            if existing is None:
                raise HTTPException(status_code=404, detail="Tenant not found")

            updates = []
            update_params: list[Any] = []
            param_idx = 0

            if "display_name" in body:
                param_idx += 1
                updates.append(f"display_name = ${param_idx}")
                update_params.append(body["display_name"])

            if "contact_email" in body:
                param_idx += 1
                updates.append(f"contact_email = ${param_idx}")
                update_params.append(body["contact_email"])

            if new_status and new_status in ("active", "disabled"):
                param_idx += 1
                updates.append(f"status = ${param_idx}")
                update_params.append(new_status)

            if updates:
                param_idx += 1
                update_params.append(tenant_id)
                await conn.execute(
                    f"UPDATE tenants SET {', '.join(updates)} WHERE tenant_id = ${param_idx}",
                    *update_params,
                )

            # Cascade revoke if disabling
            if new_status == "disabled":
                await conn.execute(
                    """
                    UPDATE api_keys
                    SET revoked_at = NOW()
                    WHERE tenant_id = $1 AND revoked_at IS NULL
                    """,
                    tenant_id,
                )
                logger.info(
                    "tenant_disabled_cascade tenant_id=%s admin_id=%s",
                    tenant_id,
                    admin_id,
                )

            # Fetch updated record
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, display_name, contact_email,
                       status, created_at
                FROM tenants WHERE tenant_id = $1
                """,
                tenant_id,
            )

            return {
                "id": str(row["id"]),
                "tenant_id": row["tenant_id"],
                "display_name": row["display_name"],
                "contact_email": row["contact_email"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("update_tenant_error tenant_id=%s error=%s", tenant_id, str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to update tenant")


@router.post("/api/admin/tenants/{tenant_id}/keys")
async def create_api_key(
    tenant_id: str,
    request: Request,
    admin_id: str = Depends(verify_admin_session),
    _csrf: None = Depends(verify_csrf_token),
) -> dict[str, Any]:
    """Create a new API key for a tenant. Returns the plaintext key EXACTLY ONCE."""
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="request body must be an object")
    raw_label = body.get("label") or body.get("description") or ""
    if not isinstance(raw_label, str):
        raise HTTPException(status_code=422, detail="label must be a string")
    label = raw_label.strip()
    if len(label) > 200:
        raise HTTPException(status_code=422, detail="label must be at most 200 characters")
    expires_at = _parse_api_key_expiry(body.get("expires_at"))
    database_expires_at = expires_at.replace(tzinfo=None)

    # Verify tenant exists and is active
    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            tenant = await conn.fetchrow(
                "SELECT tenant_id, status FROM tenants WHERE tenant_id = $1",
                tenant_id,
            )
            if tenant is None:
                raise HTTPException(status_code=404, detail="Tenant not found")
            if tenant["status"] != "active":
                raise HTTPException(
                    status_code=400, detail="Cannot create keys for a disabled tenant"
                )

            # Generate key
            raw_key = secrets.token_urlsafe(32)
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

            row = await conn.fetchrow(
                """
                INSERT INTO api_keys (
                    tenant_id, key_hash, description, permissions, expires_at
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, created_at, expires_at
                """,
                tenant_id,
                key_hash,
                label,
                '["all"]',
                database_expires_at,
            )

            logger.info(
                "api_key_created tenant_id=%s key_id=%s admin_id=%s",
                tenant_id,
                str(row["id"]),
                admin_id,
            )

            stored_expires_at = (
                _as_utc_datetime(row["expires_at"])
                if row["expires_at"]
                else None
            )
            return {
                "id": str(row["id"]),
                "tenant_id": tenant_id,
                "api_key": raw_key,  # PLAINTEXT — only returned once
                "label": label,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "expires_at": (
                    stored_expires_at.isoformat() if stored_expires_at else None
                ),
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("create_api_key_error tenant_id=%s error=%s", tenant_id, str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to create API key")


@router.post("/api/admin/tenants/{tenant_id}/keys/{key_id}/revoke")
async def revoke_api_key(
    tenant_id: str,
    key_id: str,
    admin_id: str = Depends(verify_admin_session),
    _csrf: None = Depends(verify_csrf_token),
) -> dict[str, Any]:
    """Revoke an API key."""
    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE api_keys
                SET revoked_at = NOW()
                WHERE id = $1 AND tenant_id = $2 AND revoked_at IS NULL
                """,
                key_id,
                tenant_id,
            )

            # Check if any row was actually updated
            tag = result.split()[-1] if result else "0"
            if tag == "0":
                raise HTTPException(
                    status_code=404, detail="Key not found or already revoked"
                )

            logger.info(
                "api_key_revoked tenant_id=%s key_id=%s admin_id=%s",
                tenant_id,
                key_id,
                admin_id,
            )

            return {
                "success": True,
                "key_id": key_id,
                "revoked_at": datetime.now(UTC).isoformat(),
            }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "revoke_api_key_error tenant_id=%s key_id=%s error=%s",
            tenant_id,
            key_id,
            str(exc)[:200],
        )
        raise HTTPException(status_code=500, detail="Failed to revoke API key")


# ═══════════════════════════════════════════════════════════════════
# Dashboard
# ═══════════════════════════════════════════════════════════════════
