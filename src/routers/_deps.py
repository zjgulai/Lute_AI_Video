"""Shared dependencies for all routers (P1-11).

Extracted from api.py to avoid duplication across domain routers.
"""

import logging
import os
import secrets
from typing import Any

from fastapi import HTTPException, Header, Request

# ── API Key management ──
API_KEY = os.getenv("API_KEY", "")
if not API_KEY:
    logging.warning("SECURITY: API_KEY environment variable is not set. Generating a temporary key for this session.")
    API_KEY = secrets.token_urlsafe(32)
    logging.warning("SECURITY: Temporary API_KEY = %s  (set this in your .env for persistence)", API_KEY)

DEMO_KEY = "ai_video_demo_2026"


def verify_api_key(request: Request, x_api_key: str | None = Header(None)):
    """Verify API key and enforce demo key restrictions."""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    # P0-11: Demo key restrictions — read and generate only
    if x_api_key == DEMO_KEY:
        method = request.method
        path = request.url.path

        # Block all DELETE operations
        if method == "DELETE":
            raise HTTPException(status_code=403, detail="Demo key cannot delete resources")

        # Block publish endpoints
        if path.startswith("/distribution/publish") or path.startswith("/publish/"):
            raise HTTPException(status_code=403, detail="Demo key cannot publish")

        # Block asset uploads and brand/influencer mutations
        if path.startswith("/api/upload") or path.startswith("/api/assets/"):
            if method in ("POST", "PUT"):
                raise HTTPException(status_code=403, detail="Demo key cannot modify assets")
        if path.startswith("/brand-packages") or path.startswith("/influencers") or path.startswith("/remix-brief"):
            if method in ("POST", "PUT", "DELETE"):
                raise HTTPException(status_code=403, detail="Demo key cannot modify resources")

    return True


def _safe_error(exc: Exception, is_dev: bool = False) -> str:
    """Return a generic error message unless in dev mode. Includes trace_id for production debugging."""
    if is_dev:
        return str(exc)
    import uuid as _uuid
    _trace = str(_uuid.uuid4())[:8]
    logging.getLogger("api.error").error("internal_error trace_id=%s error=%s", _trace, str(exc)[:200])
    return f"Internal server error [trace: {_trace}]"


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
