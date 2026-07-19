"""W1-25 receipt schema and atomic publish-attempt persistence contracts."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.models.publish_attempt import PublishReceiptV1
from src.storage import db as db_module

TENANT_ID = "tenant-receipt"
ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"


def _receipt(**overrides: object) -> PublishReceiptV1:
    data: dict[str, object] = {
        "schema_version": "publish-receipt.v1",
        "platform": "tiktok",
        "protocol_version": "tiktok-content-posting-v2",
        "completion_scope": "tiktok_direct_post",
        "provider_operation_id": "v_pub_file_receipt_123",
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
    }
    data.update(overrides)
    return PublishReceiptV1.model_validate(data)


def _partial_receipt() -> PublishReceiptV1:
    return _receipt(
        provider_resource_id=None,
        provider_status="PROCESSING_UPLOAD",
        post_id=None,
        post_url=None,
        public_visibility_verified=False,
        verified_by=None,
    )


def _consumed_content() -> dict[str, object]:
    return {
        "schema_version": "publish-attempt.v1",
        "route_kind": "canonical",
        "source": {
            "resource_type": "scenario",
            "resource_id": "s2_receipt_fixture",
            "scenario": "s2",
        },
        "artifact": {
            "path": (
                f"tenants/{TENANT_ID}/pending_review/s2_receipt_fixture/"
                "assemble/final.mp4"
            ),
            "sha256": "a" * 64,
            "size_bytes": 20,
            "kind": "video",
        },
        "metadata": {"title": "Reviewed"},
    }


def _install_sqlite(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_pg_available", False)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)


@pytest.fixture
def receipt_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        str(tmp_path / "publish-receipts.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    _install_sqlite(connection, monkeypatch)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


def test_receipt_migration_is_additive_reversible_and_chained() -> None:
    path = Path(
        "migrations/alembic/versions/"
        "a6b7c8d9e0f1_add_publish_receipt.py"
    )
    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "a6b7c8d9e0f1"' in source
    assert 'down_revision: str | None = "f9a2b3c4d5e6"' in source
    assert "JSONB" in source
    assert "idx_publish_logs_tenant_platform_post_receipt" in source
    assert "receipt IS NOT NULL" in source
    assert "post_id IS NOT NULL" in source

    spec = importlib.util.spec_from_file_location("w125_receipt_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class RecordingOp:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def add_column(self, table: str, column: Any) -> None:
            self.calls.append(("add_column", table, column))

        def execute(self, sql: str) -> None:
            self.calls.append(("execute", " ".join(sql.split())))

        def drop_index(self, name: str, *, table_name: str) -> None:
            self.calls.append(("drop_index", name, table_name))

        def drop_column(self, table: str, column: str) -> None:
            self.calls.append(("drop_column", table, column))

    recorder = RecordingOp()
    module.op = recorder
    module.upgrade()
    add_column = next(call for call in recorder.calls if call[0] == "add_column")
    assert add_column[1] == "publish_logs"
    assert add_column[2].name == "receipt"
    assert add_column[2].nullable is True
    assert "JSONB" in str(add_column[2].type)
    assert any(
        call[0] == "execute"
        and "idx_publish_logs_tenant_platform_post_receipt" in call[1]
        for call in recorder.calls
    )

    recorder.calls.clear()
    module.downgrade()
    assert recorder.calls == [
        (
            "drop_index",
            "idx_publish_logs_tenant_platform_post_receipt",
            "publish_logs",
        ),
        ("drop_column", "publish_logs", "receipt"),
    ]


def test_sqlite_fresh_schema_has_receipt_and_partial_index(
    receipt_db: sqlite3.Connection,
) -> None:
    columns = {
        row["name"]
        for row in receipt_db.execute("PRAGMA table_info(publish_logs)").fetchall()
    }
    indexes = {
        row["name"]
        for row in receipt_db.execute("PRAGMA index_list(publish_logs)").fetchall()
    }
    assert "receipt" in columns
    assert "idx_publish_logs_tenant_platform_post_receipt" in indexes


def test_sqlite_compat_backfills_nullable_receipt_without_rewriting_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = sqlite3.connect(
        str(tmp_path / "legacy-publish-receipt.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE publish_logs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            tenant_id TEXT,
            acceptance_id TEXT,
            post_id TEXT,
            content TEXT DEFAULT '{}',
            status TEXT,
            url TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    connection.execute(
        """
        INSERT INTO publish_logs (
            id, platform, tenant_id, acceptance_id, post_id, content,
            status, url, updated_at
        ) VALUES (?, 'tiktok', ?, ?, 'legacy-post', ?, 'published',
                  'https://legacy.invalid/post', CURRENT_TIMESTAMP)
        """,
        (
            "91ec3593-cc3c-42bf-99ee-c98655c5826b",
            TENANT_ID,
            ACCEPTANCE_ID,
            json.dumps(
                {
                    "schema_version": "publish-attempt.v1",
                    "route_kind": "canonical",
                    "metadata": {},
                    "source": _consumed_content()["source"],
                    "artifact": _consumed_content()["artifact"],
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
        ),
    )
    connection.commit()
    _install_sqlite(connection, monkeypatch)

    db_module._create_sqlite_tables()

    row = connection.execute("SELECT * FROM publish_logs").fetchone()
    assert row["receipt"] is None
    assert row["post_id"] == "legacy-post"
    connection.close()


@pytest.mark.asyncio
async def test_new_published_transition_requires_matching_receipt_atomically(
    receipt_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed"},
    )
    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(),
    )
    assert consumed is not None

    with pytest.raises(ValueError, match="receipt"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="acceptance_consumed",
            new_status="published",
            post_id="7512345678901234567",
        )

    receipt = _receipt()
    published = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="acceptance_consumed",
        new_status="published",
        receipt=receipt,
        post_id=receipt.post_id,
        url=receipt.post_url,
    )

    assert published is not None
    assert published["status"] == "published"
    assert published["receipt"] == receipt.model_dump(mode="json")
    stored = receipt_db.execute(
        "SELECT status, receipt, post_id, url, error FROM publish_logs WHERE id = ?",
        (prepared["id"],),
    ).fetchone()
    assert stored["status"] == "published"
    assert stored["receipt"] == receipt.canonical_json()
    assert stored["post_id"] == receipt.post_id
    assert stored["url"] == receipt.post_url
    assert stored["error"] is None


@pytest.mark.asyncio
async def test_failed_and_ambiguous_can_store_safe_partial_receipt(
    receipt_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    for status, error_code in (
        ("failed", "publish_connector_failed"),
        ("ambiguous", "publish_outcome_ambiguous"),
    ):
        prepared = await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={"title": "Reviewed"},
        )
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=_consumed_content(),
        )
        result = await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="acceptance_consumed",
            new_status=status,
            error_code=error_code,
            receipt=_partial_receipt(),
        )
        assert result is not None
        assert result["receipt"]["provider_status"] == "PROCESSING_UPLOAD"
        assert result["post_id"] is None
        assert result["url"] is None


@pytest.mark.asyncio
async def test_historical_null_receipt_is_readable_but_malformed_is_not(
    receipt_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    repository = PublishAttemptRepository(require_postgres=False)
    content = repository._encode_content(_consumed_content(), tenant_id=TENANT_ID)
    legacy_id = "91ec3593-cc3c-42bf-99ee-c98655c5826b"
    receipt_db.execute(
        """
        INSERT INTO publish_logs (
            id, platform, tenant_id, acceptance_id, content, status,
            created_at, updated_at
        ) VALUES (?, 'tiktok', ?, ?, ?, 'published',
                  CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (legacy_id, TENANT_ID, ACCEPTANCE_ID, content),
    )
    receipt_db.commit()

    legacy = await repository.get_by_id(tenant_id=TENANT_ID, attempt_id=legacy_id)
    assert legacy is not None
    assert legacy["receipt"] is None

    receipt_db.execute(
        "UPDATE publish_logs SET receipt = ? WHERE id = ?",
        ('{"simulated":false}', legacy_id),
    )
    receipt_db.commit()
    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.get_by_id(tenant_id=TENANT_ID, attempt_id=legacy_id)
