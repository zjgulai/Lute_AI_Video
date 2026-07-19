"""Durable tenant-scoped submission idempotency repository contracts.

All tests are hermetic.  PostgreSQL arbitration is exercised with a fake
asyncpg connection; SQLite uses an isolated on-disk database so reconstruction
and transaction behavior are real without touching production.
"""

from __future__ import annotations

import asyncio
import inspect
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from src.storage import db as db_module
from src.storage.idempotency_repository import (
    IdempotencyStoreUnavailableError,
    SubmissionIdempotencyRepository,
)


@pytest.fixture
def sqlite_idempotency_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Install the normal SQLite schema against an isolated database."""

    conn = sqlite3.connect(
        str(tmp_path / "submission-idempotency.db"),
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    async def no_pool():
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_sqlite_conn", conn)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    db_module._create_sqlite_tables()

    yield conn

    conn.close()


def _claim_kwargs(
    *,
    tenant_id: str = "tenant-alpha",
    key_hash: str = "a" * 64,
    request_hash: str = "b" * 64,
    operation: str = "scenario.submit",
    scenario: str = "s1",
    resource_type: str = "scenario",
    resource_id: str = "s1_job_original",
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "key_hash": key_hash,
        "fingerprint_version": "submit-fingerprint.v1",
        "request_hash": request_hash,
        "operation": operation,
        "scenario": scenario,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "effective_policy_version": "generation-policy.v1",
        "response_status": 200,
        "response_body": {
            "label": resource_id,
            "status": "reserved",
            "trace_id": "trace-fixture",
        },
        "owner_instance_id": "worker-fixture",
        "lease_seconds": 120,
    }


def test_sqlite_schema_contains_ledger_constraints(sqlite_idempotency_db: sqlite3.Connection) -> None:
    columns = {
        row["name"] for row in sqlite_idempotency_db.execute("PRAGMA table_info(idempotency_records)").fetchall()
    }
    assert {
        "tenant_id",
        "key_hash",
        "fingerprint_version",
        "request_hash",
        "resource_type",
        "resource_id",
        "record_status",
        "response_body",
        "result_snapshot",
        "owner_instance_id",
        "lease_expires_at",
    } <= columns

    unique_indexes = {
        tuple(
            row["name"] for row in sqlite_idempotency_db.execute(f"PRAGMA index_info({index_row['name']})").fetchall()
        )
        for index_row in sqlite_idempotency_db.execute("PRAGMA index_list(idempotency_records)").fetchall()
        if index_row["unique"]
    }
    assert ("tenant_id", "key_hash") in unique_indexes
    assert ("tenant_id", "resource_type", "resource_id") in unique_indexes


@pytest.mark.asyncio
async def test_sqlite_claim_owner_replay_and_payload_conflict(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)

    owner = await repository.claim(**_claim_kwargs())
    replay = await repository.claim(**_claim_kwargs(resource_id="s1_job_duplicate_preallocation"))
    conflict = await repository.claim(
        **_claim_kwargs(
            request_hash="c" * 64,
            resource_id="s1_job_conflicting_payload",
        )
    )

    assert owner.outcome == "owner"
    assert replay.outcome == "replay"
    assert conflict.outcome == "conflict"
    assert replay.record["resource_id"] == "s1_job_original"
    assert conflict.record["resource_id"] == "s1_job_original"
    count = sqlite_idempotency_db.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]
    assert count == 1


@pytest.mark.asyncio
async def test_service_conflicts_operation_scenario_and_effective_policy_changes(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    from src.services.submission_idempotency import (
        IdempotencyPayloadConflict,
        SubmissionIdempotencyService,
    )

    del sqlite_idempotency_db
    service = SubmissionIdempotencyService(
        SubmissionIdempotencyRepository(require_postgres=False),
        instance_id="service-conflict-fixture",
    )
    key = "service-conflict-key-0001"
    base_policy = {
        "version": "generation-safety.v1",
        "tenant_id": "tenant-alpha",
        "scenario": "fast",
        "provider_submit_allowed": True,
        "enable_media_synthesis": False,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }
    await service.claim_submission(
        tenant_id="tenant-alpha",
        raw_key=key,
        validated_request={"user_prompt": "fixture", "duration": 10},
        effective_policy=base_policy,
        operation="fast.submit",
        scenario="fast",
        resource_type="fast",
        resource_id="fast-original",
        response_body={"task_id": "fast-original", "status": "reserved"},
    )

    variants = [
        {
            "operation": "fast.submit.changed",
            "scenario": "fast",
            "resource_type": "fast",
            "effective_policy": base_policy,
        },
        {
            "operation": "scenario.submit",
            "scenario": "s1",
            "resource_type": "scenario",
            "effective_policy": {**base_policy, "scenario": "s1"},
        },
        {
            "operation": "fast.submit",
            "scenario": "fast",
            "resource_type": "fast",
            "effective_policy": {
                **base_policy,
                "version": "generation-safety.v2",
            },
        },
    ]
    for index, variant in enumerate(variants):
        with pytest.raises(IdempotencyPayloadConflict):
            await service.claim_submission(
                tenant_id="tenant-alpha",
                raw_key=key,
                validated_request={"user_prompt": "fixture", "duration": 10},
                effective_policy=variant["effective_policy"],
                operation=variant["operation"],
                scenario=variant["scenario"],
                resource_type=variant["resource_type"],
                resource_id=f"conflicting-resource-{index}",
                response_body={"status": "reserved"},
            )


@pytest.mark.asyncio
async def test_sqlite_claim_is_tenant_scoped(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)

    first = await repository.claim(**_claim_kwargs(tenant_id="tenant-alpha"))
    second = await repository.claim(
        **_claim_kwargs(
            tenant_id="tenant-beta",
            resource_id="s1_job_tenant_beta",
        )
    )

    assert first.outcome == "owner"
    assert second.outcome == "owner"
    assert first.record["id"] != second.record["id"]


@pytest.mark.asyncio
async def test_sqlite_concurrent_claim_has_exactly_one_owner(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)

    claims = await asyncio.gather(
        *(repository.claim(**_claim_kwargs(resource_id=f"s1_preallocated_{index}")) for index in range(12))
    )

    assert [result.outcome for result in claims].count("owner") == 1
    assert [result.outcome for result in claims].count("replay") == 11
    assert len({result.record["resource_id"] for result in claims}) == 1


@pytest.mark.asyncio
async def test_repository_reconstruction_reads_original_resource(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    original_repository = SubmissionIdempotencyRepository(require_postgres=False)
    owner = await original_repository.claim(**_claim_kwargs())

    reconstructed_repository = SubmissionIdempotencyRepository(require_postgres=False)
    by_key = await reconstructed_repository.get_by_key_hash(
        tenant_id="tenant-alpha",
        key_hash="a" * 64,
    )
    by_resource = await reconstructed_repository.get_by_resource(
        tenant_id="tenant-alpha",
        resource_type="scenario",
        resource_id="s1_job_original",
    )

    assert by_key == owner.record
    assert by_resource == owner.record


@pytest.mark.asyncio
async def test_terminal_transition_cannot_regress(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)
    owner = await repository.claim(**_claim_kwargs())

    completed = await repository.transition(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
        expected_statuses={"reserved"},
        new_status="completed",
        owner_instance_id="worker-fixture",
        stage="completed",
        response_body={"label": "s1_job_original", "status": "completed"},
        result_snapshot={"status": "completed", "output_url": "/media/result.mp4"},
        mark_completed=True,
    )
    late_callback = await repository.transition(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
        expected_statuses={"running"},
        new_status="running",
        owner_instance_id="worker-fixture",
        stage="rendering",
    )

    assert completed is not None
    assert completed["record_status"] == "completed"
    assert completed["result_snapshot"]["output_url"] == "/media/result.mp4"
    assert late_callback is None
    persisted = await repository.get_by_key_hash(
        tenant_id="tenant-alpha",
        key_hash="a" * 64,
    )
    assert persisted is not None
    assert persisted["record_status"] == "completed"


@pytest.mark.asyncio
async def test_transition_rejects_stale_owner_instance(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)
    owner = await repository.claim(**_claim_kwargs())

    stale = await repository.transition(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
        expected_statuses={"reserved"},
        new_status="queued",
        owner_instance_id="worker-stale",
    )
    stale_terminal = await repository.transition(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
        expected_statuses={"reserved"},
        new_status="failed",
        owner_instance_id="worker-stale",
        safe_error_code="stale_worker_must_not_win",
    )
    current = await repository.transition(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
        expected_statuses={"reserved"},
        new_status="queued",
        owner_instance_id="worker-fixture",
    )

    assert stale is None
    assert stale_terminal is None
    assert current is not None
    assert current["record_status"] == "queued"
    assert current["owner_instance_id"] == "worker-fixture"


@pytest.mark.asyncio
async def test_expired_lease_reconciles_once_without_sleep(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)
    owner = await repository.claim(**_claim_kwargs())
    sqlite_idempotency_db.execute(
        "UPDATE idempotency_records SET lease_expires_at = datetime('now', '-1 second') WHERE id = ?",
        (owner.record["id"],),
    )
    sqlite_idempotency_db.commit()

    reconciled = await repository.reconcile_expired_lease(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
    )
    repeated = await repository.reconcile_expired_lease(
        tenant_id="tenant-alpha",
        record_id=owner.record["id"],
    )

    assert reconciled is not None
    assert reconciled["record_status"] == "recovery_required"
    assert reconciled["response_body"]["status"] == "recovery_required"
    assert repeated == reconciled


@pytest.mark.asyncio
async def test_production_mode_never_uses_sqlite_fallback(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=True)

    with pytest.raises(IdempotencyStoreUnavailableError):
        await repository.claim(**_claim_kwargs())

    count = sqlite_idempotency_db.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]
    assert count == 0


@pytest.mark.asyncio
async def test_repository_rejects_raw_or_malformed_digests_before_persistence(
    sqlite_idempotency_db: sqlite3.Connection,
) -> None:
    repository = SubmissionIdempotencyRepository(require_postgres=False)

    with pytest.raises(ValueError, match="key_hash"):
        await repository.claim(**_claim_kwargs(key_hash="raw-idempotency-key"))
    with pytest.raises(ValueError, match="request_hash"):
        await repository.claim(**_claim_kwargs(request_hash="not-a-digest"))

    count = sqlite_idempotency_db.execute("SELECT COUNT(*) FROM idempotency_records").fetchone()[0]
    assert count == 0


def test_postgres_claim_uses_unique_constraint_arbitration() -> None:
    source = inspect.getsource(SubmissionIdempotencyRepository)
    assert "ON CONFLICT (tenant_id, key_hash) DO NOTHING" in source
    assert "RETURNING *" in source


def test_alembic_revision_descends_from_current_head() -> None:
    migration = Path("migrations/alembic/versions/d5e6f7a8b9c0_add_submission_idempotency_records.py").read_text(
        encoding="utf-8"
    )
    assert 'revision: str = "d5e6f7a8b9c0"' in migration
    assert 'down_revision: str | None = "7c4b8e2f1a09"' in migration
    assert "idempotency_records" in migration
    assert "uq_idempotency_records_tenant_key" in migration
    assert "uq_idempotency_records_tenant_resource" in migration
