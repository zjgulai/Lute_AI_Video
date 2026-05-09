"""Shared dependencies for all routers (P1-11).

Extracted from api.py to avoid duplication across domain routers.
"""

import contextvars
import hashlib
import logging
import os
import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import Header, HTTPException, Request

# Tenant ID context for request-scoped isolation (P2-8)
_tenant_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "tenant_id", default=None
)


def set_tenant_id(tenant_id: str | None) -> None:
    """Bind a tenant_id to the current request context."""
    _tenant_id_var.set(tenant_id)


def get_tenant_id() -> str | None:
    """Return the tenant_id bound to the current request context."""
    return _tenant_id_var.get()

# ── API Key management ──
API_KEY = os.getenv("API_KEY", "")
if not API_KEY:
    logging.warning("SECURITY: API_KEY environment variable is not set. Generating a temporary key for this session.")
    API_KEY = secrets.token_urlsafe(32)
    logging.warning("SECURITY: Temporary API_KEY = %s  (set this in your .env for persistence)", API_KEY)

async def verify_api_key(request: Request, x_api_key: str | None = Header(None)):
    """Verify API key and resolve tenant_id (P2-8).

    Resolution order:
    1. Query api_keys table (PG) by key_hash → tenant_id
    2. Fallback to env var API_KEY → tenant_id = "default"
    3. Reject if neither matches

    The resolved tenant_id is stored in a contextvar so downstream code
    (cost tracking, audit logs) can access it without threading the value
    through every call signature.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    tenant_id = None
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    # 1. Try database lookup first
    try:
        from src.storage.db import is_pg_available
        if is_pg_available():
            from src.storage.db import get_pool
            pool = await get_pool()
            assert pool is not None
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT tenant_id, revoked_at, expires_at FROM api_keys WHERE key_hash = $1",
                    key_hash,
                )
                if row and not row["revoked_at"]:
                    expires = row["expires_at"]
                    if expires is None or expires > datetime.now(UTC):
                        tenant_id = row["tenant_id"]
                        await conn.execute(
                            "UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = $1",
                            key_hash,
                        )
    except Exception:
        pass  # PG unavailable or query failed — fall through to env fallback

    # 2. Fallback to env var
    if tenant_id is None and x_api_key == API_KEY:
        tenant_id = "default"

    # 3. Reject if no match
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    set_tenant_id(tenant_id)
    return tenant_id


def _safe_error(exc: Exception, is_dev: bool = False) -> str:
    """Return a generic error message unless in dev mode. Includes trace_id for production debugging."""
    if is_dev:
        return str(exc)
    import uuid as _uuid
    _trace = str(_uuid.uuid4())[:8]
    logging.getLogger("api.error").error("internal_error trace_id=%s error=%s", _trace, str(exc)[:200])
    return f"Internal server error [trace: {_trace}]"


def _classified_error(exc: Exception, is_dev: bool = False) -> dict[str, Any]:
    """Return structured error with code, message, recoverable flag, and trace_id.

    T1.4: Uses error_classifier to map exceptions to structured PipelineError.
    """
    import uuid as _uuid

    from src.tools.error_classifier import classify_error
    _trace = str(_uuid.uuid4())[:8]
    logging.getLogger("api.error").error("internal_error trace_id=%s error=%s", _trace, str(exc)[:200])
    structured = classify_error(exc, context="api")
    return {
        "error_code": structured.code.value,
        "message": str(exc) if is_dev else structured.message,
        "recoverable": structured.recoverable,
        "trace": _trace,
    }


def _serialize(obj: Any) -> Any:
    """Recursively serialize Pydantic models to JSON-safe dicts."""
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


def _inject_api_keys(api_keys: dict[str, str]) -> None:
    """Store API keys in request context (not process-wide os.environ).

    Using contextvars ensures concurrent requests do not contaminate each
    other's keys. The LLM client reads from request context first, then
    falls back to os.environ — no global client cache clearing needed.
    """
    if not api_keys:
        return

    key_map = {
        "openai": "OPENAI_API_KEY",
        "OPENAI_API_KEY": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "ELEVENLABS_API_KEY": "ELEVENLABS_API_KEY",
        "poyo": "POYO_API_KEY",
        "POYO_API_KEY": "POYO_API_KEY",
        "seedance": "SEEDANCE_API_KEY",
        "SEEDANCE_API_KEY": "SEEDANCE_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "SILICONFLOW_API_KEY": "SILICONFLOW_API_KEY",
        "supabase_url": "SUPABASE_URL",
        "SUPABASE_URL": "SUPABASE_URL",
        "supabase_key": "SUPABASE_SERVICE_KEY",
        "SUPABASE_SERVICE_KEY": "SUPABASE_SERVICE_KEY",
    }
    normalized: dict[str, str] = {}
    for key_or_alias, value in api_keys.items():
        if value and value.strip():
            env_key = key_map.get(key_or_alias, key_or_alias)
            normalized[env_key] = value.strip()

    # Store in request context — isolated per asyncio task
    from src.tools.llm_client import set_request_api_keys
    set_request_api_keys(normalized)
