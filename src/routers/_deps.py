"""Shared dependencies for all routers (P1-11).

Extracted from api.py to avoid duplication across domain routers.
"""

import contextvars
import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

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


class ApiKeyType(StrEnum):
    TENANT = "tenant"
    TEST_BUNDLE = "test_bundle"
    ENV_FALLBACK = "env_fallback"


@dataclass(frozen=True)
class AuthContext:
    """Request auth context resolved from API key credentials."""

    tenant_id: str
    permissions: frozenset[str]
    key_type: ApiKeyType
    key_id: str | None = None

    def has_permission(self, permission: str) -> bool:
        return "all" in self.permissions or permission in self.permissions


_auth_context_var: contextvars.ContextVar[AuthContext | None] = contextvars.ContextVar(
    "auth_context", default=None
)


def get_auth_context() -> AuthContext | None:
    """Return auth context bound to the current request."""
    return _auth_context_var.get()


def _bind_auth_context(ctx: AuthContext) -> None:
    set_tenant_id(ctx.tenant_id)
    _auth_context_var.set(ctx)


def _normalize_permissions(raw: Any) -> frozenset[str]:
    if raw is None:
        return frozenset({"all"})
    if isinstance(raw, str):
        try:
            import json

            parsed = json.loads(raw)
        except Exception:
            parsed = [raw]
        raw = parsed
    if isinstance(raw, list):
        cleaned = {str(p).strip() for p in raw if str(p).strip()}
        return frozenset(cleaned or {"all"})
    return frozenset({"all"})


def _as_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


API_KEY = os.getenv("API_KEY", "")
TEST_BUNDLE_KEY = os.getenv("TEST_BUNDLE_KEY", "")
ALLOW_TEST_BUNDLE_KEY = os.getenv("ALLOW_TEST_BUNDLE_KEY", "").lower() in ("1", "true", "yes")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
if not API_KEY and not TEST_BUNDLE_KEY:
    logging.error("SECURITY: API_KEY environment variable is not set and no TEST_BUNDLE_KEY configured.")
    raise RuntimeError(
        "API_KEY or TEST_BUNDLE_KEY environment variable is required. "
        "Set API_KEY before starting the server in production, "
        "or TEST_BUNDLE_KEY for local development."
    )

async def verify_api_key(request: Request, x_api_key: str | None = Header(None)) -> AuthContext:
    """Verify API key and resolve request auth context.

    Resolution order:
    1. Query api_keys table (PG) by key_hash → tenant_id + permissions
    2. Optional TEST_BUNDLE_KEY for local/test bundled provider access
    3. Env var API_KEY fallback → tenant_id = "default"
    4. Reject if neither matches

    The resolved tenant_id is stored in a contextvar so downstream code
    (cost tracking, audit logs) can access it without threading the value
    through every call signature.
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    auth_ctx: AuthContext | None = None
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
                    """
                    SELECT id, tenant_id, permissions, revoked_at, expires_at
                    FROM api_keys
                    WHERE key_hash = $1
                    """,
                    key_hash,
                )
                if row and not row["revoked_at"]:
                    expires = row["expires_at"]
                    if expires is None or _as_utc_datetime(expires) > datetime.now(UTC):
                        auth_ctx = AuthContext(
                            tenant_id=row["tenant_id"],
                            key_id=str(row["id"]),
                            permissions=_normalize_permissions(row["permissions"]),
                            key_type=ApiKeyType.TENANT,
                        )
                        await conn.execute(
                            "UPDATE api_keys SET last_used_at = NOW() WHERE key_hash = $1",
                            key_hash,
                        )
    except Exception as exc:
        logging.getLogger("api.auth").error(
            "api_key_db_lookup_failed env=%s error=%s", ENVIRONMENT, str(exc)[:200]
        )
        if ENVIRONMENT == "production":
            raise HTTPException(status_code=503, detail="Authentication backend unavailable")
        # Development: PG lookup failed, but do NOT auto-approve.
        # Auth must still pass via TEST_BUNDLE_KEY or env API_KEY below.

    # 2. Explicit test bundle key. This is a developer/test convenience, not a public demo key.
    if auth_ctx is None and TEST_BUNDLE_KEY and x_api_key == TEST_BUNDLE_KEY:
        if ENVIRONMENT == "production" and not ALLOW_TEST_BUNDLE_KEY:
            raise HTTPException(status_code=401, detail="Invalid or expired API key")
        auth_ctx = AuthContext(
            tenant_id="test-bundle",
            key_id="test-bundle",
            permissions=frozenset({"all"}),
            key_type=ApiKeyType.TEST_BUNDLE,
        )

    # 3. Legacy env var fallback. Production may still use a private env key,
    # but the public test bundle key must be explicitly enabled.
    if auth_ctx is None and x_api_key == API_KEY:
        is_test_bundle_fallback = API_KEY == TEST_BUNDLE_KEY or API_KEY == "ai_video_demo_2026"
        if ENVIRONMENT == "production" and is_test_bundle_fallback:
            if not ALLOW_TEST_BUNDLE_KEY:
                raise HTTPException(status_code=401, detail="Invalid or expired API key")
            key_type = ApiKeyType.TEST_BUNDLE
        else:
            key_type = ApiKeyType.ENV_FALLBACK
        auth_ctx = AuthContext(
            tenant_id="default",
            key_id="env-api-key",
            permissions=frozenset({"all"}),
            key_type=key_type,
        )

    # 3. Reject if no match
    if auth_ctx is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    _bind_auth_context(auth_ctx)
    return auth_ctx


def require_permission(permission: str):
    """FastAPI dependency factory for permission-gated creative API endpoints."""

    async def _dependency(ctx: AuthContext = Depends(verify_api_key)) -> AuthContext:
        if not ctx.has_permission(permission):
            raise HTTPException(status_code=403, detail="Insufficient permission")
        return ctx

    return _dependency


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
