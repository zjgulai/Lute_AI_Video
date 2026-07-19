from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response

from src.models.publish_attempt import (
    DurableTikTokStatusResponse,
    PublishAttemptReadbackResponse,
)
from src.routers._deps import ApiKeyType, AuthContext
from src.storage.publish_attempt_repository import PublishAttemptStoreUnavailable

ATTEMPT_ID = "91ec3593-cc3c-42bf-99ee-c98655c5826b"
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
POST_ID = "7512345678901234567"
POST_URL = f"https://www.tiktok.com/@fixture/video/{POST_ID}"


def _auth() -> AuthContext:
    return AuthContext(
        tenant_id="tenant-a",
        permissions=frozenset({"artifact:publish"}),
        key_type=ApiKeyType.TENANT,
        key_id="publisher-fixture",
    )


def _receipt() -> dict[str, object]:
    return {
        "schema_version": "publish-receipt.v1",
        "platform": "tiktok",
        "protocol_version": "tiktok-content-posting-v2",
        "completion_scope": "tiktok_direct_post",
        "provider_operation_id": "v_pub_file_status_fixture",
        "provider_resource_id": POST_ID,
        "target_id": None,
        "provider_status": "PUBLISH_COMPLETE",
        "post_id": POST_ID,
        "post_url": POST_URL,
        "public_visibility_verified": True,
        "observed_at": "2026-07-14T08:00:00Z",
        "verified_by": "video_query",
        "simulated": False,
    }


def _attempt_response() -> PublishAttemptReadbackResponse:
    return PublishAttemptReadbackResponse.model_validate(
        {
            "publish_attempt_id": ATTEMPT_ID,
            "acceptance_id": ACCEPTANCE_ID,
            "platform": "tiktok",
            "status": "published",
            "error_code": None,
            "post_id": POST_ID,
            "post_url": POST_URL,
            "receipt": _receipt(),
            "acceptance_consumed": True,
            "retry_allowed": False,
            "created_at": "2026-07-14T07:59:00Z",
            "updated_at": "2026-07-14T08:00:00Z",
        }
    )


def _status_response() -> DurableTikTokStatusResponse:
    return DurableTikTokStatusResponse(
        platform="tiktok",
        post_id=POST_ID,
        status="PUBLISH_COMPLETE",
        post_url=POST_URL,
        simulated=False,
        observed_at=datetime(2026, 7, 14, 8, 0, tzinfo=UTC),
        verified_by="video_query",
    )


class FakeReadbackService:
    def __init__(self) -> None:
        self.attempt_result: PublishAttemptReadbackResponse | None = (
            _attempt_response()
        )
        self.status_result: DurableTikTokStatusResponse | None = _status_response()
        self.attempt_error: Exception | None = None
        self.status_error: Exception | None = None
        self.attempt_calls: list[dict[str, Any]] = []
        self.status_calls: list[dict[str, Any]] = []

    async def get_attempt_readback(
        self,
        *,
        auth: AuthContext,
        attempt_id: str,
    ) -> PublishAttemptReadbackResponse | None:
        self.attempt_calls.append({"auth": auth, "attempt_id": attempt_id})
        if self.attempt_error is not None:
            raise self.attempt_error
        return self.attempt_result

    async def get_durable_tiktok_status(
        self,
        *,
        auth: AuthContext,
        post_id: str,
    ) -> DurableTikTokStatusResponse | None:
        self.status_calls.append({"auth": auth, "post_id": post_id})
        if self.status_error is not None:
            raise self.status_error
        return self.status_result


@pytest.fixture
def fake_readback_service(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeReadbackService:
    from src.routers import distribution

    service = FakeReadbackService()
    monkeypatch.setattr(distribution, "get_publish_attempt_service", lambda: service)
    return service


@pytest.fixture(autouse=True)
def bypass_readback_auth() -> Iterator[None]:
    from src.api import app
    from src.routers import distribution
    from src.routers._deps import verify_api_key

    app.dependency_overrides[distribution._PUBLISH_PERMISSION] = _auth
    app.dependency_overrides[verify_api_key] = _auth
    try:
        yield
    finally:
        app.dependency_overrides.pop(distribution._PUBLISH_PERMISSION, None)
        app.dependency_overrides.pop(verify_api_key, None)


async def _get(path: str) -> Response:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.get(path)


@pytest.mark.asyncio
async def test_attempt_readback_is_safe_tenant_bound_projection(
    fake_readback_service: FakeReadbackService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    monkeypatch.setattr(
        registry,
        "get_connector",
        lambda _: pytest.fail("attempt readback must not construct a connector"),
    )

    response = await _get(f"/distribution/publish-attempts/{ATTEMPT_ID}")

    assert response.status_code == 200, response.text
    payload = response.json()
    payload.pop("_meta")
    assert payload == _attempt_response().model_dump(mode="json")
    assert "content" not in payload
    assert "metadata" not in payload
    assert "artifact" not in payload
    assert fake_readback_service.attempt_calls == [
        {"auth": _auth(), "attempt_id": ATTEMPT_ID}
    ]


@pytest.mark.asyncio
async def test_attempt_readback_missing_or_cross_tenant_is_404(
    fake_readback_service: FakeReadbackService,
) -> None:
    fake_readback_service.attempt_result = None

    response = await _get(f"/distribution/publish-attempts/{ATTEMPT_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "publish_attempt_not_found"}


@pytest.mark.asyncio
async def test_attempt_readback_store_failure_is_stable_503(
    fake_readback_service: FakeReadbackService,
) -> None:
    fake_readback_service.attempt_error = PublishAttemptStoreUnavailable(
        "raw-store-secret"
    )

    response = await _get(f"/distribution/publish-attempts/{ATTEMPT_ID}")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "publish_attempt_store_unavailable"
    }
    assert "raw-store-secret" not in response.text


@pytest.mark.asyncio
async def test_attempt_readback_rejects_malformed_id_before_service(
    fake_readback_service: FakeReadbackService,
) -> None:
    response = await _get("/distribution/publish-attempts/not-an-attempt")

    assert response.status_code == 422
    assert fake_readback_service.attempt_calls == []


@pytest.mark.asyncio
async def test_legacy_status_returns_only_durable_tiktok_receipt_projection(
    fake_readback_service: FakeReadbackService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry

    monkeypatch.setattr(
        registry,
        "get_connector",
        lambda _: pytest.fail("legacy status must not construct a connector"),
    )

    response = await _get(f"/distribution/status/tiktok/{POST_ID}")

    assert response.status_code == 200, response.text
    payload = response.json()
    payload.pop("_meta")
    assert payload == _status_response().model_dump(mode="json")
    assert fake_readback_service.status_calls == [
        {"auth": _auth(), "post_id": POST_ID}
    ]


@pytest.mark.asyncio
async def test_legacy_status_missing_receipt_is_404(
    fake_readback_service: FakeReadbackService,
) -> None:
    fake_readback_service.status_result = None

    response = await _get(f"/distribution/status/tiktok/{POST_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == {"code": "distribution_status_not_found"}


@pytest.mark.asyncio
async def test_legacy_status_contradictory_receipts_fail_closed_503(
    fake_readback_service: FakeReadbackService,
) -> None:
    fake_readback_service.status_error = PublishAttemptStoreUnavailable(
        "contradictory-receipts"
    )

    response = await _get(f"/distribution/status/tiktok/{POST_ID}")

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "publish_attempt_store_unavailable"
    }
    assert "contradictory-receipts" not in response.text


@pytest.mark.asyncio
async def test_legacy_shopify_status_is_stable_410_without_store_lookup(
    fake_readback_service: FakeReadbackService,
) -> None:
    response = await _get(f"/distribution/status/shopify/{POST_ID}")

    assert response.status_code == 410
    assert response.json()["detail"] == {
        "code": "distribution_status_route_deprecated"
    }
    assert fake_readback_service.status_calls == []


@pytest.mark.asyncio
async def test_legacy_status_rejects_unknown_platform_and_non_numeric_post_id(
    fake_readback_service: FakeReadbackService,
) -> None:
    unsupported = await _get(f"/distribution/status/instagram/{POST_ID}")
    malformed = await _get("/distribution/status/tiktok/not-a-post")

    assert unsupported.status_code == 400
    assert unsupported.json()["detail"] == {
        "code": "distribution_status_platform_unsupported"
    }
    assert malformed.status_code == 422
    assert fake_readback_service.status_calls == []


@pytest.mark.asyncio
async def test_platform_listing_uses_strict_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry
    from src.connectors.registry import PublishConnectorReadiness

    def readiness(platform: str) -> PublishConnectorReadiness:
        return PublishConnectorReadiness(
            platform=platform,  # type: ignore[arg-type]
            ready=platform == "tiktok",
            reason=None if platform == "tiktok" else "missing_credentials",
        )

    monkeypatch.setattr(registry, "inspect_publish_readiness", readiness)
    response = await _get("/distribution/platforms")

    assert response.status_code == 200
    assert response.json()["data"][:2] == [
        {"id": "tiktok", "name": "TikTok", "connected": True},
        {"id": "shopify", "name": "Shopify", "connected": False},
    ]
