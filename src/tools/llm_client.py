"""Unified LLM client — routes to OpenAI or Anthropic based on config.

All public methods have timeout protection (60s default) via asyncio.timeout()
to prevent pipeline hangs on slow or dead LLM calls.

Preferred usage from async code:    await llm.invoke(...)
                                   await llm.invoke_json(...)

SSOT for per-request API keys: _request_api_keys ContextVar.
Callers (e.g. api.py) set this per-request so that concurrent pipelines do not
contaminate each other's keys via the global os.environ.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import json
import os
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import (
    ANTHROPIC_API_KEY,
    DEFAULT_LLM_PROVIDER,
    DEEPSEEK_API_BASE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    KIMI_MODEL,
    OPENAI_API_KEY,
)

# Optional LLM provider imports — only needed when API keys are configured
try:
    from langchain_openai import ChatOpenAI
    HAS_OPENAI = True
except ImportError:
    ChatOpenAI = None
    HAS_OPENAI = False

try:
    from langchain_anthropic import ChatAnthropic
    HAS_ANTHROPIC = True
except ImportError:
    ChatAnthropic = None
    HAS_ANTHROPIC = False

logger = structlog.get_logger()

# Timeout per LLM call in seconds — prevents pipeline hangs on dead connections.
# 60s lets DeepSeek finish typical 80-150 word structured outputs while keeping
# the fallback-to-raw-prompt path responsive when the upstream API is sluggish.
LLM_TIMEOUT_SECONDS = 60.0

# Per-request API keys — prevents cross-request contamination via os.environ.
# Set by api.py _inject_api_keys before pipeline execution.
_request_api_keys: contextvars.ContextVar[dict[str, str]] = contextvars.ContextVar(
    "request_api_keys", default={}
)


def set_request_api_keys(keys: dict[str, str]) -> None:
    """Set API keys for the current request context."""
    _request_api_keys.set(keys)


def get_request_api_key(env_name: str) -> str | None:
    """Get an API key from request context, falling back to os.environ."""
    request_keys = _request_api_keys.get()
    if env_name in request_keys:
        return request_keys[env_name]
    return os.environ.get(env_name)


class LLMTimeoutError(asyncio.TimeoutError):
    """Raised when an LLM call exceeds LLM_TIMEOUT_SECONDS."""


class LLMClient:
    """Multi-provider LLM client with structured output support.

    Every `ainvoke` and `ainvoke_json` call is wrapped in asyncio.timeout().
    If the LLM doesn't respond within LLM_TIMEOUT_SECONDS, LLMTimeoutError
    is raised — the caller should catch and fallback.
    """

    def __init__(self, provider: str | None = None, timeout: float = LLM_TIMEOUT_SECONDS):
        self.provider = provider or DEFAULT_LLM_PROVIDER
        self.timeout = timeout
        self._clients: dict[str, Any] = {}

    def _resolve_api_key(self, env_name: str) -> str | None:
        """Resolve API key from request context or global env."""
        return get_request_api_key(env_name)

    def is_configured(self) -> bool:
        """Return True if an API key is available for the configured provider.

        Checks the request-scoped key first (contextvars), then falls back
        to the global environment variable.
        """
        if self.provider == "anthropic":
            return bool(self._resolve_api_key("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY)
        elif self.provider == "kimi":
            return bool(self._resolve_api_key("OPENAI_API_KEY") or OPENAI_API_KEY)
        elif self.provider == "deepseek":
            return bool(self._resolve_api_key("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY)
        else:
            return bool(self._resolve_api_key("OPENAI_API_KEY") or OPENAI_API_KEY)

    def _get_client(self, model: str | None = None):
        # Build a cache key that includes the actual API key hash so that
        # concurrent requests using different keys do not share (or evict)
        # each other's client instances.
        if self.provider == "anthropic":
            key = self._resolve_api_key("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY or ""
        elif self.provider == "kimi":
            key = self._resolve_api_key("OPENAI_API_KEY") or OPENAI_API_KEY or ""
        elif self.provider == "deepseek":
            key = self._resolve_api_key("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY or ""
        else:
            key = self._resolve_api_key("OPENAI_API_KEY") or OPENAI_API_KEY or ""

        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16] if key else "default"
        cache_key = f"{self.provider}:{model}:{key_hash}"

        if cache_key not in self._clients:
            if self.provider == "anthropic":
                self._clients[cache_key] = ChatAnthropic(
                    model=model or "claude-sonnet-4-20250514",
                    api_key=self._resolve_api_key("ANTHROPIC_API_KEY") or ANTHROPIC_API_KEY,
                    temperature=0.7,
                    max_tokens=4096,
                    timeout=self.timeout,
                )
            elif self.provider == "kimi":
                # Kimi / Moonshot — OpenAI-compatible API
                from langchain_openai import ChatOpenAI
                self._clients[cache_key] = ChatOpenAI(
                    model=model or KIMI_MODEL,
                    api_key=self._resolve_api_key("OPENAI_API_KEY") or OPENAI_API_KEY,
                    base_url="https://api.moonshot.cn/v1",
                    temperature=0.7,
                    max_tokens=4096,
                    timeout=self.timeout,
                )
            elif self.provider == "deepseek":
                # DeepSeek V4 Pro — native API, OpenAI-compatible
                # Reference: https://api-docs.deepseek.com/
                from langchain_openai import ChatOpenAI
                self._clients[cache_key] = ChatOpenAI(
                    model=model or DEEPSEEK_MODEL,
                    api_key=self._resolve_api_key("DEEPSEEK_API_KEY") or DEEPSEEK_API_KEY,
                    base_url=DEEPSEEK_API_BASE,
                    temperature=0.7,
                    max_tokens=4096,
                    timeout=self.timeout,
                )
            else:
                # Default: OpenAI (or any OpenAI-compatible provider via base_url)
                from langchain_openai import ChatOpenAI
                kwargs = {
                    "model": model or "gpt-4o",
                    "api_key": self._resolve_api_key("OPENAI_API_KEY") or OPENAI_API_KEY,
                    "temperature": 0.7,
                    "max_tokens": 4096,
                    "timeout": self.timeout,
                }
                self._clients[cache_key] = ChatOpenAI(**kwargs)
        return self._clients[cache_key]

    async def ainvoke(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
    ) -> str:
        """Call LLM asynchronously with timeout and retry.

        Retries up to 3 times with exponential backoff on transient failures.
        Raises LLMTimeoutError if the call exceeds the configured timeout.
        Raises MaxRetriesExceededError if all retry attempts fail.
        """
        from src.tools.retry import retry_with_backoff

        async def _do_invoke():
            client = self._get_client(model)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
            response = await asyncio.wait_for(
                _async_invoke(client, messages),
                timeout=self.timeout,
            )
            return response.content

        try:
            result = await retry_with_backoff(_do_invoke)
            from src.tools.cost_tracker import track
            track(
                api="deepseek_reasoning" if "reasoning" in str(model).lower() else "deepseek",
                units=1,
            )
            return result
        except TimeoutError:
            logger.error("llm: invoke timed out", timeout=self.timeout)
            raise LLMTimeoutError(
                f"LLM call timed out after {self.timeout}s"
            ) from None

    async def invoke(self, *args, **kwargs) -> str:
        """Alias for ainvoke for ergonomic await."""
        return await self.ainvoke(*args, **kwargs)

    async def invoke_json(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Call LLM asynchronously and parse JSON response.

        Routes through ainvoke with timeout protection.
        """
        raw = await self.ainvoke(system_prompt, user_message, model)
        return self._parse_json(raw)

    # ── Shared helpers ──

    def _parse_json(self, raw: str) -> dict[str, Any]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON object/array from markdown text
            import re
            # Look for JSON object or array anywhere in the text
            match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', raw)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass
            logger.error("JSON parse failed", raw_preview=raw[:200])
            raise


async def _async_invoke(client, messages):
    """Use LangChain's native async invoke.

    `client.ainvoke` runs through httpx's async client, so asyncio.wait_for
    can actually cancel the request (cancellation propagates to httpx, which
    closes the underlying connection). The earlier `asyncio.to_thread(
    client.invoke, ...)` approach left zombie threads on timeout because
    sync httpx ignores task cancellation.
    """
    return await client.ainvoke(messages)


# Global singleton
llm = LLMClient()
