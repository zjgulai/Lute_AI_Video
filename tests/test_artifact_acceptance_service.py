"""Acceptance service contracts over real files and the durable SQLite repositories."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request

from src.models.acceptance import AcceptanceCreateRequest
from src.models.transparency import (
    C2PAStatus,
    SigningMode,
    TransparencyProjectionV1,
    build_file_transparency_record,
    build_transparency_sidecar,
    transparency_sidecar_sha256,
    write_transparency_sidecar,
)
from src.routers._deps import ApiKeyType, AuthContext
from src.services import artifact_acceptance as service_module
from src.services.artifact_acceptance import (
    ACCEPTANCE_FINGERPRINT_VERSION,
    AcceptanceAlreadyAvailable,
    AcceptanceArtifactIntegrityMismatch,
    AcceptanceArtifactMismatch,
    AcceptanceExpired,
    AcceptanceKeyInvalid,
    AcceptanceKeyRequired,
    AcceptanceNotAvailable,
    AcceptanceNotFound,
    AcceptanceNotRevocable,
    AcceptancePayloadConflict,
    AcceptanceSourceNotEligible,
    AcceptanceSourceNotTerminal,
    AcceptanceStoreUnavailable,
    ArtifactAcceptanceService,
    build_acceptance_fingerprint,
    extract_acceptance_key,
)
from src.services.submission_idempotency import hash_idempotency_key
from src.storage import db as db_module
from src.storage.acceptance_repository import AcceptanceRecordRepository
from src.storage.idempotency_repository import SubmissionIdempotencyRepository

TENANT_ID = "tenant-alpha"
REVIEWER_ID = "reviewer-a"
VALID_KEY = "acceptance-action-0001"
VIDEO_BYTES = b"fixture-final-video-bytes"
INVALID_STORED_RESOURCE_IDS = {
    "source_id_slash": "nested/resource",
    "source_id_whitespace": "nested resource",
    "source_id_129_chars": "r" * 129,
}


def _auth(
    *,
    tenant_id: str = TENANT_ID,
    reviewer_key_id: str | None = REVIEWER_ID,
) -> AuthContext:
    return AuthContext(
        tenant_id=tenant_id,
        permissions=frozenset({"artifact:accept"}),
        key_type=ApiKeyType.TENANT,
        key_id=reviewer_key_id,
    )


def _artifact_path(scenario: str, resource_id: str, *, tenant_id: str = TENANT_ID) -> str:
    if scenario == "fast":
        return (
            f"tenants/{tenant_id}/pending_review/fast_mode/"
            f"{resource_id}/final.mp4"
        )
    return (
        f"tenants/{tenant_id}/pending_review/{resource_id}/"
        "assemble/final.mp4"
    )


def _request(
    *,
    scenario: str = "s1",
    resource_id: str | None = None,
    artifact_path: str | None = None,
    decision: str = "accepted",
    review_notes: str = "Human reviewed the exact final video.",
) -> AcceptanceCreateRequest:
    actual_resource_id = resource_id or f"{scenario}_service_fixture"
    return AcceptanceCreateRequest.model_validate(
        {
            "source_resource_type": "fast" if scenario == "fast" else "scenario",
            "source_resource_id": actual_resource_id,
            "artifact_path": artifact_path
            or _artifact_path(scenario, actual_resource_id),
            "decision": decision,
            "review_notes": review_notes,
            "expires_in_seconds": 3600,
        }
    )


@dataclass(slots=True)
class AcceptanceHarness:
    connection: sqlite3.Connection
    output_dir: Path
    service: ArtifactAcceptanceService

    def write_artifact(
        self,
        path: str,
        *,
        content: bytes = VIDEO_BYTES,
    ) -> Path:
        absolute = self.output_dir / path
        absolute.parent.mkdir(parents=True, exist_ok=True)
        absolute.write_bytes(content)
        if content:
            self.attach_transparency(path)
        return absolute

    def attach_transparency(
        self,
        path: str,
        *,
        c2pa_status: C2PAStatus = "signed_local_readback",
        signing_mode: SigningMode = "required",
    ) -> dict[str, object]:
        parts = Path(path).parts
        resource_type = "fast" if "fast_mode" in parts else "scenario"
        resource_id = parts[4] if resource_type == "fast" else parts[3]
        row = self.connection.execute(
            """
            SELECT id, scenario, result_snapshot FROM idempotency_records
            WHERE tenant_id = ? AND resource_type = ? AND resource_id = ?
            """,
            (TENANT_ID, resource_type, resource_id),
        ).fetchone()
        if row is None:
            return {}
        record = build_file_transparency_record(
            tenant_id=TENANT_ID,
            scenario=row["scenario"],
            resource_id=resource_id,
            producer_step="video" if resource_type == "fast" else "assemble_final",
            content_kind="video",
            artifact_path=path,
            artifact_root=self.output_dir,
            origin_kind="local",
            provider=None,
            model=None,
            generated_at="2026-07-22T00:00:00Z",
            parent_record_ids=(),
            simulated=False,
            c2pa_status=c2pa_status,
        )
        sidecar = build_transparency_sidecar([record])
        digest = transparency_sidecar_sha256(sidecar)
        run_root = Path(*parts[:5]) if resource_type == "fast" else Path(*parts[:4])
        relative_sidecar = (
            run_root
            / "transparency"
            / f"transparency-sidecar.v1.{digest}.json"
        )
        sidecar_path = self.output_dir / relative_sidecar
        if not sidecar_path.exists():
            write_transparency_sidecar(
                sidecar_path,
                sidecar,
                output_root=self.output_dir,
            )
        projection = TransparencyProjectionV1(
            sidecar_path=relative_sidecar.as_posix(),
            sidecar_sha256=digest,
            record_count=1,
            c2pa_signing_mode=signing_mode,
            final_artifact_record_id=record.record_id,
            final_artifact_c2pa_status=c2pa_status,
        ).model_dump(mode="json")
        snapshot = json.loads(row["result_snapshot"])
        snapshot["transparency"] = projection
        self.connection.execute(
            "UPDATE idempotency_records SET result_snapshot = ? WHERE id = ?",
            (json.dumps(snapshot, sort_keys=True), row["id"]),
        )
        self.connection.commit()
        return projection

    def seed_source(
        self,
        *,
        scenario: str,
        resource_id: str,
        record_status: str = "completed",
        full_media_success: bool = True,
        is_stub: bool = False,
        pipeline_degraded: bool = False,
        artifact_disposition: str = "pending_review",
        artifact_path: str | None = None,
        include_artifact: bool = True,
    ) -> str:
        resource_type = "fast" if scenario == "fast" else "scenario"
        final_path = artifact_path or _artifact_path(scenario, resource_id)
        snapshot: dict[str, object] = {
            "full_media_success": full_media_success,
            "is_stub": is_stub,
            "pipeline_degraded": pipeline_degraded,
            "artifact_disposition": artifact_disposition,
            "artifact_kind": "video",
        }
        if include_artifact:
            snapshot[
                "video_path" if scenario == "fast" else "final_artifact_path"
            ] = final_path
        key_hash = hashlib.sha256(
            f"source:{TENANT_ID}:{resource_type}:{resource_id}".encode()
        ).hexdigest()
        self.connection.execute(
            """
            INSERT INTO idempotency_records (
                id, tenant_id, key_hash, fingerprint_version, request_hash,
                operation, scenario, resource_type, resource_id, record_status,
                stage, effective_policy_version, response_status, response_body,
                result_snapshot, completed_at
            ) VALUES (?, ?, ?, 'submit-fingerprint.v1', ?, ?, ?, ?, ?, ?, ?,
                      'generation-policy.v1', 200, '{}', ?, CURRENT_TIMESTAMP)
            """,
            (
                f"source-{resource_id}",
                TENANT_ID,
                key_hash,
                hashlib.sha256(f"request:{resource_id}".encode()).hexdigest(),
                f"{resource_type}.submit",
                scenario,
                resource_type,
                resource_id,
                record_status,
                record_status,
                json.dumps(snapshot, sort_keys=True),
            ),
        )
        self.connection.commit()
        return final_path

    def expire(self, acceptance_id: str) -> None:
        self.connection.execute(
            """
            UPDATE acceptance_records
            SET created_at = datetime('now', '-2 hours'),
                expires_at = datetime('now', '-1 hour')
            WHERE id = ?
            """,
            (acceptance_id,),
        )
        self.connection.commit()


@pytest.fixture
def acceptance_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[AcceptanceHarness]:
    connection = sqlite3.connect(
        str(tmp_path / "acceptance-service.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    db_module._create_sqlite_tables()

    output_dir = tmp_path / "output"
    output_dir.mkdir()
    service = ArtifactAcceptanceService(
        AcceptanceRecordRepository(require_postgres=False),
        SubmissionIdempotencyRepository(require_postgres=False),
        output_dir=output_dir,
        c2pa_reader_verifier=lambda path: "b" * 64,
    )
    yield AcceptanceHarness(connection, output_dir, service)
    connection.close()


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/acceptance-records",
            "headers": headers,
        }
    )


def test_fingerprint_includes_reviewer_and_excludes_credentials() -> None:
    request = _request()
    first = build_acceptance_fingerprint(
        request,
        tenant_id=TENANT_ID,
        reviewer_key_id="reviewer-a",
        reviewer_key_type="tenant",
        transparency_sidecar_path="tenants/tenant-alpha/pending_review/s1_service_fixture/transparency/transparency-sidecar.v1.json",
        transparency_sidecar_sha256="a" * 64,
        final_artifact_c2pa_status="signed_local_readback",
    )
    second = build_acceptance_fingerprint(
        request,
        tenant_id=TENANT_ID,
        reviewer_key_id="reviewer-b",
        reviewer_key_type="tenant",
        transparency_sidecar_path="tenants/tenant-alpha/pending_review/s1_service_fixture/transparency/transparency-sidecar.v1.json",
        transparency_sidecar_sha256="a" * 64,
        final_artifact_c2pa_status="signed_local_readback",
    )

    assert first.version == ACCEPTANCE_FINGERPRINT_VERSION
    assert first.request_hash != second.request_hash
    assert "reviewer-a" not in first.request_hash
    assert VALID_KEY not in first.request_hash


@pytest.mark.asyncio
async def test_accepted_record_binds_transparency_and_c2pa_facts(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_transparency_binding"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    projection = acceptance_harness.attach_transparency(final_path)

    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-transparency-0001",
        request=_request(scenario="s1", resource_id=resource_id),
    )

    stored = acceptance_harness.connection.execute(
        "SELECT * FROM acceptance_records WHERE id = ?",
        (record.acceptance_id,),
    ).fetchone()
    assert stored["fingerprint_version"] == "acceptance-create.v2"
    assert stored["transparency_sidecar_path"] == projection["sidecar_path"]
    assert stored["transparency_sidecar_sha256"] == projection["sidecar_sha256"]
    assert stored["final_artifact_c2pa_status"] == "signed_local_readback"
    assert record.transparency is not None
    assert record.transparency.ai_generated is True
    assert record.transparency.label == "AI-generated"
    assert record.transparency.sidecar_path == projection["sidecar_path"]
    assert record.transparency.sidecar_sha256 == projection["sidecar_sha256"]
    assert record.transparency.final_artifact_c2pa_status == "signed_local_readback"
    assert record.transparency.independently_validated is False


@pytest.mark.asyncio
async def test_unsigned_local_draft_cannot_create_available_acceptance(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_unsigned_source"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    acceptance_harness.attach_transparency(
        final_path,
        c2pa_status="unsigned_pending_review",
        signing_mode="local_draft",
    )

    with pytest.raises(AcceptanceSourceNotEligible):
        await acceptance_harness.service.create(
            auth=_auth(),
            raw_key="acceptance-transparency-0002",
            request=_request(scenario="s1", resource_id=resource_id),
        )


@pytest.mark.asyncio
async def test_publish_inspect_revalidates_bound_sidecar(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_sidecar_drift"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-transparency-0003",
        request=_request(scenario="s1", resource_id=resource_id),
    )
    stored = acceptance_harness.connection.execute(
        "SELECT transparency_sidecar_path FROM acceptance_records WHERE id = ?",
        (record.acceptance_id,),
    ).fetchone()
    (acceptance_harness.output_dir / stored[0]).write_text("{}", encoding="utf-8")

    with pytest.raises(AcceptanceArtifactIntegrityMismatch):
        await acceptance_harness.service.inspect_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
        )


@pytest.mark.asyncio
async def test_acceptance_rejects_projection_record_count_drift(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_projection_count_drift"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    row = acceptance_harness.connection.execute(
        "SELECT id, result_snapshot FROM idempotency_records WHERE resource_id = ?",
        (resource_id,),
    ).fetchone()
    snapshot = json.loads(row["result_snapshot"])
    snapshot["transparency"]["record_count"] = 2
    acceptance_harness.connection.execute(
        "UPDATE idempotency_records SET result_snapshot = ? WHERE id = ?",
        (json.dumps(snapshot, sort_keys=True), row["id"]),
    )
    acceptance_harness.connection.commit()

    with pytest.raises(AcceptanceSourceNotEligible):
        await acceptance_harness.service.create(
            auth=_auth(),
            raw_key="acceptance-transparency-count-0001",
            request=_request(scenario="s1", resource_id=resource_id),
        )


def test_extract_acceptance_key_maps_missing_invalid_and_duplicate_headers() -> None:
    with pytest.raises(AcceptanceKeyRequired):
        extract_acceptance_key(_request_with_headers([]))
    with pytest.raises(AcceptanceKeyInvalid):
        extract_acceptance_key(
            _request_with_headers([(b"idempotency-key", b"too-short")])
        )
    with pytest.raises(AcceptanceKeyInvalid):
        extract_acceptance_key(
            _request_with_headers(
                [
                    (b"idempotency-key", VALID_KEY.encode()),
                    (b"idempotency-key", VALID_KEY.encode()),
                ]
            )
        )
    assert (
        extract_acceptance_key(
            _request_with_headers([(b"idempotency-key", VALID_KEY.encode())])
        )
        == VALID_KEY
    )


@pytest.mark.parametrize("scenario", ["fast", "s1", "s2", "s3", "s4", "s5"])
@pytest.mark.asyncio
async def test_accepted_final_video_is_created_for_fast_and_s1_to_s5(
    acceptance_harness: AcceptanceHarness,
    scenario: str,
) -> None:
    resource_id = f"{scenario}_eligible_fixture"
    final_path = acceptance_harness.seed_source(
        scenario=scenario,
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)

    record, replay = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=f"acceptance-{scenario}-00000001",
        request=_request(scenario=scenario, resource_id=resource_id),
    )

    assert replay is False
    assert record.idempotent_replay is False
    assert record.tenant_id == TENANT_ID
    assert record.scenario == scenario
    assert record.status == "available"
    assert record.decision == "accepted"
    assert record.reviewer.key_id == REVIEWER_ID
    assert record.artifact.path == final_path
    assert record.artifact.sha256 == hashlib.sha256(VIDEO_BYTES).hexdigest()
    assert record.artifact.size_bytes == len(VIDEO_BYTES)


@pytest.mark.asyncio
async def test_same_key_replay_returns_current_record_without_source_or_file_access(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = "s1_replay_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s1", resource_id=resource_id)
    first, replay = await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )
    assert replay is False
    revoked = await acceptance_harness.service.revoke(
        auth=_auth(), acceptance_id=first.acceptance_id
    )
    assert revoked.status == "revoked"

    calls = {"source_repository": 0, "source_resolver": 0, "file_resolver": 0}

    async def forbidden_source_repository(**_: Any) -> None:
        calls["source_repository"] += 1
        raise AssertionError("same-key replay touched durable source")

    def forbidden_source_resolver(*_: Any, **__: Any) -> None:
        calls["source_resolver"] += 1
        raise AssertionError("same-key replay resolved source")

    def forbidden_file_resolver(*_: Any, **__: Any) -> None:
        calls["file_resolver"] += 1
        raise AssertionError("same-key replay touched file")

    monkeypatch.setattr(
        acceptance_harness.service.submission_repository,
        "get_by_resource",
        forbidden_source_repository,
    )
    monkeypatch.setattr(
        service_module,
        "resolve_acceptance_source",
        forbidden_source_resolver,
    )
    monkeypatch.setattr(
        service_module,
        "resolve_output_artifact",
        forbidden_file_resolver,
    )

    current, replay = await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )

    assert replay is True
    assert current.acceptance_id == first.acceptance_id
    assert current.status == "revoked"
    assert current.idempotent_replay is True
    assert calls == {"source_repository": 0, "source_resolver": 0, "file_resolver": 0}


@pytest.mark.asyncio
async def test_legacy_v1_record_remains_readable_revocable_and_replayable(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_legacy_v1_replay_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    artifact = acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s1", resource_id=resource_id)
    first, _ = await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )
    legacy = service_module._build_legacy_acceptance_fingerprint(
        request,
        tenant_id=TENANT_ID,
        reviewer_key_id=REVIEWER_ID,
        reviewer_key_type="tenant",
    )
    acceptance_harness.connection.execute(
        """
        UPDATE acceptance_records
        SET fingerprint_version = ?, request_hash = ?,
            transparency_sidecar_path = NULL,
            transparency_sidecar_sha256 = NULL,
            final_artifact_c2pa_status = NULL
        WHERE id = ?
        """,
        (legacy.version, legacy.request_hash, first.acceptance_id),
    )
    acceptance_harness.connection.commit()

    readback = await acceptance_harness.service.read(
        auth=_auth(), acceptance_id=first.acceptance_id
    )
    revoked = await acceptance_harness.service.revoke(
        auth=_auth(), acceptance_id=first.acceptance_id
    )
    artifact.unlink()
    acceptance_harness.connection.execute(
        "DELETE FROM idempotency_records WHERE resource_id = ?",
        (resource_id,),
    )
    acceptance_harness.connection.commit()
    replayed, is_replay = await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )

    assert readback.status == "available"
    assert revoked.status == "revoked"
    assert is_replay is True
    assert replayed.acceptance_id == first.acceptance_id
    assert replayed.status == "revoked"


@pytest.mark.asyncio
async def test_legacy_v1_record_cannot_authorize_publish_or_consume(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_legacy_v1_publish_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-legacy-v1-publish-0001",
        request=_request(scenario="s1", resource_id=resource_id),
    )
    acceptance_harness.connection.execute(
        """
        UPDATE acceptance_records
        SET fingerprint_version = 'acceptance-create.v1',
            transparency_sidecar_path = NULL,
            transparency_sidecar_sha256 = NULL,
            final_artifact_c2pa_status = NULL
        WHERE id = ?
        """,
        (record.acceptance_id,),
    )
    acceptance_harness.connection.commit()

    with pytest.raises(AcceptanceArtifactIntegrityMismatch):
        await acceptance_harness.service.inspect_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
        )
    with pytest.raises(AcceptanceArtifactIntegrityMismatch):
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-legacy-v1",
        )


@pytest.mark.asyncio
async def test_concurrent_same_key_create_has_one_owner_and_only_replays(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_concurrent_replay_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s1", resource_id=resource_id)

    results = await asyncio.gather(
        *(
            acceptance_harness.service.create(
                auth=_auth(),
                raw_key=VALID_KEY,
                request=request,
            )
            for _ in range(10)
        )
    )

    acceptance_ids = {record.acceptance_id for record, _ in results}
    replay_flags = [replay for _, replay in results]
    assert len(acceptance_ids) == 1
    assert replay_flags.count(False) == 1
    assert replay_flags.count(True) == 9
    assert acceptance_harness.connection.execute(
        "SELECT COUNT(*) FROM acceptance_records"
    ).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_changed_payload_or_reviewer_conflicts_before_source_and_file_access(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = "s2_conflict_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s2", resource_id=resource_id)
    await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )

    calls = {"source": 0, "file": 0}

    async def forbidden_source(**_: Any) -> None:
        calls["source"] += 1
        raise AssertionError("conflict touched source")

    def forbidden_file(*_: Any, **__: Any) -> None:
        calls["file"] += 1
        raise AssertionError("conflict touched file")

    monkeypatch.setattr(
        acceptance_harness.service.submission_repository,
        "get_by_resource",
        forbidden_source,
    )
    monkeypatch.setattr(service_module, "resolve_output_artifact", forbidden_file)

    with pytest.raises(AcceptancePayloadConflict) as payload_error:
        await acceptance_harness.service.create(
            auth=_auth(),
            raw_key=VALID_KEY,
            request=_request(
                scenario="s2",
                resource_id=resource_id,
                review_notes="A different human action.",
            ),
        )
    with pytest.raises(AcceptancePayloadConflict) as reviewer_error:
        await acceptance_harness.service.create(
            auth=_auth(reviewer_key_id="reviewer-b"),
            raw_key=VALID_KEY,
            request=request,
        )

    assert payload_error.value.detail == {"code": "acceptance_payload_conflict"}
    assert reviewer_error.value.detail == {"code": "acceptance_payload_conflict"}
    assert VALID_KEY not in str(payload_error.value)
    assert calls == {"source": 0, "file": 0}


@pytest.mark.asyncio
async def test_rejected_terminal_artifact_never_becomes_consumable(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s5_rejected_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s5",
        resource_id=resource_id,
        record_status="failed",
        full_media_success=False,
        pipeline_degraded=True,
    )
    acceptance_harness.write_artifact(final_path)

    record, replay = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(
            scenario="s5",
            resource_id=resource_id,
            decision="rejected",
        ),
    )

    assert replay is False
    assert record.status == "rejected"
    with pytest.raises(AcceptanceNotAvailable):
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-attempt-1",
        )


@pytest.mark.asyncio
async def test_consume_distinguishes_expired_unavailable_and_integrity_mismatch(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s3_consume_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s3",
        resource_id=resource_id,
    )
    artifact = acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s3", resource_id=resource_id),
    )

    artifact.write_bytes(b"changed-after-review")
    with pytest.raises(AcceptanceArtifactIntegrityMismatch):
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-attempt-integrity",
        )

    artifact.write_bytes(VIDEO_BYTES)
    consumed = await acceptance_harness.service.consume_for_publish(
        tenant_id=TENANT_ID,
        acceptance_id=record.acceptance_id,
        consumer_operation="distribution.publish",
        consumer_resource_id="publish-attempt-success",
    )
    assert consumed.status == "consumed"
    with pytest.raises(AcceptanceNotAvailable):
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-attempt-duplicate",
        )

    second_id = "s4_expired_fixture"
    second_path = acceptance_harness.seed_source(
        scenario="s4",
        resource_id=second_id,
    )
    acceptance_harness.write_artifact(second_path)
    expired, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-expiry-0001",
        request=_request(scenario="s4", resource_id=second_id),
    )
    acceptance_harness.expire(expired.acceptance_id)

    with pytest.raises(AcceptanceExpired):
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=expired.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-attempt-expired",
        )


@pytest.mark.asyncio
async def test_publish_inspect_validates_exact_artifact_without_mutation(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s2_publish_inspect_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-publish-inspect-0001",
        request=_request(scenario="s2", resource_id=resource_id),
    )
    before = dict(
        acceptance_harness.connection.execute(
            "SELECT * FROM acceptance_records WHERE id = ?",
            (record.acceptance_id,),
        ).fetchone()
    )

    inspected = await acceptance_harness.service.inspect_for_publish(
        tenant_id=TENANT_ID,
        acceptance_id=record.acceptance_id,
    )

    after = dict(
        acceptance_harness.connection.execute(
            "SELECT * FROM acceptance_records WHERE id = ?",
            (record.acceptance_id,),
        ).fetchone()
    )
    assert inspected.status == "available"
    assert inspected.artifact.path == final_path
    assert inspected.artifact.sha256 == hashlib.sha256(VIDEO_BYTES).hexdigest()
    assert before == after


@pytest.mark.asyncio
async def test_publish_inspect_fails_closed_on_tenant_expiry_and_byte_drift(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s3_publish_inspect_failure_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s3",
        resource_id=resource_id,
    )
    artifact = acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-publish-inspect-0002",
        request=_request(scenario="s3", resource_id=resource_id),
    )

    with pytest.raises(AcceptanceNotFound):
        await acceptance_harness.service.inspect_for_publish(
            tenant_id="tenant-other",
            acceptance_id=record.acceptance_id,
        )

    artifact.write_bytes(b"changed-after-acceptance")
    with pytest.raises(AcceptanceArtifactIntegrityMismatch):
        await acceptance_harness.service.inspect_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
        )
    artifact.write_bytes(VIDEO_BYTES)

    acceptance_harness.expire(record.acceptance_id)
    with pytest.raises(AcceptanceExpired):
        await acceptance_harness.service.inspect_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
        )

    stored_status = acceptance_harness.connection.execute(
        "SELECT record_status FROM acceptance_records WHERE id = ?",
        (record.acceptance_id,),
    ).fetchone()[0]
    assert stored_status == "available"


@pytest.mark.parametrize(
    (
        "case",
        "scenario",
        "record_status",
        "full_media_success",
        "is_stub",
        "pipeline_degraded",
        "artifact_disposition",
        "include_artifact",
        "expected_error",
    ),
    [
        (
            "bounded_fast",
            "fast",
            "completed",
            False,
            False,
            False,
            "pending_review",
            True,
            AcceptanceSourceNotEligible,
        ),
        (
            "stub_fast",
            "fast",
            "completed",
            True,
            True,
            False,
            "pending_review",
            True,
            AcceptanceSourceNotEligible,
        ),
        (
            "quarantine",
            "s2",
            "completed",
            True,
            False,
            False,
            "quarantine",
            True,
            AcceptanceSourceNotEligible,
        ),
        (
            "degraded_scenario",
            "s3",
            "completed",
            True,
            False,
            True,
            "pending_review",
            True,
            AcceptanceSourceNotEligible,
        ),
        (
            "recovery_required",
            "s4",
            "recovery_required",
            True,
            False,
            False,
            "pending_review",
            True,
            AcceptanceSourceNotEligible,
        ),
        (
            "running",
            "s5",
            "running",
            True,
            False,
            False,
            "pending_review",
            True,
            AcceptanceSourceNotTerminal,
        ),
        (
            "absent_assembly",
            "s1",
            "completed",
            True,
            False,
            False,
            "pending_review",
            False,
            AcceptanceSourceNotEligible,
        ),
    ],
)
@pytest.mark.asyncio
async def test_accepted_requires_exact_full_nondegraded_terminal_source(
    acceptance_harness: AcceptanceHarness,
    case: str,
    scenario: str,
    record_status: str,
    full_media_success: bool,
    is_stub: bool,
    pipeline_degraded: bool,
    artifact_disposition: str,
    include_artifact: bool,
    expected_error: type[Exception],
) -> None:
    resource_id = f"{scenario}_{case}_fixture"
    acceptance_harness.seed_source(
        scenario=scenario,
        resource_id=resource_id,
        record_status=record_status,
        full_media_success=full_media_success,
        is_stub=is_stub,
        pipeline_degraded=pipeline_degraded,
        artifact_disposition=artifact_disposition,
        include_artifact=include_artifact,
    )

    with pytest.raises(expected_error):
        await acceptance_harness.service.create(
            auth=_auth(),
            raw_key=f"acceptance-{case}-0001",
            request=_request(scenario=scenario, resource_id=resource_id),
        )

    count = acceptance_harness.connection.execute(
        "SELECT COUNT(*) FROM acceptance_records"
    ).fetchone()[0]
    assert count == 0


@pytest.mark.parametrize(
    ("mode", "expected_error"),
    [
        ("missing", AcceptanceNotFound),
        ("empty", AcceptanceNotFound),
        ("symlink_escape", AcceptanceNotFound),
        ("intermediate", AcceptanceArtifactMismatch),
        ("cross_tenant", AcceptanceNotFound),
    ],
)
@pytest.mark.asyncio
async def test_create_rejects_non_exact_or_untrusted_artifact(
    acceptance_harness: AcceptanceHarness,
    mode: str,
    expected_error: type[Exception],
) -> None:
    resource_id = f"s2_{mode}_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    requested_path = final_path
    if mode == "empty":
        acceptance_harness.write_artifact(final_path, content=b"")
    elif mode == "symlink_escape":
        outside = acceptance_harness.output_dir.parent / "outside.mp4"
        outside.write_bytes(VIDEO_BYTES)
        artifact = acceptance_harness.output_dir / final_path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.symlink_to(outside)
    elif mode == "intermediate":
        acceptance_harness.write_artifact(final_path)
        requested_path = (
            f"tenants/{TENANT_ID}/pending_review/{resource_id}/"
            "clips/intermediate.mp4"
        )
    elif mode == "cross_tenant":
        acceptance_harness.write_artifact(final_path)
        requested_path = _artifact_path(
            "s2",
            resource_id,
            tenant_id="tenant-beta",
        )

    with pytest.raises(expected_error):
        await acceptance_harness.service.create(
            auth=_auth(),
            raw_key=f"acceptance-artifact-{mode}-0001",
            request=_request(
                scenario="s2",
                resource_id=resource_id,
                artifact_path=requested_path,
            ),
        )

    count = acceptance_harness.connection.execute(
        "SELECT COUNT(*) FROM acceptance_records"
    ).fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_create_rejects_in_root_symlink_when_resolved_path_is_not_exact_source(
    acceptance_harness: AcceptanceHarness,
) -> None:
    """A safe-root symlink must not silently change the reviewed path identity."""

    resource_id = "s2_in_root_symlink_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    link = acceptance_harness.output_dir / final_path
    link.parent.mkdir(parents=True, exist_ok=True)
    target = link.with_name("actual-final.mp4")
    target.write_bytes(VIDEO_BYTES)
    link.symlink_to(target)

    with pytest.raises(AcceptanceArtifactMismatch):
        await acceptance_harness.service.create(
            auth=_auth(),
            raw_key="acceptance-in-root-link-0001",
            request=_request(scenario="s2", resource_id=resource_id),
        )

    assert acceptance_harness.connection.execute(
        "SELECT COUNT(*) FROM acceptance_records"
    ).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_different_key_cannot_bypass_existing_available_path(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s1_available_collision_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s1", resource_id=resource_id)
    await acceptance_harness.service.create(
        auth=_auth(), raw_key="acceptance-owner-0001", request=request
    )

    with pytest.raises(AcceptanceAlreadyAvailable):
        await acceptance_harness.service.create(
            auth=_auth(), raw_key="acceptance-owner-0002", request=request
        )

    statuses = acceptance_harness.connection.execute(
        "SELECT record_status FROM acceptance_records"
    ).fetchall()
    assert [row[0] for row in statuses] == ["available"]


@pytest.mark.asyncio
async def test_new_key_can_create_after_database_time_expiry_reconciliation(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s2_expiry_reopen_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s2", resource_id=resource_id)
    first, _ = await acceptance_harness.service.create(
        auth=_auth(), raw_key="acceptance-expired-0001", request=request
    )
    acceptance_harness.expire(first.acceptance_id)

    second, replay = await acceptance_harness.service.create(
        auth=_auth(), raw_key="acceptance-expired-0002", request=request
    )

    assert replay is False
    assert second.acceptance_id != first.acceptance_id
    assert second.status == "available"
    assert (await acceptance_harness.service.read(
        auth=_auth(), acceptance_id=first.acceptance_id
    )).status == "expired"


@pytest.mark.asyncio
async def test_same_key_replay_lazily_returns_expired_current_record(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s3_expired_replay_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s3",
        resource_id=resource_id,
    )
    artifact = acceptance_harness.write_artifact(final_path)
    request = _request(scenario="s3", resource_id=resource_id)
    first, _ = await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )
    acceptance_harness.expire(first.acceptance_id)
    artifact.unlink()

    replayed, replay = await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )

    assert replay is True
    assert replayed.acceptance_id == first.acceptance_id
    assert replayed.status == "expired"
    with pytest.raises(AcceptanceNotRevocable):
        await acceptance_harness.service.revoke(
            auth=_auth(), acceptance_id=first.acceptance_id
        )


@pytest.mark.parametrize("operation", ["read", "replay"])
@pytest.mark.parametrize(
    "corruption",
    [
        "cross_tenant",
        "host_path",
        "digest_type",
        "digest_invalid",
        "size_bool",
        "size_float",
        "acceptance_id_type",
        "acceptance_id_blank",
        "source_id_type",
        *INVALID_STORED_RESOURCE_IDS,
        "reviewer_id_type",
        "reviewer_id_blank",
        "required_timestamp_type",
        "optional_timestamp_type",
        "review_notes_type",
    ],
)
@pytest.mark.asyncio
async def test_read_and_replay_fail_closed_on_corrupt_response_projection(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    corruption: str,
) -> None:
    resource_id = f"s2_projection_{operation}_{corruption}_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    raw_key = f"acceptance-projection-{operation}-{corruption}-0001"
    request = _request(scenario="s2", resource_id=resource_id)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=raw_key,
        request=request,
    )
    repository = acceptance_harness.service.repository
    real_get_by_id = repository.get_by_id

    async def corrupt_get_by_id(
        *, tenant_id: str, acceptance_id: str
    ) -> dict[str, Any] | None:
        stored = await real_get_by_id(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        assert stored is not None
        corrupted = dict(stored)
        if corruption == "cross_tenant":
            corrupted["tenant_id"] = "tenant-beta"
        elif corruption == "host_path":
            corrupted["artifact_path"] = str(
                acceptance_harness.output_dir / final_path
            )
        elif corruption == "digest_type":
            corrupted["artifact_sha256"] = 123
        elif corruption == "digest_invalid":
            corrupted["artifact_sha256"] = "not-a-sha256"
        elif corruption == "size_bool":
            corrupted["artifact_size_bytes"] = True
        elif corruption == "size_float":
            corrupted["artifact_size_bytes"] = float(
                corrupted["artifact_size_bytes"]
            )
        elif corruption == "acceptance_id_type":
            corrupted["id"] = 123
        elif corruption == "acceptance_id_blank":
            corrupted["id"] = "   "
        elif corruption == "source_id_type":
            corrupted["source_resource_id"] = 123
        elif corruption in INVALID_STORED_RESOURCE_IDS:
            invalid_resource_id = INVALID_STORED_RESOURCE_IDS[corruption]
            corrupted["source_resource_id"] = invalid_resource_id
            corrupted["artifact_path"] = _artifact_path(
                "s2",
                invalid_resource_id,
            )
        elif corruption == "reviewer_id_type":
            corrupted["reviewer_key_id"] = 123
        elif corruption == "reviewer_id_blank":
            corrupted["reviewer_key_id"] = "   "
        elif corruption == "required_timestamp_type":
            corrupted["expires_at"] = 123
        elif corruption == "optional_timestamp_type":
            corrupted["consumed_at"] = 123
        else:
            corrupted["review_notes"] = 123
        return corrupted

    monkeypatch.setattr(repository, "get_by_id", corrupt_get_by_id)

    with pytest.raises(AcceptanceStoreUnavailable) as error:
        if operation == "read":
            await acceptance_harness.service.read(
                auth=_auth(),
                acceptance_id=record.acceptance_id,
            )
        else:
            await acceptance_harness.service.create(
                auth=_auth(),
                raw_key=raw_key,
                request=request,
            )

    assert error.value.detail == {"code": "acceptance_store_unavailable"}
    assert str(error.value) == "acceptance_store_unavailable"
    assert str(acceptance_harness.output_dir) not in str(error.value.detail)
    if corruption in INVALID_STORED_RESOURCE_IDS:
        assert INVALID_STORED_RESOURCE_IDS[corruption] not in str(error.value.detail)


@pytest.mark.asyncio
async def test_projection_supports_postgres_datetimes_without_coercing_other_types(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = "s3_projection_pg_datetime_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s3",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s3", resource_id=resource_id),
    )
    repository = acceptance_harness.service.repository
    real_get_by_id = repository.get_by_id
    timestamp = datetime(2026, 7, 12, 12, 30, tzinfo=UTC)

    async def pg_datetime_get_by_id(
        *, tenant_id: str, acceptance_id: str
    ) -> dict[str, Any] | None:
        stored = await real_get_by_id(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        assert stored is not None
        projected = dict(stored)
        projected["expires_at"] = timestamp
        projected["created_at"] = timestamp
        projected["updated_at"] = timestamp
        return projected

    monkeypatch.setattr(repository, "get_by_id", pg_datetime_get_by_id)

    current = await acceptance_harness.service.read(
        auth=_auth(),
        acceptance_id=record.acceptance_id,
    )

    assert current.expires_at == timestamp.isoformat()
    assert current.created_at == timestamp.isoformat()
    assert current.updated_at == timestamp.isoformat()


@pytest.mark.asyncio
async def test_rejected_decision_atomically_revokes_older_available_record(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s4_rejection_revokes_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s4",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    accepted, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-before-reject-0001",
        request=_request(scenario="s4", resource_id=resource_id),
    )
    rejected, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-rejection-0001",
        request=_request(
            scenario="s4",
            resource_id=resource_id,
            decision="rejected",
        ),
    )

    old = await acceptance_harness.service.read(
        auth=_auth(), acceptance_id=accepted.acceptance_id
    )
    assert old.status == "revoked"
    assert rejected.status == "rejected"
    available = acceptance_harness.connection.execute(
        "SELECT COUNT(*) FROM acceptance_records WHERE record_status = 'available'"
    ).fetchone()[0]
    assert available == 0
    for acceptance_id in (accepted.acceptance_id, rejected.acceptance_id):
        with pytest.raises(AcceptanceNotAvailable):
            await acceptance_harness.service.consume_for_publish(
                tenant_id=TENANT_ID,
                acceptance_id=acceptance_id,
                consumer_operation="distribution.publish",
                consumer_resource_id=f"publish-{acceptance_id}",
            )


@pytest.mark.parametrize(
    ("scenario", "record_status", "full_media_success", "is_stub", "degraded"),
    [
        ("fast", "completed", False, True, False),
        ("s1", "completed", False, False, True),
        ("s5", "failed", False, False, True),
    ],
)
@pytest.mark.asyncio
async def test_rejected_decision_allows_bounded_stub_or_degraded_final_truth(
    acceptance_harness: AcceptanceHarness,
    scenario: str,
    record_status: str,
    full_media_success: bool,
    is_stub: bool,
    degraded: bool,
) -> None:
    resource_id = f"{scenario}_bounded_rejection_fixture"
    final_path = acceptance_harness.seed_source(
        scenario=scenario,
        resource_id=resource_id,
        record_status=record_status,
        full_media_success=full_media_success,
        is_stub=is_stub,
        pipeline_degraded=degraded,
    )
    acceptance_harness.write_artifact(final_path)

    record, replay = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=f"acceptance-rejected-{scenario}-0001",
        request=_request(
            scenario=scenario,
            resource_id=resource_id,
            decision="rejected",
        ),
    )

    assert replay is False
    assert record.status == "rejected"
    assert record.decision == "rejected"


@pytest.mark.parametrize("mode", ["missing", "moved", "empty", "symlink_escape"])
@pytest.mark.asyncio
async def test_consume_integrity_failure_never_changes_historical_record(
    acceptance_harness: AcceptanceHarness,
    mode: str,
) -> None:
    resource_id = f"s1_consume_{mode}_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    artifact = acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=f"acceptance-consume-{mode}-0001",
        request=_request(scenario="s1", resource_id=resource_id),
    )

    if mode == "missing":
        artifact.unlink()
    elif mode == "moved":
        artifact.rename(artifact.with_name("moved.mp4"))
    elif mode == "empty":
        artifact.write_bytes(b"")
    else:
        outside = acceptance_harness.output_dir.parent / "consume-outside.mp4"
        outside.write_bytes(VIDEO_BYTES)
        artifact.unlink()
        artifact.symlink_to(outside)

    with pytest.raises(AcceptanceArtifactIntegrityMismatch) as error:
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id=f"publish-{mode}",
        )

    assert error.value.detail == {
        "code": "acceptance_artifact_integrity_mismatch"
    }
    current = await acceptance_harness.service.read(
        auth=_auth(), acceptance_id=record.acceptance_id
    )
    assert current.status == "available"


@pytest.mark.asyncio
async def test_consume_compares_stored_byte_size_before_repository_cas(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s2_consume_size_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s2",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s2", resource_id=resource_id),
    )
    acceptance_harness.connection.execute(
        "UPDATE acceptance_records SET artifact_size_bytes = artifact_size_bytes + 1 WHERE id = ?",
        (record.acceptance_id,),
    )
    acceptance_harness.connection.commit()

    with pytest.raises(AcceptanceArtifactIntegrityMismatch):
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-size-mismatch",
        )

    assert acceptance_harness.connection.execute(
        "SELECT record_status FROM acceptance_records WHERE id = ?",
        (record.acceptance_id,),
    ).fetchone()[0] == "available"


@pytest.mark.parametrize(
    "corruption",
    [
        "foreign_tenant",
        "illegal_resource_type",
        "mismatched_type_scenario",
        "empty_resource_id",
        *INVALID_STORED_RESOURCE_IDS,
        "non_video_kind",
        "noncanonical_path",
        "absolute_path",
        "cross_tenant_path",
        "wrong_source_prefix",
        "unsupported_suffix",
        "uppercase_digest",
        "short_digest",
        "bool_size",
        "float_size",
        "zero_size",
    ],
)
@pytest.mark.asyncio
async def test_consume_rejects_corrupt_stored_authority_before_repository_cas(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    resource_id = f"s1_stored_{corruption}_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=f"acceptance-stored-{corruption}-0001",
        request=_request(scenario="s1", resource_id=resource_id),
    )
    repository = acceptance_harness.service.repository
    real_get_by_id = repository.get_by_id
    cas_calls = 0

    async def corrupt_get_by_id(
        *, tenant_id: str, acceptance_id: str
    ) -> dict[str, Any] | None:
        stored = await real_get_by_id(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )
        assert stored is not None
        corrupted = dict(stored)
        if corruption == "foreign_tenant":
            corrupted["tenant_id"] = "tenant-beta"
        elif corruption == "illegal_resource_type":
            corrupted["source_resource_type"] = "toolbox"
        elif corruption == "mismatched_type_scenario":
            corrupted["source_resource_type"] = "fast"
        elif corruption == "empty_resource_id":
            corrupted["source_resource_id"] = ""
        elif corruption in INVALID_STORED_RESOURCE_IDS:
            invalid_resource_id = INVALID_STORED_RESOURCE_IDS[corruption]
            matching_path = _artifact_path("s1", invalid_resource_id)
            corrupted["source_resource_id"] = invalid_resource_id
            corrupted["artifact_path"] = matching_path
            acceptance_harness.write_artifact(matching_path)
        elif corruption == "non_video_kind":
            corrupted["artifact_kind"] = "image"
        elif corruption == "noncanonical_path":
            corrupted["artifact_path"] = final_path.replace(
                "/assemble/final.mp4",
                "/assemble/../assemble/final.mp4",
            )
        elif corruption == "absolute_path":
            corrupted["artifact_path"] = str(
                acceptance_harness.output_dir / final_path
            )
        elif corruption == "cross_tenant_path":
            corrupted["artifact_path"] = final_path.replace(
                "tenant-alpha",
                "tenant-beta",
            )
        elif corruption == "wrong_source_prefix":
            corrupted["artifact_path"] = final_path.replace(
                resource_id,
                "s1_other_resource",
            )
        elif corruption == "unsupported_suffix":
            corrupted["artifact_path"] = final_path.removesuffix(".mp4") + ".mov"
        elif corruption == "uppercase_digest":
            corrupted["artifact_sha256"] = str(
                corrupted["artifact_sha256"]
            ).upper()
        elif corruption == "short_digest":
            corrupted["artifact_sha256"] = "a" * 63
        elif corruption == "bool_size":
            corrupted["artifact_size_bytes"] = True
        elif corruption == "float_size":
            corrupted["artifact_size_bytes"] = float(
                corrupted["artifact_size_bytes"]
            )
        else:
            corrupted["artifact_size_bytes"] = 0
        return corrupted

    async def forbidden_consume(**_: Any) -> None:
        nonlocal cas_calls
        cas_calls += 1
        raise AssertionError("corrupt stored authority reached repository CAS")

    monkeypatch.setattr(repository, "get_by_id", corrupt_get_by_id)
    monkeypatch.setattr(repository, "consume", forbidden_consume)

    with pytest.raises(AcceptanceArtifactIntegrityMismatch) as error:
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id=f"publish-corrupt-{corruption}",
        )

    assert error.value.detail == {
        "code": "acceptance_artifact_integrity_mismatch"
    }
    assert cas_calls == 0


@pytest.mark.asyncio
async def test_concurrent_consume_has_one_winner_and_one_typed_loser(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s3_concurrent_consume_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s3",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s3", resource_id=resource_id),
    )

    results = await asyncio.gather(
        *(
            acceptance_harness.service.consume_for_publish(
                tenant_id=TENANT_ID,
                acceptance_id=record.acceptance_id,
                consumer_operation="distribution.publish",
                consumer_resource_id=f"publish-concurrent-{index}",
            )
            for index in range(2)
        ),
        return_exceptions=True,
    )

    winners = [result for result in results if not isinstance(result, BaseException)]
    losers = [result for result in results if isinstance(result, BaseException)]
    assert len(winners) == 1
    assert winners[0].status == "consumed"
    assert len(losers) == 1
    assert isinstance(losers[0], AcceptanceNotAvailable)


@pytest.mark.parametrize(
    ("consumer_operation", "consumer_resource_id"),
    [
        ("", "publish-attempt"),
        ("   ", "publish-attempt"),
        ("o" * 65, "publish-attempt"),
        (123, "publish-attempt"),
        ("distribution.publish", ""),
        ("distribution.publish", "   "),
        ("distribution.publish", "r" * 129),
        ("distribution.publish", 123),
    ],
)
@pytest.mark.asyncio
async def test_consume_maps_invalid_internal_consumer_identity_to_typed_error(
    acceptance_harness: AcceptanceHarness,
    consumer_operation: Any,
    consumer_resource_id: Any,
) -> None:
    resource_id = "s4_invalid_consumer_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s4",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s4", resource_id=resource_id),
    )

    with pytest.raises(AcceptanceNotAvailable) as error:
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation=consumer_operation,
            consumer_resource_id=consumer_resource_id,
        )

    assert error.value.detail == {"code": "acceptance_not_available"}
    assert (
        await acceptance_harness.service.read(
            auth=_auth(),
            acceptance_id=record.acceptance_id,
        )
    ).status == "available"


@pytest.mark.asyncio
async def test_consume_accepts_bounded_internal_consumer_identity(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s5_bounded_consumer_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s5",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s5", resource_id=resource_id),
    )

    consumed = await acceptance_harness.service.consume_for_publish(
        tenant_id=TENANT_ID,
        acceptance_id=record.acceptance_id,
        consumer_operation="o" * 64,
        consumer_resource_id="r" * 128,
    )

    assert consumed.status == "consumed"


@pytest.mark.asyncio
async def test_consume_maps_unexpected_repository_value_error_to_store_unavailable(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resource_id = "fast_repository_value_error_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="fast",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="fast", resource_id=resource_id),
    )

    async def corrupt_repository_consume(**_: Any) -> None:
        raise ValueError("raw repository detail /host/path")

    monkeypatch.setattr(
        acceptance_harness.service.repository,
        "consume",
        corrupt_repository_consume,
    )

    with pytest.raises(AcceptanceStoreUnavailable) as error:
        await acceptance_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-attempt-value-error",
        )

    assert error.value.detail == {"code": "acceptance_store_unavailable"}
    assert str(error.value) == "acceptance_store_unavailable"
    assert "/host/path" not in str(error.value.detail)


@pytest.mark.asyncio
async def test_read_revoke_and_consume_keep_acceptance_ids_tenant_bound(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s4_tenant_bound_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s4",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s4", resource_id=resource_id),
    )

    with pytest.raises(AcceptanceNotFound):
        await acceptance_harness.service.read(
            auth=_auth(tenant_id="tenant-beta"),
            acceptance_id=record.acceptance_id,
        )
    with pytest.raises(AcceptanceNotFound):
        await acceptance_harness.service.revoke(
            auth=_auth(tenant_id="tenant-beta"),
            acceptance_id=record.acceptance_id,
        )
    with pytest.raises(AcceptanceNotFound):
        await acceptance_harness.service.consume_for_publish(
            tenant_id="tenant-beta",
            acceptance_id=record.acceptance_id,
            consumer_operation="distribution.publish",
            consumer_resource_id="publish-cross-tenant",
        )
    assert (await acceptance_harness.service.read(
        auth=_auth(), acceptance_id=record.acceptance_id
    )).status == "available"


@pytest.mark.asyncio
async def test_revoke_is_idempotent_but_cannot_revoke_consumed_record(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "s5_revoke_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="s5",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="s5", resource_id=resource_id),
    )
    first = await acceptance_harness.service.revoke(
        auth=_auth(), acceptance_id=record.acceptance_id
    )
    second = await acceptance_harness.service.revoke(
        auth=_auth(reviewer_key_id="reviewer-b"),
        acceptance_id=record.acceptance_id,
    )
    assert first.status == second.status == "revoked"
    assert first.revoked_at == second.revoked_at

    second_resource = "s1_consumed_not_revocable_fixture"
    second_path = acceptance_harness.seed_source(
        scenario="s1",
        resource_id=second_resource,
    )
    acceptance_harness.write_artifact(second_path)
    consumed_record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key="acceptance-consumed-revoke-0001",
        request=_request(scenario="s1", resource_id=second_resource),
    )
    await acceptance_harness.service.consume_for_publish(
        tenant_id=TENANT_ID,
        acceptance_id=consumed_record.acceptance_id,
        consumer_operation="distribution.publish",
        consumer_resource_id="publish-before-revoke",
    )
    with pytest.raises(AcceptanceNotRevocable):
        await acceptance_harness.service.revoke(
            auth=_auth(), acceptance_id=consumed_record.acceptance_id
        )


@pytest.mark.asyncio
async def test_missing_authenticated_reviewer_fails_before_authority_creation(
    acceptance_harness: AcceptanceHarness,
) -> None:
    with pytest.raises(AcceptanceStoreUnavailable) as error:
        await acceptance_harness.service.create(
            auth=_auth(reviewer_key_id=None),
            raw_key=VALID_KEY,
            request=_request(),
        )

    assert error.value.detail == {"code": "acceptance_store_unavailable"}
    assert acceptance_harness.connection.execute(
        "SELECT COUNT(*) FROM acceptance_records"
    ).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_raw_action_key_is_only_persisted_as_sha256_and_never_leaked(
    acceptance_harness: AcceptanceHarness,
) -> None:
    resource_id = "fast_secret_key_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="fast",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    request = _request(scenario="fast", resource_id=resource_id)
    await acceptance_harness.service.create(
        auth=_auth(), raw_key=VALID_KEY, request=request
    )

    row = dict(
        acceptance_harness.connection.execute(
            "SELECT * FROM acceptance_records"
        ).fetchone()
    )
    assert row["creation_key_hash"] == hash_idempotency_key(VALID_KEY)
    assert VALID_KEY not in json.dumps(row, default=str, sort_keys=True)

    with pytest.raises(AcceptancePayloadConflict) as error:
        await acceptance_harness.service.create(
            auth=_auth(reviewer_key_id="reviewer-b"),
            raw_key=VALID_KEY,
            request=request,
        )
    assert VALID_KEY not in str(error.value)
    assert VALID_KEY not in json.dumps(error.value.detail)


@pytest.mark.asyncio
async def test_required_authority_store_failure_is_safe_and_fail_closed(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: None)
    service = ArtifactAcceptanceService(
        AcceptanceRecordRepository(require_postgres=True),
        acceptance_harness.service.submission_repository,
        output_dir=acceptance_harness.output_dir,
    )

    with pytest.raises(AcceptanceStoreUnavailable) as error:
        await service.create(
            auth=_auth(),
            raw_key=VALID_KEY,
            request=_request(
                scenario="s1",
                resource_id="s1_store_unavailable_fixture",
            ),
        )

    serialized = json.dumps(error.value.detail)
    assert error.value.detail == {"code": "acceptance_store_unavailable"}
    assert VALID_KEY not in serialized
    assert str(acceptance_harness.output_dir) not in serialized


@pytest.mark.asyncio
async def test_acceptance_flow_never_calls_provider_translator_or_connector(
    acceptance_harness: AcceptanceHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.publish_engine import PublishEngine
    from src.tools import translate as translate_module
    from src.tools.poyo_client import PoyoClient

    calls = {"provider": 0, "translator": 0, "connector": 0}

    async def forbidden_provider(*_: Any, **__: Any) -> None:
        calls["provider"] += 1
        raise AssertionError("acceptance called a provider")

    async def forbidden_translator(*_: Any, **__: Any) -> None:
        calls["translator"] += 1
        raise AssertionError("acceptance called a translator")

    async def forbidden_connector(*_: Any, **__: Any) -> None:
        calls["connector"] += 1
        raise AssertionError("acceptance called a publish connector")

    monkeypatch.setattr(PoyoClient, "submit", forbidden_provider)
    monkeypatch.setattr(
        translate_module,
        "translate_catalog_to_english",
        forbidden_translator,
    )
    monkeypatch.setattr(PublishEngine, "publish", forbidden_connector)

    resource_id = "fast_no_external_calls_fixture"
    final_path = acceptance_harness.seed_source(
        scenario="fast",
        resource_id=resource_id,
    )
    acceptance_harness.write_artifact(final_path)
    record, _ = await acceptance_harness.service.create(
        auth=_auth(),
        raw_key=VALID_KEY,
        request=_request(scenario="fast", resource_id=resource_id),
    )

    assert record.status == "available"
    assert calls == {"provider": 0, "translator": 0, "connector": 0}
