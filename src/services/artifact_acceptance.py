"""Tenant-bound, single-use authority for exact reviewed final artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast, overload

from starlette.requests import Request

from src.config import OUTPUT_DIR
from src.models.acceptance import (
    AcceptanceArtifactProjection,
    AcceptanceCreateRequest,
    AcceptanceRecordResponse,
    AcceptanceReviewerProjection,
    AcceptanceTransparencyProjection,
)
from src.models.transparency import (
    TransparencyProjectionV1,
    validate_transparency_sidecar,
)
from src.routers._deps import AuthContext
from src.services.acceptance_source import (
    AcceptanceSource,
    AcceptanceSourceMismatchError,
    AcceptanceSourceNotEligibleError,
    AcceptanceSourceNotTerminalError,
    resolve_acceptance_source,
)
from src.services.artifact_identity import (
    ArtifactIdentityError,
    ResolvedOutputArtifact,
    classify_output_scope,
    resolve_output_artifact,
    validate_output_reference,
)
from src.services.submission_idempotency import (
    IdempotencyKeyInvalid,
    IdempotencyKeyRequired,
    hash_idempotency_key,
    validate_idempotency_key_headers,
)
from src.storage.acceptance_repository import (
    AcceptanceAlreadyAvailableError,
    AcceptanceNotAvailableError,
    AcceptanceNotRevocableError,
    AcceptancePayloadConflictError,
    AcceptanceRecordRepository,
    AcceptanceSourceNotFoundError,
    AcceptanceStoreUnavailableError,
)
from src.storage.idempotency_repository import (
    IdempotencyStoreUnavailableError,
    SubmissionIdempotencyRepository,
)
from src.tools.c2pa_signer import C2PASigningError, verify_signed_media_readback

ACCEPTANCE_FINGERPRINT_VERSION = "acceptance-create.v2"
_LEGACY_ACCEPTANCE_FINGERPRINT_VERSION = "acceptance-create.v1"
_VIDEO_SUFFIXES = {".mp4", ".webm"}
_REVIEWER_KEY_TYPES = frozenset({"tenant", "test_bundle", "env_fallback"})
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ACCEPTANCE_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

AcceptanceConsumeOutcome = Literal[
    "available_not_consumed",
    "consumed_by_this_attempt",
    "consumed_by_another_attempt",
    "not_available",
    "unknown",
]
AcceptanceResourceType = Literal["fast", "scenario"]
AcceptanceScenario = Literal["fast", "s1", "s2", "s3", "s4", "s5"]


class ArtifactAcceptanceError(Exception):
    status_code = 500
    code = "artifact_acceptance_error"

    def __init__(self) -> None:
        super().__init__(self.code)

    @property
    def detail(self) -> dict[str, str]:
        return {"code": self.code}


class AcceptanceKeyRequired(ArtifactAcceptanceError):
    status_code = 400
    code = "acceptance_key_required"


class AcceptanceKeyInvalid(ArtifactAcceptanceError):
    status_code = 400
    code = "acceptance_key_invalid"


class AcceptancePayloadConflict(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_payload_conflict"


class AcceptanceNotFound(ArtifactAcceptanceError):
    status_code = 404
    code = "acceptance_not_found"


class AcceptanceSourceNotTerminal(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_source_not_terminal"


class AcceptanceSourceNotEligible(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_source_not_eligible"


class AcceptanceArtifactMismatch(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_artifact_mismatch"


class AcceptanceAlreadyAvailable(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_already_available"


class AcceptanceNotRevocable(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_not_revocable"


class AcceptanceStoreUnavailable(ArtifactAcceptanceError):
    status_code = 503
    code = "acceptance_store_unavailable"


class AcceptanceNotAvailable(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_not_available"


class AcceptanceExpired(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_expired"


class AcceptanceArtifactIntegrityMismatch(ArtifactAcceptanceError):
    status_code = 409
    code = "acceptance_artifact_integrity_mismatch"


@dataclass(frozen=True, slots=True)
class AcceptanceFingerprint:
    version: str
    request_hash: str


@dataclass(frozen=True, slots=True)
class StoredArtifactAuthority:
    tenant_id: str
    resource_type: AcceptanceResourceType
    resource_id: str
    scenario: AcceptanceScenario
    artifact_path: str
    artifact_sha256: str
    artifact_size_bytes: int


@dataclass(frozen=True, slots=True)
class StoredTransparencyAuthority:
    sidecar_path: str
    sidecar_sha256: str
    final_artifact_c2pa_status: Literal[
        "unsigned_pending_review",
        "signed_local_readback",
    ]


def build_acceptance_fingerprint(
    request: AcceptanceCreateRequest,
    *,
    tenant_id: str,
    reviewer_key_id: str,
    reviewer_key_type: str,
    transparency_sidecar_path: str,
    transparency_sidecar_sha256: str,
    final_artifact_c2pa_status: str,
) -> AcceptanceFingerprint:
    """Hash the strict action plus authenticated principal, never credentials."""

    envelope = {
        "fingerprint_version": ACCEPTANCE_FINGERPRINT_VERSION,
        "tenant_id": tenant_id,
        "reviewer": {
            "key_id": reviewer_key_id,
            "key_type": reviewer_key_type,
        },
        "request": request.model_dump(
            mode="json",
            exclude_defaults=False,
            exclude_none=False,
            exclude_unset=False,
        ),
        "transparency": {
            "sidecar_path": transparency_sidecar_path,
            "sidecar_sha256": transparency_sidecar_sha256,
            "final_artifact_c2pa_status": final_artifact_c2pa_status,
        },
    }
    canonical = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return AcceptanceFingerprint(
        ACCEPTANCE_FINGERPRINT_VERSION,
        hashlib.sha256(canonical).hexdigest(),
    )


def _build_legacy_acceptance_fingerprint(
    request: AcceptanceCreateRequest,
    *,
    tenant_id: str,
    reviewer_key_id: str,
    reviewer_key_type: str,
) -> AcceptanceFingerprint:
    envelope = {
        "fingerprint_version": _LEGACY_ACCEPTANCE_FINGERPRINT_VERSION,
        "tenant_id": tenant_id,
        "reviewer": {
            "key_id": reviewer_key_id,
            "key_type": reviewer_key_type,
        },
        "request": request.model_dump(
            mode="json",
            exclude_defaults=False,
            exclude_none=False,
            exclude_unset=False,
        ),
    }
    canonical = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return AcceptanceFingerprint(
        _LEGACY_ACCEPTANCE_FINGERPRINT_VERSION,
        hashlib.sha256(canonical).hexdigest(),
    )


def extract_acceptance_key(request: Request) -> str:
    """Read all raw action-key headers and map the shared grammar safely."""

    try:
        return validate_idempotency_key_headers(
            request.headers.getlist("idempotency-key")
        )
    except IdempotencyKeyRequired:
        raise AcceptanceKeyRequired from None
    except IdempotencyKeyInvalid:
        raise AcceptanceKeyInvalid from None


class ArtifactAcceptanceService:
    def __init__(
        self,
        repository: AcceptanceRecordRepository | None = None,
        submission_repository: SubmissionIdempotencyRepository | None = None,
        *,
        output_dir: Path | None = None,
        c2pa_reader_verifier: Callable[[Path], str] | None = None,
    ) -> None:
        self.repository = repository or AcceptanceRecordRepository()
        self.submission_repository = (
            submission_repository or SubmissionIdempotencyRepository()
        )
        self.output_dir = output_dir or OUTPUT_DIR
        self.c2pa_reader_verifier = (
            c2pa_reader_verifier
            or (lambda path: verify_signed_media_readback(path, media_format="video/mp4"))
        )

    async def create(
        self,
        *,
        auth: AuthContext,
        raw_key: str,
        request: AcceptanceCreateRequest,
    ) -> tuple[AcceptanceRecordResponse, bool]:
        tenant_id, reviewer_key_id, reviewer_key_type = _reviewer_identity(auth)
        validated_key = _validate_raw_key(raw_key)
        creation_key_hash = hash_idempotency_key(validated_key)

        existing = await self._get_by_creation_key(
            tenant_id=tenant_id,
            creation_key_hash=creation_key_hash,
        )
        if existing is not None:
            if existing.get("fingerprint_version") == _LEGACY_ACCEPTANCE_FINGERPRINT_VERSION:
                legacy_fingerprint = _build_legacy_acceptance_fingerprint(
                    request,
                    tenant_id=tenant_id,
                    reviewer_key_id=reviewer_key_id,
                    reviewer_key_type=reviewer_key_type,
                )
                if not _fingerprint_matches(existing, legacy_fingerprint):
                    raise AcceptancePayloadConflict
                return await self._current_replay(tenant_id, existing), True
            stored_transparency = _validate_stored_transparency_authority(existing)
            fingerprint = build_acceptance_fingerprint(
                request,
                tenant_id=tenant_id,
                reviewer_key_id=reviewer_key_id,
                reviewer_key_type=reviewer_key_type,
                transparency_sidecar_path=stored_transparency.sidecar_path,
                transparency_sidecar_sha256=stored_transparency.sidecar_sha256,
                final_artifact_c2pa_status=(
                    stored_transparency.final_artifact_c2pa_status
                ),
            )
            if not _fingerprint_matches(existing, fingerprint):
                raise AcceptancePayloadConflict
            return await self._current_replay(tenant_id, existing), True

        source_record = await self._get_source(
            tenant_id=tenant_id,
            resource_type=request.source_resource_type,
            resource_id=request.source_resource_id,
        )
        source = _resolve_source(
            source_record,
            tenant_id=tenant_id,
            resource_type=request.source_resource_type,
            resource_id=request.source_resource_id,
        )
        _validate_decision_eligibility(source, request.decision)
        requested_path = _validate_requested_path(
            request.artifact_path,
            tenant_id=tenant_id,
            expected_path=source.artifact_path,
        )
        artifact = _resolve_exact_artifact(
            requested_path,
            tenant_id=source.tenant_id,
            resource_type=source.resource_type,
            resource_id=source.resource_id,
            output_dir=self.output_dir,
            missing_error=AcceptanceNotFound,
        )
        if artifact.canonical_path != requested_path:
            raise AcceptanceArtifactMismatch
        transparency = _validate_source_transparency(
            source_record,
            artifact=artifact,
            tenant_id=source.tenant_id,
            scenario=source.scenario,
            resource_type=source.resource_type,
            resource_id=source.resource_id,
            output_dir=self.output_dir,
            decision=request.decision,
            c2pa_reader_verifier=self.c2pa_reader_verifier,
        )
        fingerprint = build_acceptance_fingerprint(
            request,
            tenant_id=tenant_id,
            reviewer_key_id=reviewer_key_id,
            reviewer_key_type=reviewer_key_type,
            transparency_sidecar_path=transparency.sidecar_path,
            transparency_sidecar_sha256=transparency.sidecar_sha256,
            final_artifact_c2pa_status=transparency.final_artifact_c2pa_status,
        )

        try:
            result = await self.repository.create_or_replay(
                tenant_id=tenant_id,
                creation_key_hash=creation_key_hash,
                fingerprint_version=fingerprint.version,
                request_hash=fingerprint.request_hash,
                source_resource_type=source.resource_type,
                source_resource_id=source.resource_id,
                scenario=source.scenario,
                artifact_path=artifact.canonical_path,
                artifact_sha256=artifact.sha256,
                artifact_size_bytes=artifact.size_bytes,
                artifact_kind=source.artifact_kind,
                transparency_sidecar_path=transparency.sidecar_path,
                transparency_sidecar_sha256=transparency.sidecar_sha256,
                final_artifact_c2pa_status=(
                    transparency.final_artifact_c2pa_status
                ),
                decision=request.decision,
                reviewer_key_id=reviewer_key_id,
                reviewer_key_type=reviewer_key_type,
                review_notes=request.review_notes,
                expires_in_seconds=request.expires_in_seconds,
            )
        except AcceptancePayloadConflictError:
            raise AcceptancePayloadConflict from None
        except AcceptanceAlreadyAvailableError:
            raise AcceptanceAlreadyAvailable from None
        except AcceptanceSourceNotFoundError:
            raise AcceptanceNotFound from None
        except AcceptanceStoreUnavailableError:
            raise AcceptanceStoreUnavailable from None

        if result.outcome == "replay":
            return await self._current_replay(tenant_id, result.record), True
        return (
            _project_record(
                result.record,
                idempotent_replay=False,
                expected_tenant_id=tenant_id,
            ),
            False,
        )

    async def read(
        self,
        *,
        auth: AuthContext,
        acceptance_id: str,
    ) -> AcceptanceRecordResponse:
        tenant_id = _tenant_identity(auth)
        await self._reconcile_expired(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        record = await self._get_record(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        return _project_record(
            record,
            idempotent_replay=False,
            expected_tenant_id=tenant_id,
        )

    async def revoke(
        self,
        *,
        auth: AuthContext,
        acceptance_id: str,
    ) -> AcceptanceRecordResponse:
        tenant_id, reviewer_key_id, _ = _reviewer_identity(auth)
        await self._reconcile_expired(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        await self._get_record(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        try:
            record = await self.repository.revoke(
                tenant_id=tenant_id,
                acceptance_id=acceptance_id,
                reviewer_key_id=reviewer_key_id,
            )
        except AcceptanceNotRevocableError:
            raise AcceptanceNotRevocable from None
        except AcceptanceStoreUnavailableError:
            raise AcceptanceStoreUnavailable from None
        return _project_record(
            record,
            idempotent_replay=False,
            expected_tenant_id=tenant_id,
        )

    async def consume_for_publish(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        consumer_operation: str,
        consumer_resource_id: str,
    ) -> AcceptanceRecordResponse:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise AcceptanceNotFound
        consumer_operation = _validate_consumer_identity(
            consumer_operation,
            max_length=64,
        )
        consumer_resource_id = _validate_consumer_identity(
            consumer_resource_id,
            max_length=128,
        )
        await self._reconcile_expired(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        record = await self._get_record(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        _ensure_consumable(record)

        stored = _validate_stored_artifact_authority(
            record,
            expected_tenant_id=tenant_id,
        )
        artifact = _resolve_exact_artifact(
            stored.artifact_path,
            tenant_id=stored.tenant_id,
            resource_type=stored.resource_type,
            resource_id=stored.resource_id,
            output_dir=self.output_dir,
            missing_error=AcceptanceArtifactIntegrityMismatch,
        )
        if (
            artifact.canonical_path != stored.artifact_path
            or artifact.sha256 != stored.artifact_sha256
            or artifact.size_bytes != stored.artifact_size_bytes
        ):
            raise AcceptanceArtifactIntegrityMismatch
        transparency = _revalidate_stored_transparency(
            record,
            artifact=artifact,
            output_dir=self.output_dir,
            c2pa_reader_verifier=self.c2pa_reader_verifier,
        )

        try:
            consumed = await self.repository.consume(
                tenant_id=tenant_id,
                acceptance_id=acceptance_id,
                artifact_path=artifact.canonical_path,
                artifact_sha256=artifact.sha256,
                artifact_size_bytes=artifact.size_bytes,
                transparency_sidecar_path=transparency.sidecar_path,
                transparency_sidecar_sha256=transparency.sidecar_sha256,
                final_artifact_c2pa_status=(
                    transparency.final_artifact_c2pa_status
                ),
                consumer_operation=consumer_operation,
                consumer_resource_id=consumer_resource_id,
            )
        except AcceptanceNotAvailableError:
            await self._raise_current_consume_state(
                tenant_id=tenant_id,
                acceptance_id=acceptance_id,
            )
            raise AssertionError("unreachable")
        except AcceptanceStoreUnavailableError:
            raise AcceptanceStoreUnavailable from None
        except ValueError:
            raise AcceptanceStoreUnavailable from None
        return _project_record(
            consumed,
            idempotent_replay=False,
            expected_tenant_id=tenant_id,
        )

    async def inspect_for_publish(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
    ) -> AcceptanceRecordResponse:
        """Validate publish authority and exact bytes without changing state."""

        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise AcceptanceNotFound
        record = await self._get_record(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        expires_at = _consume_outcome_timestamp(record.get("expires_at"))
        if expires_at <= datetime.now(UTC):
            raise AcceptanceExpired
        _ensure_consumable(record)

        stored = _validate_stored_artifact_authority(
            record,
            expected_tenant_id=tenant_id,
        )
        artifact = _resolve_exact_artifact(
            stored.artifact_path,
            tenant_id=stored.tenant_id,
            resource_type=stored.resource_type,
            resource_id=stored.resource_id,
            output_dir=self.output_dir,
            missing_error=AcceptanceArtifactIntegrityMismatch,
        )
        if (
            artifact.canonical_path != stored.artifact_path
            or artifact.sha256 != stored.artifact_sha256
            or artifact.size_bytes != stored.artifact_size_bytes
        ):
            raise AcceptanceArtifactIntegrityMismatch
        _revalidate_stored_transparency(
            record,
            artifact=artifact,
            output_dir=self.output_dir,
            c2pa_reader_verifier=self.c2pa_reader_verifier,
        )
        return _project_record(
            record,
            idempotent_replay=False,
            expected_tenant_id=tenant_id,
        )

    async def inspect_publish_consume_outcome(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        consumer_operation: str,
        consumer_resource_id: str,
    ) -> AcceptanceConsumeOutcome:
        """Inspect durable consume truth without mutating acceptance state."""

        try:
            if not isinstance(tenant_id, str) or not tenant_id.strip():
                return "unknown"
            if (
                not isinstance(acceptance_id, str)
                or _ACCEPTANCE_UUID4_RE.fullmatch(acceptance_id) is None
            ):
                return "unknown"
            operation = _validate_consumer_identity(
                consumer_operation,
                max_length=64,
            )
            resource_id = _validate_consumer_identity(
                consumer_resource_id,
                max_length=128,
            )
            record = await self.repository.get_by_id(
                tenant_id=tenant_id,
                acceptance_id=acceptance_id,
            )
            if record is None or not isinstance(record, Mapping):
                return "unknown"
            if record.get("id") != acceptance_id:
                return "unknown"

            stored_artifact = _validate_stored_artifact_authority(
                record,
                expected_tenant_id=tenant_id,
            )
            decision = record.get("decision")
            status = record.get("record_status")
            if decision not in {"accepted", "rejected"} or status not in {
                "available",
                "consumed",
                "expired",
                "rejected",
                "revoked",
            }:
                return "unknown"

            expires_at = _consume_outcome_timestamp(record.get("expires_at"))
            created_at = _consume_outcome_timestamp(record.get("created_at"))
            updated_at = _consume_outcome_timestamp(record.get("updated_at"))
            if expires_at <= created_at or updated_at < created_at:
                return "unknown"

            consumed_at = record.get("consumed_at")
            stored_operation = record.get("consumed_by_operation")
            stored_resource = record.get("consumed_by_resource_id")
            revoked_at = record.get("revoked_at")
            revoked_by_key_id = record.get("revoked_by_key_id")
            revoked_by_record_id = record.get("revoked_by_record_id")
            has_consume_evidence = any(
                value is not None
                for value in (consumed_at, stored_operation, stored_resource)
            )
            has_revocation_evidence = any(
                value is not None
                for value in (
                    revoked_at,
                    revoked_by_key_id,
                    revoked_by_record_id,
                )
            )

            if status == "available":
                if (
                    decision != "accepted"
                    or has_consume_evidence
                    or has_revocation_evidence
                ):
                    return "unknown"
                if expires_at <= datetime.now(UTC):
                    return "not_available"
                _revalidate_stored_publish_authority(
                    record,
                    stored_artifact=stored_artifact,
                    output_dir=self.output_dir,
                    c2pa_reader_verifier=self.c2pa_reader_verifier,
                )
                return "available_not_consumed"

            if status == "consumed":
                if (
                    decision != "accepted"
                    or has_revocation_evidence
                    or consumed_at is None
                ):
                    return "unknown"
                consumed_event_at = _consume_outcome_timestamp(consumed_at)
                if not (
                    created_at <= consumed_event_at < expires_at
                    and consumed_event_at <= updated_at
                ):
                    return "unknown"
                _revalidate_stored_publish_authority(
                    record,
                    stored_artifact=stored_artifact,
                    output_dir=self.output_dir,
                    c2pa_reader_verifier=self.c2pa_reader_verifier,
                )
                validated_operation = _validate_consumer_identity(
                    stored_operation,
                    max_length=64,
                )
                validated_resource = _validate_consumer_identity(
                    stored_resource,
                    max_length=128,
                )
                if (
                    validated_operation == operation
                    and validated_resource == resource_id
                ):
                    return "consumed_by_this_attempt"
                return "consumed_by_another_attempt"

            if has_consume_evidence:
                return "unknown"
            if status == "rejected":
                if decision != "rejected" or has_revocation_evidence:
                    return "unknown"
                return "not_available"
            if status == "expired":
                if (
                    decision != "accepted"
                    or has_revocation_evidence
                    or expires_at > datetime.now(UTC)
                    or expires_at > updated_at
                ):
                    return "unknown"
                return "not_available"
            if status == "revoked":
                if (
                    decision != "accepted"
                    or revoked_at is None
                    or not isinstance(revoked_by_key_id, str)
                    or not revoked_by_key_id.strip()
                ):
                    return "unknown"
                revoked_event_at = _consume_outcome_timestamp(revoked_at)
                if not (
                    created_at <= revoked_event_at < expires_at
                    and revoked_event_at <= updated_at
                ):
                    return "unknown"
                if revoked_by_record_id is not None and (
                    not isinstance(revoked_by_record_id, str)
                    or not revoked_by_record_id.strip()
                ):
                    return "unknown"
                return "not_available"
            return "unknown"
        except (
            AcceptanceArtifactIntegrityMismatch,
            AcceptanceNotAvailable,
            AcceptanceStoreUnavailable,
            AcceptanceStoreUnavailableError,
            TypeError,
            ValueError,
        ):
            return "unknown"

    async def _get_by_creation_key(
        self,
        *,
        tenant_id: str,
        creation_key_hash: str,
    ) -> dict[str, Any] | None:
        try:
            return await self.repository.get_by_creation_key_hash(
                tenant_id=tenant_id,
                creation_key_hash=creation_key_hash,
            )
        except AcceptanceStoreUnavailableError:
            raise AcceptanceStoreUnavailable from None

    async def _get_source(
        self,
        *,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
    ) -> Mapping[str, Any]:
        try:
            record = await self.submission_repository.get_by_resource(
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except IdempotencyStoreUnavailableError:
            raise AcceptanceStoreUnavailable from None
        if record is None:
            raise AcceptanceNotFound
        return record

    async def _reconcile_expired(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
    ) -> None:
        try:
            await self.repository.reconcile_expired(
                tenant_id=tenant_id,
                acceptance_id=acceptance_id,
            )
        except (AcceptanceStoreUnavailableError, ValueError):
            raise AcceptanceStoreUnavailable from None

    async def _get_record(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
    ) -> dict[str, Any]:
        try:
            record = await self.repository.get_by_id(
                tenant_id=tenant_id,
                acceptance_id=acceptance_id,
            )
        except AcceptanceStoreUnavailableError:
            raise AcceptanceStoreUnavailable from None
        if record is None:
            raise AcceptanceNotFound
        return record

    async def _current_replay(
        self,
        tenant_id: str,
        record: Mapping[str, Any],
    ) -> AcceptanceRecordResponse:
        acceptance_id = record.get("id")
        if not isinstance(acceptance_id, str):
            raise AcceptanceStoreUnavailable
        await self._reconcile_expired(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        current = await self._get_record(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        return _project_record(
            current,
            idempotent_replay=True,
            expected_tenant_id=tenant_id,
        )

    async def _raise_current_consume_state(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
    ) -> None:
        await self._reconcile_expired(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        current = await self._get_record(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        if current.get("record_status") == "expired":
            raise AcceptanceExpired
        raise AcceptanceNotAvailable


def _validate_raw_key(raw_key: str) -> str:
    try:
        return validate_idempotency_key_headers([raw_key])
    except IdempotencyKeyRequired:
        raise AcceptanceKeyRequired from None
    except IdempotencyKeyInvalid:
        raise AcceptanceKeyInvalid from None


def _validate_consumer_identity(value: Any, *, max_length: int) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > max_length
    ):
        raise AcceptanceNotAvailable
    return value


def _consume_outcome_timestamp(value: Any) -> datetime:
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str) and value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise AcceptanceStoreUnavailable
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (OverflowError, ValueError):
        raise AcceptanceStoreUnavailable from None


def _tenant_identity(auth: AuthContext) -> str:
    tenant_id = auth.tenant_id
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise AcceptanceStoreUnavailable
    return tenant_id


def _reviewer_identity(auth: AuthContext) -> tuple[str, str, str]:
    tenant_id = _tenant_identity(auth)
    reviewer_key_id = auth.key_id
    reviewer_key_type = str(auth.key_type)
    if (
        not isinstance(reviewer_key_id, str)
        or not reviewer_key_id.strip()
        or reviewer_key_type not in _REVIEWER_KEY_TYPES
    ):
        raise AcceptanceStoreUnavailable
    return tenant_id, reviewer_key_id, reviewer_key_type


def _fingerprint_matches(
    record: Mapping[str, Any],
    fingerprint: AcceptanceFingerprint,
) -> bool:
    return (
        record.get("fingerprint_version") == fingerprint.version
        and record.get("request_hash") == fingerprint.request_hash
    )


def _resolve_source(
    record: Mapping[str, Any],
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
) -> AcceptanceSource:
    try:
        return resolve_acceptance_source(
            record,
            tenant_id=tenant_id,
            requested_resource_type=resource_type,
            requested_resource_id=resource_id,
        )
    except AcceptanceSourceMismatchError:
        raise AcceptanceNotFound from None
    except AcceptanceSourceNotTerminalError:
        raise AcceptanceSourceNotTerminal from None
    except AcceptanceSourceNotEligibleError:
        raise AcceptanceSourceNotEligible from None


def _validate_decision_eligibility(source: AcceptanceSource, decision: str) -> None:
    if decision != "accepted":
        return
    if (
        source.record_status != "completed"
        or not source.full_media_success
        or source.is_stub
        or source.pipeline_degraded
    ):
        raise AcceptanceSourceNotEligible


def _validate_requested_path(
    path: str,
    *,
    tenant_id: str,
    expected_path: str,
) -> str:
    try:
        canonical = validate_output_reference(path)
        scope = classify_output_scope(canonical)
    except ArtifactIdentityError:
        raise AcceptanceNotFound from None
    if canonical != path or scope != tenant_id:
        raise AcceptanceNotFound
    if canonical != expected_path:
        raise AcceptanceArtifactMismatch
    return canonical


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


def _resolve_exact_artifact(
    path: str,
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    output_dir: Path,
    missing_error: type[ArtifactAcceptanceError],
) -> ResolvedOutputArtifact:
    try:
        return resolve_output_artifact(
            path,
            output_dir=output_dir,
            tenant_id=tenant_id,
            required_prefix=_source_prefix(
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
            ),
            allowed_suffixes=_VIDEO_SUFFIXES,
        )
    except (ArtifactIdentityError, OSError, RuntimeError):
        raise missing_error from None


def _result_snapshot(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("result_snapshot")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("acceptance transparency snapshot is invalid") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("acceptance transparency snapshot is invalid")
    return raw


def _validate_stored_transparency_authority(
    record: Mapping[str, Any],
) -> StoredTransparencyAuthority:
    sidecar_path = record.get("transparency_sidecar_path")
    sidecar_sha256 = record.get("transparency_sidecar_sha256")
    c2pa_status = record.get("final_artifact_c2pa_status")
    if not isinstance(sidecar_path, str) or not sidecar_path:
        raise AcceptanceArtifactIntegrityMismatch
    try:
        canonical = validate_output_reference(sidecar_path)
    except ArtifactIdentityError:
        raise AcceptanceArtifactIntegrityMismatch from None
    if canonical != sidecar_path or not sidecar_path.endswith(".json"):
        raise AcceptanceArtifactIntegrityMismatch
    if not isinstance(sidecar_sha256, str) or _SHA256_RE.fullmatch(sidecar_sha256) is None:
        raise AcceptanceArtifactIntegrityMismatch
    if c2pa_status not in {"unsigned_pending_review", "signed_local_readback"}:
        raise AcceptanceArtifactIntegrityMismatch
    return StoredTransparencyAuthority(
        sidecar_path=sidecar_path,
        sidecar_sha256=sidecar_sha256,
        final_artifact_c2pa_status=cast(
            Literal["unsigned_pending_review", "signed_local_readback"],
            c2pa_status,
        ),
    )


def _validate_transparency_sidecar_binding(
    *,
    transparency: StoredTransparencyAuthority,
    artifact: ResolvedOutputArtifact,
    tenant_id: str,
    scenario: str,
    resource_type: str,
    resource_id: str,
    output_dir: Path,
    expected_record_id: str | None,
    expected_record_count: int | None,
    c2pa_reader_verifier: Callable[[Path], str],
) -> None:
    prefix = _source_prefix(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if not transparency.sidecar_path.startswith(f"{prefix}/transparency/"):
        raise AcceptanceArtifactIntegrityMismatch
    try:
        sidecar = validate_transparency_sidecar(
            output_dir / transparency.sidecar_path,
            expected_sha256=transparency.sidecar_sha256,
            artifact_root=output_dir,
        )
    except (OSError, ValueError):
        raise AcceptanceArtifactIntegrityMismatch from None
    if expected_record_count is not None and len(sidecar.records) != expected_record_count:
        raise AcceptanceArtifactIntegrityMismatch
    matching = [
        record
        for record in sidecar.records
        if record.artifact is not None
        and record.artifact.relative_path == artifact.canonical_path
    ]
    if len(matching) != 1:
        raise AcceptanceArtifactIntegrityMismatch
    final_record = matching[0]
    if (
        final_record.tenant_id != tenant_id
        or final_record.scenario != scenario
        or final_record.resource_id != resource_id
        or final_record.content_kind != "video"
        or final_record.simulated
        or final_record.artifact is None
        or final_record.artifact.sha256 != artifact.sha256
        or final_record.artifact.size_bytes != artifact.size_bytes
        or final_record.c2pa_status != transparency.final_artifact_c2pa_status
        or (expected_record_id is not None and final_record.record_id != expected_record_id)
    ):
        raise AcceptanceArtifactIntegrityMismatch
    if transparency.final_artifact_c2pa_status == "signed_local_readback":
        try:
            manifest_digest = c2pa_reader_verifier(artifact.absolute_path)
        except (C2PASigningError, OSError, RuntimeError, ValueError):
            raise AcceptanceArtifactIntegrityMismatch from None
        if not isinstance(manifest_digest, str) or _SHA256_RE.fullmatch(manifest_digest) is None:
            raise AcceptanceArtifactIntegrityMismatch


def _validate_source_transparency(
    source_record: Mapping[str, Any],
    *,
    artifact: ResolvedOutputArtifact,
    tenant_id: str,
    scenario: str,
    resource_type: str,
    resource_id: str,
    output_dir: Path,
    decision: str,
    c2pa_reader_verifier: Callable[[Path], str],
) -> StoredTransparencyAuthority:
    try:
        raw_projection = _result_snapshot(source_record).get("transparency")
        projection = TransparencyProjectionV1.model_validate(raw_projection)
        transparency = StoredTransparencyAuthority(
            sidecar_path=projection.sidecar_path,
            sidecar_sha256=projection.sidecar_sha256,
            final_artifact_c2pa_status=cast(
                Literal["unsigned_pending_review", "signed_local_readback"],
                projection.final_artifact_c2pa_status,
            ),
        )
        if (
            projection.final_artifact_record_id is None
            or projection.final_artifact_c2pa_status
            not in {"unsigned_pending_review", "signed_local_readback"}
        ):
            raise AcceptanceArtifactIntegrityMismatch
        if decision == "accepted" and (
            projection.c2pa_signing_mode != "required"
            or projection.final_artifact_c2pa_status != "signed_local_readback"
        ):
            raise AcceptanceSourceNotEligible
        _validate_transparency_sidecar_binding(
            transparency=transparency,
            artifact=artifact,
            tenant_id=tenant_id,
            scenario=scenario,
            resource_type=resource_type,
            resource_id=resource_id,
            output_dir=output_dir,
            expected_record_id=projection.final_artifact_record_id,
            expected_record_count=projection.record_count,
            c2pa_reader_verifier=c2pa_reader_verifier,
        )
        return transparency
    except AcceptanceSourceNotEligible:
        raise
    except (AcceptanceArtifactIntegrityMismatch, TypeError, ValueError):
        raise AcceptanceSourceNotEligible from None


def _revalidate_stored_transparency(
    record: Mapping[str, Any],
    *,
    artifact: ResolvedOutputArtifact,
    output_dir: Path,
    c2pa_reader_verifier: Callable[[Path], str],
) -> StoredTransparencyAuthority:
    transparency = _validate_stored_transparency_authority(record)
    artifact_authority = _validate_stored_artifact_authority(
        record,
        expected_tenant_id=str(record.get("tenant_id")),
    )
    if transparency.final_artifact_c2pa_status != "signed_local_readback":
        raise AcceptanceArtifactIntegrityMismatch
    _validate_transparency_sidecar_binding(
        transparency=transparency,
        artifact=artifact,
        tenant_id=artifact_authority.tenant_id,
        scenario=artifact_authority.scenario,
        resource_type=artifact_authority.resource_type,
        resource_id=artifact_authority.resource_id,
        output_dir=output_dir,
        expected_record_id=None,
        expected_record_count=None,
        c2pa_reader_verifier=c2pa_reader_verifier,
    )
    return transparency


def _revalidate_stored_publish_authority(
    record: Mapping[str, Any],
    *,
    stored_artifact: StoredArtifactAuthority,
    output_dir: Path,
    c2pa_reader_verifier: Callable[[Path], str],
) -> None:
    artifact = _resolve_exact_artifact(
        stored_artifact.artifact_path,
        tenant_id=stored_artifact.tenant_id,
        resource_type=stored_artifact.resource_type,
        resource_id=stored_artifact.resource_id,
        output_dir=output_dir,
        missing_error=AcceptanceArtifactIntegrityMismatch,
    )
    if (
        artifact.canonical_path != stored_artifact.artifact_path
        or artifact.sha256 != stored_artifact.artifact_sha256
        or artifact.size_bytes != stored_artifact.artifact_size_bytes
    ):
        raise AcceptanceArtifactIntegrityMismatch
    _revalidate_stored_transparency(
        record,
        artifact=artifact,
        output_dir=output_dir,
        c2pa_reader_verifier=c2pa_reader_verifier,
    )


def _validate_stored_artifact_authority(
    record: Mapping[str, Any],
    *,
    expected_tenant_id: str,
) -> StoredArtifactAuthority:
    tenant_id = record.get("tenant_id")
    resource_type = record.get("source_resource_type")
    resource_id = record.get("source_resource_id")
    scenario = record.get("scenario")
    artifact_path = record.get("artifact_path")
    artifact_sha256 = record.get("artifact_sha256")
    artifact_size_bytes = record.get("artifact_size_bytes")

    if not isinstance(tenant_id, str) or tenant_id != expected_tenant_id:
        raise AcceptanceArtifactIntegrityMismatch
    if not isinstance(resource_type, str) or resource_type not in {"fast", "scenario"}:
        raise AcceptanceArtifactIntegrityMismatch
    if (
        not isinstance(resource_id, str)
        or _RESOURCE_ID_RE.fullmatch(resource_id) is None
    ):
        raise AcceptanceArtifactIntegrityMismatch
    if not isinstance(scenario, str) or (
        (resource_type == "fast" and scenario != "fast")
        or (resource_type == "scenario" and scenario not in {"s1", "s2", "s3", "s4", "s5"})
    ):
        raise AcceptanceArtifactIntegrityMismatch
    if record.get("artifact_kind") != "video":
        raise AcceptanceArtifactIntegrityMismatch
    if not isinstance(artifact_path, str):
        raise AcceptanceArtifactIntegrityMismatch

    try:
        canonical_path = validate_output_reference(artifact_path)
        scope = classify_output_scope(canonical_path)
    except ArtifactIdentityError:
        raise AcceptanceArtifactIntegrityMismatch from None
    expected_prefix = _source_prefix(
        tenant_id=tenant_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    if (
        canonical_path != artifact_path
        or scope != tenant_id
        or not canonical_path.startswith(expected_prefix + "/")
        or Path(canonical_path).suffix.lower() not in _VIDEO_SUFFIXES
    ):
        raise AcceptanceArtifactIntegrityMismatch
    if not isinstance(artifact_sha256, str) or _SHA256_RE.fullmatch(artifact_sha256) is None:
        raise AcceptanceArtifactIntegrityMismatch
    if type(artifact_size_bytes) is not int or artifact_size_bytes <= 0:
        raise AcceptanceArtifactIntegrityMismatch

    return StoredArtifactAuthority(
        tenant_id=tenant_id,
        resource_type=cast(AcceptanceResourceType, resource_type),
        resource_id=resource_id,
        scenario=cast(AcceptanceScenario, scenario),
        artifact_path=canonical_path,
        artifact_sha256=artifact_sha256,
        artifact_size_bytes=artifact_size_bytes,
    )


def _ensure_consumable(record: Mapping[str, Any]) -> None:
    status = record.get("record_status")
    if status == "expired":
        raise AcceptanceExpired
    if record.get("decision") != "accepted" or status != "available":
        raise AcceptanceNotAvailable


@overload
def _project_timestamp(value: Any, *, required: Literal[True]) -> str: ...


@overload
def _project_timestamp(value: Any, *, required: Literal[False]) -> str | None: ...


def _project_timestamp(value: Any, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise AcceptanceStoreUnavailable
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if not isinstance(value, str) or not value:
        raise AcceptanceStoreUnavailable
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AcceptanceStoreUnavailable from None
    return value


def _project_record(
    record: Mapping[str, Any],
    *,
    idempotent_replay: bool,
    expected_tenant_id: str,
) -> AcceptanceRecordResponse:
    try:
        artifact = _validate_stored_artifact_authority(
            record,
            expected_tenant_id=expected_tenant_id,
        )
        acceptance_id = record.get("id")
        reviewer_key_id = record.get("reviewer_key_id")
        reviewer_key_type = record.get("reviewer_key_type")
        review_notes = record.get("review_notes")
        decision = record.get("decision")
        status = record.get("record_status")
        if not isinstance(acceptance_id, str) or not acceptance_id.strip():
            raise AcceptanceStoreUnavailable
        if not isinstance(reviewer_key_id, str) or not reviewer_key_id.strip():
            raise AcceptanceStoreUnavailable
        if reviewer_key_type not in _REVIEWER_KEY_TYPES:
            raise AcceptanceStoreUnavailable
        if not isinstance(review_notes, str):
            raise AcceptanceStoreUnavailable
        if decision not in {"accepted", "rejected"}:
            raise AcceptanceStoreUnavailable
        if status not in {"available", "rejected", "consumed", "expired", "revoked"}:
            raise AcceptanceStoreUnavailable
        if (decision == "accepted" and status == "rejected") or (
            decision == "rejected" and status != "rejected"
        ):
            raise AcceptanceStoreUnavailable

        fingerprint_version = record.get("fingerprint_version")
        if fingerprint_version == ACCEPTANCE_FINGERPRINT_VERSION:
            stored_transparency = _validate_stored_transparency_authority(record)
            transparency = AcceptanceTransparencyProjection(
                sidecar_path=stored_transparency.sidecar_path,
                sidecar_sha256=stored_transparency.sidecar_sha256,
                final_artifact_c2pa_status=(
                    stored_transparency.final_artifact_c2pa_status
                ),
            )
        elif fingerprint_version == _LEGACY_ACCEPTANCE_FINGERPRINT_VERSION:
            transparency = None
        else:
            raise AcceptanceStoreUnavailable

        expires_at = _project_timestamp(record.get("expires_at"), required=True)
        consumed_at = _project_timestamp(record.get("consumed_at"), required=False)
        revoked_at = _project_timestamp(record.get("revoked_at"), required=False)
        created_at = _project_timestamp(record.get("created_at"), required=True)
        updated_at = _project_timestamp(record.get("updated_at"), required=True)
        if (status == "consumed") != (consumed_at is not None):
            raise AcceptanceStoreUnavailable
        if (status == "revoked") != (revoked_at is not None):
            raise AcceptanceStoreUnavailable

        return AcceptanceRecordResponse(
            acceptance_id=acceptance_id,
            tenant_id=artifact.tenant_id,
            source_resource_type=artifact.resource_type,
            source_resource_id=artifact.resource_id,
            scenario=artifact.scenario,
            artifact=AcceptanceArtifactProjection(
                path=artifact.artifact_path,
                sha256=artifact.artifact_sha256,
                size_bytes=artifact.artifact_size_bytes,
                kind="video",
            ),
            decision=decision,
            status=status,
            reviewer=AcceptanceReviewerProjection(
                key_id=reviewer_key_id,
                key_type=reviewer_key_type,
            ),
            transparency=transparency,
            review_notes=review_notes,
            expires_at=expires_at,
            consumed_at=consumed_at,
            revoked_at=revoked_at,
            idempotent_replay=idempotent_replay,
            created_at=created_at,
            updated_at=updated_at,
        )
    except AcceptanceArtifactIntegrityMismatch:
        raise AcceptanceStoreUnavailable from None
    except (KeyError, TypeError, ValueError):
        raise AcceptanceStoreUnavailable from None


_service: ArtifactAcceptanceService | None = None


def get_artifact_acceptance_service() -> ArtifactAcceptanceService:
    global _service
    if _service is None:
        _service = ArtifactAcceptanceService()
    return _service


__all__ = [
    "ACCEPTANCE_FINGERPRINT_VERSION",
    "AcceptanceConsumeOutcome",
    "AcceptanceAlreadyAvailable",
    "AcceptanceArtifactIntegrityMismatch",
    "AcceptanceArtifactMismatch",
    "AcceptanceExpired",
    "AcceptanceKeyInvalid",
    "AcceptanceKeyRequired",
    "AcceptanceNotAvailable",
    "AcceptanceNotFound",
    "AcceptanceNotRevocable",
    "AcceptancePayloadConflict",
    "AcceptanceSourceNotEligible",
    "AcceptanceSourceNotTerminal",
    "AcceptanceStoreUnavailable",
    "ArtifactAcceptanceError",
    "ArtifactAcceptanceService",
    "build_acceptance_fingerprint",
    "extract_acceptance_key",
    "get_artifact_acceptance_service",
]
