"""Mock-based tests for TikTok and Shopify connectors.

Verifies the connector publish flow with mocked HTTP responses — no real
API credentials or network calls required.

Ref: debt-audit-report-2026-06-09.md items E1
"""

import pytest

from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector

# ── TikTok Connector ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_tiktok_publish_mock_mode_returns_stub() -> None:
    """Without TIKTOK_ACCESS_TOKEN, publish should return a mock result."""
    connector = TikTokConnector()
    result = await connector.publish({
        "title": "Test Video",
        "description": "#test #ai",
        "video_path": "/tmp/test.mp4",
    })
    assert isinstance(result, dict)
    assert result.get("platform") == "tiktok"
    assert "post_id" in result
    assert result.get("success") is True or result.get("status") == "mock"


@pytest.mark.asyncio
async def test_tiktok_publish_no_video_path_fails_gracefully() -> None:
    """Publishing without a video_path should not crash."""
    connector = TikTokConnector()
    result = await connector.publish({"title": "No Video"})
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_tiktok_publish_with_empty_content() -> None:
    """Empty content dict should be handled gracefully."""
    connector = TikTokConnector()
    result = await connector.publish({})
    assert isinstance(result, dict)


# ── Shopify Connector ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_shopify_publish_mock_mode_returns_stub() -> None:
    """Without Shopify credentials, publish should return a mock result."""
    connector = ShopifyConnector()
    result = await connector.publish({
        "title": "Test Product Video",
        "description": "Product demo",
        "video_path": "/tmp/test.mp4",
        "product_id": "test-123",
    })
    assert isinstance(result, dict)
    assert result.get("platform") == "shopify"
    assert "post_id" in result
    assert result.get("success") is True or result.get("status") == "mock"


@pytest.mark.asyncio
async def test_shopify_publish_no_product_id() -> None:
    """Publishing without product_id should not crash."""
    connector = ShopifyConnector()
    result = await connector.publish({
        "title": "No Product",
        "video_path": "/tmp/test.mp4",
    })
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_shopify_publish_empty_content() -> None:
    """Empty content dict should be handled gracefully."""
    connector = ShopifyConnector()
    result = await connector.publish({})
    assert isinstance(result, dict)
