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

def verify_api_key(request: Request, x_api_key: str | None = Header(None)):
    """Verify API key.

    API_KEY 是按用户分发的全权限凭证(每个开通用户拿一组独立 key)。
    没有"低权限只读"概念 —— 模型矩阵稳定,key 才是按租户隔离的依据。
    早期 P0-11 给 `ai_video_demo_2026` 做了 publish/upload 拦截,实际生产
    `API_KEY` 就是这串字符,拦截把 distribution/publish + 资产上传链路堵死,
    与"端到端验证"目标冲突,已移除。
    """
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


def _safe_error(exc: Exception, is_dev: bool = False) -> str:
    """Return a generic error message unless in dev mode. Includes trace_id for production debugging."""
    if is_dev:
        return str(exc)
    import uuid as _uuid
    _trace = str(_uuid.uuid4())[:8]
    logging.getLogger("api.error").error("internal_error trace_id=%s error=%s", _trace, str(exc)[:200])
    return f"Internal server error [trace: {_trace}]"


def _classified_error(exc: Exception, is_dev: bool = False) -> dict:
    """Return structured error with code, message, recoverable flag, and trace_id.

    T1.4: Uses error_classifier to map exceptions to structured PipelineError.
    """
    from src.tools.error_classifier import classify_error
    import uuid as _uuid
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
