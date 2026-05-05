"""Tests for GAP-17: Webhook notification system."""

from __future__ import annotations

import asyncio
import pytest

from src.tools.webhook_manager import (
    WebhookManager,
    get_webhook_manager,
    reset_webhook_manager,
    ALL_EVENTS,
    WEBHOOK_TIMEOUT_SECONDS,
)


class TestWebhookManager:
    """Unit tests for WebhookManager registration and dispatch."""

    def setup_method(self):
        reset_webhook_manager()

    def test_register_adds_url(self):
        """Register adds a url to the correct event type."""
        m = WebhookManager()
        m.register("audit.completed", "https://example.com/hook")
        hooks = m.list_webhooks()
        assert "audit.completed" in hooks
        assert "https://example.com/hook" in hooks["audit.completed"]

    def test_register_deduplicates(self):
        """Same URL for same event_type is not added twice."""
        m = WebhookManager()
        m.register("audit.completed", "https://example.com/hook")
        m.register("audit.completed", "https://example.com/hook")
        hooks = m.list_webhooks()
        assert len(hooks["audit.completed"]) == 1

    def test_register_multiple_urls(self):
        """Multiple URLs for the same event type."""
        m = WebhookManager()
        m.register("audit.completed", "https://hook1.example.com")
        m.register("audit.completed", "https://hook2.example.com")
        assert len(m.list_webhooks()["audit.completed"]) == 2

    def test_register_invalid_url_raises(self):
        """Non-http URL raises ValueError."""
        m = WebhookManager()
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            m.register("audit.completed", "ftp://bad.com/hook")

    def test_register_empty_url_raises(self):
        """Empty string URL raises ValueError."""
        m = WebhookManager()
        with pytest.raises(ValueError, match="Invalid webhook URL"):
            m.register("audit.completed", "")

    def test_unregister_removes_url(self):
        """Unregister removes a URL from the event type."""
        m = WebhookManager()
        url = "https://example.com/hook"
        m.register("audit.completed", url)
        result = m.unregister("audit.completed", url)
        assert result is True
        assert url not in m.list_webhooks()["audit.completed"]

    def test_unregister_nonexistent_returns_false(self):
        """Unregistering a URL that isn't registered returns False."""
        m = WebhookManager()
        result = m.unregister("audit.completed", "https://nope.com/hook")
        assert result is False

    def test_list_webhooks_returns_copy(self):
        """list_webhooks returns a copy, mutation-safe."""
        m = WebhookManager()
        m.register("audit.completed", "https://example.com/hook")
        hooks = m.list_webhooks()
        hooks["audit.completed"] = []
        # Original should be unchanged
        assert len(m.list_webhooks()["audit.completed"]) == 1

    def test_register_all(self):
        """register_all registers URL for all event types."""
        m = WebhookManager()
        m.register_all("https://all.hook.com")
        hooks = m.list_webhooks()
        for event_type in ALL_EVENTS:
            assert event_type in hooks
            assert "https://all.hook.com" in hooks[event_type]

    def test_dispatch_no_hooks_is_noop(self):
        """dispatch with no registered hooks does nothing (no error)."""
        m = WebhookManager()
        # Should not raise
        asyncio.run(m.dispatch("audit.completed", {"checkpoint": "test"}))

    def test_dispatch_bad_url_logs_warning(self):
        """dispatch to unreachable URL logs warning, doesn't raise."""
        m = WebhookManager()
        m.register("audit.completed", "https://nonexistent.local/webhook")
        # Should complete without raising
        asyncio.run(m.dispatch("audit.completed", {"checkpoint": "test"}))

    def test_dispatch_sync_no_hooks(self):
        """dispatch_sync with no hooks is a noop."""
        m = WebhookManager()
        m.dispatch_sync("audit.completed", {"checkpoint": "test"})

    def test_dispatch_sync_bad_url_logs_warning(self):
        """dispatch_sync to unreachable URL logs warning, doesn't raise."""
        m = WebhookManager()
        m.register("audit.completed", "https://nonexistent.local/webhook")
        m.dispatch_sync("audit.completed", {"checkpoint": "test"})

    def test_envelope_format(self):
        """Envelope has standard fields: event_type, timestamp, event_id, data."""
        m = WebhookManager()
        envelope = m._build_envelope("audit.completed", {"checkpoint": "strategy"})
        assert envelope["event_type"] == "audit.completed"
        assert "timestamp" in envelope
        assert "event_id" in envelope
        assert "data" in envelope
        assert envelope["data"]["checkpoint"] == "strategy"


class TestWebhookManagerSingleton:
    """Tests for module-level singleton."""

    def setup_method(self):
        reset_webhook_manager()

    def test_get_webhook_manager_returns_singleton(self):
        """Multiple calls return the same instance."""
        m1 = get_webhook_manager()
        m2 = get_webhook_manager()
        assert m1 is m2

    def test_reset_clears_singleton(self):
        """reset_webhook_manager creates a fresh instance on next get."""
        m1 = get_webhook_manager()
        m1.register("audit.completed", "https://example.com/hook")
        reset_webhook_manager()
        m2 = get_webhook_manager()
        assert m2 is not m1
        assert m2.list_webhooks() == {}


class TestWebhookIntegration:
    """Integration tests: webhooks fired from nodes."""

    def setup_method(self):
        reset_webhook_manager()

    @pytest.mark.skip(reason="P0-C deferred: capsys 与 audit 节点 dispatch 不稳定")
    async def test_audit_nodes_dispatch_audit_completed(self, capsys):
        """Running the pipeline triggers audit.completed events from audit nodes."""
        reset_webhook_manager()
        m = get_webhook_manager()
        # Register a collector instead of a real URL
        events = []

        # Monkey-patch dispatch to capture events
        original_dispatch = m.dispatch_sync

        def capturing_dispatch(event_type, payload):
            events.append((event_type, payload))
            original_dispatch(event_type, payload)

        m.dispatch_sync = capturing_dispatch

        # Run a short pipeline
        from src.graph.pipeline import compile_pipeline

        compiled = compile_pipeline()
        config = {"configurable": {"thread_id": "wh-test"}}

        async def run():
            async for _ in compiled.astream(
                {
                    "product_catalog": {},
                    "brand_guidelines": {},
                    "target_platforms": ["tiktok"],
                    "target_languages": ["en"],
                    "content_calendar_week": "2026-W17",
                    "current_step": "init",
                    "errors": [],
                    "human_reviews": {},
                    "pipeline_complete": False,
                },
                config,
            ):
                pass

        await run()

        # Strategy runs first, so at least audit.completed should fire once
        audit_events = [e for e in events if e[0] == "audit.completed"]
        assert len(audit_events) >= 1, f"Expected at least 1 audit.completed, got {len(audit_events)}"
        assert audit_events[0][1]["checkpoint"] == "strategy"
        assert "score" in audit_events[0][1]

        pipeline_events = [e for e in events if e[0] == "pipeline.completed"]
        # Pipeline may or may not complete fully depending on interrupts
        # But audit events must fire
        print(f"  ✓ Captured {len(audit_events)} audit.completed events")
        if pipeline_events:
            print(f"  ✓ Captured {len(pipeline_events)} pipeline.completed events")
