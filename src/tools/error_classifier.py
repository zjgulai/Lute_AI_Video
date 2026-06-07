"""Error classifier — maps raw exceptions to structured PipelineError instances.

Usage:
    try:
        result = await llm.ainvoke(...)
    except Exception as e:
        error = classify_error(e, context="ainvoke")
        raise PipelineErrorWrapper(error) from e

Thread-safe. No external dependencies beyond project models.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from src.models import ErrorCode, PipelineError

logger = structlog.get_logger(__name__)


def classify_error(
    exc: Exception,
    context: str = "",
    node: str | None = None,
    extra: dict[str, Any] | None = None,
) -> PipelineError:
    """Classify any exception into a structured PipelineError.

    Uses heuristic chains:
    1. Exact type match (asyncio.TimeoutError, httpx.TimeoutException)
    2. Message content match ("API key", "api_key", "timeout")
    3. Fallback to UNKNOWN_NODE_ERROR

    Args:
        exc: The raw exception to classify.
        context: Human-readable context hint (e.g. "LLM ainvoke", "DALL-E generate").
        node: Name of the node where the error occurred.
        extra: Additional structured detail to include.

    Returns:
        A PipelineError with best-guess ErrorCode.
    """
    exc_type = type(exc).__name__
    exc_msg = str(exc).lower()
    extra = dict(extra or {})
    extra.setdefault("exc_type", exc_type)
    extra.setdefault("context", context)

    # ── Moderation / policy rejection classification ──
    if (
        "content_moderation" in exc_msg
        or "content_violation" in exc_msg
        or "safety_block" in exc_msg
    ):
        return _make(
            ErrorCode.CONTENT_MODERATION_REJECTED,
            exc,
            context,
            node,
            {**extra, "detector": "content_moderation_rules"},
        )

    # ── Timeout-based classification ──
    if isinstance(exc, asyncio.TimeoutError):
        return _make(ErrorCode.INPUT_TIMEOUT, exc, context, node, extra)

    if isinstance(exc, httpx.TimeoutException):
        _http_hint = _detect_http_client(exc_msg)
        if _http_hint:
            code_map = {"llm": ErrorCode.LLM_TIMEOUT, "dalle": ErrorCode.DALLE_TIMEOUT, "elevenlabs": ErrorCode.ELEVENLABS_TIMEOUT}
            return _make(code_map.get(_http_hint, ErrorCode.INPUT_TIMEOUT), exc, context, node, extra)
        if "llm" in exc_msg or "anthropic" in exc_msg or "openai" in exc_msg:
            return _make(ErrorCode.LLM_TIMEOUT, exc, context, node, extra)
        if "dalle" in exc_msg or "generation" in exc_msg:
            return _make(ErrorCode.DALLE_TIMEOUT, exc, context, node, extra)
        if "eleven" in exc_msg or "tts" in exc_msg or "synthesis" in exc_msg:
            return _make(ErrorCode.ELEVENLABS_TIMEOUT, exc, context, node, extra)
        return _make(ErrorCode.INPUT_TIMEOUT, exc, context, node, extra)

    # ── HTTP errors → API errors ──
    if isinstance(exc, httpx.HTTPStatusError):
        status = extra.get("status_code", 0) or getattr(exc, "response", None) and exc.response.status_code or 0
        if context.startswith("llm") or "llm" in context:
            return _make(ErrorCode.LLM_API_ERROR, exc, context, node, {**extra, "status_code": status})
        if context.startswith("dalle") or "dalle" in context:
            return _make(ErrorCode.DALLE_API_ERROR, exc, context, node, {**extra, "status_code": status})
        if context.startswith("elevenlabs") or "eleven" in context:
            return _make(ErrorCode.ELEVENLABS_API_ERROR, exc, context, node, {**extra, "status_code": status})

    # ── Message-based classification ──
    if "api_key" in exc_msg or "api key" in exc_msg or "apikey" in exc_msg:
        return _make(ErrorCode.API_KEY_MISSING, exc, context, node, extra)

    if "not found" in exc_msg and ("asset" in context or "shot" in context or "candidate" in context):
        return _make(ErrorCode.ASSET_NOT_FOUND, exc, context, node, extra)

    if "postgres" in exc_msg or "connection refused" in exc_msg and "db" in context:
        return _make(ErrorCode.POSTGRES_UNAVAILABLE, exc, context, node, extra)

    if "msgpack" in exc_msg or "serialize" in exc_msg or "deserializ" in exc_msg:
        return _make(ErrorCode.MSGPACK_SERIALIZE, exc, context, node, extra)

    if "webhook" in context:
        return _make(ErrorCode.WEBHOOK_FAILED, exc, context, node, extra)

    # ── Fallback ──
    return _make(ErrorCode.UNKNOWN_NODE_ERROR, exc, context, node, extra)


def make_blocked_error(
    reason: str,
    node: str | None = None,
    code: ErrorCode = ErrorCode.AUDIT_BLOCKED,
) -> PipelineError:
    """Create a structured pipeline-blocked error (audit or compliance).

    Intended for use in audit/compliance nodes that decide to BLOCK the pipeline,
    not for exception handlers.
    """
    return PipelineError(
        code=code,
        message=reason,
        node=node,
        recoverable=False,
        detail={"block_reason": reason},
    )


def _make(
    code: ErrorCode,
    exc: Exception,
    context: str,
    node: str | None,
    extra: dict[str, Any],
) -> PipelineError:
    """Internal factory method."""
    _recoverable = _is_recoverable(code)
    detail = {"context": context, "exc_type": type(exc).__name__, "exc_msg": str(exc)[:200]}
    if extra:
        detail.update(extra)

    return PipelineError(
        code=code,
        message=str(exc)[:500] or f"{code.value} in {context}",
        node=node,
        recoverable=_recoverable,
        detail=detail,
    )


def _is_recoverable(code: ErrorCode) -> bool:
    """Determine if an error is recoverable (can be retried)."""
    recoverable = {
        ErrorCode.INPUT_TIMEOUT: True,
        ErrorCode.LLM_TIMEOUT: True,
        ErrorCode.DALLE_TIMEOUT: True,
        ErrorCode.ELEVENLABS_TIMEOUT: True,
        ErrorCode.LLM_API_ERROR: True,
        ErrorCode.DALLE_API_ERROR: True,
        ErrorCode.ELEVENLABS_API_ERROR: True,
        ErrorCode.WEBHOOK_FAILED: True,
        ErrorCode.POSTGRES_UNAVAILABLE: True,
        ErrorCode.ASSET_NOT_FOUND: True,
        ErrorCode.ASSET_LIBRARY_UNAVAILABLE: True,
        ErrorCode.MSGPACK_SERIALIZE: True,
        ErrorCode.CONTENT_MODERATION_REJECTED: False,
    }
    return recoverable.get(code, False)


def _detect_http_client(msg: str) -> str | None:
    """Try to infer which client triggered the HTTP error from message context."""
    if "openai" in msg or "gpt" in msg or "o1" in msg:
        return "llm"
    if "dalle" in msg or "image" in msg:
        return "dalle"
    if "eleven" in msg:
        return "elevenlabs"
    if "claude" in msg or "anthropic" in msg:
        return "llm"
    return None
