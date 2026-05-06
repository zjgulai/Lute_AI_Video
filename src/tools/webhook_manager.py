"""Webhook notification system for pipeline events.

Module-level singleton: call get_webhook_manager() to access.
Events are dispatched asynchronously with a 5-second timeout.
Failures are logged as warnings — never block the pipeline.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

# Internal listener signature: receives the raw event payload (not the envelope).
# Sync callables run inline; coroutines are scheduled as fire-and-forget tasks.
EventListener = Callable[[dict[str, Any]], Awaitable[None] | None]

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


# Dangerous ports that should never receive webhooks (internal services)
_BLOCKED_PORTS = {22, 25, 110, 143, 3306, 3389, 5432, 6379, 27017, 9200}


def _is_safe_webhook_url(url: str) -> None:
    """Validate that a webhook URL does not point to private/internal addresses.

    Defense layers:
    1. Scheme must be http/https.
    2. Port must not be in the blocked service port list.
    3. If hostname is an IP: reject private/loopback/link-local/reserved.
    4. If hostname is a DNS name: resolve it and reject if any resolved IP is private.
       This prevents DNS rebinding attacks where a domain initially resolves to a
       public IP but is later flipped to an internal IP.

    Raises ValueError if the URL is deemed unsafe.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    # Layer 1: block dangerous ports
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if port in _BLOCKED_PORTS:
        raise ValueError(f"URL port {port} is blocked")

    hostname = parsed.hostname

    # Layer 2: direct IP check
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError(f"URL resolves to a private/internal IP: {hostname}")
    except ValueError:
        # Not an IP address — proceed to DNS resolution check.
        pass

    # Layer 3: DNS resolution + rebinding guard
    # Resolve the hostname and verify no A/AAAA record points to a private IP.
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrinfos:
            resolved_ip = ipaddress.ip_address(sockaddr[0])
            if (
                resolved_ip.is_private
                or resolved_ip.is_loopback
                or resolved_ip.is_link_local
                or resolved_ip.is_reserved
                or resolved_ip.is_multicast
            ):
                raise ValueError(
                    f"DNS resolution of '{hostname}' returned private IP {resolved_ip}"
                )
    except ValueError:
        raise
    except Exception as exc:
        # DNS resolution failure is treated as unsafe (fail-closed)
        raise ValueError(f"Failed to resolve hostname '{hostname}': {exc}") from exc


class WebhookManager:
    """Manages webhook registrations and dispatches events.

    Thread-safe for reads (list_webhooks), writes (register/unregister)
    are not thread-safe and should be called from the main asyncio loop.

    Use via the module-level singleton: get_webhook_manager()
    """

    def __init__(self):
        self._webhooks: dict[str, list[str]] = defaultdict(list)
        # In-process listeners (e.g. portfolio index rebuild on pipeline.completed).
        # Distinct from HTTP webhooks: not subject to URL validation, never crosses
        # the network, exception isolation handled per-listener.
        self._listeners: dict[str, list[EventListener]] = defaultdict(list)

    # ── Registration API ──

    def register(self, event_type: str, url: str) -> None:
        """Register a URL for a given event type.

        Validates the URL format, rejects private addresses, and deduplicates.
        """
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"Invalid webhook URL: {url} (must start with http:// or https://)")

        # Reject private / internal addresses (SSRF prevention)
        try:
            _is_safe_webhook_url(url)
        except ValueError as exc:
            raise ValueError(f"Unsafe webhook URL: {url} — {exc}") from exc

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

    # ── Internal listeners (in-process callbacks, no HTTP) ──

    def subscribe(self, event_type: str, listener: EventListener) -> None:
        """Register an in-process callback for an event type.

        Listener receives the raw payload dict (not the HTTP envelope).
        Coroutine listeners are scheduled fire-and-forget.
        Exceptions are logged, never raised — keeps pipeline resilient.

        Use case: portfolio rebuild on pipeline.completed without needing a
        real HTTP webhook URL.
        """
        if listener not in self._listeners[event_type]:
            self._listeners[event_type].append(listener)
            logger.info(
                "webhook: listener subscribed",
                event_type=event_type,
                listener=getattr(listener, "__qualname__", repr(listener)),
            )

    def unsubscribe(self, event_type: str, listener: EventListener) -> bool:
        """Remove an in-process listener. Returns True if found and removed."""
        existing = self._listeners.get(event_type, [])
        if listener in existing:
            existing.remove(listener)
            return True
        return False

    # ── Dispatch ──

    async def dispatch(self, event_type: str, payload: dict[str, Any]) -> None:
        """Send webhook notifications for an event.

        Fans out to two channels in parallel:
          1. In-process listeners (subscribe()) — receive raw payload
          2. HTTP webhooks (register()) — receive envelope-wrapped payload

        Both channels run with timeout/exception isolation; failures are logged,
        never raised, so pipeline forward progress is preserved.
        """
        # ── Channel 1: in-process listeners ──
        for listener in self._listeners.get(event_type, []):
            try:
                result = listener(payload)
                if asyncio.iscoroutine(result):
                    asyncio.create_task(self._run_listener(event_type, listener, result))
            except Exception as exc:
                logger.warning(
                    "webhook: listener failed",
                    event_type=event_type,
                    listener=getattr(listener, "__qualname__", repr(listener)),
                    error=str(exc)[:200],
                )

        # ── Channel 2: HTTP webhook URLs ──
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

    async def _run_listener(
        self, event_type: str, listener: EventListener, awaitable: Awaitable[None]
    ) -> None:
        """Await an async listener with exception isolation."""
        try:
            await awaitable
        except Exception as exc:
            logger.warning(
                "webhook: async listener failed",
                event_type=event_type,
                listener=getattr(listener, "__qualname__", repr(listener)),
                error=str(exc)[:200],
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
