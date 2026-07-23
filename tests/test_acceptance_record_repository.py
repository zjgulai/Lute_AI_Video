"""Durable single-use acceptance repository contracts.

SQLite tests use the real schema and transaction engine against an isolated
database.  PostgreSQL-specific arbitration is covered separately without
contacting any external database.
"""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from asyncpg.exceptions import UniqueViolationError

from src.storage import db as db_module


def _seed_source(
    connection: sqlite3.Connection,
    *,
    tenant_id: str = "tenant-alpha",
    resource_type: str = "scenario",
    resource_id: str = "s1-job-completed",
    scenario: str = "s1",
) -> None:
    connection.execute(
        """
        INSERT INTO idempotency_records (
            id, tenant_id, key_hash, fingerprint_version, request_hash,
            operation, scenario, resource_type, resource_id, record_status,
            stage, effective_policy_version, response_status, response_body,
            completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', 'completed', ?, 200, '{}', CURRENT_TIMESTAMP)
        """,
        (
            f"source-{tenant_id}-{resource_id}",
            tenant_id,
            "1" * 64,
            "submit-fingerprint.v1",
            "2" * 64,
            f"{resource_type}.submit",
            scenario,
            resource_type,
            resource_id,
            "generation-policy.v1",
        ),
    )
    connection.commit()


@pytest.fixture
def sqlite_acceptance_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> sqlite3.Connection:
    """Install the normal SQLite schema against an isolated database."""

    connection = sqlite3.connect(
        str(tmp_path / "acceptance-records.db"),
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
    _seed_source(connection)

    yield connection

    connection.close()


def _record_kwargs(
    *,
    tenant_id: str = "tenant-alpha",
    creation_key_hash: str = "a" * 64,
    fingerprint_version: str = "acceptance-fingerprint.v1",
    request_hash: str = "b" * 64,
    source_resource_type: str = "scenario",
    source_resource_id: str = "s1-job-completed",
    scenario: str = "s1",
    artifact_path: str = "output/tenant-alpha/final.mp4",
    artifact_sha256: str = "c" * 64,
    artifact_size_bytes: int = 1024,
    artifact_kind: str = "video",
    transparency_sidecar_path: str = (
        "tenants/tenant-alpha/pending_review/s1-job-completed/"
        "transparency/transparency-sidecar.v1.fixture.json"
    ),
    transparency_sidecar_sha256: str = "e" * 64,
    final_artifact_c2pa_status: str = "signed_local_readback",
    decision: str = "accepted",
    reviewer_key_id: str = "reviewer-key-alpha",
    reviewer_key_type: str = "tenant",
    review_notes: str = "Approved after human review.",
    expires_in_seconds: int = 3600,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "creation_key_hash": creation_key_hash,
        "fingerprint_version": fingerprint_version,
        "request_hash": request_hash,
        "source_resource_type": source_resource_type,
        "source_resource_id": source_resource_id,
        "scenario": scenario,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "artifact_size_bytes": artifact_size_bytes,
        "artifact_kind": artifact_kind,
        "transparency_sidecar_path": transparency_sidecar_path,
        "transparency_sidecar_sha256": transparency_sidecar_sha256,
        "final_artifact_c2pa_status": final_artifact_c2pa_status,
        "decision": decision,
        "reviewer_key_id": reviewer_key_id,
        "reviewer_key_type": reviewer_key_type,
        "review_notes": review_notes,
        "expires_in_seconds": expires_in_seconds,
    }


def _consume_kwargs(
    acceptance_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "tenant_id": "tenant-alpha",
        "acceptance_id": acceptance_id,
        "artifact_path": "output/tenant-alpha/final.mp4",
        "artifact_sha256": "c" * 64,
        "artifact_size_bytes": 1024,
        "transparency_sidecar_path": (
            "tenants/tenant-alpha/pending_review/s1-job-completed/"
            "transparency/transparency-sidecar.v1.fixture.json"
        ),
        "transparency_sidecar_sha256": "e" * 64,
        "final_artifact_c2pa_status": "signed_local_readback",
        "consumer_operation": "delivery.prepare",
        "consumer_resource_id": "delivery-owner",
    }
    values.update(overrides)
    return values


def _normalized_sql(query: str) -> str:
    return " ".join(query.split())


class _RecordingTransaction:
    def __init__(self, connection: _RecordingPgConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        assert not self.connection.in_transaction
        self.connection.in_transaction = True

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.connection.in_transaction = False


class _RecordingPgConnection:
    """Small SQL recorder; it models only asyncpg behavior used by creation."""

    def __init__(self, *, source_exists: bool = True) -> None:
        self.source_exists = source_exists
        self.in_transaction = False
        self.calls: list[tuple[str, str, tuple[Any, ...], bool]] = []

    def transaction(self) -> _RecordingTransaction:
        return _RecordingTransaction(self)

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        normalized = _normalized_sql(query)
        self.calls.append(("fetchrow", normalized, args, self.in_transaction))
        if normalized.startswith("SELECT id FROM idempotency_records"):
            return {"id": "source-row"} if self.source_exists else None
        if normalized.startswith("SELECT * FROM acceptance_records"):
            return None
        if normalized.startswith("INSERT INTO acceptance_records"):
            decision = args[12]
            return {
                "id": args[0],
                "tenant_id": args[1],
                "creation_key_hash": args[2],
                "fingerprint_version": args[3],
                "request_hash": args[4],
                "source_resource_type": args[5],
                "source_resource_id": args[6],
                "scenario": args[7],
                "artifact_path": args[8],
                "artifact_sha256": args[9],
                "artifact_size_bytes": args[10],
                "artifact_kind": args[11],
                "decision": decision,
                "record_status": "available" if decision == "accepted" else "rejected",
                "reviewer_key_id": args[13],
                "reviewer_key_type": args[14],
                "review_notes": args[15],
                "expires_at": "2099-01-01 00:00:00+00",
                "consumed_at": None,
                "consumed_by_operation": None,
                "consumed_by_resource_id": None,
                "revoked_at": None,
                "revoked_by_key_id": None,
                "revoked_by_record_id": None,
                "created_at": "2026-07-12 00:00:00+00",
                "updated_at": "2026-07-12 00:00:00+00",
            }
        raise AssertionError(f"unexpected fetchrow SQL: {normalized}")

    async def execute(self, query: str, *args: Any) -> str:
        normalized = _normalized_sql(query)
        self.calls.append(("execute", normalized, args, self.in_transaction))
        if normalized.startswith("UPDATE acceptance_records"):
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute SQL: {normalized}")


class _RecordingAcquire:
    def __init__(self, connection: _RecordingPgConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _RecordingPgConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None


class _RecordingPgPool:
    def __init__(self, connection: _RecordingPgConnection) -> None:
        self.connection = connection

    def acquire(self) -> _RecordingAcquire:
        return _RecordingAcquire(self.connection)


class _LifecyclePgConnection(_RecordingPgConnection):
    def __init__(self) -> None:
        super().__init__()
        self.record: dict[str, Any] = {
            "id": "acceptance-lifecycle",
            "tenant_id": "tenant-alpha",
            "creation_key_hash": "a" * 64,
            "fingerprint_version": "acceptance-fingerprint.v1",
            "request_hash": "b" * 64,
            "source_resource_type": "scenario",
            "source_resource_id": "s1-job-completed",
            "scenario": "s1",
            "artifact_path": "output/tenant-alpha/final.mp4",
            "artifact_sha256": "c" * 64,
            "artifact_size_bytes": 1024,
            "artifact_kind": "video",
            "decision": "accepted",
            "record_status": "available",
            "reviewer_key_id": "reviewer-key-alpha",
            "reviewer_key_type": "tenant",
            "review_notes": "Approved after human review.",
            "expires_at": "2099-01-01 00:00:00+00",
            "consumed_at": None,
            "consumed_by_operation": None,
            "consumed_by_resource_id": None,
            "revoked_at": None,
            "revoked_by_key_id": None,
            "revoked_by_record_id": None,
            "created_at": "2026-07-12 00:00:00+00",
            "updated_at": "2026-07-12 00:00:00+00",
        }

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        normalized = _normalized_sql(query)
        self.calls.append(("fetchrow", normalized, args, self.in_transaction))
        if normalized.startswith("SELECT * FROM acceptance_records"):
            if args[0] != self.record["tenant_id"]:
                return None
            return dict(self.record)
        if normalized.startswith("UPDATE acceptance_records"):
            if self.record["record_status"] != "available":
                return None
            if "record_status = 'revoked'" in normalized:
                self.record.update(
                    {
                        "record_status": "revoked",
                        "revoked_at": "2026-07-12 01:00:00+00",
                        "revoked_by_key_id": args[2],
                    }
                )
                return dict(self.record)
            if "record_status = 'consumed'" in normalized:
                self.record.update(
                    {
                        "record_status": "consumed",
                        "consumed_at": "2026-07-12 01:00:00+00",
                        "consumed_by_operation": args[4],
                        "consumed_by_resource_id": args[5],
                    }
                )
                return dict(self.record)
        raise AssertionError(f"unexpected fetchrow SQL: {normalized}")

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        normalized = _normalized_sql(query)
        self.calls.append(("fetch", normalized, args, self.in_transaction))
        if normalized.startswith("UPDATE acceptance_records"):
            return [{"id": self.record["id"]}]
        raise AssertionError(f"unexpected fetch SQL: {normalized}")


class _AvailablePathCollisionPgConnection(_RecordingPgConnection):
    """Expose a creation-key winner only after the failed insert rolls back."""

    def __init__(self, *, existing_request_hash: str) -> None:
        super().__init__()
        self.insert_failed = False
        self.existing_record = dict(_LifecyclePgConnection().record)
        self.existing_record["request_hash"] = existing_request_hash

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        normalized = _normalized_sql(query)
        self.calls.append(("fetchrow", normalized, args, self.in_transaction))
        if normalized.startswith("SELECT id FROM idempotency_records"):
            return {"id": "source-row"}
        if normalized.startswith("SELECT * FROM acceptance_records"):
            if not self.insert_failed:
                return None
            assert not self.in_transaction
            return dict(self.existing_record)
        if normalized.startswith("INSERT INTO acceptance_records"):
            self.insert_failed = True
            error = UniqueViolationError("available path collision")
            setattr(
                error,
                "constraint_name",
                "uq_acceptance_records_tenant_available_path",
            )
            raise error
        raise AssertionError(f"unexpected fetchrow SQL: {normalized}")


def test_sqlite_schema_contains_lifecycle_constraints_and_partial_index(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in sqlite_acceptance_db.execute(
            "PRAGMA table_info(acceptance_records)"
        ).fetchall()
    }
    assert {
        "tenant_id",
        "creation_key_hash",
        "fingerprint_version",
        "request_hash",
        "source_resource_type",
        "source_resource_id",
        "artifact_path",
        "artifact_sha256",
        "transparency_sidecar_path",
        "transparency_sidecar_sha256",
        "final_artifact_c2pa_status",
        "decision",
        "record_status",
        "expires_at",
        "consumed_at",
        "consumed_by_operation",
        "consumed_by_resource_id",
        "revoked_at",
        "revoked_by_key_id",
        "revoked_by_record_id",
    } <= columns

    indexes = {
        row["name"]: row
        for row in sqlite_acceptance_db.execute(
            "PRAGMA index_list(acceptance_records)"
        ).fetchall()
    }
    available_index = indexes["uq_acceptance_records_tenant_available_path"]
    assert available_index["unique"] == 1
    assert available_index["partial"] == 1
    indexed_columns = tuple(
        row["name"]
        for row in sqlite_acceptance_db.execute(
            "PRAGMA index_info(uq_acceptance_records_tenant_available_path)"
        ).fetchall()
    )
    assert indexed_columns == ("tenant_id", "artifact_path")
    index_sql = sqlite_acceptance_db.execute(
        """
        SELECT sql FROM sqlite_master
        WHERE type = 'index'
          AND name = 'uq_acceptance_records_tenant_available_path'
        """
    ).fetchone()["sql"]
    assert "WHERE record_status = 'available'" in index_sql


@pytest.mark.asyncio
async def test_sqlite_schema_rejects_invalid_lifecycle_shapes(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import AcceptanceRecordRepository

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())

    with pytest.raises(sqlite3.IntegrityError):
        sqlite_acceptance_db.execute(
            "UPDATE acceptance_records SET record_status = 'consumed' WHERE id = ?",
            (owner.record["id"],),
        )
    sqlite_acceptance_db.rollback()

    with pytest.raises(sqlite3.IntegrityError):
        sqlite_acceptance_db.execute(
            """
            UPDATE acceptance_records
            SET fingerprint_version = 'acceptance-create.v2',
                transparency_sidecar_path = NULL
            WHERE id = ?
            """,
            (owner.record["id"],),
        )
    sqlite_acceptance_db.rollback()

    with pytest.raises(sqlite3.IntegrityError):
        sqlite_acceptance_db.execute(
            """
            UPDATE acceptance_records
            SET final_artifact_c2pa_status = 'unsigned_pending_review'
            WHERE id = ?
            """,
            (owner.record["id"],),
        )
    sqlite_acceptance_db.rollback()

    with pytest.raises(sqlite3.IntegrityError):
        sqlite_acceptance_db.execute(
            """
            UPDATE acceptance_records
            SET created_at = CURRENT_TIMESTAMP,
                expires_at = datetime('now', '-1 second')
            WHERE id = ?
            """,
            (owner.record["id"],),
        )
    sqlite_acceptance_db.rollback()


@pytest.mark.asyncio
async def test_create_owner_replay_conflict_and_one_available_per_path(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceAlreadyAvailableError,
        AcceptancePayloadConflictError,
        AcceptanceRecordRepository,
    )

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())
    replay = await repository.create_or_replay(**_record_kwargs())
    assert owner.outcome == "owner"
    assert replay.outcome == "replay"
    assert owner.record["id"] == replay.record["id"]

    with pytest.raises(AcceptancePayloadConflictError):
        await repository.create_or_replay(**_record_kwargs(request_hash="d" * 64))

    with pytest.raises(AcceptanceAlreadyAvailableError):
        await repository.create_or_replay(
            **_record_kwargs(
                creation_key_hash="e" * 64,
                request_hash="f" * 64,
                artifact_sha256="0" * 64,
            )
        )

    rows = sqlite_acceptance_db.execute(
        "SELECT id, record_status FROM acceptance_records"
    ).fetchall()
    assert [(row["id"], row["record_status"]) for row in rows] == [
        (owner.record["id"], "available")
    ]


@pytest.mark.asyncio
async def test_create_requires_tenant_owned_source_row(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceRecordRepository,
        AcceptanceSourceNotFoundError,
    )

    repository = AcceptanceRecordRepository(require_postgres=False)

    with pytest.raises(AcceptanceSourceNotFoundError):
        await repository.create_or_replay(
            **_record_kwargs(source_resource_id="missing-source")
        )

    assert (
        sqlite_acceptance_db.execute(
            "SELECT COUNT(*) FROM acceptance_records"
        ).fetchone()[0]
        == 0
    )


def test_acceptance_migration_descends_from_submission_ledger() -> None:
    migration = Path(
        "migrations/alembic/versions/e8f1a2b3c4d5_add_acceptance_records.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "e8f1a2b3c4d5"' in migration
    assert 'down_revision: str | None = "d5e6f7a8b9c0"' in migration
    assert "acceptance_records" in migration
    assert "uq_acceptance_records_tenant_available_path" in migration
    assert "ck_acceptance_records_decision_status" in migration
    assert "ck_acceptance_records_consumed_fields" in migration
    assert "ck_acceptance_records_revoked_fields" in migration
    fresh_schema = Path("src/storage/migrations/001_init.sql").read_text(
        encoding="utf-8"
    )
    assert "CREATE TABLE IF NOT EXISTS acceptance_records" in fresh_schema
    assert "uq_acceptance_records_tenant_available_path" in fresh_schema
    assert "acceptance_records" in db_module._REQUIRED_TABLES


def test_acceptance_transparency_migration_is_additive_and_legacy_nullable() -> None:
    migration = Path(
        "migrations/alembic/versions/d9e0f1a2b3c4_bind_acceptance_transparency.py"
    ).read_text(encoding="utf-8")
    fresh_schema = Path("src/storage/migrations/001_init.sql").read_text(
        encoding="utf-8"
    )

    assert 'revision: str = "d9e0f1a2b3c4"' in migration
    assert 'down_revision: str | None = "c8d9e0f1a2b3"' in migration
    for column in (
        "transparency_sidecar_path",
        "transparency_sidecar_sha256",
        "final_artifact_c2pa_status",
    ):
        assert column in migration
        assert column in fresh_schema
    assert '"pipeline_states"' in migration
    assert 'sa.Column("transparency", JSONB(), nullable=True)' in migration
    assert "ADD COLUMN IF NOT EXISTS transparency JSONB" in fresh_schema
    assert migration.count("nullable=True") == 4


@pytest.mark.asyncio
async def test_rejected_conflict_has_no_revocation_side_effect(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptancePayloadConflictError,
        AcceptanceRecordRepository,
    )

    repository = AcceptanceRecordRepository(require_postgres=False)
    accepted = await repository.create_or_replay(**_record_kwargs())

    with pytest.raises(AcceptancePayloadConflictError):
        await repository.create_or_replay(
            **_record_kwargs(
                request_hash="d" * 64,
                decision="rejected",
                review_notes="Conflicting decision must not revoke.",
            )
        )

    current = sqlite_acceptance_db.execute(
        "SELECT * FROM acceptance_records WHERE id = ?",
        (accepted.record["id"],),
    ).fetchone()
    assert current is not None
    assert current["record_status"] == "available"
    assert current["revoked_by_record_id"] is None
    assert (
        sqlite_acceptance_db.execute(
            "SELECT COUNT(*) FROM acceptance_records"
        ).fetchone()[0]
        == 1
    )


@pytest.mark.asyncio
async def test_rejected_revokes_available_and_accepted_can_reopen_path(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import AcceptanceRecordRepository

    repository = AcceptanceRecordRepository(require_postgres=False)
    first = await repository.create_or_replay(**_record_kwargs())
    rejection = await repository.create_or_replay(
        **_record_kwargs(
            creation_key_hash="d" * 64,
            request_hash="e" * 64,
            decision="rejected",
            reviewer_key_id="reviewer-key-rejection",
            review_notes="Rejected after a second human review.",
        )
    )

    revoked = sqlite_acceptance_db.execute(
        "SELECT * FROM acceptance_records WHERE id = ?",
        (first.record["id"],),
    ).fetchone()
    assert rejection.outcome == "owner"
    assert rejection.record["record_status"] == "rejected"
    assert revoked is not None
    assert revoked["record_status"] == "revoked"
    assert revoked["revoked_by_key_id"] == "reviewer-key-rejection"
    assert revoked["revoked_by_record_id"] == rejection.record["id"]

    reopened = await repository.create_or_replay(
        **_record_kwargs(
            creation_key_hash="f" * 64,
            request_hash="0" * 64,
            review_notes="Accepted by a later independent review.",
        )
    )
    statuses = [
        row["record_status"]
        for row in sqlite_acceptance_db.execute(
            "SELECT record_status FROM acceptance_records ORDER BY created_at, rowid"
        ).fetchall()
    ]
    assert reopened.outcome == "owner"
    assert reopened.record["record_status"] == "available"
    assert statuses == ["revoked", "rejected", "available"]


@pytest.mark.asyncio
async def test_database_time_expiry_reconciles_once_and_is_reconstructed(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import AcceptanceRecordRepository

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())
    sqlite_acceptance_db.execute(
        """
        UPDATE acceptance_records
        SET created_at = datetime('now', '-2 seconds'),
            expires_at = datetime('now', '-1 second')
        WHERE id = ?
        """,
        (owner.record["id"],),
    )
    sqlite_acceptance_db.commit()

    first = await repository.reconcile_expired(
        tenant_id="tenant-alpha",
        artifact_path="output/tenant-alpha/final.mp4",
    )
    repeated = await repository.reconcile_expired(
        tenant_id="tenant-alpha",
        acceptance_id=owner.record["id"],
    )
    by_id = await repository.get_by_id(
        tenant_id="tenant-alpha",
        acceptance_id=owner.record["id"],
    )
    by_key = await repository.get_by_creation_key_hash(
        tenant_id="tenant-alpha",
        creation_key_hash="a" * 64,
    )

    assert first == 1
    assert repeated == 0
    assert by_id is not None
    assert by_id["record_status"] == "expired"
    assert by_key == by_id


@pytest.mark.asyncio
async def test_explicit_revoke_is_idempotent_and_rejects_terminal_rows(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceNotRevocableError,
        AcceptanceRecordRepository,
    )

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())
    revoked = await repository.revoke(
        tenant_id="tenant-alpha",
        acceptance_id=owner.record["id"],
        reviewer_key_id="revoker-original",
    )
    repeated = await repository.revoke(
        tenant_id="tenant-alpha",
        acceptance_id=owner.record["id"],
        reviewer_key_id="revoker-must-not-overwrite",
    )

    assert revoked["record_status"] == "revoked"
    assert revoked["revoked_by_key_id"] == "revoker-original"
    assert repeated == revoked

    rejected = await repository.create_or_replay(
        **_record_kwargs(
            creation_key_hash="d" * 64,
            request_hash="e" * 64,
            decision="rejected",
        )
    )
    with pytest.raises(AcceptanceNotRevocableError):
        await repository.revoke(
            tenant_id="tenant-alpha",
            acceptance_id=rejected.record["id"],
            reviewer_key_id="revoker-rejected",
        )

    expiring = await repository.create_or_replay(
        **_record_kwargs(
            creation_key_hash="f" * 64,
            request_hash="0" * 64,
        )
    )
    sqlite_acceptance_db.execute(
        """
        UPDATE acceptance_records
        SET created_at = datetime('now', '-2 seconds'),
            expires_at = datetime('now', '-1 second')
        WHERE id = ?
        """,
        (expiring.record["id"],),
    )
    sqlite_acceptance_db.commit()
    assert (
        await repository.reconcile_expired(
            tenant_id="tenant-alpha",
            acceptance_id=expiring.record["id"],
        )
        == 1
    )
    with pytest.raises(AcceptanceNotRevocableError):
        await repository.revoke(
            tenant_id="tenant-alpha",
            acceptance_id=expiring.record["id"],
            reviewer_key_id="revoker-expired",
        )


@pytest.mark.asyncio
async def test_consume_requires_exact_artifact_identity_and_blocks_revoke(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceNotAvailableError,
        AcceptanceNotRevocableError,
        AcceptanceRecordRepository,
    )

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())

    with pytest.raises(AcceptanceNotAvailableError):
        await repository.consume(
            **_consume_kwargs(
                owner.record["id"],
                artifact_path="output/tenant-alpha/wrong.mp4",
                consumer_resource_id="delivery-wrong-path",
            )
        )
    with pytest.raises(AcceptanceNotAvailableError):
        await repository.consume(
            **_consume_kwargs(
                owner.record["id"],
                artifact_sha256="d" * 64,
                consumer_resource_id="delivery-wrong-digest",
            )
        )
    unchanged = await repository.get_by_id(
        tenant_id="tenant-alpha",
        acceptance_id=owner.record["id"],
    )
    assert unchanged is not None
    assert unchanged["record_status"] == "available"
    assert unchanged["consumed_at"] is None

    consumed = await repository.consume(
        **_consume_kwargs(owner.record["id"])
    )
    assert consumed["record_status"] == "consumed"
    assert consumed["consumed_at"] is not None
    assert consumed["consumed_by_operation"] == "delivery.prepare"
    assert consumed["consumed_by_resource_id"] == "delivery-owner"

    with pytest.raises(AcceptanceNotRevocableError):
        await repository.revoke(
            tenant_id="tenant-alpha",
            acceptance_id=owner.record["id"],
            reviewer_key_id="revoker-too-late",
        )


@pytest.mark.asyncio
async def test_concurrent_consume_has_exactly_one_winner(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceNotAvailableError,
        AcceptanceRecordRepository,
    )

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())

    results = await asyncio.gather(
        *(
            repository.consume(
                **_consume_kwargs(
                    owner.record["id"],
                    consumer_resource_id=f"delivery-{index}",
                )
            )
            for index in range(12)
        ),
        return_exceptions=True,
    )

    winners = [result for result in results if isinstance(result, dict)]
    losers = [
        result
        for result in results
        if isinstance(result, AcceptanceNotAvailableError)
    ]
    assert len(winners) == 1
    assert len(losers) == 11
    persisted = sqlite_acceptance_db.execute(
        "SELECT * FROM acceptance_records WHERE id = ?",
        (owner.record["id"],),
    ).fetchone()
    assert persisted is not None
    assert persisted["record_status"] == "consumed"
    assert persisted["consumed_by_resource_id"] == winners[0][
        "consumed_by_resource_id"
    ]


@pytest.mark.asyncio
async def test_tenant_isolation_allows_same_path_without_cross_tenant_access(
    sqlite_acceptance_db: sqlite3.Connection,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceNotAvailableError,
        AcceptanceNotRevocableError,
        AcceptanceRecordRepository,
    )

    _seed_source(
        sqlite_acceptance_db,
        tenant_id="tenant-beta",
        resource_id="s1-job-beta",
    )
    repository = AcceptanceRecordRepository(require_postgres=False)
    alpha = await repository.create_or_replay(**_record_kwargs())
    beta = await repository.create_or_replay(
        **_record_kwargs(
            tenant_id="tenant-beta",
            source_resource_id="s1-job-beta",
        )
    )

    assert alpha.outcome == "owner"
    assert beta.outcome == "owner"
    assert alpha.record["id"] != beta.record["id"]
    assert (
        await repository.get_by_id(
            tenant_id="tenant-beta",
            acceptance_id=alpha.record["id"],
        )
        is None
    )
    with pytest.raises(AcceptanceNotRevocableError):
        await repository.revoke(
            tenant_id="tenant-beta",
            acceptance_id=alpha.record["id"],
            reviewer_key_id="cross-tenant-revoker",
        )
    with pytest.raises(AcceptanceNotAvailableError):
        await repository.consume(
            **_consume_kwargs(
                alpha.record["id"],
                tenant_id="tenant-beta",
                consumer_resource_id="cross-tenant-consumer",
            )
        )
    persisted_alpha = sqlite_acceptance_db.execute(
        "SELECT * FROM acceptance_records WHERE id = ?",
        (alpha.record["id"],),
    ).fetchone()
    assert persisted_alpha is not None
    assert persisted_alpha["record_status"] == "available"


@pytest.mark.asyncio
async def test_close_and_reopen_reconstructs_acceptance_truth(
    sqlite_acceptance_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.acceptance_repository import AcceptanceRecordRepository

    repository = AcceptanceRecordRepository(require_postgres=False)
    owner = await repository.create_or_replay(**_record_kwargs())
    database_path = Path(
        sqlite_acceptance_db.execute("PRAGMA database_list").fetchone()["file"]
    )
    sqlite_acceptance_db.close()

    reopened = sqlite3.connect(str(database_path), check_same_thread=False)
    reopened.row_factory = sqlite3.Row
    monkeypatch.setattr(db_module, "_sqlite_conn", reopened)
    reconstructed = AcceptanceRecordRepository(require_postgres=False)
    by_key = await reconstructed.get_by_creation_key_hash(
        tenant_id="tenant-alpha",
        creation_key_hash="a" * 64,
    )
    by_id = await reconstructed.get_by_id(
        tenant_id="tenant-alpha",
        acceptance_id=owner.record["id"],
    )

    assert by_key == owner.record
    assert by_id == owner.record
    reopened.close()


@pytest.mark.asyncio
async def test_production_requires_verified_pool_and_never_falls_back(
    sqlite_acceptance_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceRecordRepository,
        AcceptanceStoreUnavailableError,
    )

    async def forbidden_fallback() -> None:
        raise AssertionError("production must not initialize a fallback")

    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: None)
    monkeypatch.setattr(db_module, "get_pool", forbidden_fallback)
    repository = AcceptanceRecordRepository(require_postgres=True)

    with pytest.raises(AcceptanceStoreUnavailableError):
        await repository.create_or_replay(**_record_kwargs())

    assert (
        sqlite_acceptance_db.execute(
            "SELECT COUNT(*) FROM acceptance_records"
        ).fetchone()[0]
        == 0
    )


@pytest.mark.asyncio
async def test_postgres_creation_locks_source_before_acceptance_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.acceptance_repository import AcceptanceRecordRepository

    connection = _RecordingPgConnection()
    pool = _RecordingPgPool(connection)

    async def forbidden_fallback() -> None:
        raise AssertionError("verified PostgreSQL path must not call get_pool")

    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: pool)
    monkeypatch.setattr(db_module, "get_pool", forbidden_fallback)
    repository = AcceptanceRecordRepository(require_postgres=True)
    result = await repository.create_or_replay(**_record_kwargs())

    statements = [call[1] for call in connection.calls]
    source_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("SELECT id FROM idempotency_records")
    )
    creation_key_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("SELECT * FROM acceptance_records")
    )
    expiry_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("UPDATE acceptance_records")
        and "record_status = 'expired'" in statement
    )
    insert_index = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith("INSERT INTO acceptance_records")
    )

    assert result.outcome == "owner"
    assert "FOR UPDATE" in statements[source_index]
    assert source_index < creation_key_index < expiry_index < insert_index
    assert all(call[3] for call in connection.calls)


@pytest.mark.asyncio
async def test_postgres_create_casts_reused_decision_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep asyncpg from inferring both text and varchar for the decision."""

    from src.storage.acceptance_repository import AcceptanceRecordRepository

    connection = _RecordingPgConnection()
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPgPool(connection),
    )
    repository = AcceptanceRecordRepository(require_postgres=True)

    await repository.create_or_replay(**_record_kwargs())

    insert_sql = next(
        call[1]
        for call in connection.calls
        if call[1].startswith("INSERT INTO acceptance_records")
    )
    assert "$16::varchar," in insert_sql
    assert "CASE WHEN $16::varchar = 'accepted'" in insert_sql


@pytest.mark.asyncio
async def test_postgres_rejection_preallocates_revocation_pointer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.acceptance_repository import AcceptanceRecordRepository

    connection = _RecordingPgConnection()
    pool = _RecordingPgPool(connection)
    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: pool)
    repository = AcceptanceRecordRepository(require_postgres=True)

    result = await repository.create_or_replay(
        **_record_kwargs(
            decision="rejected",
            request_hash="d" * 64,
            reviewer_key_id="reviewer-key-rejection",
        )
    )
    revoke_call = next(
        call
        for call in connection.calls
        if call[1].startswith("UPDATE acceptance_records")
        and "revoked_by_record_id" in call[1]
    )
    insert_call = next(
        call
        for call in connection.calls
        if call[1].startswith("INSERT INTO acceptance_records")
    )

    assert result.record["record_status"] == "rejected"
    assert revoke_call[2][1] == insert_call[2][0]
    assert revoke_call[2][1] == result.record["id"]
    assert connection.calls.index(revoke_call) < connection.calls.index(insert_call)


@pytest.mark.parametrize(
    ("existing_request_hash", "expected_outcome"),
    [
        ("b" * 64, "replay"),
        ("d" * 64, "conflict"),
    ],
    ids=["matching-fingerprint", "conflicting-fingerprint"],
)
@pytest.mark.asyncio
async def test_postgres_collision_checks_creation_key_before_path_mapping(
    monkeypatch: pytest.MonkeyPatch,
    existing_request_hash: str,
    expected_outcome: str,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptancePayloadConflictError,
        AcceptanceRecordRepository,
    )

    connection = _AvailablePathCollisionPgConnection(
        existing_request_hash=existing_request_hash
    )
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPgPool(connection),
    )
    repository = AcceptanceRecordRepository(require_postgres=True)

    if expected_outcome == "replay":
        result = await repository.create_or_replay(**_record_kwargs())
        assert result.outcome == "replay"
        assert result.record["id"] == "acceptance-lifecycle"
    else:
        with pytest.raises(AcceptancePayloadConflictError):
            await repository.create_or_replay(**_record_kwargs())


@pytest.mark.asyncio
async def test_postgres_lifecycle_uses_database_time_and_compare_and_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.acceptance_repository import (
        AcceptanceNotAvailableError,
        AcceptanceRecordRepository,
    )

    reconcile_connection = _LifecyclePgConnection()
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPgPool(reconcile_connection),
    )
    repository = AcceptanceRecordRepository(require_postgres=True)
    read = await repository.get_by_id(
        tenant_id="tenant-alpha",
        acceptance_id="acceptance-lifecycle",
    )
    reconciled = await repository.reconcile_expired(
        tenant_id="tenant-alpha",
        acceptance_id="acceptance-lifecycle",
    )
    assert read is not None
    assert read["record_status"] == "available"
    assert reconciled == 1

    revoke_connection = _LifecyclePgConnection()
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPgPool(revoke_connection),
    )
    repository = AcceptanceRecordRepository(require_postgres=True)
    revoked = await repository.revoke(
        tenant_id="tenant-alpha",
        acceptance_id="acceptance-lifecycle",
        reviewer_key_id="revoker-pg",
    )
    replayed_revoke = await repository.revoke(
        tenant_id="tenant-alpha",
        acceptance_id="acceptance-lifecycle",
        reviewer_key_id="revoker-pg-late",
    )
    assert revoked["record_status"] == "revoked"
    assert replayed_revoke == revoked

    consume_connection = _LifecyclePgConnection()
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPgPool(consume_connection),
    )
    repository = AcceptanceRecordRepository(require_postgres=True)
    consumed = await repository.consume(
        **_consume_kwargs(
            "acceptance-lifecycle",
            consumer_resource_id="delivery-pg",
        )
    )
    with pytest.raises(AcceptanceNotAvailableError):
        await repository.consume(
            **_consume_kwargs(
                "acceptance-lifecycle",
                consumer_resource_id="delivery-pg-late",
            )
        )
    assert consumed["record_status"] == "consumed"

    lifecycle_calls = (
        reconcile_connection.calls
        + revoke_connection.calls
        + consume_connection.calls
    )
    reconcile_sql = next(
        call[1]
        for call in lifecycle_calls
        if call[0] == "fetch" and "record_status = 'expired'" in call[1]
    )
    revoke_sql = next(
        call[1]
        for call in lifecycle_calls
        if call[0] == "fetchrow" and "record_status = 'revoked'" in call[1]
    )
    consume_sql = next(
        call[1]
        for call in lifecycle_calls
        if call[0] == "fetchrow" and "record_status = 'consumed'" in call[1]
    )
    assert "expires_at <= NOW()" in reconcile_sql
    assert "record_status = 'available'" in reconcile_sql
    assert "expires_at > NOW()" in revoke_sql
    assert "record_status = 'available'" in revoke_sql
    assert "expires_at > NOW()" in consume_sql
    assert "artifact_path = $3" in consume_sql
    assert "artifact_sha256 = $4" in consume_sql
    assert "RETURNING *" in consume_sql
