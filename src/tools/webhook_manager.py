"""Webhook notification system for pipeline events.

Module-level singleton: call get_webhook_manager() to access.
Events are dispatched asynchronously with a 5-second timeout.
Failures are logged as warnings — never block the pipeline.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

# ── Event type constants ──

EVENT_PIPELINE_STARTED = "pipeline.started"
EVENT_AUDIT_COMPLETED = "audit.completed"
EVENT_HUMAN_REVIEW_REQUIRED = "human_review.required"
EVENT_HUMAN_REVIEW_SUBMITTED = "human_review.submitted"
EVENT_PIPELINE_COMPLETED = "pipeline.completed"
EVENT_PIPELINE_ERROR = "pipeline.error"

ALL_EVENTS = [
    EVENT_PIPELINE_STARTED,
    EVENT_AUDIT_COMPLETED,
    EVENT_HUMAN_REVIEW_REQUIRED,
    EVENT_HUMAN_REVIEW_SUBMITTED,
    EVENT_PIPELINE_COMPLETED,
    EVENT_PIPELINE_ERROR,
]

# ── Webhook timeout ──

WEBHOOK_TIMEOUT_SECONDS = 5.0


class WebhookManager:
    """Manages webhook registrations and dispatches events.

    Thread-safe for reads (list_webhooks), writes (register/unregister)
    are not thread-safe and should be called from the main asyncio loop.

    Use via the module-level singleton: get_webhook_manager()
    """

    def __init__(self):
        self._webhooks: dict[str, list[str]] = defaultdict(list)

    # ── Registration API ──

    def register(self, event_type: str, url: str) -> None:
        """Register a URL for a given event type.

        Validates the URL format and deduplicates.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid webhook URL: {url} (must start with http:// or https://)")

        existing = self._webhooks[event_type]
        # Prevent duplicates (use set-like membership check)
        if url not in existing:
            # Validate httpx can parse it
            try:
                httpx.URL(url)
            except Exception as e:
                raise ValueError(f"Invalid webhook URL format: {url}") from e

            existing.append(url)
            logger.info("webhook: registered", event_type=event_type, url=url)

    def unregister(self, event_type: str, url: str) -> bool:
        """Remove a webhook registration. Returns True if found and removed."""
        existing = self._webhooks.get(event_type, [])
        if url in existing:
            existing.remove(url)
            logger.info("webhook: unregistered", event_type=event_type, url=url)
            return True
        return False

    def list_webhooks(self) -> dict[str, list[str]]:
        """Return a copy of all current registrations."""
        return dict(self._webhooks)

    def register_all(self, url: str) -> None:
        """Register a URL for ALL event types. Convenience for config-driven setup."""
        for event_type in ALL_EVENTS:
            self.register(event_type, url)

    # ── Dispatch ──

    async def dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """Send webhook notifications for an event.

        Dispatches to all URLs registered for this event_type.
        Parallel POST with 5s timeout. Failures are logged, never raised.
        """
        urls = self._webhooks.get(event_type, [])
        if not urls:
            return

        envelope = self._build_envelope(event_type, payload)
        tasks = [self._send(url, envelope) for url in urls]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                logger.warning(
                    "webhook: dispatch failed",
                    event_type=event_type,
                    url=url,
                    error=str(result),
                )
            else:
                logger.debug(
                    "webhook: dispatched",
                    event_type=event_type,
                    url=url,
                    status=result,
                )

    def dispatch_sync(self, event_type: str, payload: dict[str, Any]) -> None:
        """Synchronous dispatch — for use in synchronous code paths.

        Creates a new event loop in the current thread if needed.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop — create one
            asyncio.run(self.dispatch(event_type, payload))
            return

        # Already in an event loop — schedule and wait (blocking call from sync context)
        if loop.is_running():
            loop.create_task(self.dispatch(event_type, payload))
        else:
            loop.run_until_complete(self.dispatch(event_type, payload))

    # ── Internal ──

    def _build_envelope(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Wrap event payload in a standard envelope."""
        return {
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "event_id": uuid.uuid4().hex[:12],
            "data": payload,
        }

    async def _send(self, url: str, envelope: dict[str, Any]) -> int:
        """POST the envelope to a single webhook URL.

        Returns HTTP status code on success.
        Raises on connection error, timeout, or non-2xx status.
        """
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=envelope)
            response.raise_for_status()
            return response.status_code


# ── Module-level singleton ──

_manager: WebhookManager | None = None


def get_webhook_manager() -> WebhookManager:
    """Get or create the singleton WebhookManager."""
    global _manager
    if _manager is None:
        _manager = WebhookManager()
    return _manager


def reset_webhook_manager() -> None:
    """Reset the singleton (for testing)."""
    global _manager
    _manager = None
