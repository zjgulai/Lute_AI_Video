"""W1-25 pre-consume publish preflight ordering and failure boundaries."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.connectors.base import (
    ConnectorPreflightRejected,
    ConnectorPreflightUnavailable,
    TikTokPreflightSnapshot,
)
from src.connectors.registry import PublishConnectorReadiness
from src.models.acceptance import AcceptanceRecordResponse
from src.models.publish_attempt import PublishAttemptRequest
from src.routers._deps import ApiKeyType, AuthContext
from src.services.artifact_acceptance import (
    AcceptanceArtifactIntegrityMismatch,
    AcceptanceNotFound,
    AcceptanceStoreUnavailable,
)

TENANT_ID = "tenant-preflight"
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
VIDEO_BYTES = b"publish-preflight-video"


def _auth() -> AuthContext:
    return AuthContext(
        tenant_id=TENANT_ID,
        permissions=frozenset({"artifact:publish"}),
        key_type=ApiKeyType.TENANT,
        key_id="publisher-preflight",
    )


def _request() -> PublishAttemptRequest:
    return PublishAttemptRequest.model_validate(
        {
            "acceptance_id": ACCEPTANCE_ID,
            "platform": "tiktok",
            "metadata": {"description": "Reviewed caption"},
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
    )


def _acceptance(*, status: str, path: str) -> AcceptanceRecordResponse:
    return AcceptanceRecordResponse.model_validate(
        {
            "acceptance_id": ACCEPTANCE_ID,
            "tenant_id": TENANT_ID,
            "source_resource_type": "scenario",
            "source_resource_id": "s2_preflight_fixture",
            "scenario": "s2",
            "artifact": {
                "path": path,
                "sha256": hashlib.sha256(VIDEO_BYTES).hexdigest(),
                "size_bytes": len(VIDEO_BYTES),
                "kind": "video",
            },
            "decision": "accepted",
            "status": status,
            "reviewer": {"key_id": "reviewer", "key_type": "tenant"},
            "review_notes": "must not leave acceptance service",
            "expires_at": "2030-01-01T00:00:00+00:00",
            "consumed_at": (
                "2026-07-14T08:00:00+00:00" if status == "consumed" else None
            ),
            "revoked_at": None,
            "idempotent_replay": False,
            "created_at": "2026-07-14T07:00:00+00:00",
            "updated_at": "2026-07-14T08:00:00+00:00",
        }
    )


class FakeRepository:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.rows: dict[str, dict[str, Any]] = {}

    async def create_prepared(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append("attempt:prepared")
        attempt_id = str(uuid.uuid4())
        row = {
            "id": attempt_id,
            "tenant_id": kwargs["tenant_id"],
            "acceptance_id": kwargs["acceptance_id"],
            "platform": kwargs["platform"],
            "status": "prepared",
            "post_id": None,
            "url": None,
            "error": None,
        }
        self.rows[attempt_id] = row
        return dict(row)

    async def transition(
        self,
        *,
        attempt_id: str,
        expected_status: str,
        new_status: str,
        error_code: str | None = None,
        post_id: str | None = None,
        url: str | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any] | None:
        self.calls.append(f"attempt:{new_status}")
        row = self.rows[attempt_id]
        if row["status"] != expected_status:
            return None
        row.update(
            status=new_status,
            error=error_code,
            post_id=post_id,
            url=url,
        )
        return dict(row)


class FakeAcceptanceService:
    def __init__(
        self,
        calls: list[str],
        *,
        available: AcceptanceRecordResponse,
        consumed: AcceptanceRecordResponse,
        inspect_error: Exception | None = None,
    ) -> None:
        self.calls = calls
        self.available = available
        self.consumed = consumed
        self.inspect_error = inspect_error
        self.consume_calls = 0

    async def inspect_for_publish(self, **_kwargs: Any) -> AcceptanceRecordResponse:
        self.calls.append("acceptance:inspect")
        if self.inspect_error is not None:
            raise self.inspect_error
        return self.available

    async def consume_for_publish(self, **_kwargs: Any) -> AcceptanceRecordResponse:
        self.calls.append("acceptance:consume")
        self.consume_calls += 1
        return self.consumed

    async def inspect_publish_consume_outcome(self, **_kwargs: Any) -> str:
        self.calls.append("acceptance:consume_outcome")
        return "unknown"


class FakeConnector:
    def __init__(
        self,
        calls: list[str],
        *,
        preflight_error: Exception | None = None,
    ) -> None:
        self.calls = calls
        self.preflight_error = preflight_error
        self.snapshot = TikTokPreflightSnapshot(
            privacy_level="SELF_ONLY",
            disable_comment=True,
            disable_duet=True,
            disable_stitch=True,
            brand_content_toggle=False,
            brand_organic_toggle=False,
            max_video_post_duration_sec=600,
            media_duration_seconds=1.0,
            observed_at=datetime(2026, 7, 14, 8, tzinfo=UTC),
        )
        self.preflight_contents: list[dict[str, Any]] = []
        self.publish_contents: list[dict[str, Any]] = []
        self.publish_snapshots: list[object] = []

    async def preflight(self, content: dict[str, Any]) -> TikTokPreflightSnapshot:
        self.calls.append("connector:preflight")
        self.preflight_contents.append(content)
        if self.preflight_error is not None:
            raise self.preflight_error
        return self.snapshot

    async def publish(
        self,
        content: dict[str, Any],
        *,
        preflight: object,
    ) -> Mapping[str, Any]:
        self.calls.append("connector:publish")
        self.publish_contents.append(content)
        self.publish_snapshots.append(preflight)
        return {
            "simulated": False,
            "success": True,
            "platform": "tiktok",
            "status": "published",
            "post_id": "7512345678901234567",
            "url": (
                "https://www.tiktok.com/@fixture/video/7512345678901234567"
            ),
            "receipt": {
                "schema_version": "publish-receipt.v1",
                "platform": "tiktok",
                "protocol_version": "tiktok-content-posting-v2",
                "completion_scope": "tiktok_direct_post",
                "provider_operation_id": "v_pub_file_preflight_fixture",
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
            },
        }


def _harness(
    tmp_path: Path,
    *,
    inspect_error: Exception | None = None,
    preflight_error: Exception | None = None,
) -> tuple[Any, list[str], FakeRepository, FakeAcceptanceService, FakeConnector]:
    from src.services.publish_attempt import PublishAttemptService

    output_dir = tmp_path / "output"
    relative = (
        f"tenants/{TENANT_ID}/pending_review/s2_preflight_fixture/"
        "assemble/final.mp4"
    )
    absolute = output_dir / relative
    absolute.parent.mkdir(parents=True)
    absolute.write_bytes(VIDEO_BYTES)
    calls: list[str] = []
    repository = FakeRepository(calls)
    acceptance = FakeAcceptanceService(
        calls,
        available=_acceptance(status="available", path=relative),
        consumed=_acceptance(status="consumed", path=relative),
        inspect_error=inspect_error,
    )
    connector = FakeConnector(calls, preflight_error=preflight_error)
    service = PublishAttemptService(
        attempt_repository=repository,
        acceptance_service=acceptance,
        output_dir=output_dir,
        readiness_inspector=lambda platform: PublishConnectorReadiness(
            platform=platform,
            ready=True,
            reason=None,
        ),
        connector_factory=lambda platform: (
            connector if platform == "tiktok" else pytest.fail(platform)
        ),
    )
    return service, calls, repository, acceptance, connector


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preflight_error", "status_code", "code"),
    [
        (
            ConnectorPreflightRejected(),
            409,
            "publish_preflight_rejected",
        ),
        (
            ConnectorPreflightUnavailable(),
            502,
            "publish_preflight_unavailable",
        ),
        (RuntimeError("raw-provider-detail"), 502, "publish_preflight_unavailable"),
    ],
)
async def test_preflight_failure_is_durable_and_never_consumes(
    tmp_path: Path,
    preflight_error: Exception,
    status_code: int,
    code: str,
) -> None:
    from src.services.publish_attempt import PublishAttemptError

    service, calls, repository, acceptance, connector = _harness(
        tmp_path,
        preflight_error=preflight_error,
    )

    with pytest.raises(PublishAttemptError) as captured:
        await service.execute(auth=_auth(), request=_request(), route_kind="canonical")

    error = captured.value
    row = next(iter(repository.rows.values()))
    assert error.status_code == status_code
    assert error.code == code
    assert error.detail.acceptance_consumed is False
    assert error.detail.retry_allowed is True
    assert row["status"] == "preflight_failed"
    assert row["error"] == code
    assert acceptance.consume_calls == 0
    assert connector.publish_contents == []
    assert calls == [
        "attempt:prepared",
        "acceptance:inspect",
        "connector:preflight",
        "attempt:preflight_failed",
    ]
    assert "raw-provider-detail" not in str(error)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("inspect_error", "status_code", "code", "retry_allowed"),
    [
        (AcceptanceNotFound(), 404, "acceptance_not_found", False),
        (
            AcceptanceArtifactIntegrityMismatch(),
            409,
            "acceptance_artifact_integrity_mismatch",
            False,
        ),
        (AcceptanceStoreUnavailable(), 503, "acceptance_store_unavailable", True),
    ],
)
async def test_acceptance_inspect_failure_stops_before_connector(
    tmp_path: Path,
    inspect_error: Exception,
    status_code: int,
    code: str,
    retry_allowed: bool,
) -> None:
    from src.services.publish_attempt import PublishAttemptError

    service, calls, repository, acceptance, connector = _harness(
        tmp_path,
        inspect_error=inspect_error,
    )

    with pytest.raises(PublishAttemptError) as captured:
        await service.execute(auth=_auth(), request=_request(), route_kind="canonical")

    error = captured.value
    row = next(iter(repository.rows.values()))
    assert error.status_code == status_code
    assert error.code == code
    assert error.detail.acceptance_consumed is False
    assert error.detail.retry_allowed is retry_allowed
    assert row["status"] == "authorization_failed"
    assert acceptance.consume_calls == 0
    assert connector.preflight_contents == []
    assert calls == [
        "attempt:prepared",
        "acceptance:inspect",
        "attempt:authorization_failed",
    ]


@pytest.mark.asyncio
async def test_success_uses_one_retained_connector_and_same_preflight_snapshot(
    tmp_path: Path,
) -> None:
    service, calls, repository, acceptance, connector = _harness(tmp_path)

    response = await service.execute(
        auth=_auth(),
        request=_request(),
        route_kind="canonical",
    )

    row = next(iter(repository.rows.values()))
    assert response.status == "published"
    assert row["status"] == "published"
    assert acceptance.consume_calls == 1
    assert connector.publish_snapshots == [connector.snapshot]
    assert len(connector.preflight_contents) == 1
    assert len(connector.publish_contents) == 1
    assert connector.preflight_contents[0]["platform_options"]["platform"] == (
        "tiktok"
    )
    assert connector.publish_contents[0]["platform_options"] == (
        connector.preflight_contents[0]["platform_options"]
    )
    assert calls == [
        "attempt:prepared",
        "acceptance:inspect",
        "connector:preflight",
        "acceptance:consume",
        "attempt:acceptance_consumed",
        "connector:publish",
        "attempt:published",
    ]
