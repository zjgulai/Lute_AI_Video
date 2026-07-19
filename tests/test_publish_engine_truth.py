from __future__ import annotations

from typing import Any

import pytest

from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorOutcomeAmbiguous,
)
from src.connectors.publish_engine import PublishEngine


def _published_receipt(platform: str) -> dict[str, object]:
    if platform == "tiktok":
        return {
            "schema_version": "publish-receipt.v1",
            "platform": "tiktok",
            "protocol_version": "tiktok-content-posting-v2",
            "completion_scope": "tiktok_direct_post",
            "provider_operation_id": "v_pub_file_fixture_123",
            "provider_resource_id": "7512345678901234567",
            "target_id": None,
            "provider_status": "PUBLISH_COMPLETE",
            "post_id": "7512345678901234567",
            "post_url": (
                "https://www.tiktok.com/@fixture/video/7512345678901234567"
            ),
            "public_visibility_verified": True,
            "observed_at": "2026-07-14T08:00:00Z",
            "verified_by": "video_query",
            "simulated": False,
        }
    return {
        "schema_version": "publish-receipt.v1",
        "platform": "shopify",
        "protocol_version": "shopify-admin-2026-07",
        "completion_scope": "shopify_product_media",
        "provider_operation_id": None,
        "provider_resource_id": "gid://shopify/Video/987654321",
        "target_id": "gid://shopify/Product/123456789",
        "provider_status": "READY",
        "post_id": None,
        "post_url": None,
        "public_visibility_verified": False,
        "observed_at": "2026-07-14T08:00:00Z",
        "verified_by": "file_query_and_product_readback",
        "simulated": False,
    }


class FakeConnector:
    def __init__(
        self,
        *,
        result: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.preflight_calls: list[dict[str, Any]] = []
        self.snapshot = object()

    async def preflight(self, content: dict[str, Any]) -> object:
        self.preflight_calls.append(content)
        return self.snapshot

    async def publish(
        self,
        content: dict[str, Any],
        *,
        preflight: object,
    ) -> Any:
        assert preflight is self.snapshot
        self.calls.append(content)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
async def test_engine_projects_trusted_real_success_once(platform: str) -> None:
    receipt = _published_receipt(platform)
    connector = FakeConnector(
        result={
            "success": True,
            "simulated": False,
            "platform": platform,
            "post_id": receipt["post_id"],
            "url": receipt["post_url"],
            "receipt": receipt,
        }
    )
    engine = PublishEngine()
    setattr(engine, f"_{platform}", connector)

    method = getattr(engine, f"publish_to_{platform}")
    result = await method("/fixture/video.mp4", {"hook": "Reviewed"})

    assert result.platform == platform
    assert result.success is True
    assert result.simulated is False
    assert result.post_id == receipt["post_id"]
    assert result.post_url == receipt["post_url"]
    assert result.receipt == receipt
    assert len(connector.preflight_calls) == 1
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_engine_never_converts_simulated_result_to_success(success: bool) -> None:
    connector = FakeConnector(
        result={"success": success, "simulated": True, "post_id": "fake"}
    )
    engine = PublishEngine()
    engine._tiktok = connector  # type: ignore[assignment]

    result = await engine.publish_to_tiktok("/fixture/video.mp4", {})

    assert result.success is False
    assert result.simulated is True
    assert result.error == "publish_connector_simulated"
    assert result.post_id is None
    assert len(connector.preflight_calls) == 1
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"simulated": 0, "success": True},
        {"simulated": False},
        {"simulated": False, "success": 1},
    ],
)
async def test_engine_rejects_missing_or_nonbool_truth_as_ambiguous(
    result: Any,
) -> None:
    connector = FakeConnector(result=result)
    engine = PublishEngine()
    engine._tiktok = connector  # type: ignore[assignment]

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await engine.publish_to_tiktok("/fixture/video.mp4", {})
    assert len(connector.preflight_calls) == 1
    assert len(connector.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ConnectorCredentialNotReady("missing_credentials"),
        ConnectorOutcomeAmbiguous(),
    ],
)
async def test_engine_propagates_typed_connector_errors_without_retry(
    error: Exception,
) -> None:
    connector = FakeConnector(error=error)
    engine = PublishEngine()
    engine._shopify = connector  # type: ignore[assignment]

    with pytest.raises(type(error)):
        await engine.publish_to_shopify("/fixture/video.mp4", {})
    assert len(connector.preflight_calls) == 1
    assert len(connector.calls) == 1


@pytest.mark.asyncio
async def test_engine_unsupported_platform_keeps_order_and_real_local_truth() -> None:
    tiktok = FakeConnector(
        result={"success": False, "simulated": False, "platform": "tiktok"}
    )
    engine = PublishEngine()
    engine._tiktok = tiktok  # type: ignore[assignment]

    results = await engine.publish(
        "/fixture/video.mp4",
        {},
        ["instagram", "tiktok"],
    )

    assert [result.platform for result in results] == ["instagram", "tiktok"]
    assert results[0].success is False
    assert results[0].simulated is False
    assert results[0].error == "unsupported_platform"
    assert results[1].error == "publish_connector_failed"
    assert len(tiktok.preflight_calls) == 1
    assert len(tiktok.calls) == 1


@pytest.mark.asyncio
async def test_engine_does_not_capture_raw_unknown_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sentinel = "raw-provider-secret-shaped-exception"
    connector = FakeConnector(error=RuntimeError(sentinel))
    engine = PublishEngine()
    engine._tiktok = connector  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match=sentinel):
        await engine.publish_to_tiktok("/fixture/video.mp4", {})
    assert sentinel not in caplog.text
    assert len(connector.preflight_calls) == 1
    assert len(connector.calls) == 1
