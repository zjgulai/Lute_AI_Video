"""Admin authentication endpoints."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from src.routers._admin_deps import (
    CSRF_COOKIE_NAME,
    _check_login_rate_limit,
    _record_login_attempt,
    generate_csrf_token,
    verify_admin_session,
    verify_csrf_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin"])

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
    expires_at = datetime.now(UTC) + timedelta(hours=24)

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

    csrf_token = generate_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
        max_age=86400,
    )

    from src.storage.audit_logger import audit_log
    await audit_log(
        actor_type="admin",
        actor_id=admin_id,
        action="admin.login.success",
        resource_type="admin",
        resource_id=admin_id,
        payload={"email": admin_email},
        client_ip=client_ip,
        trace_id=request.headers.get("x-trace-id"),
    )

    return {
        "admin_id": admin_id,
        "email": admin_email,
        "csrf_token": csrf_token,
    }


@router.post("/api/admin/auth/logout")
async def admin_logout(
    request: Request,
    response: Response,
    admin_id: str = Depends(verify_admin_session),
    _csrf: None = Depends(verify_csrf_token),
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
        except Exception as exc:
            logger.warning(
                "admin logout session cleanup failed: %s",
                str(exc)[:200],
            )

    response.delete_cookie(
        key="admin_session",
        path="/api/admin",
    )
    response.delete_cookie(
        key=CSRF_COOKIE_NAME,
        path="/",
    )
    from src.storage.audit_logger import audit_log
    await audit_log(
        actor_type="admin",
        actor_id=admin_id,
        action="admin.logout",
        resource_type="admin",
        resource_id=admin_id,
        client_ip=request.client.host if request.client else None,
        trace_id=request.headers.get("x-trace-id"),
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
