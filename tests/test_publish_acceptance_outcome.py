"""Read-only inspection of uncertain W1-22 publish-consume outcomes."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest

from src.services import artifact_acceptance as service_module
from src.services.artifact_acceptance import (
    AcceptanceStoreUnavailable,
    ArtifactAcceptanceService,
)
from src.storage import db as db_module
from src.storage.acceptance_repository import (
    AcceptanceRecordRepository,
    AcceptanceStoreUnavailableError,
)
from src.storage.idempotency_repository import SubmissionIdempotencyRepository

TENANT_ID = "tenant-alpha"
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
ATTEMPT_ID = "91ec3593-cc3c-42bf-99ee-c98655c5826b"
OTHER_ATTEMPT_ID = "df6e473c-f3bc-4cc4-af8c-1f73a7c74863"
VIDEO_BYTES = b"publish-outcome-fixture"


@dataclass(slots=True)
class OutcomeHarness:
    connection: sqlite3.Connection
    output_dir: Path
    repository: AcceptanceRecordRepository
    service: ArtifactAcceptanceService

    def insert_record(
        self,
        *,
        decision: str = "accepted",
        status: str = "available",
        expires_modifier: str = "+1 hour",
        consumed_at: str | None = None,
        consumed_by_operation: str | None = None,
        consumed_by_resource_id: str | None = None,
        revoked_at: str | None = None,
        revoked_by_key_id: str | None = None,
    ) -> str:
        path = (
            "tenants/tenant-alpha/pending_review/"
            "s2_outcome_fixture/assemble/final.mp4"
        )
        target = self.output_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(VIDEO_BYTES)
        self.connection.execute(
            """
            INSERT INTO acceptance_records (
                id, tenant_id, creation_key_hash, fingerprint_version,
                request_hash, source_resource_type, source_resource_id,
                scenario, artifact_path, artifact_sha256,
                artifact_size_bytes, artifact_kind, decision, record_status,
                reviewer_key_id, reviewer_key_type, review_notes,
                expires_at, consumed_at, consumed_by_operation,
                consumed_by_resource_id, revoked_at, revoked_by_key_id,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, 'acceptance-create.v1', ?, 'scenario',
                's2_outcome_fixture', 's2', ?, ?, ?, 'video', ?, ?,
                'reviewer-a', 'tenant', 'Reviewed exact bytes.',
                datetime('now', ?), ?, ?, ?, ?, ?,
                datetime('now', '-2 hours'), CURRENT_TIMESTAMP
            )
            """,
            (
                ACCEPTANCE_ID,
                TENANT_ID,
                "a" * 64,
                "b" * 64,
                path,
                hashlib.sha256(VIDEO_BYTES).hexdigest(),
                len(VIDEO_BYTES),
                decision,
                status,
                expires_modifier,
                consumed_at,
                consumed_by_operation,
                consumed_by_resource_id,
                revoked_at,
                revoked_by_key_id,
            ),
        )
        self.connection.commit()
        return path

    def row(self) -> dict[str, Any]:
        record = self.connection.execute(
            "SELECT * FROM acceptance_records WHERE id = ?",
            (ACCEPTANCE_ID,),
        ).fetchone()
        assert record is not None
        return dict(record)

    async def inspect(
        self,
        *,
        tenant_id: Any = TENANT_ID,
        acceptance_id: Any = ACCEPTANCE_ID,
        consumer_operation: Any = "distribution.publish",
        consumer_resource_id: Any = ATTEMPT_ID,
    ) -> str:
        return await self.service.inspect_publish_consume_outcome(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
            consumer_operation=consumer_operation,
            consumer_resource_id=consumer_resource_id,
        )


@pytest.fixture
def outcome_harness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> OutcomeHarness:
    connection = sqlite3.connect(
        str(tmp_path / "publish-outcome.db"),
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
    repository = AcceptanceRecordRepository(require_postgres=False)
    service = ArtifactAcceptanceService(
        repository,
        SubmissionIdempotencyRepository(require_postgres=False),
        output_dir=output_dir,
    )
    yield OutcomeHarness(connection, output_dir, repository, service)
    connection.close()


def test_outcome_type_exports_only_the_bounded_literals() -> None:
    from src.services.artifact_acceptance import AcceptanceConsumeOutcome

    assert get_args(AcceptanceConsumeOutcome) == (
        "available_not_consumed",
        "consumed_by_this_attempt",
        "consumed_by_another_attempt",
        "not_available",
        "unknown",
    )
    assert "AcceptanceConsumeOutcome" in service_module.__all__


@pytest.mark.asyncio
async def test_inspector_distinguishes_available_and_consumed_owner(
    outcome_harness: OutcomeHarness,
) -> None:
    outcome_harness.insert_record()

    assert await outcome_harness.inspect() == "available_not_consumed"

    await outcome_harness.service.consume_for_publish(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        consumer_operation="distribution.publish",
        consumer_resource_id=ATTEMPT_ID,
    )

    assert await outcome_harness.inspect() == "consumed_by_this_attempt"


@pytest.mark.parametrize(
    ("stored_operation", "stored_resource"),
    [
        ("distribution.publish", OTHER_ATTEMPT_ID),
        ("delivery.prepare", ATTEMPT_ID),
    ],
)
@pytest.mark.asyncio
async def test_inspector_reports_a_different_valid_consumer_as_another_attempt(
    outcome_harness: OutcomeHarness,
    stored_operation: str,
    stored_resource: str,
) -> None:
    now = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    outcome_harness.insert_record(
        status="consumed",
        consumed_at=now,
        consumed_by_operation=stored_operation,
        consumed_by_resource_id=stored_resource,
    )

    assert await outcome_harness.inspect() == "consumed_by_another_attempt"


@pytest.mark.parametrize(
    ("decision", "status", "expires_modifier", "revoked_at", "revoker"),
    [
        ("rejected", "rejected", "+1 hour", None, None),
        (
            "accepted",
            "revoked",
            "+1 hour",
            datetime.now(UTC).isoformat(),
            "reviewer-revoker",
        ),
        ("accepted", "expired", "-1 hour", None, None),
    ],
    ids=["rejected", "revoked", "expired"],
)
@pytest.mark.asyncio
async def test_inspector_reports_consistent_terminal_rows_as_not_available(
    outcome_harness: OutcomeHarness,
    decision: str,
    status: str,
    expires_modifier: str,
    revoked_at: str | None,
    revoker: str | None,
) -> None:
    outcome_harness.insert_record(
        decision=decision,
        status=status,
        expires_modifier=expires_modifier,
        revoked_at=revoked_at,
        revoked_by_key_id=revoker,
    )

    assert await outcome_harness.inspect() == "not_available"


@pytest.mark.asyncio
async def test_past_available_row_is_classified_without_any_write_or_projection(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome_harness.insert_record(expires_modifier="-1 hour")
    before = outcome_harness.row()
    before_total_changes = outcome_harness.connection.total_changes
    before_data_version = outcome_harness.connection.execute(
        "PRAGMA data_version"
    ).fetchone()[0]
    get_calls = 0
    real_get_by_id = outcome_harness.repository.get_by_id

    async def tracked_get_by_id(
        *, tenant_id: str, acceptance_id: str
    ) -> dict[str, Any] | None:
        nonlocal get_calls
        get_calls += 1
        return await real_get_by_id(
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
        )

    async def forbidden_repository_call(*_: Any, **__: Any) -> None:
        raise AssertionError("read-only inspector called a mutating repository method")

    def forbidden_projection(*_: Any, **__: Any) -> None:
        raise AssertionError("read-only inspector projected a public response")

    def forbidden_artifact_resolution(*_: Any, **__: Any) -> None:
        raise AssertionError("read-only inspector touched artifact bytes")

    monkeypatch.setattr(outcome_harness.repository, "get_by_id", tracked_get_by_id)
    for method_name in (
        "create_or_replay",
        "reconcile_expired",
        "revoke",
        "consume",
    ):
        monkeypatch.setattr(
            outcome_harness.repository,
            method_name,
            forbidden_repository_call,
        )
    monkeypatch.setattr(
        outcome_harness.service.submission_repository,
        "get_by_resource",
        forbidden_repository_call,
    )
    monkeypatch.setattr(service_module, "_project_record", forbidden_projection)
    monkeypatch.setattr(
        service_module,
        "resolve_output_artifact",
        forbidden_artifact_resolution,
    )

    assert await outcome_harness.inspect() == "not_available"
    assert get_calls == 1
    assert outcome_harness.connection.total_changes == before_total_changes
    assert (
        outcome_harness.connection.execute("PRAGMA data_version").fetchone()[0]
        == before_data_version
    )
    assert outcome_harness.row() == before
    assert outcome_harness.row()["record_status"] == "available"


@pytest.mark.asyncio
async def test_missing_row_is_unknown(outcome_harness: OutcomeHarness) -> None:
    assert await outcome_harness.inspect() == "unknown"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("tenant_id", ""),
        ("tenant_id", "   "),
        ("tenant_id", None),
        ("acceptance_id", ACCEPTANCE_ID.upper()),
        ("acceptance_id", "7f947625-2898-1e9e-9e71-dce4309e5f4f"),
        ("acceptance_id", f" {ACCEPTANCE_ID}"),
        ("acceptance_id", 123),
        ("consumer_operation", ""),
        ("consumer_operation", "   "),
        ("consumer_operation", "o" * 65),
        ("consumer_operation", 123),
        ("consumer_resource_id", ""),
        ("consumer_resource_id", "   "),
        ("consumer_resource_id", "r" * 129),
        ("consumer_resource_id", 123),
    ],
)
@pytest.mark.asyncio
async def test_invalid_inspection_identity_is_unknown_before_repository_lookup(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    invalid_value: Any,
) -> None:
    async def forbidden_lookup(**_: Any) -> None:
        raise AssertionError("invalid inspector identity reached the repository")

    monkeypatch.setattr(outcome_harness.repository, "get_by_id", forbidden_lookup)
    arguments: dict[str, Any] = {
        "tenant_id": TENANT_ID,
        "acceptance_id": ACCEPTANCE_ID,
        "consumer_operation": "distribution.publish",
        "consumer_resource_id": ATTEMPT_ID,
    }
    arguments[field] = invalid_value

    assert await outcome_harness.inspect(**arguments) == "unknown"


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("tenant_id", "tenant-beta"),
        ("source_resource_type", "toolbox"),
        ("source_resource_type", "fast"),
        ("source_resource_id", "nested/resource"),
        ("scenario", "fast"),
        ("artifact_kind", "image"),
        ("artifact_path", "/host/output/final.mp4"),
        (
            "artifact_path",
            "tenants/tenant-alpha/pending_review/"
            "s2_outcome_fixture/assemble/../assemble/final.mp4",
        ),
        (
            "artifact_path",
            "tenants/tenant-beta/pending_review/"
            "s2_outcome_fixture/assemble/final.mp4",
        ),
        (
            "artifact_path",
            "tenants/tenant-alpha/pending_review/"
            "s2_other_fixture/assemble/final.mp4",
        ),
        (
            "artifact_path",
            "tenants/tenant-alpha/pending_review/"
            "s2_outcome_fixture/assemble/final.mov",
        ),
        ("artifact_sha256", "A" * 64),
        ("artifact_sha256", 123),
        ("artifact_size_bytes", 0),
        ("artifact_size_bytes", True),
    ],
)
@pytest.mark.asyncio
async def test_malformed_stored_source_or_artifact_authority_is_unknown(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    invalid_value: Any,
) -> None:
    outcome_harness.insert_record()
    stored = outcome_harness.row()
    stored[field] = invalid_value

    async def corrupt_lookup(**_: Any) -> dict[str, Any]:
        return stored

    monkeypatch.setattr(outcome_harness.repository, "get_by_id", corrupt_lookup)

    assert await outcome_harness.inspect() == "unknown"


_NOW = datetime.now(UTC).isoformat()
_FUTURE = (datetime.now(UTC) + timedelta(hours=4)).isoformat()


@pytest.mark.parametrize(
    "updates",
    [
        {"decision": "pending"},
        {"decision": "rejected"},
        {"record_status": "pending"},
        {"expires_at": "not-a-timestamp"},
        {"expires_at": 123},
        {"expires_at": "9999-12-31T23:59:59.999999-23:59"},
        {"expires_at": "0001-01-01T00:00:00+23:59"},
        {
            "consumed_at": _NOW,
            "consumed_by_operation": "distribution.publish",
            "consumed_by_resource_id": ATTEMPT_ID,
        },
        {"revoked_at": _NOW, "revoked_by_key_id": "reviewer-revoker"},
        {
            "record_status": "consumed",
            "consumed_at": None,
            "consumed_by_operation": "distribution.publish",
            "consumed_by_resource_id": ATTEMPT_ID,
        },
        {
            "record_status": "consumed",
            "consumed_at": "invalid",
            "consumed_by_operation": "distribution.publish",
            "consumed_by_resource_id": ATTEMPT_ID,
        },
        {
            "record_status": "consumed",
            "consumed_at": _NOW,
            "consumed_by_operation": "",
            "consumed_by_resource_id": ATTEMPT_ID,
        },
        {
            "record_status": "consumed",
            "consumed_at": _NOW,
            "consumed_by_operation": "distribution.publish",
            "consumed_by_resource_id": "r" * 129,
        },
        {
            "record_status": "consumed",
            "consumed_at": _NOW,
            "consumed_by_operation": "distribution.publish",
            "consumed_by_resource_id": ATTEMPT_ID,
            "revoked_at": _NOW,
            "revoked_by_key_id": "reviewer-revoker",
        },
        {"record_status": "revoked", "revoked_at": None},
        {"record_status": "revoked", "revoked_at": "invalid"},
        {"record_status": "revoked", "revoked_at": _NOW},
        {"record_status": "expired", "expires_at": _FUTURE},
    ],
    ids=[
        "unknown-decision",
        "available-rejected-conflict",
        "unknown-status",
        "invalid-expires-string",
        "invalid-expires-type",
        "expires-utc-overflow",
        "expires-utc-underflow",
        "available-consumer-evidence",
        "available-revocation-evidence",
        "consumed-missing-time",
        "consumed-invalid-time",
        "consumed-invalid-operation",
        "consumed-invalid-resource",
        "consumed-revocation-conflict",
        "revoked-missing-time",
        "revoked-invalid-time",
        "revoked-missing-revoker",
        "expired-future-expiry",
    ],
)
@pytest.mark.asyncio
async def test_malformed_or_conflicting_lifecycle_evidence_is_unknown(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
    updates: dict[str, Any],
) -> None:
    outcome_harness.insert_record()
    stored = outcome_harness.row()
    stored.update(updates)

    async def corrupt_lookup(**_: Any) -> dict[str, Any]:
        return stored

    monkeypatch.setattr(outcome_harness.repository, "get_by_id", corrupt_lookup)

    assert await outcome_harness.inspect() == "unknown"


_LIFECYCLE_CREATED_AT = "2026-07-12T10:00:00+00:00"
_LIFECYCLE_EXPIRES_AT = "2026-07-12T12:00:00+00:00"
_LIFECYCLE_UPDATED_AT = "2026-07-12T13:00:00+00:00"


@pytest.mark.parametrize(
    ("status", "event_at", "updated_at"),
    [
        ("consumed", "2026-07-12T09:59:59+00:00", _LIFECYCLE_UPDATED_AT),
        ("consumed", "2026-07-12T12:00:01+00:00", _LIFECYCLE_UPDATED_AT),
        ("consumed", _LIFECYCLE_EXPIRES_AT, _LIFECYCLE_UPDATED_AT),
        ("consumed", "2026-07-12T11:00:00+00:00", "2026-07-12T10:59:59+00:00"),
        ("revoked", "2026-07-12T09:59:59+00:00", _LIFECYCLE_UPDATED_AT),
        ("revoked", "2026-07-12T12:00:01+00:00", _LIFECYCLE_UPDATED_AT),
        ("revoked", _LIFECYCLE_EXPIRES_AT, _LIFECYCLE_UPDATED_AT),
        ("revoked", "2026-07-12T11:00:00+00:00", "2026-07-12T10:59:59+00:00"),
        ("expired", None, "2026-07-12T11:59:59+00:00"),
    ],
    ids=[
        "consumed-before-created",
        "consumed-after-expiry",
        "consumed-at-expiry-boundary",
        "updated-before-consumed",
        "revoked-before-created",
        "revoked-after-expiry",
        "revoked-at-expiry-boundary",
        "updated-before-revoked",
        "expired-updated-before-expiry",
    ],
)
@pytest.mark.asyncio
async def test_lifecycle_timestamp_contradictions_are_unknown(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    event_at: str | None,
    updated_at: str,
) -> None:
    outcome_harness.insert_record()
    stored = outcome_harness.row()
    stored.update(
        {
            "decision": "accepted",
            "record_status": status,
            "created_at": _LIFECYCLE_CREATED_AT,
            "expires_at": _LIFECYCLE_EXPIRES_AT,
            "updated_at": updated_at,
            "consumed_at": None,
            "consumed_by_operation": None,
            "consumed_by_resource_id": None,
            "revoked_at": None,
            "revoked_by_key_id": None,
            "revoked_by_record_id": None,
        }
    )
    if status == "consumed":
        stored.update(
            {
                "consumed_at": event_at,
                "consumed_by_operation": "distribution.publish",
                "consumed_by_resource_id": ATTEMPT_ID,
            }
        )
    elif status == "revoked":
        stored.update(
            {
                "revoked_at": event_at,
                "revoked_by_key_id": "reviewer-revoker",
            }
        )

    async def corrupt_lookup(**_: Any) -> dict[str, Any]:
        return stored

    monkeypatch.setattr(outcome_harness.repository, "get_by_id", corrupt_lookup)

    assert await outcome_harness.inspect() == "unknown"


@pytest.mark.parametrize(
    "error",
    [
        AcceptanceStoreUnavailableError(),
        AcceptanceStoreUnavailable(),
        ValueError("typed repository validation failure"),
    ],
)
@pytest.mark.asyncio
async def test_typed_repository_or_store_error_is_unknown(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    async def failed_lookup(**_: Any) -> None:
        raise error

    monkeypatch.setattr(outcome_harness.repository, "get_by_id", failed_lookup)

    assert await outcome_harness.inspect() == "unknown"


@pytest.mark.asyncio
async def test_post_cas_projection_failure_still_inspects_as_consumed_by_this_attempt(
    outcome_harness: OutcomeHarness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome_harness.insert_record()

    def failed_projection(*_: Any, **__: Any) -> None:
        raise AcceptanceStoreUnavailable

    monkeypatch.setattr(service_module, "_project_record", failed_projection)

    with pytest.raises(AcceptanceStoreUnavailable):
        await outcome_harness.service.consume_for_publish(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            consumer_operation="distribution.publish",
            consumer_resource_id=ATTEMPT_ID,
        )

    assert outcome_harness.row()["record_status"] == "consumed"
    assert await outcome_harness.inspect() == "consumed_by_this_attempt"
