"""Credential-absence and invalid-content compatibility for publish connectors."""

from __future__ import annotations

import pytest

from src.connectors.base import ConnectorCredentialNotReady, ConnectorPreflightRejected
from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector


@pytest.mark.asyncio
async def test_tiktok_publish_without_credentials_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TIKTOK_ACCESS_TOKEN", raising=False)
    with pytest.raises(ConnectorCredentialNotReady):
        await TikTokConnector().publish(
            {"title": "Test Video", "video_path": "/not/read.mp4"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [{"title": "No Video"}, {}])
async def test_tiktok_invalid_content_is_real_deterministic_failure(
    content: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-tiktok-token")
    for name in (
        "TIKTOK_USERNAME",
        "TIKTOK_API_UPLOAD_URL",
        "TIKTOK_API_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConnectorPreflightRejected):
        await TikTokConnector().preflight(content)


@pytest.mark.asyncio
async def test_shopify_publish_without_credentials_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "SHOPIFY_ACCESS_TOKEN",
        "SHOPIFY_API_KEY",
        "SHOPIFY_STORE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConnectorCredentialNotReady):
        await ShopifyConnector().publish(
            {"title": "Test Product Video", "video_path": "/not/read.mp4"}
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        {"title": "No Product", "video_path": ""},
        {},
    ],
)
async def test_shopify_invalid_content_is_real_deterministic_failure(
    content: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.com")
    for name in (
        "SHOPIFY_API_KEY",
        "SHOPIFY_ADMIN_TOKEN",
        "SHOPIFY_API_PASSWORD",
        "SHOPIFY_GRAPHQL_URL_TEMPLATE",
    ):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConnectorPreflightRejected):
        await ShopifyConnector().preflight(content)
