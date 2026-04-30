"""Unified LLM client — routes to OpenAI or Anthropic based on config.

All public methods have timeout protection (60s default) via asyncio.timeout()
to prevent pipeline hangs on slow or dead LLM calls.

Preferred usage from async code:    await llm.invoke(...)
                                   await llm.invoke_json(...)
"""

from __future__ import annotations

import asyncio
import json
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

# Timeout per LLM call in seconds — prevents pipeline hangs on dead connections
LLM_TIMEOUT_SECONDS = 120.0


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

    def _get_client(self, model: str | None = None):
        cache_key = f"{self.provider}:{model}"
        if cache_key not in self._clients:
            if self.provider == "anthropic":
                self._clients[cache_key] = ChatAnthropic(
                    model=model or "claude-sonnet-4-20250514",
                    api_key=ANTHROPIC_API_KEY,
                    temperature=0.7,
                    max_tokens=4096,
                    timeout=self.timeout,
                )
            elif self.provider == "kimi":
                # Kimi / Moonshot — OpenAI-compatible API
                from langchain_openai import ChatOpenAI
                self._clients[cache_key] = ChatOpenAI(
                    model=model or KIMI_MODEL,
                    api_key=OPENAI_API_KEY,
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
                    api_key=DEEPSEEK_API_KEY,
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
                    "api_key": OPENAI_API_KEY,
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
            return await retry_with_backoff(_do_invoke)
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
    """Run the synchronous LangChain invoke in a thread.

    This avoids blocking the event loop and allows asyncio.wait_for
    to cancel the call when it times out.
    """
    return await asyncio.to_thread(client.invoke, messages)


# Global singleton
llm = LLMClient()
