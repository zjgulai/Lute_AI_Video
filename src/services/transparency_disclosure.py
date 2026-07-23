"""Strict read-only disclosure and evidence-package projection."""

from __future__ import annotations

import io
import re
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol, cast

from pydantic import ValidationError

from src.config import OUTPUT_DIR
from src.models.transparency import (
    TransparencyDisclosureV1,
    TransparencyProjectionV1,
    TransparencyRecordV1,
    load_validated_transparency_sidecar,
)
from src.services.artifact_identity import (
    ArtifactIdentityError,
    canonicalize_output_artifact_path,
    validate_output_reference,
)
from src.storage.idempotency_repository import (
    IdempotencyStoreUnavailableError,
    SubmissionIdempotencyRepository,
)
from src.tools.c2pa_signer import C2PASigningError, verify_signed_media_readback

ResourceType = Literal["fast", "scenario"]
ReaderVerifier = Callable[[Path], str]
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class TransparencyDisclosureError(RuntimeError):
    pass


class TransparencyDisclosureNotFound(TransparencyDisclosureError):
    pass


class TransparencyDisclosureIntegrityError(TransparencyDisclosureError):
    pass


class TransparencyDisclosureStoreUnavailable(TransparencyDisclosureError):
    pass


class SubmissionRepository(Protocol):
    async def get_by_resource(
        self,
        *,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class TransparencyPackage:
    filename: str
    payload: bytes


@dataclass(frozen=True, slots=True)
class _ValidatedDisclosure:
    disclosure: TransparencyDisclosureV1
    sidecar_path: Path
    detached_path: Path
    sidecar_bytes: bytes
    detached_bytes: bytes


class TransparencyDisclosureService:
    def __init__(
        self,
        submission_repository: SubmissionRepository | None = None,
        *,
        output_dir: Path | None = None,
        c2pa_reader_verifier: ReaderVerifier = verify_signed_media_readback,
    ) -> None:
        self.submission_repository = (
            submission_repository or SubmissionIdempotencyRepository()
        )
        self.output_dir = output_dir if output_dir is not None else OUTPUT_DIR
        self.c2pa_reader_verifier = c2pa_reader_verifier

    async def inspect(
        self,
        *,
        tenant_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> TransparencyDisclosureV1:
        validated = await self._validate(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return validated.disclosure

    async def build_package(
        self,
        *,
        tenant_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> TransparencyPackage:
        validated = await self._validate(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, payload in (
                (validated.sidecar_path.name, validated.sidecar_bytes),
                (validated.detached_path.name, validated.detached_bytes),
            ):
                entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.external_attr = 0o600 << 16
                archive.writestr(entry, payload)
        return TransparencyPackage(
            filename=f"transparency-{resource_id}.zip",
            payload=buffer.getvalue(),
        )

    async def _validate(
        self,
        *,
        tenant_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> _ValidatedDisclosure:
        if (
            not isinstance(tenant_id, str)
            or not tenant_id
            or resource_type not in {"fast", "scenario"}
            or _RESOURCE_ID_RE.fullmatch(resource_id) is None
        ):
            raise TransparencyDisclosureNotFound
        try:
            record = await self.submission_repository.get_by_resource(
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        except IdempotencyStoreUnavailableError as exc:
            raise TransparencyDisclosureStoreUnavailable from exc
        except Exception as exc:
            raise TransparencyDisclosureStoreUnavailable from exc
        if record is None or record.get("tenant_id") != tenant_id:
            raise TransparencyDisclosureNotFound

        try:
            projection, scenario = self._projection_from_record(
                record,
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            self._validate_projection_scope(
                projection,
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            required_prefix = projection.sidecar_path.rsplit("/transparency/", 1)[0]
            resolved_sidecar = canonicalize_output_artifact_path(
                projection.sidecar_path,
                output_dir=self.output_dir,
                tenant_id=tenant_id,
                required_prefix=required_prefix,
                allowed_suffixes={".json"},
                allow_absolute_under_root=False,
            )
            if resolved_sidecar.canonical_path != projection.sidecar_path:
                raise TransparencyDisclosureIntegrityError
            sidecar_path = resolved_sidecar.absolute_path
            validated_sidecar = load_validated_transparency_sidecar(
                sidecar_path,
                expected_sha256=projection.sidecar_sha256,
                artifact_root=self.output_dir,
            )
            sidecar = validated_sidecar.sidecar
            records = tuple(sidecar.records)
            if len(records) != projection.record_count:
                raise TransparencyDisclosureIntegrityError
            if any(
                item.tenant_id != tenant_id
                or item.scenario != scenario
                or item.resource_id != resource_id
                for item in records
            ):
                raise TransparencyDisclosureIntegrityError
            verification_scope = self._verification_scope(
                projection,
                records,
            )
            disclosure = TransparencyDisclosureV1(
                verification_scope=verification_scope,
                sidecar_path=projection.sidecar_path,
                sidecar_sha256=projection.sidecar_sha256,
                record_count=len(records),
                human_edit_record_count=sum(
                    item.origin_kind == "human_edit" for item in records
                ),
                source_reference_count=sum(
                    len(item.source_record_ids) for item in records
                ),
                c2pa_signing_mode=projection.c2pa_signing_mode,
                final_artifact_c2pa_status=projection.final_artifact_c2pa_status,
            )
            detached_path = sidecar_path.with_name(sidecar_path.name + ".sha256")
            return _ValidatedDisclosure(
                disclosure,
                sidecar_path,
                detached_path,
                validated_sidecar.sidecar_bytes,
                validated_sidecar.detached_bytes,
            )
        except TransparencyDisclosureIntegrityError:
            raise
        except (
            ArtifactIdentityError,
            C2PASigningError,
            OSError,
            TypeError,
            ValidationError,
            ValueError,
        ):
            raise TransparencyDisclosureIntegrityError from None

    @staticmethod
    def _projection_from_record(
        record: Mapping[str, Any],
        *,
        tenant_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> tuple[TransparencyProjectionV1, Literal["fast", "s1", "s2", "s3", "s4", "s5"]]:
        scenario = record.get("scenario")
        expected_scenario = scenario == "fast" if resource_type == "fast" else scenario in {
            "s1",
            "s2",
            "s3",
            "s4",
            "s5",
        }
        snapshot = record.get("result_snapshot")
        if (
            record.get("resource_type") != resource_type
            or record.get("resource_id") != resource_id
            or record.get("tenant_id") != tenant_id
            or record.get("record_status") != "completed"
            or not expected_scenario
            or not isinstance(snapshot, Mapping)
        ):
            raise TransparencyDisclosureIntegrityError
        projection = TransparencyProjectionV1.model_validate(snapshot.get("transparency"))
        return projection, cast(
            Literal["fast", "s1", "s2", "s3", "s4", "s5"], scenario
        )

    @staticmethod
    def _validate_projection_scope(
        projection: TransparencyProjectionV1,
        *,
        tenant_id: str,
        resource_type: ResourceType,
        resource_id: str,
    ) -> None:
        canonical = validate_output_reference(projection.sidecar_path)
        if canonical != projection.sidecar_path:
            raise TransparencyDisclosureIntegrityError
        parts = PurePosixPath(canonical).parts
        if len(parts) < 6 or parts[:2] != ("tenants", tenant_id):
            raise TransparencyDisclosureIntegrityError
        if parts[2] not in {"pending_review", "quarantine"}:
            raise TransparencyDisclosureIntegrityError
        if resource_type == "fast":
            expected = ("tenants", tenant_id, parts[2], "fast_mode", resource_id, "transparency")
        else:
            expected = ("tenants", tenant_id, parts[2], resource_id, "transparency")
        if parts[: len(expected)] != expected:
            raise TransparencyDisclosureIntegrityError

    def _verification_scope(
        self,
        projection: TransparencyProjectionV1,
        records: tuple[TransparencyRecordV1, ...],
    ) -> Literal["provenance_only", "unsigned_pending_review", "local_reader_only"]:
        record_id = projection.final_artifact_record_id
        status = projection.final_artifact_c2pa_status
        if record_id is None:
            if status is not None:
                raise TransparencyDisclosureIntegrityError
            return "provenance_only"
        matches = [item for item in records if item.record_id == record_id]
        if len(matches) != 1:
            raise TransparencyDisclosureIntegrityError
        final = matches[0]
        if (
            final.artifact is None
            or final.content_kind not in {"image", "video"}
            or final.simulated
            or final.c2pa_status != status
        ):
            raise TransparencyDisclosureIntegrityError
        if status == "unsigned_pending_review":
            if projection.c2pa_signing_mode != "local_draft":
                raise TransparencyDisclosureIntegrityError
            return "unsigned_pending_review"
        if status != "signed_local_readback" or projection.c2pa_signing_mode != "required":
            raise TransparencyDisclosureIntegrityError
        media_path = self.output_dir.joinpath(*PurePosixPath(final.artifact.relative_path).parts)
        digest = self.c2pa_reader_verifier(media_path)
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise TransparencyDisclosureIntegrityError
        return "local_reader_only"


_service: TransparencyDisclosureService | None = None


def get_transparency_disclosure_service() -> TransparencyDisclosureService:
    global _service
    if _service is None:
        _service = TransparencyDisclosureService()
    return _service


__all__ = [
    "TransparencyDisclosureError",
    "TransparencyDisclosureIntegrityError",
    "TransparencyDisclosureNotFound",
    "TransparencyDisclosureService",
    "TransparencyDisclosureStoreUnavailable",
    "TransparencyPackage",
    "get_transparency_disclosure_service",
]
