"""Admin panel API router.

Mount point: /api/admin/* (mounted in src/api.py startup).

This router serves the admin web UI. All endpoints use session-cookie
authentication (verify_admin_session), completely separate from the
x-api-key tenant auth used by the creative API.

Endpoints by module:
  /auth/*       — Login, logout, session validation
  /dashboard/*  — Aggregated system overview
  /tenants/*    — Tenant CRUD + API key lifecycle
  /logs/*       — Persistent error log viewer
  /health/*     — Service health status + history
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

# ── Tenant ID format ──
# Lowercase alphanumeric + hyphens, 3-32 chars, no leading/trailing hyphens.
_TENANT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")

# ── Helpers ──

from src.routers._admin_deps import (  # noqa: E402
    _check_login_rate_limit,
    _record_login_attempt,
    get_admin_id,
    verify_admin_session,
)

# ═══════════════════════════════════════════════════════════════════
# Auth
# ═══════════════════════════════════════════════════════════════════


@router.post("/api/admin/auth/login")
async def admin_login(request: Request, response: Response) -> dict[str, Any]:
    """Login with email + password. Returns admin session cookie."""
    # Rate limit check
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)

    # Parse body
    try:
        body = await request.json()
    except Exception:
        _record_login_attempt(client_ip)
        raise HTTPException(status_code=400, detail="Invalid request body")

    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    if not email or not password:
        _record_login_attempt(client_ip)
        raise HTTPException(status_code=400, detail="Email and password required")

    # Query admin account
    try:
        from src.storage.db import get_pool, is_pg_available

        if not is_pg_available():
            raise HTTPException(status_code=503, detail="Database unavailable")

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, email, password_hash FROM admin_accounts WHERE email = $1",
                email,
            )
    except HTTPException:
        raise
    except Exception as exc:
        _record_login_attempt(client_ip)
        logger.error("admin_login_db_error error=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail="Authentication failed")

    # Constant-time comparison via bcrypt — same error regardless of cause
    if row is None:
        _record_login_attempt(client_ip)
        # Do a dummy hash to maintain constant-time timing
        bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=12))
        raise HTTPException(status_code=401, detail="Invalid credentials")

    stored_hash: str = row["password_hash"]
    if not bcrypt.checkpw(password.encode(), stored_hash.encode()):
        _record_login_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Generate session token
    token = secrets.token_bytes(64)
    token_plain = token.hex()
    token_hash = hashlib.sha256(token_plain.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    admin_id = str(row["id"])
    admin_email = row["email"]

    # Store session
    try:
        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO admin_sessions (admin_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                """,
                admin_id,
                token_hash,
                expires_at,
            )
            # Update last_login_at
            await conn.execute(
                "UPDATE admin_accounts SET last_login_at = NOW() WHERE id = $1",
                admin_id,
            )
    except Exception as exc:
        logger.error("admin_session_create_error error=%s", str(exc)[:200])
        raise HTTPException(status_code=500, detail="Failed to create session")

    # Set cookie
    response.set_cookie(
        key="admin_session",
        value=token_plain,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/api/admin",
        max_age=86400,  # 24 hours
    )

    return {
        "admin_id": admin_id,
        "email": admin_email,
    }


@router.post("/api/admin/auth/logout")
async def admin_logout(
    request: Request,
    response: Response,
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Logout — clear the admin session."""
    admin_session = request.cookies.get("admin_session", "")
    if admin_session:
        token_hash = hashlib.sha256(admin_session.encode()).hexdigest()
        try:
            from src.storage.db import get_pool

            pool = await get_pool()
            assert pool is not None
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM admin_sessions WHERE token_hash = $1",
                    token_hash,
                )
        except Exception:
            pass  # Best-effort cleanup

    response.delete_cookie(
        key="admin_session",
        path="/api/admin",
    )
    return {"success": True}


@router.get("/api/admin/auth/session")
async def admin_session_check(
    admin_id: str = Depends(verify_admin_session),
) -> dict[str, Any]:
    """Validate the current admin session."""
    # Fetch email for the admin
    try:
        from src.storage.db import get_pool

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT email FROM admin_accounts WHERE id = $1",
                admin_id,
            )
    except Exception:
        row = None

    return {
        "admin_id": admin_id,
        "email": row["email"] if row else "unknown",
        "authenticated": True,
    }


# ═══════════════════════════════════════════════════════════════════
# Tenant Management
# ═══════════════════════════════════════════════════════════════════


def _validate_tenant_id(tenant_id: str) -> None:
    """Validate tenant_id format, raise 422 on mismatch."""
    if not _TENANT_ID_RE.match(tenant_id):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid tenant_id format. Must be 3-32 characters, "
                "lowercase alphanumeric with optional hyphens, "
                "no leading/trailing hyphens."
            ),
        )


@router.post("/api/admin/tenants")
async def create_tenant(
    request: Request,
    admin_id: str = Depends(verify_admin_session),
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
                SELECT id, key_hash, label, created_at, expires_at,
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
                status = "revoked" if k["revoked_at"] else "active"
                if k["expires_at"] and k["expires_at"] < datetime.now(timezone.utc):
                    status = "expired"
                keys.append({
                    "id": key_id,
                    "key_preview": key_hash[:12] + "..." if key_hash else "unknown",
                    "label": k["label"] or "",
                    "status": status,
                    "created_at": k["created_at"].isoformat() if k["created_at"] else None,
                    "expires_at": k["expires_at"].isoformat() if k["expires_at"] else None,
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
            except Exception:
                pass  # pipeline_states table might not exist or query might fail

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
) -> dict[str, Any]:
    """Create a new API key for a tenant. Returns the plaintext key EXACTLY ONCE."""
    body = await request.json()
    label = (body.get("label") or "").strip()

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
                INSERT INTO api_keys (tenant_id, key_hash, description, permissions)
                VALUES ($1, $2, $3, $4)
                RETURNING id, created_at
                """,
                tenant_id,
                key_hash,
                label,
                '["all"]',
            )

            logger.info(
                "api_key_created tenant_id=%s key_id=%s admin_id=%s",
                tenant_id,
                str(row["id"]),
                admin_id,
            )

            return {
                "id": str(row["id"]),
                "tenant_id": tenant_id,
                "api_key": raw_key,  # PLAINTEXT — only returned once
                "label": label,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
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
                "revoked_at": datetime.now(timezone.utc).isoformat(),
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
            except Exception:
                pass  # pipeline_states may have different schema or be empty

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
            except Exception:
                pass

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
    except Exception:
        pass


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
    except Exception:
        pass


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
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                resp = await http_client.get(
                    "https://api.poyo.ai/v1/models",
                    headers={"Authorization": f"Bearer {__import__('os').getenv('POYO_API_KEY', '')}"},
                )
                if resp.status_code >= 500:
                    raise Exception(f"POYO returned {resp.status_code}")
        elif name == "siliconflow":
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as http_client:
                resp = await http_client.get(
                    "https://api.siliconflow.cn/v1/models",
                    headers={"Authorization": f"Bearer {__import__('os').getenv('SILICONFLOW_API_KEY', '')}"},
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
    from datetime import datetime as _dt, timezone as _tz

    services = {}
    for svc in ["postgres", "deepseek", "poyo", "siliconflow", "remotion"]:
        services[svc] = await _check_single_service(svc)

    entry = {
        "checked_at": _dt.now(_tz.utc).isoformat(),
        "services": services,
    }

    async with _health_lock:
        _health_history.append(entry)
        if len(_health_history) > 288:
            _health_history.pop(0)


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
