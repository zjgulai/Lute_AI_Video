"""Retry with exponential backoff for external API calls.

Usage:
    result = await retry_with_backoff(
        callable_fn,
        max_retries=3,
        base_delay=1.0,
    )

Transient failures (429, 5xx, connection errors, timeouts) trigger retry.
Non-transient failures (4xx except 429) raise immediately.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import structlog

T = TypeVar("T")

logger = structlog.get_logger()

# Default: 3 retries with 1s → 2s → 4s exponential backoff
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 30.0  # seconds cap

# HTTP status codes that should trigger a retry
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# HTTP status codes that should NEVER trigger a retry (client errors)
NON_RETRYABLE_STATUSES = {400, 401, 403, 404, 405, 406, 409, 410, 422}

# Connection-related exception types that are always retryable
_RETRYABLE_EXCEPTION_TYPES = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
    OSError,
)


class MaxRetriesExceededError(Exception):
    """Raised when all retry attempts have been exhausted."""


def _extract_status_code(exception: Exception) -> int | None:
    """Extract HTTP status code from exception via type chain."""
    # httpx / requests / aiohttp style: exception.response.status_code
    response = getattr(exception, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code

    # Some clients put status_code directly on the exception
    code = getattr(exception, "status_code", None)
    if isinstance(code, int):
        return code

    # Fallback: grep status code from error message (less reliable)
    return None


def is_retryable(exception: Exception) -> bool:
    """Determine if an exception represents a transient failure.

    Priority: type-based check → status_code extraction → string fallback.
    Retryable: connection/timeout errors, 429, 5xx.
    Non-retryable: 4xx (except 429), auth errors, invalid requests.
    """
    # 1. Type-based check: connection / timeout / OS-level errors are always retryable
    if isinstance(exception, _RETRYABLE_EXCEPTION_TYPES):
        return True

    # 2. Status-code extraction from exception attributes (httpx/requests/aiohttp)
    status_code = _extract_status_code(exception)
    if status_code is not None:
        if status_code in RETRYABLE_STATUSES:
            return True
        if status_code in NON_RETRYABLE_STATUSES:
            return False
        # Unknown status: fall through to string-based heuristics

    # 3. String-based fallback (legacy, less reliable but catches edge cases)
    msg = str(exception).lower()

    # Blacklist first: explicit non-retryable patterns
    if any(x in msg for x in [
        "invalid api key", "authentication", "unauthorized",
        "forbidden", "not found", "bad request",
    ]):
        return False

    # Connection / timeout errors (string fallback)
    if any(x in msg for x in [
        "connection", "timeout", "timed out", "eof", "reset",
        "dns", "unreachable", "refused", "broken pipe",
        "name or service not known", "no route to host",
    ]):
        return True

    # Rate limiting
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return True

    # Server errors
    if any(x in msg for x in ["500", "502", "503", "504", "server error"]):
        return True

    # Transient network / SSL errors
    if any(x in msg for x in ["ssl", "certificate verify failed", "temporary"]):
        return True

    return False


async def retry_with_backoff(
    fn: Callable[..., Awaitable[T]],
    *args,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs,
) -> T:
    """Call an async function with exponential backoff retry.

    Retries on transient failures (connection errors, 429, 5xx, timeouts).
    Non-retryable errors are raised immediately.
    Exhausting retries raises MaxRetriesExceededError.

    Args:
        fn: Async callable to invoke.
        max_retries: Maximum number of retry attempts (default: 3).
        base_delay: Initial delay in seconds (default: 1.0).
        max_delay: Maximum delay cap in seconds (default: 30.0).
        *args, **kwargs: Passed through to fn.

    Returns:
        The result of fn(*args, **kwargs).

    Raises:
        MaxRetriesExceededError: All retry attempts failed.
    """
    from src.pipeline.generation_policy import get_effective_provider_max_retries

    max_retries = get_effective_provider_max_retries(max_retries)
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):  # +1 for initial attempt
        try:
            return await fn(*args, **kwargs)
        except Exception as e:
            last_exc = e

            if not is_retryable(e):
                raise  # Non-retryable — re-raise immediately

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                jitter = delay * 0.1  # Small jitter: delay ± 10%
                import random
                actual_delay = delay + random.uniform(-jitter, jitter)
                logger.warning(
                    "retry: transient failure",
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    delay=f"{actual_delay:.1f}s",
                    error=str(e)[:120],
                )
                await asyncio.sleep(actual_delay)

    # All attempts exhausted
    logger.error(
        "retry: all attempts exhausted",
        max_retries=max_retries,
        error=str(last_exc)[:200],
    )
    raise MaxRetriesExceededError(
        f"All {max_retries + 1} attempts failed. Last error: {last_exc}"
    ) from last_exc
