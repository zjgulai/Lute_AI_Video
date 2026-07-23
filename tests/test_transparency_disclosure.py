from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Any, Literal, cast

import pytest
from fastapi import HTTPException

from src.models.transparency import (
    C2PAStatus,
    TransparencyProjectionV1,
    build_file_transparency_record,
    build_inline_transparency_record,
    build_transparency_sidecar,
    transparency_sidecar_sha256,
    write_transparency_sidecar,
)
from src.routers._deps import ApiKeyType, AuthContext
from src.services.transparency_disclosure import (
    TransparencyDisclosureIntegrityError,
    TransparencyDisclosureNotFound,
    TransparencyDisclosureService,
)

TENANT_ID = "tenant-transparency"
RESOURCE_ID = "s1-disclosure-fixture"


class FakeSubmissionRepository:
    def __init__(self, record: dict[str, Any] | None) -> None:
        self.record = record
        self.calls: list[tuple[str, str, str]] = []

    async def get_by_resource(
        self,
        *,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        self.calls.append((tenant_id, resource_type, resource_id))
        return self.record


def _seed_record(
    output_dir: Path,
    *,
    c2pa_status: C2PAStatus = "signed_local_readback",
) -> tuple[dict[str, Any], TransparencyProjectionV1, bytes, bytes, Path]:
    run_root = output_dir / "tenants" / TENANT_ID / "pending_review" / RESOURCE_ID
    run_root.mkdir(parents=True)
    video_path = run_root / "artifacts" / "final.mp4"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"strict-disclosure-video")

    generated = build_inline_transparency_record(
        tenant_id=TENANT_ID,
        scenario="s1",
        resource_id=RESOURCE_ID,
        producer_step="scripts",
        content_kind="text",
        content={"digest_only": True},
        origin_kind="provider",
        provider="fixture",
        model="fixture-model",
        generated_at="2026-07-23T00:00:00Z",
        parent_record_ids=(),
        simulated=False,
    )
    edited = build_inline_transparency_record(
        tenant_id=TENANT_ID,
        scenario="s1",
        resource_id=RESOURCE_ID,
        producer_step="scripts",
        content_kind="text",
        content={"digest_only": "edited"},
        origin_kind="human_edit",
        provider=None,
        model=None,
        generated_at="2026-07-23T00:01:00Z",
        parent_record_ids=(generated.record_id,),
        source_record_ids=(generated.record_id,),
        human_edit_ids=(hashlib.sha256(b"review-edit-1").hexdigest(),),
        simulated=False,
    )
    final = build_file_transparency_record(
        tenant_id=TENANT_ID,
        scenario="s1",
        resource_id=RESOURCE_ID,
        producer_step="assemble_final",
        content_kind="video",
        artifact_path=video_path.relative_to(output_dir),
        artifact_root=output_dir,
        origin_kind="local",
        provider=None,
        model=None,
        generated_at="2026-07-23T00:02:00Z",
        parent_record_ids=(),
        source_record_ids=(edited.record_id,),
        simulated=False,
        c2pa_status=c2pa_status,
    )
    sidecar = build_transparency_sidecar([generated, edited, final])
    digest = transparency_sidecar_sha256(sidecar)
    sidecar_path = run_root / "transparency" / f"transparency-sidecar.v1.{digest}.json"
    write_transparency_sidecar(sidecar_path, sidecar, output_root=output_dir)
    relative_sidecar = sidecar_path.relative_to(output_dir).as_posix()
    projection = TransparencyProjectionV1(
        sidecar_path=relative_sidecar,
        sidecar_sha256=digest,
        record_count=3,
        c2pa_signing_mode=(
            "required" if c2pa_status == "signed_local_readback" else "local_draft"
        ),
        final_artifact_record_id=final.record_id,
        final_artifact_c2pa_status=c2pa_status,
    )
    record = {
        "tenant_id": TENANT_ID,
        "resource_type": "scenario",
        "resource_id": RESOURCE_ID,
        "scenario": "s1",
        "record_status": "completed",
        "result_snapshot": {"transparency": projection.model_dump(mode="json")},
    }
    return (
        record,
        projection,
        sidecar_path.read_bytes(),
        sidecar_path.with_name(sidecar_path.name + ".sha256").read_bytes(),
        video_path,
    )


@pytest.mark.asyncio
async def test_signed_disclosure_revalidates_sidecar_and_projects_bounded_truth(
    tmp_path: Path,
) -> None:
    record, projection, _, _, video_path = _seed_record(tmp_path)
    reader_calls: list[Path] = []

    def reader(path: Path) -> str:
        reader_calls.append(path)
        return "b" * 64

    repository = FakeSubmissionRepository(record)
    service = TransparencyDisclosureService(
        submission_repository=repository,
        output_dir=tmp_path,
        c2pa_reader_verifier=reader,
    )

    disclosure = await service.inspect(
        tenant_id=TENANT_ID,
        resource_type="scenario",
        resource_id=RESOURCE_ID,
    )

    assert disclosure.ai_generated is True
    assert disclosure.label == "AI-generated"
    assert disclosure.verification_scope == "local_reader_only"
    assert disclosure.independently_validated is False
    assert disclosure.sidecar_path == projection.sidecar_path
    assert disclosure.sidecar_sha256 == projection.sidecar_sha256
    assert disclosure.record_count == 3
    assert disclosure.human_edit_record_count == 1
    assert disclosure.source_reference_count == 2
    assert disclosure.package_available is True
    assert reader_calls == [video_path]


@pytest.mark.asyncio
async def test_unsigned_disclosure_stays_pending_and_never_calls_reader(
    tmp_path: Path,
) -> None:
    record, _, _, _, _ = _seed_record(
        tmp_path,
        c2pa_status="unsigned_pending_review",
    )

    def reader(path: Path) -> str:
        raise AssertionError(f"unsigned disclosure must not call Reader: {path.name}")

    service = TransparencyDisclosureService(
        submission_repository=FakeSubmissionRepository(record),
        output_dir=tmp_path,
        c2pa_reader_verifier=reader,
    )

    disclosure = await service.inspect(
        tenant_id=TENANT_ID,
        resource_type="scenario",
        resource_id=RESOURCE_ID,
    )

    assert disclosure.verification_scope == "unsigned_pending_review"
    assert disclosure.final_artifact_c2pa_status == "unsigned_pending_review"
    assert disclosure.independently_validated is False


@pytest.mark.asyncio
async def test_package_contains_exact_sidecar_and_detached_digest(tmp_path: Path) -> None:
    record, _, sidecar_bytes, digest_bytes, _ = _seed_record(tmp_path)
    service = TransparencyDisclosureService(
        submission_repository=FakeSubmissionRepository(record),
        output_dir=tmp_path,
        c2pa_reader_verifier=lambda path: "c" * 64,
    )

    package = await service.build_package(
        tenant_id=TENANT_ID,
        resource_type="scenario",
        resource_id=RESOURCE_ID,
    )

    with zipfile.ZipFile(io.BytesIO(package.payload)) as archive:
        names = archive.namelist()
        assert len(names) == 2
        assert names[0].endswith(".json")
        assert names[1] == names[0] + ".sha256"
        assert archive.read(names[0]) == sidecar_bytes
        assert archive.read(names[1]) == digest_bytes
    assert package.filename == f"transparency-{RESOURCE_ID}.zip"


@pytest.mark.asyncio
async def test_package_uses_the_exact_bytes_bound_during_validation(
    tmp_path: Path,
) -> None:
    record, _, sidecar_bytes, digest_bytes, _ = _seed_record(tmp_path)

    class DriftAfterValidationService(TransparencyDisclosureService):
        async def _validate(
            self,
            *,
            tenant_id: str,
            resource_type: Literal["fast", "scenario"],
            resource_id: str,
        ) -> Any:
            validated = await super()._validate(
                tenant_id=tenant_id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            validated.sidecar_path.write_bytes(b"UNVALIDATED-SIDECAR")
            validated.detached_path.write_bytes(b"UNVALIDATED-DIGEST")
            return validated

    service = DriftAfterValidationService(
        submission_repository=FakeSubmissionRepository(record),
        output_dir=tmp_path,
        c2pa_reader_verifier=lambda path: "c" * 64,
    )

    package = await service.build_package(
        tenant_id=TENANT_ID,
        resource_type="scenario",
        resource_id=RESOURCE_ID,
    )

    with zipfile.ZipFile(io.BytesIO(package.payload)) as archive:
        names = archive.namelist()
        assert archive.read(names[0]) == sidecar_bytes
        assert archive.read(names[1]) == digest_bytes


@pytest.mark.asyncio
async def test_missing_or_inconsistent_projection_fails_closed(tmp_path: Path) -> None:
    record, projection, _, _, _ = _seed_record(tmp_path)
    missing = {**record, "result_snapshot": {}}
    mismatched = {
        **record,
        "result_snapshot": {
            "transparency": {
                **projection.model_dump(mode="json"),
                "sidecar_sha256": "f" * 64,
            }
        },
    }

    for candidate in (missing, mismatched):
        service = TransparencyDisclosureService(
            submission_repository=FakeSubmissionRepository(candidate),
            output_dir=tmp_path,
            c2pa_reader_verifier=lambda path: "d" * 64,
        )
        with pytest.raises(TransparencyDisclosureIntegrityError):
            await service.inspect(
                tenant_id=TENANT_ID,
                resource_type="scenario",
                resource_id=RESOURCE_ID,
            )


@pytest.mark.asyncio
async def test_missing_or_cross_tenant_resource_is_not_disclosed(tmp_path: Path) -> None:
    record, _, _, _, _ = _seed_record(tmp_path)
    for candidate in (None, record):
        service = TransparencyDisclosureService(
            submission_repository=FakeSubmissionRepository(candidate),
            output_dir=tmp_path,
            c2pa_reader_verifier=lambda path: "e" * 64,
        )
        with pytest.raises(TransparencyDisclosureNotFound):
            await service.inspect(
                tenant_id="tenant-other",
                resource_type="scenario",
                resource_id=RESOURCE_ID,
            )


@pytest.mark.asyncio
async def test_read_and_package_routes_are_tenant_bound() -> None:
    from src.models.transparency import TransparencyDisclosureV1
    from src.routers.media import (
        get_transparency_disclosure,
        get_transparency_package,
    )
    from src.services.transparency_disclosure import TransparencyPackage

    calls: list[tuple[str, str, str]] = []

    class FakeService:
        async def inspect(self, *, tenant_id: str, resource_type: str, resource_id: str):
            calls.append((tenant_id, resource_type, resource_id))
            return TransparencyDisclosureV1(
                verification_scope="provenance_only",
                sidecar_path=(
                    f"tenants/{tenant_id}/pending_review/{resource_id}/transparency/"
                    f"transparency-sidecar.v1.{'a' * 64}.json"
                ),
                sidecar_sha256="a" * 64,
                record_count=1,
                human_edit_record_count=0,
                source_reference_count=0,
                c2pa_signing_mode="local_draft",
                final_artifact_c2pa_status=None,
            )

        async def build_package(
            self,
            *,
            tenant_id: str,
            resource_type: str,
            resource_id: str,
        ) -> TransparencyPackage:
            calls.append((tenant_id, resource_type, resource_id))
            return TransparencyPackage(
                filename=f"transparency-{resource_id}.zip",
                payload=b"strict-package",
            )

    auth = AuthContext(
        tenant_id=TENANT_ID,
        permissions=frozenset({"all"}),
        key_type=ApiKeyType.TENANT,
        key_id="disclosure-reader",
    )
    service = FakeService()

    disclosure = await get_transparency_disclosure(
        "scenario",
        RESOURCE_ID,
        auth,
        cast(TransparencyDisclosureService, service),
    )
    package = await get_transparency_package(
        "scenario",
        RESOURCE_ID,
        auth,
        cast(TransparencyDisclosureService, service),
    )

    assert disclosure.label == "AI-generated"
    assert package.body == b"strict-package"
    assert package.media_type == "application/zip"
    assert package.headers["content-disposition"] == (
        f'attachment; filename="transparency-{RESOURCE_ID}.zip"'
    )
    assert calls == [
        (TENANT_ID, "scenario", RESOURCE_ID),
        (TENANT_ID, "scenario", RESOURCE_ID),
    ]


@pytest.mark.asyncio
async def test_transparency_route_maps_integrity_failure_without_partial_package() -> None:
    from src.routers.media import get_transparency_package

    class FailingService:
        async def build_package(self, **kwargs: object):
            del kwargs
            raise TransparencyDisclosureIntegrityError

    auth = AuthContext(
        tenant_id=TENANT_ID,
        permissions=frozenset({"all"}),
        key_type=ApiKeyType.TENANT,
        key_id="disclosure-reader",
    )
    with pytest.raises(HTTPException) as error:
        await get_transparency_package(
            "scenario",
            RESOURCE_ID,
            auth,
            cast(TransparencyDisclosureService, FailingService()),
        )
    assert error.value.status_code == 409
    assert error.value.detail == "transparency_integrity_error"
