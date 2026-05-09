"""Admin panel shared dependencies.

Provides verify_admin_session — the admin equivalent of verify_api_key.
Admin auth uses session cookies (email + password login), completely
independent of the tenant API key auth layer.

Two layers of auth, zero crossover:
  Creative API:  x-api-key header → verify_api_key → tenant_id
  Admin API:     admin_session cookie → verify_admin_session → admin_id
"""

import contextvars
import hashlib
import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import Cookie, HTTPException, Request

logger = logging.getLogger(__name__)

# ── Admin identity context ──
_admin_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "admin_id", default=None
)


def set_admin_id(admin_id: str | None) -> None:
    """Bind an admin_id to the current request context."""
    _admin_id_var.set(admin_id)


def get_admin_id() -> str | None:
    """Return the admin_id bound to the current request context."""
    return _admin_id_var.get()


# ── In-memory login rate limiter ──
_login_attempts: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 60


def _check_login_rate_limit(client_ip: str) -> None:
    """Raise 429 if the IP has exceeded the login rate limit."""
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SECONDS

    # Prune old entries for this IP
    attempts = _login_attempts.get(client_ip, [])
    attempts = [t for t in attempts if t > window_start]
    _login_attempts[client_ip] = attempts

    # Periodic global prune to prevent unbounded memory growth
    if len(_login_attempts) > 1000:
        stale_ips = [
            ip for ip, ts_list in _login_attempts.items()
            if not any(t > window_start for t in ts_list)
        ]
        for ip in stale_ips:
            del _login_attempts[ip]

    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Please try again later.",
        )


def _record_login_attempt(client_ip: str) -> None:
    """Record a login attempt for the given IP."""
    now = time.time()
    if client_ip not in _login_attempts:
        _login_attempts[client_ip] = []
    _login_attempts[client_ip].append(now)


# ── Session validation ──


async def verify_admin_session(
    request: Request,
    admin_session: str | None = Cookie(None),
) -> str:
    """Validate the admin session cookie and return the admin_id.

    Resolution order:
    1. Read admin_session cookie from request
    2. SHA-256(cookie value) → token_hash
    3. Query admin_sessions table for valid, non-expired token
    4. On success → store admin_id in contextvar, return admin_id
    5. On failure → 401

    This follows the same dependency-injection pattern as verify_api_key
    in src/routers/_deps.py.
    """
    if not admin_session:
        raise HTTPException(status_code=401, detail="Missing admin session")

    token_hash = hashlib.sha256(admin_session.encode()).hexdigest()

    try:
        from src.storage.db import get_pool, is_pg_available

        if not is_pg_available():
            raise HTTPException(
                status_code=503, detail="Database unavailable"
            )

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT admin_id, expires_at
                FROM admin_sessions
                WHERE token_hash = $1
                """,
                token_hash,
            )

        if row is None:
            raise HTTPException(
                status_code=401, detail="Invalid or expired session"
            )

        expires_at: datetime = row["expires_at"]
        if expires_at < datetime.now(UTC):
            raise HTTPException(
                status_code=401, detail="Invalid or expired session"
            )

        admin_id: str = str(row["admin_id"])
        set_admin_id(admin_id)
        return admin_id

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("admin_session_validation_failed error=%s", str(exc)[:200])
        raise HTTPException(
            status_code=500, detail="Session validation failed"
        )


# ── Helpers ──


def _safe_error(exc: Exception, is_dev: bool = False) -> str:
    """Return a generic error message unless in dev mode."""
    if is_dev:
        return str(exc)
    import uuid as _uuid

    trace = str(_uuid.uuid4())[:8]
    logger.error("admin_internal_error trace_id=%s error=%s", trace, str(exc)[:200])
    return f"Internal server error [trace: {trace}]"


def _serialize(obj: Any) -> Any:
    """Recursively serialize objects to JSON-safe dicts."""
    from pydantic import BaseModel as PydanticBase

    if isinstance(obj, PydanticBase):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj
