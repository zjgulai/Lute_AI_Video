from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from src.models.acceptance import AcceptanceRecordResponse
from src.models.publish_attempt import PublishAttemptRequest, PublishReceiptV1
from src.routers._deps import ApiKeyType, AuthContext
from src.services.artifact_acceptance import (
    AcceptanceArtifactIntegrityMismatch,
    AcceptanceExpired,
    AcceptanceNotAvailable,
    AcceptanceNotFound,
    AcceptanceStoreUnavailable,
)
from src.services.artifact_identity import (
    ArtifactIdentityError,
    ResolvedOutputArtifact,
    resolve_output_artifact,
)
from src.storage.publish_attempt_repository import PublishAttemptStoreUnavailable

TENANT_ID = "tenant-alpha"
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
VIDEO_BYTES = b"reviewed-publish-attempt-video"
_DEFAULT_PUBLISHER_RESULT = object()


def _tiktok_receipt(**overrides: object) -> dict[str, object]:
    receipt: dict[str, object] = {
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
            "https://www.tiktok.com/@fixture_creator/video/7512345678901234567"
        ),
        "public_visibility_verified": True,
        "observed_at": "2026-07-14T08:00:00Z",
        "verified_by": "video_query",
        "simulated": False,
    }
    receipt.update(overrides)
    return receipt


def _shopify_receipt(**overrides: object) -> dict[str, object]:
    receipt: dict[str, object] = {
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
    receipt.update(overrides)
    return receipt


def _tiktok_success_result() -> dict[str, object]:
    receipt = _tiktok_receipt()
    return {
        "simulated": False,
        "success": True,
        "platform": "tiktok",
        "status": "published",
        "post_id": receipt["post_id"],
        "url": receipt["post_url"],
        "receipt": receipt,
    }


def _shopify_success_result() -> dict[str, object]:
    return {
        "simulated": False,
        "success": True,
        "platform": "shopify",
        "status": "published",
        "post_id": None,
        "url": None,
        "receipt": _shopify_receipt(),
    }


def _service_symbols() -> tuple[type[Any], type[Any]]:
    from src.services.publish_attempt import PublishAttemptError, PublishAttemptService

    return PublishAttemptService, PublishAttemptError


def _auth(
    *,
    tenant_id: str = TENANT_ID,
    permissions: frozenset[str] = frozenset({"artifact:publish"}),
) -> AuthContext:
    return AuthContext(
        tenant_id=tenant_id,
        permissions=permissions,
        key_type=ApiKeyType.TENANT,
        key_id="publisher-fixture",
    )


def _request(
    *,
    platform: str = "tiktok",
    metadata: Mapping[str, Any] | None = None,
) -> PublishAttemptRequest:
    platform_options: dict[str, Any]
    if platform == "tiktok":
        platform_options = {
            "platform": "tiktok",
            "privacy_level": "SELF_ONLY",
            "disable_comment": True,
            "disable_duet": True,
            "disable_stitch": True,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        }
    else:
        platform_options = {
            "platform": "shopify",
            "product_id": "gid://shopify/Product/123456789",
        }
    return PublishAttemptRequest.model_validate(
        {
            "acceptance_id": ACCEPTANCE_ID,
            "platform": platform,
            "platform_options": platform_options,
            "metadata": dict(
                metadata
                if metadata is not None
                else {
                    "title": "Reviewed campaign",
                    "description": "Approved caption",
                    "product_name": "Wearable Breast Pump",
                    "hashtags": ["momlife", "wearablepump"],
                }
            ),
        }
    )


def _artifact_path(
    *,
    resource_type: str = "scenario",
    resource_id: str = "s2_publish_fixture",
) -> str:
    if resource_type == "fast":
        return (
            f"tenants/{TENANT_ID}/pending_review/fast_mode/"
            f"{resource_id}/final.mp4"
        )
    return (
        f"tenants/{TENANT_ID}/pending_review/{resource_id}/"
        "assemble/final.mp4"
    )


def _consumed_record(
    *,
    platform_path: str | None = None,
    resource_type: str = "scenario",
    resource_id: str = "s2_publish_fixture",
    scenario: str = "s2",
    sha256: str | None = None,
    size_bytes: int | None = None,
) -> AcceptanceRecordResponse:
    return AcceptanceRecordResponse.model_validate(
        {
            "acceptance_id": ACCEPTANCE_ID,
            "tenant_id": TENANT_ID,
            "source_resource_type": resource_type,
            "source_resource_id": resource_id,
            "scenario": scenario,
            "artifact": {
                "path": platform_path
                or _artifact_path(
                    resource_type=resource_type,
                    resource_id=resource_id,
                ),
                "sha256": sha256 or hashlib.sha256(VIDEO_BYTES).hexdigest(),
                "size_bytes": size_bytes or len(VIDEO_BYTES),
                "kind": "video",
            },
            "decision": "accepted",
            "status": "consumed",
            "reviewer": {"key_id": "reviewer-a", "key_type": "tenant"},
            "transparency": {
                "schema_version": "acceptance-transparency.v1",
                "ai_generated": True,
                "label": "AI-generated",
                "sidecar_path": (
                    f"tenants/{TENANT_ID}/pending_review/{resource_id}/transparency/"
                    f"transparency-sidecar.v1.{'a' * 64}.json"
                    if resource_type == "scenario"
                    else f"tenants/{TENANT_ID}/pending_review/fast_mode/{resource_id}/"
                    f"transparency/transparency-sidecar.v1.{'a' * 64}.json"
                ),
                "sidecar_sha256": "a" * 64,
                "final_artifact_c2pa_status": "signed_local_readback",
                "independently_validated": False,
            },
            "review_notes": "Never forward reviewer notes.",
            "expires_at": "2030-01-01T00:00:00+00:00",
            "consumed_at": "2026-07-13T00:00:00+00:00",
            "revoked_at": None,
            "idempotent_replay": False,
            "created_at": "2026-07-12T00:00:00+00:00",
            "updated_at": "2026-07-13T00:00:00+00:00",
        }
    )


class FakeAttemptRepository:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls
        self.records: dict[str, dict[str, Any]] = {}
        self.prepared_snapshots: list[dict[str, Any]] = []
        self.create_error: Exception | None = None
        self.transition_errors: dict[str, Exception] = {}
        self.transition_none: set[str] = set()
        self.read_error: Exception | None = None
        self.receipt_lookup_error: Exception | None = None

    async def create_prepared(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        platform: str,
        route_kind: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append("attempt:prepared")
        if self.create_error is not None:
            raise self.create_error
        attempt_id = str(uuid.uuid4())
        content = {
            "schema_version": "publish-attempt.v1",
            "route_kind": route_kind,
            "metadata": dict(metadata),
        }
        row = {
            "id": attempt_id,
            "tenant_id": tenant_id,
            "acceptance_id": acceptance_id,
            "platform": platform,
            "status": "prepared",
            "content": content,
            "post_id": None,
            "url": None,
            "error": None,
            "receipt": None,
            "created_at": "2026-07-14T07:59:00Z",
            "updated_at": "2026-07-14T07:59:00Z",
        }
        self.records[attempt_id] = row
        self.prepared_snapshots.append(json.loads(json.dumps(row)))
        return dict(row)

    async def transition(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_status: str,
        new_status: str,
        content: Mapping[str, Any] | None = None,
        post_id: str | None = None,
        url: str | None = None,
        error_code: str | None = None,
        receipt: PublishReceiptV1 | Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        del tenant_id
        label = {
            "authorization_failed": "attempt:authorization_failed",
            "acceptance_consumed": "attempt:acceptance_consumed",
            "published": "attempt:published",
            "failed": "attempt:failed",
            "ambiguous": "attempt:ambiguous",
        }[new_status]
        self.calls.append(label)
        if new_status in self.transition_errors:
            raise self.transition_errors[new_status]
        if new_status in self.transition_none:
            return None
        row = self.records[attempt_id]
        if row["status"] != expected_status:
            return None
        row["status"] = new_status
        if content is not None:
            row["content"] = dict(content)
        row["post_id"] = post_id
        row["url"] = url
        row["error"] = error_code
        row["receipt"] = (
            receipt.model_dump(mode="json")
            if isinstance(receipt, PublishReceiptV1)
            else (dict(receipt) if receipt is not None else None)
        )
        row["updated_at"] = "2026-07-14T08:00:00Z"
        return dict(row)

    async def get_by_id(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        if self.read_error is not None:
            raise self.read_error
        row = self.records.get(attempt_id)
        if row is None or row["tenant_id"] != tenant_id:
            return None
        return dict(row)

    async def get_published_receipt_by_post_id(
        self,
        *,
        tenant_id: str,
        platform: str,
        post_id: str,
    ) -> PublishReceiptV1 | None:
        if self.receipt_lookup_error is not None:
            raise self.receipt_lookup_error
        matches = [
            row
            for row in self.records.values()
            if row["tenant_id"] == tenant_id
            and row["platform"] == platform
            and row["status"] == "published"
            and row["post_id"] == post_id
            and row["receipt"] is not None
        ]
        if not matches:
            return None
        if len(matches) != 1:
            raise PublishAttemptStoreUnavailable
        return PublishReceiptV1.model_validate(matches[0]["receipt"])


class FakeAcceptanceService:
    def __init__(
        self,
        calls: list[str],
        consumed: AcceptanceRecordResponse,
        *,
        consume_error: Exception | None = None,
        inspect_outcome: str = "unknown",
        inspect_error: Exception | None = None,
        single_use: bool = False,
    ) -> None:
        self.calls = calls
        self.consumed = consumed
        self.inspected: AcceptanceRecordResponse | None = None
        self.consume_error = consume_error
        self.inspect_outcome = inspect_outcome
        self.inspect_error = inspect_error
        self.single_use = single_use
        self.consume_calls = 0
        self.consume_winners = 0
        self.inspect_calls = 0
        self._consumed = False
        self._lock = asyncio.Lock()

    async def inspect_for_publish(self, **kwargs: Any) -> AcceptanceRecordResponse:
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["acceptance_id"] == ACCEPTANCE_ID
        return (self.inspected or self.consumed).model_copy(
            update={"status": "available", "consumed_at": None}
        )

    async def consume_for_publish(self, **kwargs: Any) -> AcceptanceRecordResponse:
        assert kwargs["tenant_id"] == TENANT_ID
        assert kwargs["acceptance_id"] == ACCEPTANCE_ID
        assert kwargs["consumer_operation"] == "distribution.publish"
        assert isinstance(kwargs["consumer_resource_id"], str)
        self.calls.append("acceptance:consume")
        self.consume_calls += 1
        if self.consume_error is not None:
            raise self.consume_error
        if self.single_use:
            async with self._lock:
                if self._consumed:
                    raise AcceptanceNotAvailable
                self._consumed = True
                self.consume_winners += 1
        else:
            self.consume_winners += 1
        return self.consumed

    async def inspect_publish_consume_outcome(self, **kwargs: Any) -> str:
        assert kwargs["consumer_operation"] == "distribution.publish"
        self.calls.append("acceptance:inspect")
        self.inspect_calls += 1
        if self.inspect_error is not None:
            raise self.inspect_error
        return self.inspect_outcome


class FakePublisher:
    def __init__(
        self,
        calls: list[str],
        *,
        result: Any = _DEFAULT_PUBLISHER_RESULT,
        error: Exception | None = None,
    ) -> None:
        self.calls = calls
        self.result = (
            _tiktok_success_result()
            if result is _DEFAULT_PUBLISHER_RESULT
            else result
        )
        self.error = error
        self.call_count = 0
        self.platforms: list[str] = []
        self.contents: list[dict[str, Any]] = []

    async def __call__(self, platform: str, content: dict[str, Any]) -> Any:
        self.calls.append(f"connector:{platform}")
        self.call_count += 1
        self.platforms.append(platform)
        self.contents.append(content)
        await asyncio.sleep(0)
        if self.error is not None:
            raise self.error
        return self.result


@dataclass(slots=True)
class ServiceHarness:
    output_dir: Path
    artifact_absolute: Path
    calls: list[str]
    repository: FakeAttemptRepository
    acceptance: FakeAcceptanceService
    publisher: FakePublisher
    service: Any


def _build_harness(
    tmp_path: Path,
    *,
    platform: str = "tiktok",
    resource_type: str = "scenario",
    resource_id: str = "s2_publish_fixture",
    scenario: str = "s2",
    readiness_ready: bool = True,
    consume_error: Exception | None = None,
    inspect_outcome: str = "unknown",
    inspect_error: Exception | None = None,
    single_use: bool = False,
    publisher_result: Any = _DEFAULT_PUBLISHER_RESULT,
    publisher_error: Exception | None = None,
    artifact_resolver: Callable[..., ResolvedOutputArtifact] = resolve_output_artifact,
) -> ServiceHarness:
    PublishAttemptService, _ = _service_symbols()
    output_dir = tmp_path / "output"
    relative = _artifact_path(
        resource_type=resource_type,
        resource_id=resource_id,
    )
    absolute = output_dir / relative
    absolute.parent.mkdir(parents=True, exist_ok=True)
    absolute.write_bytes(VIDEO_BYTES)
    consumed = _consumed_record(
        platform_path=relative,
        resource_type=resource_type,
        resource_id=resource_id,
        scenario=scenario,
    )
    calls: list[str] = []
    repository = FakeAttemptRepository(calls)
    acceptance = FakeAcceptanceService(
        calls,
        consumed,
        consume_error=consume_error,
        inspect_outcome=inspect_outcome,
        inspect_error=inspect_error,
        single_use=single_use,
    )
    publisher = FakePublisher(
        calls,
        result=publisher_result,
        error=publisher_error,
    )

    def readiness(selected_platform: str) -> SimpleNamespace:
        calls.append(f"readiness:{selected_platform}")
        return SimpleNamespace(
            platform=selected_platform,
            ready=readiness_ready,
            reason=(None if readiness_ready else "missing_credentials"),
        )

    service = PublishAttemptService(
        attempt_repository=repository,
        acceptance_service=acceptance,
        output_dir=output_dir,
        readiness_inspector=readiness,
        artifact_resolver=artifact_resolver,
        publisher=publisher,
    )
    return ServiceHarness(
        output_dir,
        absolute,
        calls,
        repository,
        acceptance,
        publisher,
        service,
    )


def _only_record(repository: FakeAttemptRepository) -> dict[str, Any]:
    assert len(repository.records) == 1
    return next(iter(repository.records.values()))


def test_readiness_reports_missing_credentials_without_exposing_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry
    from src.connectors.base import ConnectorCredentialState

    calls = 0

    def credential_state() -> ConnectorCredentialState:
        nonlocal calls
        calls += 1
        return ConnectorCredentialState(False, "missing_credentials")

    monkeypatch.setattr(
        "src.connectors.tiktok_connector._credential_state",
        credential_state,
    )
    monkeypatch.setattr(
        registry,
        "get_connector",
        lambda _: pytest.fail("readiness must not instantiate a connector"),
    )

    readiness = registry.inspect_publish_readiness("tiktok")

    assert calls == 1
    assert readiness.ready is False
    assert readiness.reason == "missing_credentials"
    assert readiness.platform == "tiktok"
    assert "token" not in repr(readiness).lower()
    with pytest.raises((AttributeError, TypeError)):
        setattr(readiness, "ready", True)


@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
def test_readiness_ready_is_no_network_and_calls_only_existing_predicate(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors import registry
    from src.connectors.base import ConnectorCredentialState

    calls: list[str] = []
    monkeypatch.setattr(
        f"src.connectors.{platform}_connector._credential_state",
        lambda: calls.append(platform) or ConnectorCredentialState(True, None),
    )
    monkeypatch.setattr(
        registry,
        "get_connector",
        lambda _: pytest.fail("readiness must not instantiate a connector"),
    )

    readiness = registry.inspect_publish_readiness(platform)

    assert calls == [platform]
    assert readiness.platform == platform
    assert readiness.ready is True
    assert readiness.reason is None


def test_readiness_rejects_unknown_platform() -> None:
    from src.connectors.registry import inspect_publish_readiness

    with pytest.raises(ValueError, match="Unsupported platform"):
        inspect_publish_readiness("instagram")


@pytest.mark.asyncio
async def test_tiktok_exact_order_payload_and_safe_audit_content(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)

    response = await harness.service.execute(
        auth=_auth(),
        request=_request(),
        route_kind="canonical",
    )

    assert harness.calls == [
        "readiness:tiktok",
        "attempt:prepared",
        "acceptance:consume",
        "attempt:acceptance_consumed",
        "connector:tiktok",
        "attempt:published",
    ]
    assert harness.publisher.contents == [
        {
            "video_path": str(harness.artifact_absolute.resolve()),
            "title": "Reviewed campaign",
            "description": (
                "Approved caption\n#momlife #wearablepump\nAI-generated content."
            ),
            "tags": ["momlife", "wearablepump"],
            "disclosure": {
                "schema_version": "publish-disclosure.v1",
                "label": "AI-generated",
                "visible_text": "AI-generated content.",
                "sidecar_sha256": "a" * 64,
                "final_artifact_c2pa_status": "signed_local_readback",
                "verification_scope": "local_reader_only",
                "independently_validated": False,
            },
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
    ]
    prepared = harness.repository.prepared_snapshots[0]["content"]
    assert set(prepared) == {"schema_version", "route_kind", "metadata"}
    assert "source" not in prepared
    assert "artifact" not in prepared
    row = _only_record(harness.repository)
    assert row["status"] == "published"
    assert row["content"]["source"] == {
        "resource_type": "scenario",
        "resource_id": "s2_publish_fixture",
        "scenario": "s2",
    }
    assert row["content"]["artifact"] == {
        "path": _artifact_path(),
        "sha256": hashlib.sha256(VIDEO_BYTES).hexdigest(),
        "size_bytes": len(VIDEO_BYTES),
        "kind": "video",
    }
    assert row["content"]["effective_metadata"] == {
        "title": "Reviewed campaign",
        "description": (
            "Approved caption\n#momlife #wearablepump\nAI-generated content."
        ),
        "tags": ["momlife", "wearablepump"],
    }
    assert row["content"]["disclosure"]["label"] == "AI-generated"
    assert str(harness.artifact_absolute.resolve()) not in repr(
        harness.repository.records
    )
    assert "Never forward reviewer notes" not in repr(harness.repository.records)
    assert response.model_dump(mode="json") == {
        "publish_attempt_id": row["id"],
        "acceptance_id": ACCEPTANCE_ID,
        "platform": "tiktok",
        "status": "published",
        "success": True,
        "post_id": "7512345678901234567",
        "post_url": (
            "https://www.tiktok.com/@fixture_creator/video/7512345678901234567"
        ),
        "receipt": _tiktok_receipt(),
        "acceptance_consumed": True,
        "retry_allowed": False,
    }


@pytest.mark.asyncio
async def test_service_readback_and_legacy_status_use_only_durable_tenant_receipt(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)
    published = await harness.service.execute(
        auth=_auth(),
        request=_request(),
        route_kind="canonical",
    )

    readback = await harness.service.get_attempt_readback(
        auth=_auth(),
        attempt_id=published.publish_attempt_id,
    )
    status = await harness.service.get_durable_tiktok_status(
        auth=_auth(),
        post_id="7512345678901234567",
    )

    assert readback is not None
    assert readback.receipt == published.receipt
    assert readback.acceptance_consumed is True
    assert readback.retry_allowed is False
    assert "content" not in readback.model_dump(mode="json")
    assert status is not None
    assert status.post_id == published.receipt.post_id
    assert status.status == "PUBLISH_COMPLETE"
    assert harness.publisher.call_count == 1

    assert await harness.service.get_attempt_readback(
        auth=_auth(tenant_id="tenant-other"),
        attempt_id=published.publish_attempt_id,
    ) is None
    assert await harness.service.get_durable_tiktok_status(
        auth=_auth(tenant_id="tenant-other"),
        post_id="7512345678901234567",
    ) is None


@pytest.mark.asyncio
async def test_shopify_exact_payload_and_fast_source_prefix(tmp_path: Path) -> None:
    harness = _build_harness(
        tmp_path,
        platform="shopify",
        resource_type="fast",
        resource_id="fast_publish_fixture",
        scenario="fast",
        publisher_result={
            **_shopify_success_result(),
            "error": "ignored-remote-message",
            "unknown": str(tmp_path / "must-not-persist"),
        },
    )

    response = await harness.service.execute(
        auth=_auth(),
        request=_request(platform="shopify"),
        route_kind="legacy_adapter",
    )

    assert harness.publisher.contents == [
        {
            "video_path": str(harness.artifact_absolute.resolve()),
            "title": "[AI-generated] Reviewed campaign",
            "product_name": "Wearable Breast Pump",
            "disclosure": {
                "schema_version": "publish-disclosure.v1",
                "label": "AI-generated",
                "visible_text": "AI-generated content.",
                "sidecar_sha256": "a" * 64,
                "final_artifact_c2pa_status": "signed_local_readback",
                "verification_scope": "local_reader_only",
                "independently_validated": False,
            },
            "platform_options": {
                "platform": "shopify",
                "product_id": "gid://shopify/Product/123456789",
            },
        }
    ]
    row = _only_record(harness.repository)
    assert row["content"]["source"] == {
        "resource_type": "fast",
        "resource_id": "fast_publish_fixture",
        "scenario": "fast",
    }
    assert row["content"]["artifact"]["path"] == _artifact_path(
        resource_type="fast",
        resource_id="fast_publish_fixture",
    )
    assert row["content"]["effective_metadata"] == {
        "title": "[AI-generated] Reviewed campaign",
        "product_name": "Wearable Breast Pump",
    }
    assert row["content"]["disclosure"]["label"] == "AI-generated"
    assert "ignored-remote-message" not in repr(row)
    assert "must-not-persist" not in repr(row)
    assert response.post_id is None
    assert response.post_url is None
    assert response.receipt.model_dump(mode="json") == _shopify_receipt()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        (
            {"hook": "Hook fallback", "tags": ["one", "two"]},
            {
                "title": "Hook fallback",
                "description": "Hook fallback\n#one #two\nAI-generated content.",
                "tags": ["one", "two"],
            },
        ),
        (
            {},
            {
                "title": "AI-generated video",
                "description": "AI-generated video\nAI-generated content.",
                "tags": [],
            },
        ),
    ],
)
async def test_tiktok_metadata_fallbacks_are_deterministic(
    tmp_path: Path,
    metadata: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    harness = _build_harness(tmp_path)

    await harness.service.execute(
        auth=_auth(),
        request=_request(metadata=metadata),
        route_kind="canonical",
    )

    content = dict(harness.publisher.contents[0])
    content.pop("video_path")
    content.pop("platform_options")
    disclosure = content.pop("disclosure")
    assert content == expected
    assert disclosure == {
        "schema_version": "publish-disclosure.v1",
        "label": "AI-generated",
        "visible_text": "AI-generated content.",
        "sidecar_sha256": "a" * 64,
        "final_artifact_c2pa_status": "signed_local_readback",
        "verification_scope": "local_reader_only",
        "independently_validated": False,
    }


@pytest.mark.asyncio
async def test_client_cannot_remove_or_duplicate_server_disclosure(tmp_path: Path) -> None:
    harness = _build_harness(tmp_path)

    await harness.service.execute(
        auth=_auth(),
        request=_request(
            metadata={
                "description": "AI-generated content.",
                "title": "Campaign",
            }
        ),
        route_kind="canonical",
    )

    description = harness.publisher.contents[0]["description"]
    assert description == "AI-generated content."
    assert description.count("AI-generated content.") == 1


@pytest.mark.asyncio
async def test_changed_transparency_between_inspect_and_consume_fails_closed(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path)
    inspected = harness.acceptance.consumed
    changed = inspected.model_dump(mode="json")
    changed_transparency = changed["transparency"]
    assert isinstance(changed_transparency, dict)
    changed_transparency["sidecar_sha256"] = "b" * 64
    harness.acceptance.inspected = inspected
    harness.acceptance.consumed = AcceptanceRecordResponse.model_validate(changed)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 500
    assert error.value.code == "publish_attempt_state_unknown"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.acceptance.consume_winners == 1
    assert harness.publisher.call_count == 0
    assert _only_record(harness.repository)["status"] == "prepared"


@pytest.mark.asyncio
async def test_service_rejects_missing_tenant_or_publish_permission_before_readiness(
    tmp_path: Path,
) -> None:
    for auth in (
        _auth(tenant_id=""),
        _auth(permissions=frozenset({"artifact:accept"})),
    ):
        harness = _build_harness(tmp_path / str(uuid.uuid4()))
        with pytest.raises(HTTPException) as error:
            await harness.service.execute(
                auth=auth,
                request=_request(),
                route_kind="canonical",
            )
        assert error.value.status_code in {401, 403}
        assert harness.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route_kind",
    ["unexpected_route_kind", None, 1],
    ids=["unexpected-string", "none", "integer"],
)
async def test_invalid_route_kind_fails_before_every_dependency(
    tmp_path: Path,
    route_kind: Any,
) -> None:
    harness = _build_harness(tmp_path)

    with pytest.raises(ValueError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind=route_kind,
        )

    assert str(error.value) == "route_kind is invalid"
    assert str(route_kind) not in str(error.value)
    assert harness.calls == []
    assert harness.repository.records == {}
    assert harness.acceptance.consume_calls == 0
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
async def test_authentication_precedes_invalid_route_kind_validation(
    tmp_path: Path,
) -> None:
    harness = _build_harness(tmp_path)

    with pytest.raises(HTTPException) as error:
        await harness.service.execute(
            auth=_auth(permissions=frozenset({"artifact:accept"})),
            request=_request(),
            route_kind="unexpected_route_kind",
        )

    assert error.value.status_code == 403
    assert harness.calls == []


@pytest.mark.asyncio
async def test_readiness_false_creates_no_attempt_or_acceptance_side_effect(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, readiness_ready=False)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 503
    assert error.value.detail.model_dump(mode="json") == {
        "code": "publish_connector_not_ready",
        "publish_attempt_id": None,
        "acceptance_consumed": False,
        "retry_allowed": True,
    }
    assert harness.calls == ["readiness:tiktok"]
    assert harness.repository.records == {}
    assert harness.acceptance.consume_calls == 0
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
async def test_prepared_store_failure_leaves_acceptance_untouched(tmp_path: Path) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path)
    harness.repository.create_error = PublishAttemptStoreUnavailable(
        "raw-store-path-/private/db"
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 503
    assert error.value.code == "publish_attempt_store_unavailable"
    assert error.value.detail.publish_attempt_id is None
    assert error.value.detail.acceptance_consumed is False
    assert error.value.detail.retry_allowed is True
    assert harness.acceptance.consume_calls == 0
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("acceptance_error", "status_code", "code"),
    [
        (AcceptanceNotFound(), 404, "acceptance_not_found"),
        (AcceptanceExpired(), 409, "acceptance_expired"),
        (AcceptanceNotAvailable(), 409, "acceptance_not_available"),
        (
            AcceptanceArtifactIntegrityMismatch(),
            409,
            "acceptance_artifact_integrity_mismatch",
        ),
    ],
)
async def test_typed_acceptance_failure_never_calls_connector(
    tmp_path: Path,
    acceptance_error: Exception,
    status_code: int,
    code: str,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, consume_error=acceptance_error)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == status_code
    assert error.value.code == code
    assert error.value.detail.acceptance_consumed is False
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 0
    row = _only_record(harness.repository)
    assert row["status"] == "authorization_failed"
    assert row["error"] == code
    assert "artifact" not in row["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "outcome",
        "status_code",
        "code",
        "consumed",
        "retry_allowed",
        "expected_status",
    ),
    [
        (
            "available_not_consumed",
            503,
            "acceptance_store_unavailable",
            False,
            True,
            "authorization_failed",
        ),
        (
            "consumed_by_another_attempt",
            409,
            "acceptance_not_available",
            False,
            False,
            "authorization_failed",
        ),
        (
            "not_available",
            409,
            "acceptance_not_available",
            False,
            False,
            "authorization_failed",
        ),
        (
            "consumed_by_this_attempt",
            500,
            "publish_attempt_state_unknown",
            True,
            False,
            "prepared",
        ),
        (
            "unknown",
            500,
            "publish_attempt_state_unknown",
            None,
            False,
            "prepared",
        ),
    ],
)
async def test_consume_store_failure_inspects_once_and_never_publishes(
    tmp_path: Path,
    outcome: str,
    status_code: int,
    code: str,
    consumed: bool | None,
    retry_allowed: bool,
    expected_status: str,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        consume_error=AcceptanceStoreUnavailable(),
        inspect_outcome=outcome,
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == status_code
    assert error.value.code == code
    assert error.value.detail.acceptance_consumed is consumed
    assert error.value.detail.retry_allowed is retry_allowed
    assert harness.acceptance.consume_calls == 1
    assert harness.acceptance.inspect_calls == 1
    assert harness.publisher.call_count == 0
    row = _only_record(harness.repository)
    assert row["status"] == expected_status


@pytest.mark.asyncio
async def test_consume_store_inspector_failure_is_unknown_and_nonretryable(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        consume_error=AcceptanceStoreUnavailable(),
        inspect_error=AcceptanceStoreUnavailable(),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_attempt_state_unknown"
    assert error.value.detail.acceptance_consumed is None
    assert error.value.detail.retry_allowed is False
    assert harness.acceptance.inspect_calls == 1
    assert harness.acceptance.consume_calls == 1
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["raise", "stale_cas"])
async def test_mark_acceptance_consumed_failure_stops_before_connector(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path)
    if failure_mode == "raise":
        harness.repository.transition_errors["acceptance_consumed"] = (
            PublishAttemptStoreUnavailable("raw-store-error")
        )
    else:
        harness.repository.transition_none.add("acceptance_consumed")

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 500
    assert error.value.code == "publish_attempt_state_unknown"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.acceptance.consume_winners == 1
    assert harness.publisher.call_count == 0
    assert _only_record(harness.repository)["status"] == "prepared"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_mode", ["resolver_error", "hash_mismatch", "size_mismatch"])
async def test_post_consume_artifact_integrity_failure_is_durable_and_no_publish(
    tmp_path: Path,
    failure_mode: str,
) -> None:
    _, PublishAttemptError = _service_symbols()
    resolver_calls = 0

    def failing_resolver(*args: Any, **kwargs: Any) -> ResolvedOutputArtifact:
        nonlocal resolver_calls
        resolver_calls += 1
        if resolver_calls == 1:
            return resolve_output_artifact(*args, **kwargs)
        if failure_mode == "resolver_error":
            raise ArtifactIdentityError("raw-private-path-/host/final.mp4")
        resolved = resolve_output_artifact(*args, **kwargs)
        return ResolvedOutputArtifact(
            canonical_path=resolved.canonical_path,
            absolute_path=resolved.absolute_path,
            sha256=("0" * 64 if failure_mode == "hash_mismatch" else resolved.sha256),
            size_bytes=(resolved.size_bytes + 1 if failure_mode == "size_mismatch" else resolved.size_bytes),
        )

    harness = _build_harness(tmp_path, artifact_resolver=failing_resolver)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 500
    assert error.value.code == "publish_artifact_unavailable_after_consume"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 0
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["error"] == "publish_artifact_unavailable_after_consume"


@pytest.mark.asyncio
async def test_explicit_connector_false_is_stable_failed_outcome(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, PublishAttemptError = _service_symbols()
    sentinel = f"raw connector message credential=fixture {tmp_path}/private.mp4"
    harness = _build_harness(
        tmp_path,
        publisher_result={
            "simulated": False,
            "success": False,
            "platform": "tiktok",
            "error": sentinel,
            "response": {"body": sentinel},
        },
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 502
    assert error.value.code == "publish_connector_failed"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["error"] == "publish_connector_failed"
    evidence = caplog.text + repr(row) + repr(error.value.detail)
    assert sentinel not in evidence
    assert str(harness.artifact_absolute.resolve()) not in evidence


@pytest.mark.asyncio
async def test_explicit_connector_failure_persists_only_safe_partial_receipt(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    partial = _tiktok_receipt(
        provider_resource_id=None,
        provider_status="FAILED",
        post_id=None,
        post_url=None,
        public_visibility_verified=False,
        verified_by=None,
    )
    harness = _build_harness(
        tmp_path,
        publisher_result={
            "simulated": False,
            "success": False,
            "platform": "tiktok",
            "status": "failed",
            "receipt": partial,
        },
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_connector_failed"
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["post_id"] is None
    assert row["url"] is None
    assert row["receipt"] == partial


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_simulated_connector_result_is_durable_failed_after_consume(
    success: bool,
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_result={
            "simulated": True,
            "success": success,
            "platform": "shopify",
            "post_id": "must-not-be-trusted",
        },
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 502
    assert error.value.code == "publish_connector_simulated"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 1
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["error"] == "publish_connector_simulated"
    assert row["post_id"] is None


@pytest.mark.asyncio
async def test_known_simulated_dependency_is_blocked_before_attempt_or_consume(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        readiness_ready=False,
        publisher_result={"simulated": True, "success": True},
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 503
    assert error.value.code == "publish_connector_not_ready"
    assert error.value.detail.acceptance_consumed is False
    assert error.value.detail.retry_allowed is True
    assert harness.repository.records == {}
    assert harness.acceptance.consume_calls == 0
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
async def test_post_consume_credential_race_is_failed_without_retry_or_restore(
    tmp_path: Path,
) -> None:
    from src.connectors.base import ConnectorCredentialNotReady

    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_error=ConnectorCredentialNotReady("missing_credentials"),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 502
    assert error.value.code == "publish_connector_not_ready_after_consume"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 1
    assert harness.acceptance.consume_calls == 1
    row = _only_record(harness.repository)
    assert row["status"] == "failed"
    assert row["error"] == "publish_connector_not_ready_after_consume"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connector_result",
    [
        {},
        {"simulated": None, "success": True},
        {"simulated": 0, "success": True},
        {"simulated": "false", "success": True},
        {"simulated": False},
        {"simulated": False, "success": 1},
        {"simulated": False, "success": True, "platform": "shopify"},
        {"simulated": False, "success": True, "post_id": "unsafe\npost"},
        {
            "simulated": False,
            "success": True,
            "url": "file:///private/final.mp4",
        },
    ],
)
async def test_missing_or_malformed_truth_is_durable_ambiguous(
    connector_result: dict[str, Any],
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, publisher_result=connector_result)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    row = _only_record(harness.repository)
    assert row["status"] == "ambiguous"
    assert row["error"] == "publish_outcome_ambiguous"
    assert harness.publisher.call_count == 1


@pytest.mark.asyncio
async def test_typed_connector_ambiguity_remains_durable_ambiguous(
    tmp_path: Path,
) -> None:
    from src.connectors.base import ConnectorOutcomeAmbiguous

    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_error=ConnectorOutcomeAmbiguous(),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    assert _only_record(harness.repository)["status"] == "ambiguous"
    assert harness.publisher.call_count == 1


@pytest.mark.asyncio
async def test_typed_ambiguity_persists_safe_partial_receipt(tmp_path: Path) -> None:
    from src.connectors.base import ConnectorOutcomeAmbiguous

    _, PublishAttemptError = _service_symbols()
    partial = _tiktok_receipt(
        provider_resource_id=None,
        provider_status="PROCESSING_UPLOAD",
        post_id=None,
        post_url=None,
        public_visibility_verified=False,
        verified_by=None,
    )
    harness = _build_harness(
        tmp_path,
        publisher_error=ConnectorOutcomeAmbiguous(partial_receipt=partial),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    row = _only_record(harness.repository)
    assert row["status"] == "ambiguous"
    assert row["receipt"] == partial


@pytest.mark.asyncio
async def test_typed_ambiguity_drops_contradictory_published_receipt(
    tmp_path: Path,
) -> None:
    from src.connectors.base import ConnectorOutcomeAmbiguous

    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(
        tmp_path,
        publisher_error=ConnectorOutcomeAmbiguous(
            partial_receipt=_tiktok_receipt()
        ),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    row = _only_record(harness.repository)
    assert row["status"] == "ambiguous"
    assert row["receipt"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "connector_result",
    [
        None,
        [],
        {},
        {"simulated": False, "success": "true"},
        {"simulated": False, "success": True, "platform": "shopify"},
        {"simulated": False, "success": False, "platform": "shopify"},
        {"simulated": False, "success": True, "post_id": "unsafe\npost"},
        {
            "simulated": False,
            "success": True,
            "url": "file:///private/final.mp4",
        },
    ],
)
async def test_malformed_or_contradictory_connector_result_is_ambiguous(
    tmp_path: Path,
    connector_result: Any,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, publisher_result=connector_result)

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 502
    assert error.value.code == "publish_outcome_ambiguous"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    row = _only_record(harness.repository)
    assert row["status"] == "ambiguous"
    assert row["error"] == "publish_outcome_ambiguous"
    assert harness.publisher.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [TimeoutError, RuntimeError])
async def test_connector_exception_is_ambiguous_without_raw_exception_text(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    error_type: type[Exception],
) -> None:
    _, PublishAttemptError = _service_symbols()
    sentinel = f"raw-exception credential=fixture path={tmp_path}/private.mp4"
    harness = _build_harness(
        tmp_path,
        publisher_error=error_type(sentinel),
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_outcome_ambiguous"
    assert _only_record(harness.repository)["status"] == "ambiguous"
    assert sentinel not in caplog.text
    assert str(harness.artifact_absolute.resolve()) not in caplog.text
    assert error_type.__name__ in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("connector_result", "terminal_state"),
    [
        (
            _tiktok_success_result(),
            "published",
        ),
        ({"simulated": False, "success": False}, "failed"),
        ({"simulated": False, "success": "unknown"}, "ambiguous"),
    ],
)
async def test_terminal_persistence_failure_is_nonretryable_state_unknown(
    tmp_path: Path,
    connector_result: Any,
    terminal_state: str,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, publisher_result=connector_result)
    harness.repository.transition_errors[terminal_state] = (
        PublishAttemptStoreUnavailable("raw-terminal-store-error")
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.status_code == 500
    assert error.value.code == "publish_attempt_state_unknown"
    assert error.value.detail.acceptance_consumed is True
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 1
    assert _only_record(harness.repository)["status"] == "acceptance_consumed"


@pytest.mark.asyncio
async def test_authorization_failure_audit_failure_becomes_state_unknown(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, consume_error=AcceptanceNotAvailable())
    harness.repository.transition_errors["authorization_failed"] = (
        PublishAttemptStoreUnavailable("raw-audit-store-error")
    )

    with pytest.raises(PublishAttemptError) as error:
        await harness.service.execute(
            auth=_auth(),
            request=_request(),
            route_kind="canonical",
        )

    assert error.value.code == "publish_attempt_state_unknown"
    assert error.value.detail.acceptance_consumed is False
    assert error.value.detail.retry_allowed is False
    assert harness.publisher.call_count == 0


@pytest.mark.asyncio
async def test_twenty_concurrent_attempts_have_one_consume_and_connector_winner(
    tmp_path: Path,
) -> None:
    _, PublishAttemptError = _service_symbols()
    harness = _build_harness(tmp_path, single_use=True)
    request = _request()

    results = await asyncio.gather(
        *(
            harness.service.execute(
                auth=_auth(),
                request=request,
                route_kind="canonical",
            )
            for _ in range(20)
        ),
        return_exceptions=True,
    )

    assert harness.publisher.call_count == 1
    assert harness.acceptance.consume_winners == 1
    assert harness.acceptance.consume_calls == 20
    assert sum(
        isinstance(result, PublishAttemptError)
        and getattr(result, "code", None) == "acceptance_not_available"
        for result in results
    ) == 19
    assert sum(not isinstance(result, Exception) for result in results) == 1
    statuses = [row["status"] for row in harness.repository.records.values()]
    assert statuses.count("published") == 1
    assert statuses.count("authorization_failed") == 19
    assert all(
        row["error"] in {None, "acceptance_not_available"}
        for row in harness.repository.records.values()
    )
