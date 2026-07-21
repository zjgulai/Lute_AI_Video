"""Single-use acceptance orchestration for one connector publish attempt."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import Any, Literal, NoReturn

from fastapi import HTTPException
from pydantic import ValidationError

from src.config import OUTPUT_DIR
from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorOutcomeAmbiguous,
    ConnectorPreflightRejected,
    PlatformConnector,
)
from src.connectors.registry import (
    PublishConnectorReadiness,
    get_connector,
    inspect_publish_readiness,
)
from src.models.acceptance import AcceptanceRecordResponse
from src.models.publish_attempt import (
    DurableTikTokStatusResponse,
    PublishAttemptErrorCode,
    PublishAttemptErrorDetail,
    PublishAttemptReadbackResponse,
    PublishAttemptRequest,
    PublishAttemptResponse,
    PublishMetadata,
    PublishReceiptV1,
    ShopifyPublishOptions,
    TikTokPublishOptions,
)
from src.routers._deps import AuthContext
from src.services.artifact_acceptance import (
    AcceptanceArtifactIntegrityMismatch,
    AcceptanceExpired,
    AcceptanceNotAvailable,
    AcceptanceNotFound,
    AcceptanceStoreUnavailable,
    ArtifactAcceptanceService,
    get_artifact_acceptance_service,
)
from src.services.artifact_identity import (
    ArtifactIdentityError,
    ResolvedOutputArtifact,
    resolve_output_artifact,
)
from src.storage.publish_attempt_repository import (
    PublishAttemptRepository,
    PublishAttemptStoreUnavailable,
)

logger = logging.getLogger(__name__)

RouteKind = Literal["canonical", "legacy_adapter"]
ReadinessInspector = Callable[[str], PublishConnectorReadiness]
ArtifactResolver = Callable[..., ResolvedOutputArtifact]
Publisher = Callable[[str, dict[str, Any]], Awaitable[Mapping[str, Any]]]
ConnectorFactory = Callable[[str], PlatformConnector]

_VIDEO_SUFFIXES = {".mp4", ".webm"}
_MISSING = object()


class PublishAttemptError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: PublishAttemptErrorCode,
        publish_attempt_id: str | None,
        acceptance_consumed: bool | None,
        retry_allowed: bool,
    ) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.detail = PublishAttemptErrorDetail(
            code=code,
            publish_attempt_id=publish_attempt_id,
            acceptance_consumed=acceptance_consumed,
            retry_allowed=retry_allowed,
        )


def _source_prefix(
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
) -> str:
    if resource_type == "fast":
        return (
            f"tenants/{tenant_id}/pending_review/fast_mode/"
            f"{resource_id}"
        )
    return f"tenants/{tenant_id}/pending_review/{resource_id}"


def _tiktok_content(
    metadata: PublishMetadata,
    options: TikTokPublishOptions,
    video_path: Path,
) -> dict[str, Any]:
    title = metadata.title or metadata.hook or "AI-generated video"
    description = metadata.description or metadata.hook or title
    tags = list(metadata.hashtags or metadata.tags)
    if tags:
        description = description + "\n" + " ".join(f"#{tag}" for tag in tags)
    return {
        "video_path": str(video_path),
        "title": title,
        "description": description,
        "tags": tags,
        "platform_options": options.model_dump(mode="json"),
    }


def _shopify_content(
    metadata: PublishMetadata,
    options: ShopifyPublishOptions,
    video_path: Path,
) -> dict[str, Any]:
    title = metadata.title or metadata.hook or "AI-generated video"
    return {
        "video_path": str(video_path),
        "title": title,
        "product_name": metadata.product_name or title,
        "platform_options": options.model_dump(mode="json"),
    }


class _InjectedPublisherConnector:
    """Compatibility adapter for existing dependency-injected service tests."""

    def __init__(self, platform: str, publisher: Publisher) -> None:
        self.platform = platform
        self.publisher = publisher

    async def preflight(self, content: dict[str, Any]) -> object:
        del content
        return {"platform": self.platform, "injected_test_preflight": True}

    async def publish(
        self,
        content: dict[str, Any],
        *,
        preflight: object,
    ) -> Mapping[str, Any]:
        del preflight
        return await self.publisher(self.platform, content)


class PublishAttemptService:
    def __init__(
        self,
        attempt_repository: PublishAttemptRepository | None = None,
        acceptance_service: ArtifactAcceptanceService | None = None,
        *,
        output_dir: Path | None = None,
        readiness_inspector: ReadinessInspector = inspect_publish_readiness,
        artifact_resolver: ArtifactResolver = resolve_output_artifact,
        connector_factory: ConnectorFactory = get_connector,
        publisher: Publisher | None = None,
    ) -> None:
        self.attempt_repository = (
            attempt_repository
            if attempt_repository is not None
            else PublishAttemptRepository()
        )
        self.acceptance_service = (
            acceptance_service
            if acceptance_service is not None
            else get_artifact_acceptance_service()
        )
        self.output_dir = output_dir if output_dir is not None else OUTPUT_DIR
        self.readiness_inspector = readiness_inspector
        self.artifact_resolver = artifact_resolver
        if publisher is None:
            self.connector_factory = connector_factory
        else:
            if connector_factory is not get_connector:
                raise ValueError("connector_factory and publisher are mutually exclusive")
            self.connector_factory = lambda platform: _InjectedPublisherConnector(
                platform,
                publisher,
            )

    async def execute(
        self,
        *,
        auth: AuthContext,
        request: PublishAttemptRequest,
        route_kind: RouteKind,
    ) -> PublishAttemptResponse:
        trace_id = uuid.uuid4().hex[:8]
        tenant_id = self._require_tenant(auth)
        if route_kind not in ("canonical", "legacy_adapter"):
            raise ValueError("route_kind is invalid")
        readiness = self.readiness_inspector(request.platform)
        if not readiness.ready:
            self._raise_error(
                status_code=503,
                code="publish_connector_not_ready",
                attempt_id=None,
                acceptance_consumed=False,
                retry_allowed=True,
                platform=request.platform,
                trace_id=trace_id,
            )

        metadata = request.metadata.model_dump(mode="json", exclude_none=True)
        try:
            prepared = await self.attempt_repository.create_prepared(
                tenant_id=tenant_id,
                acceptance_id=request.acceptance_id,
                platform=request.platform,
                route_kind=route_kind,
                metadata=metadata,
            )
        except PublishAttemptStoreUnavailable as exc:
            self._raise_error(
                status_code=503,
                code="publish_attempt_store_unavailable",
                attempt_id=None,
                acceptance_consumed=False,
                retry_allowed=True,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        attempt_id = prepared["id"]

        inspected = await self._inspect_acceptance_or_fail_closed(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            request=request,
            trace_id=trace_id,
        )
        try:
            inspected_artifact = self._resolve_consumed_artifact(
                tenant_id=tenant_id,
                consumed=inspected,
            )
            preflight_content = self._build_connector_content(
                request=request,
                video_path=inspected_artifact.absolute_path,
            )
        except (ArtifactIdentityError, OSError, RuntimeError, ValueError) as exc:
            await self._record_authorization_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code="acceptance_artifact_integrity_mismatch",
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=409,
                code="acceptance_artifact_integrity_mismatch",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        connector, preflight = await self._preflight_or_fail_closed(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            request=request,
            connector_content=preflight_content,
            trace_id=trace_id,
        )

        consumed = await self._consume_or_fail_closed(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            request=request,
            trace_id=trace_id,
        )
        try:
            content = self._build_consumed_audit_content(
                tenant_id=tenant_id,
                route_kind=route_kind,
                request=request,
                consumed=consumed,
            )
        except (AttributeError, TypeError, ValueError) as exc:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=True,
                retry_allowed=False,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        await self._mark_acceptance_consumed_or_stop(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=request.platform,
            content=content,
            trace_id=trace_id,
        )

        try:
            artifact = self._resolve_consumed_artifact(
                tenant_id=tenant_id,
                consumed=consumed,
            )
        except (ArtifactIdentityError, OSError, RuntimeError) as exc:
            await self._fail_artifact_after_consume(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        connector_content = self._build_connector_content(
            request=request,
            video_path=artifact.absolute_path,
        )
        return await self._publish_once_and_persist(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            request=request,
            connector=connector,
            preflight=preflight,
            connector_content=connector_content,
            trace_id=trace_id,
        )

    async def get_attempt_readback(
        self,
        *,
        auth: AuthContext,
        attempt_id: str,
    ) -> PublishAttemptReadbackResponse | None:
        tenant_id = self._require_tenant(auth)
        try:
            record = await self.attempt_repository.get_by_id(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
            )
            if record is None:
                return None
            status = record.get("status")
            error_code = record.get("error")
            if status == "prepared":
                acceptance_consumed: bool | None = None
            elif status in {"authorization_failed", "preflight_failed"}:
                acceptance_consumed = False
            else:
                acceptance_consumed = True
            retry_allowed = status == "preflight_failed" or (
                status == "authorization_failed"
                and error_code == "acceptance_store_unavailable"
            )
            return PublishAttemptReadbackResponse.model_validate(
                {
                    "publish_attempt_id": record.get("id"),
                    "acceptance_id": record.get("acceptance_id"),
                    "platform": record.get("platform"),
                    "status": status,
                    "error_code": error_code,
                    "post_id": record.get("post_id"),
                    "post_url": record.get("url"),
                    "receipt": record.get("receipt"),
                    "acceptance_consumed": acceptance_consumed,
                    "retry_allowed": retry_allowed,
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                }
            )
        except PublishAttemptStoreUnavailable:
            raise
        except (TypeError, ValueError, ValidationError):
            raise PublishAttemptStoreUnavailable from None

    async def get_durable_tiktok_status(
        self,
        *,
        auth: AuthContext,
        post_id: str,
    ) -> DurableTikTokStatusResponse | None:
        tenant_id = self._require_tenant(auth)
        try:
            receipt = await self.attempt_repository.get_published_receipt_by_post_id(
                tenant_id=tenant_id,
                platform="tiktok",
                post_id=post_id,
            )
            if receipt is None:
                return None
            receipt.validate_published()
            if receipt.post_id != post_id:
                raise ValueError("durable receipt post ID is contradictory")
            verified_by = receipt.verified_by
            if verified_by != "status_fetch" and verified_by != "video_query":
                raise ValueError("durable TikTok receipt verifier is contradictory")
            return DurableTikTokStatusResponse(
                platform="tiktok",
                post_id=post_id,
                status="PUBLISH_COMPLETE",
                post_url=receipt.post_url,
                simulated=False,
                observed_at=receipt.observed_at,
                verified_by=verified_by,
            )
        except PublishAttemptStoreUnavailable:
            raise
        except (TypeError, ValueError, ValidationError):
            raise PublishAttemptStoreUnavailable from None

    @staticmethod
    def _require_tenant(auth: AuthContext) -> str:
        if not isinstance(auth, AuthContext):
            raise HTTPException(status_code=401, detail="Invalid authentication context")
        tenant_id = auth.tenant_id
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise HTTPException(status_code=401, detail="Invalid authentication context")
        if not auth.has_permission("artifact:publish"):
            raise HTTPException(status_code=403, detail="Insufficient permission")
        return tenant_id

    @staticmethod
    def _build_connector_content(
        *,
        request: PublishAttemptRequest,
        video_path: Path,
    ) -> dict[str, Any]:
        if request.platform == "tiktok":
            if not isinstance(request.platform_options, TikTokPublishOptions):
                raise ValueError("TikTok publish options are invalid")
            return _tiktok_content(
                request.metadata,
                request.platform_options,
                video_path,
            )
        if not isinstance(request.platform_options, ShopifyPublishOptions):
            raise ValueError("Shopify publish options are invalid")
        return _shopify_content(
            request.metadata,
            request.platform_options,
            video_path,
        )

    async def _inspect_acceptance_or_fail_closed(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        request: PublishAttemptRequest,
        trace_id: str,
    ) -> AcceptanceRecordResponse:
        try:
            return await self.acceptance_service.inspect_for_publish(
                tenant_id=tenant_id,
                acceptance_id=request.acceptance_id,
            )
        except AcceptanceStoreUnavailable as exc:
            await self._record_authorization_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code="acceptance_store_unavailable",
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=503,
                code="acceptance_store_unavailable",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=True,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        except (
            AcceptanceNotFound,
            AcceptanceExpired,
            AcceptanceNotAvailable,
            AcceptanceArtifactIntegrityMismatch,
        ) as exc:
            status_code, code = self._acceptance_error_projection(exc)
            await self._record_authorization_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code=code,
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=status_code,
                code=code,
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        raise AssertionError("unreachable")

    async def _preflight_or_fail_closed(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        request: PublishAttemptRequest,
        connector_content: dict[str, Any],
        trace_id: str,
    ) -> tuple[Any, Any]:
        try:
            connector = self.connector_factory(request.platform)
            snapshot = await connector.preflight(connector_content)
            return connector, snapshot
        except ConnectorPreflightRejected as exc:
            await self._record_preflight_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code="publish_preflight_rejected",
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=409,
                code="publish_preflight_rejected",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=True,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        except Exception as exc:
            await self._record_preflight_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code="publish_preflight_unavailable",
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=502,
                code="publish_preflight_unavailable",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=True,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        raise AssertionError("unreachable")

    async def _record_preflight_failure_or_unknown(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        error_code: Literal[
            "publish_preflight_rejected",
            "publish_preflight_unavailable",
        ],
        trace_id: str,
    ) -> None:
        try:
            record = await self.attempt_repository.transition(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                expected_status="prepared",
                new_status="preflight_failed",
                error_code=error_code,
            )
        except PublishAttemptStoreUnavailable as exc:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
                cause=exc,
            )
        if record is None:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
            )

    async def _consume_or_fail_closed(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        request: PublishAttemptRequest,
        trace_id: str,
    ) -> AcceptanceRecordResponse:
        try:
            return await self.acceptance_service.consume_for_publish(
                tenant_id=tenant_id,
                acceptance_id=request.acceptance_id,
                consumer_operation="distribution.publish",
                consumer_resource_id=attempt_id,
            )
        except AcceptanceStoreUnavailable as exc:
            await self._handle_uncertain_consume(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                request=request,
                trace_id=trace_id,
                cause=exc,
            )
        except (
            AcceptanceNotFound,
            AcceptanceExpired,
            AcceptanceNotAvailable,
            AcceptanceArtifactIntegrityMismatch,
        ) as exc:
            status_code, code = self._acceptance_error_projection(exc)
            await self._record_authorization_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code=code,
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=status_code,
                code=code,
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )
        raise AssertionError("unreachable")

    async def _handle_uncertain_consume(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        request: PublishAttemptRequest,
        trace_id: str,
        cause: Exception,
    ) -> NoReturn:
        try:
            outcome = (
                await self.acceptance_service.inspect_publish_consume_outcome(
                    tenant_id=tenant_id,
                    acceptance_id=request.acceptance_id,
                    consumer_operation="distribution.publish",
                    consumer_resource_id=attempt_id,
                )
            )
        except AcceptanceStoreUnavailable:
            outcome = "unknown"

        if outcome == "available_not_consumed":
            await self._record_authorization_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code="acceptance_store_unavailable",
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=503,
                code="acceptance_store_unavailable",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=True,
                platform=request.platform,
                trace_id=trace_id,
                cause=cause,
            )
        if outcome in {"consumed_by_another_attempt", "not_available"}:
            await self._record_authorization_failure_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                error_code="acceptance_not_available",
                trace_id=trace_id,
            )
            self._raise_error(
                status_code=409,
                code="acceptance_not_available",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=request.platform,
                trace_id=trace_id,
                cause=cause,
            )
        self._raise_error(
            status_code=500,
            code="publish_attempt_state_unknown",
            attempt_id=attempt_id,
            acceptance_consumed=(
                True if outcome == "consumed_by_this_attempt" else None
            ),
            retry_allowed=False,
            platform=request.platform,
            trace_id=trace_id,
            cause=cause,
        )

    async def _record_authorization_failure_or_unknown(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        error_code: PublishAttemptErrorCode,
        trace_id: str,
    ) -> None:
        try:
            record = await self.attempt_repository.transition(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                expected_status="prepared",
                new_status="authorization_failed",
                error_code=error_code,
            )
        except PublishAttemptStoreUnavailable as exc:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
                cause=exc,
            )
        if record is None:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=False,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
            )

    @staticmethod
    def _acceptance_error_projection(
        exc: Exception,
    ) -> tuple[int, PublishAttemptErrorCode]:
        if isinstance(exc, AcceptanceNotFound):
            return 404, "acceptance_not_found"
        if isinstance(exc, AcceptanceExpired):
            return 409, "acceptance_expired"
        if isinstance(exc, AcceptanceArtifactIntegrityMismatch):
            return 409, "acceptance_artifact_integrity_mismatch"
        return 409, "acceptance_not_available"

    @staticmethod
    def _build_consumed_audit_content(
        *,
        tenant_id: str,
        route_kind: RouteKind,
        request: PublishAttemptRequest,
        consumed: AcceptanceRecordResponse,
    ) -> dict[str, Any]:
        if (
            consumed.acceptance_id != request.acceptance_id
            or consumed.tenant_id != tenant_id
            or consumed.decision != "accepted"
            or consumed.status != "consumed"
            or consumed.artifact.kind != "video"
        ):
            raise ValueError("consumed acceptance projection is invalid")
        return {
            "schema_version": "publish-attempt.v1",
            "route_kind": route_kind,
            "source": {
                "resource_type": consumed.source_resource_type,
                "resource_id": consumed.source_resource_id,
                "scenario": consumed.scenario,
            },
            "artifact": {
                "path": consumed.artifact.path,
                "sha256": consumed.artifact.sha256,
                "size_bytes": consumed.artifact.size_bytes,
                "kind": consumed.artifact.kind,
            },
            "metadata": request.metadata.model_dump(
                mode="json",
                exclude_none=True,
            ),
        }

    async def _mark_acceptance_consumed_or_stop(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        content: Mapping[str, Any],
        trace_id: str,
    ) -> None:
        try:
            record = await self.attempt_repository.transition(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                expected_status="prepared",
                new_status="acceptance_consumed",
                content=content,
            )
        except PublishAttemptStoreUnavailable as exc:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=True,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
                cause=exc,
            )
        if record is None:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=True,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
            )

    def _resolve_consumed_artifact(
        self,
        *,
        tenant_id: str,
        consumed: AcceptanceRecordResponse,
    ) -> ResolvedOutputArtifact:
        artifact = self.artifact_resolver(
            consumed.artifact.path,
            output_dir=self.output_dir,
            tenant_id=tenant_id,
            required_prefix=_source_prefix(
                tenant_id=tenant_id,
                resource_type=consumed.source_resource_type,
                resource_id=consumed.source_resource_id,
            ),
            allowed_suffixes=_VIDEO_SUFFIXES,
        )
        if (
            artifact.canonical_path != consumed.artifact.path
            or artifact.sha256 != consumed.artifact.sha256
            or artifact.size_bytes != consumed.artifact.size_bytes
        ):
            raise ArtifactIdentityError("artifact integrity mismatch")
        return artifact

    async def _fail_artifact_after_consume(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        trace_id: str,
        cause: Exception,
    ) -> NoReturn:
        await self._persist_terminal_or_unknown(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=platform,
            new_status="failed",
            error_code="publish_artifact_unavailable_after_consume",
            trace_id=trace_id,
        )
        self._raise_error(
            status_code=500,
            code="publish_artifact_unavailable_after_consume",
            attempt_id=attempt_id,
            acceptance_consumed=True,
            retry_allowed=False,
            platform=platform,
            trace_id=trace_id,
            cause=cause,
        )

    async def _publish_once_and_persist(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        request: PublishAttemptRequest,
        connector: Any,
        preflight: Any,
        connector_content: dict[str, Any],
        trace_id: str,
    ) -> PublishAttemptResponse:
        try:
            connector_result = await connector.publish(
                connector_content,
                preflight=preflight,
            )
        except ConnectorCredentialNotReady as exc:
            await self._fail_connector_after_consume(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                code="publish_connector_not_ready_after_consume",
                cause=exc,
            )
        except ConnectorOutcomeAmbiguous as exc:
            partial_receipt = self._safe_partial_receipt_or_none(
                platform=request.platform,
                raw_receipt=exc.partial_receipt,
            )
            await self._persist_ambiguous_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
                receipt=partial_receipt,
            )
        except Exception as exc:
            await self._persist_ambiguous_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        try:
            if not isinstance(connector_result, Mapping):
                raise ValueError("connector result is not a mapping")
            simulated = connector_result.get("simulated", _MISSING)
            if type(simulated) is not bool:
                raise ValueError("connector simulated truth is invalid")
            if simulated is True:
                await self._fail_connector_after_consume(
                    tenant_id=tenant_id,
                    attempt_id=attempt_id,
                    platform=request.platform,
                    trace_id=trace_id,
                    code="publish_connector_simulated",
                )

            reported_platform = connector_result.get("platform", _MISSING)
            if reported_platform is not _MISSING and (
                not isinstance(reported_platform, str)
                or reported_platform != request.platform
            ):
                raise ValueError("connector platform is contradictory")
            success = connector_result.get("success", _MISSING)
            if type(success) is not bool:
                raise ValueError("connector success truth is invalid")
            if success is False:
                if connector_result.get("post_id") is not None or connector_result.get(
                    "url"
                ) is not None:
                    raise ValueError("failed connector result claims a post")
                receipt = self._safe_partial_receipt(
                    platform=request.platform,
                    raw_receipt=connector_result.get("receipt"),
                )
                await self._persist_terminal_or_unknown(
                    tenant_id=tenant_id,
                    attempt_id=attempt_id,
                    platform=request.platform,
                    new_status="failed",
                    error_code="publish_connector_failed",
                    trace_id=trace_id,
                    receipt=receipt,
                )
                self._raise_error(
                    status_code=502,
                    code="publish_connector_failed",
                    attempt_id=attempt_id,
                    acceptance_consumed=True,
                    retry_allowed=False,
                    platform=request.platform,
                    trace_id=trace_id,
                )

            receipt = self._published_receipt(
                platform=request.platform,
                raw_receipt=connector_result.get("receipt", _MISSING),
            )
            if (
                connector_result.get("post_id") != receipt.post_id
                or connector_result.get("url") != receipt.post_url
            ):
                raise ValueError("connector receipt projection is contradictory")
            response = PublishAttemptResponse(
                publish_attempt_id=attempt_id,
                acceptance_id=request.acceptance_id,
                platform=request.platform,
                status="published",
                success=True,
                post_id=receipt.post_id,
                post_url=receipt.post_url,
                receipt=receipt,
                acceptance_consumed=True,
                retry_allowed=False,
            )
        except PublishAttemptError:
            raise
        except (AttributeError, TypeError, ValueError, ValidationError) as exc:
            await self._persist_ambiguous_or_unknown(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                platform=request.platform,
                trace_id=trace_id,
                cause=exc,
            )

        await self._persist_terminal_or_unknown(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=request.platform,
            new_status="published",
            post_id=response.post_id,
            url=response.post_url,
            trace_id=trace_id,
            receipt=response.receipt,
        )
        return response

    @staticmethod
    def _normalize_receipt(
        *,
        platform: str,
        raw_receipt: object,
    ) -> PublishReceiptV1:
        if isinstance(raw_receipt, PublishReceiptV1):
            receipt = raw_receipt
        elif isinstance(raw_receipt, Mapping):
            receipt = PublishReceiptV1.model_validate(dict(raw_receipt))
        else:
            raise ValueError("connector receipt is missing or invalid")
        if receipt.platform != platform:
            raise ValueError("connector receipt platform is contradictory")
        return receipt

    @classmethod
    def _published_receipt(
        cls,
        *,
        platform: str,
        raw_receipt: object,
    ) -> PublishReceiptV1:
        receipt = cls._normalize_receipt(
            platform=platform,
            raw_receipt=raw_receipt,
        )
        receipt.validate_published()
        return receipt

    @classmethod
    def _safe_partial_receipt(
        cls,
        *,
        platform: str,
        raw_receipt: object,
    ) -> PublishReceiptV1 | None:
        if raw_receipt is None:
            return None
        receipt = cls._normalize_receipt(
            platform=platform,
            raw_receipt=raw_receipt,
        )
        if (
            receipt.post_id is not None
            or receipt.post_url is not None
            or receipt.public_visibility_verified
        ):
            raise ValueError("terminal failure receipt is not partial")
        try:
            receipt.validate_published()
        except ValueError:
            return receipt
        raise ValueError("terminal failure receipt claims completion")

    @classmethod
    def _safe_partial_receipt_or_none(
        cls,
        *,
        platform: str,
        raw_receipt: object,
    ) -> PublishReceiptV1 | None:
        try:
            return cls._safe_partial_receipt(
                platform=platform,
                raw_receipt=raw_receipt,
            )
        except (TypeError, ValueError, ValidationError):
            return None

    async def _fail_connector_after_consume(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        trace_id: str,
        code: Literal[
            "publish_connector_not_ready_after_consume",
            "publish_connector_simulated",
        ],
        cause: Exception | None = None,
    ) -> NoReturn:
        await self._persist_terminal_or_unknown(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=platform,
            new_status="failed",
            error_code=code,
            trace_id=trace_id,
        )
        self._raise_error(
            status_code=502,
            code=code,
            attempt_id=attempt_id,
            acceptance_consumed=True,
            retry_allowed=False,
            platform=platform,
            trace_id=trace_id,
            cause=cause,
        )

    async def _persist_ambiguous_or_unknown(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        trace_id: str,
        cause: Exception,
        receipt: PublishReceiptV1 | None = None,
    ) -> NoReturn:
        await self._persist_terminal_or_unknown(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            platform=platform,
            new_status="ambiguous",
            error_code="publish_outcome_ambiguous",
            trace_id=trace_id,
            receipt=receipt,
        )
        self._raise_error(
            status_code=502,
            code="publish_outcome_ambiguous",
            attempt_id=attempt_id,
            acceptance_consumed=True,
            retry_allowed=False,
            platform=platform,
            trace_id=trace_id,
            cause=cause,
        )

    async def _persist_terminal_or_unknown(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        platform: str,
        new_status: Literal["published", "failed", "ambiguous"],
        trace_id: str,
        post_id: str | None = None,
        url: str | None = None,
        error_code: PublishAttemptErrorCode | None = None,
        receipt: PublishReceiptV1 | None = None,
    ) -> None:
        try:
            record = await self.attempt_repository.transition(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                expected_status="acceptance_consumed",
                new_status=new_status,
                post_id=post_id,
                url=url,
                error_code=error_code,
                receipt=receipt,
            )
        except PublishAttemptStoreUnavailable as exc:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=True,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
                cause=exc,
            )
        if record is None:
            self._raise_error(
                status_code=500,
                code="publish_attempt_state_unknown",
                attempt_id=attempt_id,
                acceptance_consumed=True,
                retry_allowed=False,
                platform=platform,
                trace_id=trace_id,
            )

    @staticmethod
    def _raise_error(
        *,
        status_code: int,
        code: PublishAttemptErrorCode,
        attempt_id: str | None,
        acceptance_consumed: bool | None,
        retry_allowed: bool,
        platform: str,
        trace_id: str,
        cause: Exception | None = None,
    ) -> NoReturn:
        if cause is None:
            logger.warning(
                "publish_attempt_error code=%s attempt_id=%s platform=%s trace_id=%s",
                code,
                attempt_id or "none",
                platform,
                trace_id,
            )
        else:
            logger.warning(
                "publish_attempt_error code=%s attempt_id=%s platform=%s "
                "trace_id=%s error_class=%s",
                code,
                attempt_id or "none",
                platform,
                trace_id,
                type(cause).__name__,
            )
        raise PublishAttemptError(
            status_code=status_code,
            code=code,
            publish_attempt_id=attempt_id,
            acceptance_consumed=acceptance_consumed,
            retry_allowed=retry_allowed,
        ) from None


_service: PublishAttemptService | None = None


def get_publish_attempt_service() -> PublishAttemptService:
    global _service
    if _service is None:
        _service = PublishAttemptService()
    return _service


__all__ = [
    "PublishAttemptError",
    "PublishAttemptService",
    "RouteKind",
    "get_publish_attempt_service",
]
