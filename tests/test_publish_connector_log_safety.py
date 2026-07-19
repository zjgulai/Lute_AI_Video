"""Current-protocol connector log and secret boundary regressions."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.connectors.base import (
    ConnectorOutcomeAmbiguous,
    ConnectorStatusUnavailable,
    ShopifyPreflightSnapshot,
    TikTokPreflightSnapshot,
)
from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector

NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
PRODUCT_ID = "gid://shopify/Product/123456789"


class ExplodingClient:
    def __init__(self, sentinel: str) -> None:
        self.sentinel = sentinel
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> object:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        raise RuntimeError(self.sentinel)

    async def put(self, url: str, **kwargs: Any) -> object:
        self.calls.append({"method": "PUT", "url": url, **kwargs})
        raise RuntimeError(self.sentinel)


def _tiktok_content(video: Path) -> dict[str, object]:
    return {
        "video_path": str(video),
        "title": "Private reviewed title",
        "description": "Private reviewed caption",
        "tags": [],
        "platform_options": {
            "platform": "tiktok",
            "privacy_level": "SELF_ONLY",
            "disable_comment": True,
            "disable_duet": True,
            "disable_stitch": True,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        },
    }


def _shopify_content(video: Path) -> dict[str, object]:
    return {
        "video_path": str(video),
        "title": "Private reviewed title",
        "product_name": "Private display-only product",
        "platform_options": {
            "platform": "shopify",
            "product_id": PRODUCT_ID,
        },
    }


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "private-reviewed.mp4"
    path.write_bytes(b"fixture-video")
    return path


@pytest.mark.asyncio
async def test_tiktok_ambiguous_provider_failure_logs_only_stable_class(
    video: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "raw-tiktok-provider-body credential=secret"
    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-tiktok-token")
    for name in (
        "TIKTOK_USERNAME",
        "TIKTOK_API_UPLOAD_URL",
        "TIKTOK_API_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    client = ExplodingClient(sentinel)
    connector = TikTokConnector(
        http_client=client,  # type: ignore[arg-type]
        media_probe=lambda _: 12.5,
        now=lambda: NOW,
    )
    preflight = TikTokPreflightSnapshot(
        privacy_level="SELF_ONLY",
        disable_comment=True,
        disable_duet=True,
        disable_stitch=True,
        brand_content_toggle=False,
        brand_organic_toggle=False,
        max_video_post_duration_sec=300,
        media_duration_seconds=12.5,
        observed_at=NOW,
    )

    with pytest.raises(ConnectorOutcomeAmbiguous) as error:
        await connector.publish(
            _tiktok_content(video),  # type: ignore[arg-type]
            preflight=preflight,
        )

    evidence = caplog.text + repr(error.value)
    assert len(client.calls) == 1
    assert "RuntimeError" in caplog.text
    assert sentinel not in evidence
    assert "fixture-tiktok-token" not in evidence
    assert str(video) not in evidence
    assert "Private reviewed caption" not in evidence


@pytest.mark.asyncio
async def test_shopify_ambiguous_provider_failure_logs_only_stable_class(
    video: Path,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = "raw-shopify-provider-body credential=secret"
    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.com")
    for name in (
        "SHOPIFY_API_KEY",
        "SHOPIFY_ADMIN_TOKEN",
        "SHOPIFY_API_PASSWORD",
        "SHOPIFY_GRAPHQL_URL_TEMPLATE",
    ):
        monkeypatch.delenv(name, raising=False)
    client = ExplodingClient(sentinel)
    connector = ShopifyConnector(
        http_client=client,  # type: ignore[arg-type]
        media_probe=lambda _: 12.5,
        now=lambda: NOW,
    )
    preflight = ShopifyPreflightSnapshot(
        product_id=PRODUCT_ID,
        required_scopes_verified=True,
        media_duration_seconds=12.5,
        observed_at=NOW,
    )

    with pytest.raises(ConnectorOutcomeAmbiguous) as error:
        await connector.publish(
            _shopify_content(video),  # type: ignore[arg-type]
            preflight=preflight,
        )

    evidence = caplog.text + repr(error.value)
    assert len(client.calls) == 1
    assert "RuntimeError" in caplog.text
    assert sentinel not in evidence
    assert "fixture-shopify-token" not in evidence
    assert str(video) not in evidence
    assert "Private display-only product" not in evidence


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
async def test_direct_status_is_fail_closed_and_never_touches_network(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ExplodingClient("must-not-be-called")
    if platform == "tiktok":
        monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-tiktok-token")
        for name in (
            "TIKTOK_USERNAME",
            "TIKTOK_API_UPLOAD_URL",
            "TIKTOK_API_BASE_URL",
        ):
            monkeypatch.delenv(name, raising=False)
        connector = TikTokConnector(http_client=client)  # type: ignore[arg-type]
    else:
        monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
        monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-shopify-token")
        monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.com")
        for name in (
            "SHOPIFY_API_KEY",
            "SHOPIFY_ADMIN_TOKEN",
            "SHOPIFY_API_PASSWORD",
            "SHOPIFY_GRAPHQL_URL_TEMPLATE",
        ):
            monkeypatch.delenv(name, raising=False)
        connector = ShopifyConnector(http_client=client)  # type: ignore[arg-type]

    with pytest.raises(ConnectorStatusUnavailable):
        await connector.get_status("7512345678901234567")

    assert client.calls == []


def test_runtime_sources_do_not_restore_legacy_publish_helpers_or_raw_logging() -> None:
    import src.connectors.shopify_connector as shopify_module
    import src.connectors.tiktok_connector as tiktok_module

    tiktok_source = inspect.getsource(tiktok_module)
    shopify_source = inspect.getsource(shopify_module)
    for forbidden in ("_upload_video", "_publish_video"):
        assert forbidden not in tiktok_source
    for forbidden in (
        "_upload_video",
        "_associate_with_product",
        "productCreateMedia",
    ):
        assert forbidden not in shopify_source
    for source in (tiktok_source, shopify_source):
        assert "logger.error(response.text" not in source
        assert "logger.warning(response.text" not in source
