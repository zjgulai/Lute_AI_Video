"""Tests for GAP-17: Webhook notification system."""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest

from src.tools.webhook_manager import (
    ALL_EVENTS,
    WebhookManager,
    get_webhook_manager,
    reset_webhook_manager,
)


class TestWebhookManager:
    """Unit tests for WebhookManager registration and dispatch."""

    def setup_method(self):
        reset_webhook_manager()

    @pytest.fixture(autouse=True)
    def _mock_public_dns(self, monkeypatch):
        def _fake_getaddrinfo(hostname, *args, **kwargs):
            return [
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    6,
                    "",
                    ("93.184.216.34", 443),
                )
            ]

        monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    @pytest.fixture
    def mock_failed_http_post(self, monkeypatch):
        async def _raise_connect_error(self, url, **kwargs):
            raise httpx.ConnectError("offline test webhook", request=httpx.Request("POST", url))

        monkeypatch.setattr(httpx.AsyncClient, "post", _raise_connect_error)

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

    def test_dispatch_bad_url_logs_warning(self, mock_failed_http_post):
        """dispatch to unreachable URL logs warning, doesn't raise."""
        m = WebhookManager()
        m.register("audit.completed", "https://webhook.example.test/webhook")
        # Should complete without raising
        asyncio.run(m.dispatch("audit.completed", {"checkpoint": "test"}))

    def test_dispatch_sync_no_hooks(self):
        """dispatch_sync with no hooks is a noop."""
        m = WebhookManager()
        m.dispatch_sync("audit.completed", {"checkpoint": "test"})

    def test_dispatch_sync_bad_url_logs_warning(self, mock_failed_http_post):
        """dispatch_sync to unreachable URL logs warning, doesn't raise."""
        m = WebhookManager()
        m.register("audit.completed", "https://webhook.example.test/webhook")
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

    def test_dispatch_returns_http_readback_summary_and_preserves_envelope(self):
        """dispatch returns a local readback summary for fake receivers."""
        sent: list[tuple[str, dict]] = []

        async def fake_sender(url: str, envelope: dict) -> int:
            sent.append((url, envelope))
            return 202

        m = WebhookManager(http_sender=fake_sender, timeout_seconds=0.1)
        m.register("audit.completed", "https://receiver.example.test/hook")

        payload = {"checkpoint": "strategy", "score": 0.93}
        summary = asyncio.run(m.dispatch("audit.completed", payload))

        assert summary["event_type"] == "audit.completed"
        assert summary["http"]["attempted"] == 1
        assert summary["http"]["succeeded"] == 1
        assert summary["http"]["failed"] == 0
        assert summary["http"]["results"] == [
            {
                "url": "https://receiver.example.test/hook",
                "ok": True,
                "status_code": 202,
                "error_type": None,
                "error": None,
            }
        ]

        assert len(sent) == 1
        _, envelope = sent[0]
        assert envelope["event_type"] == "audit.completed"
        assert envelope["event_id"] == summary["event_id"]
        assert "timestamp" in envelope
        assert envelope["data"] == payload

    def test_dispatch_summary_isolates_receiver_failure_and_timeout(self):
        """One failed or slow receiver is summarized without blocking others."""

        async def fake_sender(url: str, envelope: dict) -> int:
            if "slow" in url:
                await asyncio.sleep(0.05)
                return 204
            if "fail" in url:
                raise RuntimeError("receiver rejected")
            return 204

        m = WebhookManager(http_sender=fake_sender, timeout_seconds=0.01)
        m.register("audit.completed", "https://ok.example.test/hook")
        m.register("audit.completed", "https://fail.example.test/hook")
        m.register("audit.completed", "https://slow.example.test/hook")

        summary = asyncio.run(m.dispatch("audit.completed", {"checkpoint": "edit"}))

        assert summary["http"]["attempted"] == 3
        assert summary["http"]["succeeded"] == 1
        assert summary["http"]["failed"] == 2

        results_by_url = {item["url"]: item for item in summary["http"]["results"]}
        assert results_by_url["https://ok.example.test/hook"]["ok"] is True
        assert results_by_url["https://fail.example.test/hook"]["ok"] is False
        assert results_by_url["https://fail.example.test/hook"]["error_type"] == "RuntimeError"
        assert results_by_url["https://slow.example.test/hook"]["ok"] is False
        assert results_by_url["https://slow.example.test/hook"]["error_type"] == "TimeoutError"


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


# 原 TestWebhookIntegration class 已删除(2026-05-05):
# - 用 m.dispatch_sync API,WebhookManager 当前没这方法(只有 async dispatch)
# - 端到端 pipeline 运行需要 mock LLM,本测试范围超限
# - subscribe + dispatch 真实并发流程已经在 tests/test_portfolio_mechanism.py
#   覆盖 4 用例(sync/async listener fire、subscribe 幂等、listener 异常隔离、
#   portfolio_hook end-to-end)
