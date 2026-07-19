"""W1-23 publish-attempt schema and atomic repository contracts.

All database execution in this module is isolated SQLite or a SQL-recording
fake.  No production database, connector, provider, or external service is
contacted.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from src.models.publish_attempt import PublishReceiptV1
from src.storage import db as db_module

ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
TENANT_ID = "tenant-alpha"
LEGAL_TRANSITIONS = {
    ("prepared", "authorization_failed"),
    ("prepared", "preflight_failed"),
    ("prepared", "acceptance_consumed"),
    ("acceptance_consumed", "published"),
    ("acceptance_consumed", "failed"),
    ("acceptance_consumed", "ambiguous"),
}
ALL_STATUSES = {
    "prepared",
    "authorization_failed",
    "preflight_failed",
    "acceptance_consumed",
    "published",
    "failed",
    "ambiguous",
}


def _install_sqlite_connection(
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
def sqlite_publish_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        str(tmp_path / "publish-attempts.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    _install_sqlite_connection(connection, monkeypatch)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA index_list({table})").fetchall()}


def _consumed_content(
    *,
    tenant_id: str = TENANT_ID,
    resource_type: str = "scenario",
    resource_id: str = "s2_fixture",
    scenario: str = "s2",
    artifact_path: str | None = None,
    artifact_sha256: str = "a" * 64,
    artifact_size: object = 20,
    artifact_kind: str = "video",
) -> dict[str, Any]:
    if artifact_path is None:
        if resource_type == "fast":
            artifact_path = f"tenants/{tenant_id}/pending_review/fast_mode/{resource_id}/assemble/final.mp4"
        else:
            artifact_path = f"tenants/{tenant_id}/pending_review/{resource_id}/assemble/final.mp4"
    return {
        "schema_version": "publish-attempt.v1",
        "route_kind": "canonical",
        "source": {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "scenario": scenario,
        },
        "artifact": {
            "path": artifact_path,
            "sha256": artifact_sha256,
            "size_bytes": artifact_size,
            "kind": artifact_kind,
        },
        "metadata": {"title": "Reviewed campaign"},
    }


def _tiktok_receipt() -> PublishReceiptV1:
    return PublishReceiptV1.model_validate(
        {
            "schema_version": "publish-receipt.v1",
            "platform": "tiktok",
            "protocol_version": "tiktok-content-posting-v2",
            "completion_scope": "tiktok_direct_post",
            "provider_operation_id": "v_pub_file_fixture_123",
            "provider_resource_id": "7512345678901234567",
            "target_id": None,
            "provider_status": "PUBLISH_COMPLETE",
            "post_id": "7512345678901234567",
            "post_url": ("https://www.tiktok.com/@fixture/video/7512345678901234567"),
            "public_visibility_verified": True,
            "observed_at": "2026-07-14T08:00:00Z",
            "verified_by": "video_query",
            "simulated": False,
        }
    )


def _shopify_receipt() -> PublishReceiptV1:
    return PublishReceiptV1.model_validate(
        {
            "schema_version": "publish-receipt.v1",
            "platform": "shopify",
            "protocol_version": "shopify-admin-2026-07",
            "completion_scope": "shopify_product_media",
            "provider_operation_id": None,
            "provider_resource_id": "gid://shopify/Video/7512345678901234567",
            "target_id": "gid://shopify/Product/1234567890",
            "provider_status": "READY",
            "post_id": None,
            "post_url": None,
            "public_visibility_verified": False,
            "observed_at": "2026-07-14T08:00:00Z",
            "verified_by": "file_query_and_product_readback",
            "simulated": False,
        }
    )


def test_sqlite_publish_logs_has_attempt_columns_and_indexes(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    assert {"tenant_id", "acceptance_id", "updated_at"} <= _table_columns(
        sqlite_publish_db,
        "publish_logs",
    )
    assert {
        "idx_publish_logs_tenant_created_at",
        "idx_publish_logs_tenant_acceptance",
    } <= _table_indexes(sqlite_publish_db, "publish_logs")


@pytest.mark.parametrize("include_tenant", [True, False])
def test_sqlite_compatibility_preserves_legacy_publish_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    include_tenant: bool,
) -> None:
    connection = sqlite3.connect(
        str(tmp_path / f"legacy-{include_tenant}.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    tenant_column = "tenant_id TEXT," if include_tenant else ""
    connection.execute(
        f"""
        CREATE TABLE publish_logs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            {tenant_column}
            post_id TEXT,
            content TEXT DEFAULT '{{}}',
            status TEXT,
            url TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    insert_columns = "id, platform, tenant_id, content, status" if include_tenant else ("id, platform, content, status")
    placeholders = "?, ?, ?, ?, ?" if include_tenant else "?, ?, ?, ?"
    values: tuple[Any, ...] = (
        ("legacy-row", "legacy-platform", "legacy-tenant", '{"legacy":true}', "done")
        if include_tenant
        else ("legacy-row", "legacy-platform", '{"legacy":true}', "done")
    )
    connection.execute(
        f"INSERT INTO publish_logs ({insert_columns}) VALUES ({placeholders})",
        values,
    )
    connection.commit()
    _install_sqlite_connection(connection, monkeypatch)

    db_module._create_sqlite_tables()

    row = connection.execute("SELECT * FROM publish_logs WHERE id = 'legacy-row'").fetchone()
    assert row is not None
    assert row["platform"] == "legacy-platform"
    assert row["content"] == '{"legacy":true}'
    assert row["status"] == "done"
    assert row["tenant_id"] == ("legacy-tenant" if include_tenant else None)
    assert row["acceptance_id"] is None
    assert row["updated_at"] is None
    assert {
        "idx_publish_logs_tenant_created_at",
        "idx_publish_logs_tenant_acceptance",
    } <= _table_indexes(connection, "publish_logs")
    connection.close()


def test_migration_is_additive_reversible_and_has_only_approved_indexes() -> None:
    path = Path("migrations/alembic/versions/f9a2b3c4d5e6_add_publish_acceptance_fields.py")
    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert 'revision: str = "f9a2b3c4d5e6"' in source
    assert 'down_revision: str | None = "e8f1a2b3c4d5"' in source
    assert "status" not in source
    assert "CHECK" not in source.upper()

    spec = importlib.util.spec_from_file_location("w123_publish_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class RecordingOp:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Any]] = []

        def add_column(self, table: str, column: Any) -> None:
            self.calls.append(("add_column", table, column))

        def execute(self, sql: str) -> None:
            self.calls.append(("execute", " ".join(sql.split())))

        def create_index(self, name: str, table: str, columns: list[str]) -> None:
            self.calls.append(("create_index", name, table, tuple(columns)))

        def drop_index(self, name: str, *, table_name: str) -> None:
            self.calls.append(("drop_index", name, table_name))

        def drop_column(self, table: str, column: str) -> None:
            self.calls.append(("drop_column", table, column))

    recorder = RecordingOp()
    module.op = recorder
    module.upgrade()
    add_columns = [call for call in recorder.calls if call[0] == "add_column"]
    assert [(call[1], call[2].name, call[2].nullable) for call in add_columns] == [
        ("publish_logs", "tenant_id", True),
        ("publish_logs", "acceptance_id", True),
        ("publish_logs", "updated_at", True),
    ]
    assert "VARCHAR(64)" in str(add_columns[0][2].type)
    assert "VARCHAR(36)" in str(add_columns[1][2].type)
    assert getattr(add_columns[2][2].type, "timezone") is True
    assert (
        "execute",
        "CREATE INDEX idx_publish_logs_tenant_created_at ON publish_logs(tenant_id, created_at DESC)",
    ) in recorder.calls
    assert (
        "create_index",
        "idx_publish_logs_tenant_acceptance",
        "publish_logs",
        ("tenant_id", "acceptance_id"),
    ) in recorder.calls

    recorder.calls.clear()
    module.downgrade()
    assert recorder.calls == [
        ("drop_index", "idx_publish_logs_tenant_acceptance", "publish_logs"),
        ("drop_index", "idx_publish_logs_tenant_created_at", "publish_logs"),
        ("drop_column", "publish_logs", "updated_at"),
        ("drop_column", "publish_logs", "acceptance_id"),
        ("drop_column", "publish_logs", "tenant_id"),
    ]


def test_fresh_postgres_schema_has_additive_reused_volume_parity() -> None:
    source = Path("src/storage/migrations/001_init.sql").read_text(encoding="utf-8")
    table_block = source.split("CREATE TABLE IF NOT EXISTS publish_logs (", 1)[1].split(
        ");",
        1,
    )[0]
    assert "tenant_id VARCHAR(64)" in table_block
    assert "acceptance_id VARCHAR(36)" in table_block
    assert "updated_at TIMESTAMPTZ" in table_block
    assert "video_id" not in table_block
    assert "scenario" not in table_block
    assert "published_at" not in table_block
    for clause in (
        "ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);",
        "ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS acceptance_id VARCHAR(36);",
        "ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;",
        "CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_created_at",
        "CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_acceptance",
    ):
        assert clause in source


@pytest.mark.asyncio
async def test_repository_enforces_one_way_tenant_bound_lifecycle(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    attempt_id = prepared["id"]
    assert prepared["status"] == "prepared"
    assert prepared["content"]["route_kind"] == "canonical"
    assert "artifact" not in prepared["content"]

    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(),
    )
    assert consumed is not None
    assert consumed["status"] == "acceptance_consumed"
    assert consumed["content"]["artifact"]["kind"] == "video"

    published = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        expected_status="acceptance_consumed",
        new_status="published",
        post_id=_tiktok_receipt().post_id,
        url=_tiktok_receipt().post_url,
        receipt=_tiktok_receipt(),
    )
    assert published is not None
    assert published["status"] == "published"
    assert published["post_id"] == _tiktok_receipt().post_id

    assert (
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=attempt_id,
            expected_status="acceptance_consumed",
            new_status="failed",
            error_code="publish_connector_failed",
        )
        is None
    )
    assert (
        await repository.get_by_id(
            tenant_id="tenant-beta",
            attempt_id=attempt_id,
        )
        is None
    )


def _transition_projection(new_status: str) -> dict[str, Any]:
    if new_status == "authorization_failed":
        return {"error_code": "acceptance_not_available"}
    if new_status == "acceptance_consumed":
        return {"content": _consumed_content()}
    if new_status == "preflight_failed":
        return {"error_code": "publish_preflight_rejected"}
    if new_status == "published":
        return {
            "post_id": _shopify_receipt().post_id,
            "url": _shopify_receipt().post_url,
            "receipt": _shopify_receipt(),
        }
    if new_status == "failed":
        return {"error_code": "publish_connector_failed"}
    if new_status == "ambiguous":
        return {"error_code": "publish_outcome_ambiguous"}
    raise AssertionError(new_status)


@pytest.mark.asyncio
@pytest.mark.parametrize(("expected_status", "new_status"), sorted(LEGAL_TRANSITIONS))
async def test_every_legal_transition_is_supported(
    sqlite_publish_db: sqlite3.Connection,
    expected_status: str,
    new_status: str,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="shopify",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    if expected_status == "acceptance_consumed":
        advanced = await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=_consumed_content(),
        )
        assert advanced is not None

    result = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status=expected_status,
        new_status=new_status,
        **_transition_projection(new_status),
    )
    assert result is not None
    assert result["status"] == new_status


ILLEGAL_TRANSITIONS = sorted(
    (old, new) for old in ALL_STATUSES for new in ALL_STATUSES if (old, new) not in LEGAL_TRANSITIONS
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("expected_status", "new_status"), ILLEGAL_TRANSITIONS)
async def test_every_illegal_transition_is_rejected(
    sqlite_publish_db: sqlite3.Connection,
    expected_status: str,
    new_status: str,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError, match="transition"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id="91ec3593-cc3c-42bf-99ee-c98655c5826b",
            expected_status=expected_status,
            new_status=new_status,
            **(_transition_projection(new_status) if new_status != "prepared" else {}),
        )


@pytest.mark.asyncio
async def test_tenant_and_expected_status_are_both_compare_and_set_guards(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    kwargs = {
        "attempt_id": prepared["id"],
        "expected_status": "prepared",
        "new_status": "authorization_failed",
        "error_code": "acceptance_not_available",
    }
    assert await repository.transition(tenant_id="tenant-beta", **kwargs) is None
    first = await repository.transition(tenant_id=TENANT_ID, **kwargs)
    assert first is not None
    assert await repository.transition(tenant_id=TENANT_ID, **kwargs) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("acceptance_id", "not-a-uuid"),
        ("acceptance_id", "7F947625-2898-4E9E-9E71-DCE4309E5F4F"),
        ("acceptance_id", "22d75de0-1e5d-11ef-9262-0242ac120002"),
        ("platform", "TikTok"),
        ("platform", "youtube"),
        ("route_kind", "legacy"),
        ("tenant_id", ""),
        ("tenant_id", "x" * 65),
    ],
)
async def test_create_rejects_malformed_authority_inputs(
    sqlite_publish_db: sqlite3.Connection,
    field: str,
    value: str,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    values = {
        "tenant_id": TENANT_ID,
        "acceptance_id": ACCEPTANCE_ID,
        "platform": "tiktok",
        "route_kind": "canonical",
        "metadata": {},
    }
    values[field] = value
    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError):
        await repository.create_prepared(**values)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "content",
    [
        {**_consumed_content(), "unknown": True},
        {key: value for key, value in _consumed_content().items() if key != "artifact"},
        {key: value for key, value in _consumed_content().items() if key != "source"},
        _consumed_content(artifact_path="/tmp/secret/final.mp4"),
        _consumed_content(artifact_path=("tenants/tenant-alpha/pending_review/s2_fixture/../secret/final.mp4")),
        _consumed_content(artifact_path=("tenants/tenant-beta/pending_review/s2_fixture/assemble/final.mp4")),
        _consumed_content(artifact_path=("tenants/tenant-alpha/pending_review/s2_fixture/assemble/final.mov")),
        _consumed_content(artifact_sha256="A" * 64),
        _consumed_content(artifact_size=0),
        _consumed_content(artifact_size=True),
        _consumed_content(artifact_size=20.5),
        _consumed_content(artifact_kind="image"),
        _consumed_content(resource_type="fast", scenario="s2"),
        _consumed_content(resource_type="scenario", scenario="fast"),
        _consumed_content(resource_id="bad/resource"),
    ],
)
async def test_repository_rejects_unsafe_or_noncanonical_content(
    sqlite_publish_db: sqlite3.Connection,
    content: Mapping[str, Any],
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    with pytest.raises(ValueError, match="content|artifact|source"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=content,
        )


@pytest.mark.asyncio
async def test_repository_rejects_non_json_and_content_above_32_kib(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError, match="content"):
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={"title": object()},
        )
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    oversized = _consumed_content(
        artifact_path=("tenants/tenant-alpha/pending_review/s2_fixture/assemble/" + ("a" * (33 * 1024)) + ".mp4")
    )
    with pytest.raises(ValueError, match="32 KiB"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=oversized,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [None, []])
async def test_create_rejects_non_mapping_metadata_as_value_error(
    sqlite_publish_db: sqlite3.Connection,
    metadata: object,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError, match="metadata"):
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata=metadata,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_transition_requires_safe_state_specific_projection(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    base = {
        "tenant_id": TENANT_ID,
        "attempt_id": prepared["id"],
        "expected_status": "prepared",
    }
    with pytest.raises(ValueError):
        await repository.transition(
            **base,
            new_status="acceptance_consumed",
            content=None,
        )
    with pytest.raises(ValueError):
        await repository.transition(
            **base,
            new_status="authorization_failed",
            error_code=RuntimeError("raw secret error"),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_terminal_content_cannot_replace_consumed_authority_projection(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(),
    )
    assert consumed is not None

    with pytest.raises(ValueError, match="content"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="acceptance_consumed",
            new_status="failed",
            content={
                "schema_version": "publish-attempt.v1",
                "route_kind": "canonical",
                "metadata": {},
            },
            error_code="publish_connector_failed",
        )

    current = await repository.get_by_id(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
    )
    assert current is not None
    assert current["status"] == "acceptance_consumed"
    assert current["content"]["artifact"]["kind"] == "video"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("new_status", "expected_status", "error_code", "content"),
    [
        (
            "authorization_failed",
            "prepared",
            "acceptance_not_available",
            {
                "schema_version": "publish-attempt.v1",
                "route_kind": "canonical",
                "metadata": {},
            },
        ),
        ("published", "acceptance_consumed", None, _consumed_content()),
        (
            "failed",
            "acceptance_consumed",
            "publish_connector_failed",
            _consumed_content(),
        ),
        (
            "ambiguous",
            "acceptance_consumed",
            "publish_outcome_ambiguous",
            _consumed_content(),
        ),
    ],
)
async def test_only_acceptance_consumed_transition_accepts_content(
    sqlite_publish_db: sqlite3.Connection,
    new_status: str,
    expected_status: str,
    error_code: str | None,
    content: Mapping[str, Any],
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError, match="content"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id="91ec3593-cc3c-42bf-99ee-c98655c5826b",
            expected_status=expected_status,
            new_status=new_status,
            content=content,
            error_code=error_code,
        )


@pytest.mark.asyncio
async def test_acceptance_consumed_preserves_prepared_route_and_metadata(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Original title"},
    )
    mismatched = _consumed_content(resource_id="s2_original")
    mismatched["route_kind"] = "legacy_adapter"
    mismatched["metadata"] = {"title": "Replacement title"}

    with pytest.raises(ValueError, match="prepared|authority|content"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="acceptance_consumed",
            content=mismatched,
        )

    current = await repository.get_by_id(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
    )
    assert current is not None
    assert current["status"] == "prepared"
    assert current["content"]["route_kind"] == "canonical"
    assert current["content"]["metadata"]["title"] == "Original title"


@pytest.mark.asyncio
async def test_terminal_attempt_cannot_replace_s2_original_authority(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(resource_id="s2_original"),
    )
    assert consumed is not None

    with pytest.raises(ValueError, match="content"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="acceptance_consumed",
            new_status="failed",
            content=_consumed_content(resource_id="s2_replaced"),
            error_code="publish_connector_failed",
        )

    current = await repository.get_by_id(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
    )
    assert current is not None
    assert current["status"] == "acceptance_consumed"
    assert current["content"]["source"]["resource_id"] == "s2_original"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("new_status", "expected_status", "error_code"),
    [
        ("authorization_failed", "prepared", "publish_connector_failed"),
        ("authorization_failed", "prepared", "publish_connector_not_ready"),
        ("authorization_failed", "prepared", "publish_attempt_store_unavailable"),
        ("authorization_failed", "prepared", "publish_attempt_state_unknown"),
        ("authorization_failed", "prepared", "publish_preflight_rejected"),
        (
            "authorization_failed",
            "prepared",
            "publish_connector_not_ready_after_consume",
        ),
        ("failed", "acceptance_consumed", "acceptance_not_available"),
        ("failed", "acceptance_consumed", "publish_outcome_ambiguous"),
        ("failed", "acceptance_consumed", "publish_preflight_unavailable"),
        ("preflight_failed", "prepared", "acceptance_not_available"),
        ("preflight_failed", "prepared", "publish_connector_failed"),
        ("ambiguous", "acceptance_consumed", "publish_connector_failed"),
        ("ambiguous", "acceptance_consumed", "publish_connector_simulated"),
        ("ambiguous", "acceptance_consumed", "publish_attempt_state_unknown"),
    ],
)
async def test_error_codes_are_bound_to_exact_terminal_state(
    sqlite_publish_db: sqlite3.Connection,
    new_status: str,
    expected_status: str,
    error_code: str,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError, match="error code"):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id="91ec3593-cc3c-42bf-99ee-c98655c5826b",
            expected_status=expected_status,
            new_status=new_status,
            error_code=error_code,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_code",
    [
        "publish_connector_not_ready_after_consume",
        "publish_connector_simulated",
    ],
)
async def test_new_connector_truth_codes_are_valid_only_for_failed_state(
    sqlite_publish_db: sqlite3.Connection,
    error_code: str,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(),
    )
    assert consumed is not None
    failed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="acceptance_consumed",
        new_status="failed",
        error_code=error_code,
    )
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error"] == error_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("post_id", "url"),
    [
        ("post\nunsafe", None),
        ("x" * 257, None),
        (None, "file:///tmp/final.mp4"),
        (None, "https://user:password@example.invalid/post"),
        (None, "https://example.invalid/post?token=secret"),
        (None, "https://example.invalid/post#secret"),
        (None, "https://example.invalid/bad path"),
    ],
)
async def test_repository_rejects_unsafe_success_identifiers_and_urls(
    sqlite_publish_db: sqlite3.Connection,
    post_id: str | None,
    url: str | None,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(ValueError):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id="91ec3593-cc3c-42bf-99ee-c98655c5826b",
            expected_status="acceptance_consumed",
            new_status="published",
            post_id=post_id,
            url=url,
        )


@pytest.mark.asyncio
async def test_error_column_stores_only_the_stable_code(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    failed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="authorization_failed",
        error_code="acceptance_not_available",
    )
    assert failed is not None
    assert failed["error"] == "acceptance_not_available"
    stored = sqlite_publish_db.execute(
        "SELECT error FROM publish_logs WHERE id = ?",
        (prepared["id"],),
    ).fetchone()
    assert stored is not None
    assert stored["error"] == "acceptance_not_available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("content", "{"),
        ("acceptance_id", "not-a-uuid"),
        ("platform", "youtube"),
        ("status", "legacy-status"),
        ("updated_at", None),
    ],
)
async def test_corrupt_stored_rows_fail_closed_without_projection_leaks(
    sqlite_publish_db: sqlite3.Connection,
    column: str,
    value: object,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    sqlite_publish_db.execute(
        f"UPDATE publish_logs SET {column} = ? WHERE id = ?",
        (value, prepared["id"]),
    )
    sqlite_publish_db.commit()

    with pytest.raises(PublishAttemptStoreUnavailable) as exc_info:
        await repository.get_by_id(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
        )
    assert "JSONDecodeError" not in str(exc_info.value)
    assert "ValueError" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_semantically_valid_noncanonical_sqlite_json_is_corrupt(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    noncanonical = json.dumps(prepared["content"], ensure_ascii=False, indent=2)
    sqlite_publish_db.execute(
        "UPDATE publish_logs SET content = ? WHERE id = ?",
        (noncanonical, prepared["id"]),
    )
    sqlite_publish_db.commit()

    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.get_by_id(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("column", ["created_at", "updated_at"])
async def test_invalid_stored_timestamp_is_rejected(
    sqlite_publish_db: sqlite3.Connection,
    column: str,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    sqlite_publish_db.execute(
        f"UPDATE publish_logs SET {column} = ? WHERE id = ?",
        ("not-a-timestamp", prepared["id"]),
    )
    sqlite_publish_db.commit()

    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.get_by_id(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
        )


@pytest.mark.asyncio
async def test_corrupt_prepared_projection_rolls_back_transition(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    sqlite_publish_db.execute(
        "UPDATE publish_logs SET content = '{}' WHERE id = ?",
        (prepared["id"],),
    )
    sqlite_publish_db.commit()

    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="authorization_failed",
            error_code="acceptance_not_available",
        )

    row = sqlite_publish_db.execute(
        "SELECT status FROM publish_logs WHERE id = ?",
        (prepared["id"],),
    ).fetchone()
    assert row is not None
    assert row["status"] == "prepared"


@pytest.mark.asyncio
async def test_sqlite_insert_projection_failure_rolls_back_before_commit(
    sqlite_publish_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    def reject_projection(
        cls: type[PublishAttemptRepository],
        row: Mapping[str, Any],
        *,
        require_canonical_json_text: bool = False,
    ) -> dict[str, Any]:
        raise PublishAttemptStoreUnavailable

    monkeypatch.setattr(
        PublishAttemptRepository,
        "_normalize_record",
        classmethod(reject_projection),
    )
    repository = PublishAttemptRepository(require_postgres=False)
    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )
    assert sqlite_publish_db.execute("SELECT COUNT(*) FROM publish_logs").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_sqlite_concurrent_compare_and_set_has_exactly_one_winner(
    sqlite_publish_db: sqlite3.Connection,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    repository = PublishAttemptRepository(require_postgres=False)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )

    async def transition_once() -> dict[str, Any] | None:
        return await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="authorization_failed",
            error_code="acceptance_not_available",
        )

    results = await asyncio.gather(transition_once(), transition_once())
    assert sum(result is not None for result in results) == 1


class _RecordingTransaction:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> None:
        self.connection.transaction_entries += 1
        self.connection.in_transaction = True

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.connection.transaction_exit_types.append(exc_type)
        self.connection.in_transaction = False


class _RecordingConnection:
    def __init__(
        self,
        *,
        zero_returning: bool = False,
        failure: Exception | None = None,
        corrupt_insert_projection: bool = False,
    ) -> None:
        self.zero_returning = zero_returning
        self.failure = failure
        self.corrupt_insert_projection = corrupt_insert_projection
        self.calls: list[tuple[str, tuple[Any, ...], bool]] = []
        self.transaction_entries = 0
        self.transaction_exit_types: list[type[BaseException] | None] = []
        self.in_transaction = False
        self.row: dict[str, Any] | None = None

    def transaction(self) -> _RecordingTransaction:
        return _RecordingTransaction(self)

    async def fetchrow(self, query: str, *args: Any) -> dict[str, Any] | None:
        normalized = " ".join(query.split())
        self.calls.append((normalized, args, self.in_transaction))
        if self.failure is not None:
            raise self.failure
        if normalized.startswith("INSERT INTO publish_logs"):
            self.row = {
                "id": args[0],
                "tenant_id": args[1],
                "acceptance_id": args[2],
                "platform": args[3],
                "post_id": None,
                "content": args[4],
                "status": "prepared",
                "url": None,
                "error": None,
                "created_at": "2026-07-13 00:00:00+00:00",
                "updated_at": ("not-a-timestamp" if self.corrupt_insert_projection else "2026-07-13 00:00:00+00:00"),
            }
            return dict(self.row)
        if normalized.startswith("UPDATE publish_logs"):
            if self.zero_returning:
                return None
            assert self.row is not None
            self.row.update(
                {
                    "status": args[3],
                    "content": args[4] if args[4] is not None else self.row["content"],
                    "post_id": args[5] if args[5] is not None else self.row["post_id"],
                    "url": args[6] if args[6] is not None else self.row["url"],
                    "error": args[7] if args[7] is not None else self.row["error"],
                    "updated_at": "2026-07-13 00:01:00+00:00",
                }
            )
            return dict(self.row)
        if normalized.startswith("SELECT * FROM publish_logs"):
            if "AND status = $3" in normalized and (self.row is None or self.row["status"] != args[2]):
                return None
            return dict(self.row) if self.row is not None else None
        raise AssertionError(f"unexpected SQL: {normalized}")


class _Acquire:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _RecordingConnection:
        return self.connection

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _RecordingPool:
    def __init__(self, connection: _RecordingConnection) -> None:
        self.connection = connection

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_production_repository_requires_verified_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    async def forbidden_fallback() -> None:
        raise AssertionError("production repository must not initialize fallback storage")

    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: None)
    monkeypatch.setattr(db_module, "get_pool", forbidden_fallback)
    repository = PublishAttemptRepository(require_postgres=True)

    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )


@pytest.mark.asyncio
async def test_postgres_acquire_oserror_is_sanitized_store_unavailable(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    class FailingAcquire:
        async def __aenter__(self) -> None:
            raise OSError("network-host-secret")

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            return None

    class FailingPool:
        def acquire(self) -> FailingAcquire:
            return FailingAcquire()

    monkeypatch.setattr(db_module, "get_verified_pg_pool", FailingPool)
    caplog.set_level(
        "WARNING",
        logger="src.storage.publish_attempt_repository",
    )
    repository = PublishAttemptRepository(require_postgres=True)

    with pytest.raises(PublishAttemptStoreUnavailable) as exc_info:
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )

    assert "network-host-secret" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    assert "OSError" in caplog.text
    assert "network-host-secret" not in caplog.text


@pytest.mark.asyncio
async def test_postgres_sql_is_tenant_bound_casted_transactional_and_database_timed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    connection = _RecordingConnection()
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPool(connection),
    )
    repository = PublishAttemptRepository(require_postgres=True)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={"title": "Reviewed campaign"},
    )
    fetched = await repository.get_by_id(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
    )
    assert fetched is not None
    consumed = await repository.transition(
        tenant_id=TENANT_ID,
        attempt_id=prepared["id"],
        expected_status="prepared",
        new_status="acceptance_consumed",
        content=_consumed_content(),
    )
    assert consumed is not None

    insert_sql, insert_args, insert_in_tx = connection.calls[0]
    assert "$1::uuid" in insert_sql
    assert "$5::jsonb" in insert_sql
    assert "NOW(), NOW()" in insert_sql
    assert insert_args[1:4] == (TENANT_ID, ACCEPTANCE_ID, "tiktok")
    assert insert_in_tx is True

    select_sql, select_args, select_in_tx = connection.calls[1]
    assert "WHERE tenant_id = $1 AND id = $2::uuid" in select_sql
    assert select_args == (TENANT_ID, prepared["id"])
    assert select_in_tx is True

    transition_select_sql, transition_select_args, transition_select_in_tx = connection.calls[2]
    assert "WHERE tenant_id = $1" in transition_select_sql
    assert "id = $2::uuid" in transition_select_sql
    assert "status = $3" in transition_select_sql
    assert "FOR UPDATE" in transition_select_sql
    assert transition_select_args == (TENANT_ID, prepared["id"], "prepared")
    assert transition_select_in_tx is True

    update_sql, update_args, update_in_tx = connection.calls[3]
    assert "content = COALESCE($5::jsonb, content)" in update_sql
    assert "updated_at = NOW()" in update_sql
    assert "WHERE tenant_id = $1" in update_sql
    assert "id = $2::uuid" in update_sql
    assert "status = $3" in update_sql
    assert update_args[:4] == (
        TENANT_ID,
        prepared["id"],
        "prepared",
        "acceptance_consumed",
    )
    assert update_in_tx is True
    assert connection.transaction_entries == 3


@pytest.mark.asyncio
async def test_postgres_zero_row_returning_is_a_stale_cas_not_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    connection = _RecordingConnection()
    pool = _RecordingPool(connection)
    monkeypatch.setattr(db_module, "get_verified_pg_pool", lambda: pool)
    repository = PublishAttemptRepository(require_postgres=True)
    prepared = await repository.create_prepared(
        tenant_id=TENANT_ID,
        acceptance_id=ACCEPTANCE_ID,
        platform="tiktok",
        route_kind="canonical",
        metadata={},
    )
    connection.zero_returning = True
    assert (
        await repository.transition(
            tenant_id=TENANT_ID,
            attempt_id=prepared["id"],
            expected_status="prepared",
            new_status="authorization_failed",
            error_code="acceptance_not_available",
        )
        is None
    )


@pytest.mark.asyncio
async def test_postgres_driver_and_corrupt_projection_failures_are_store_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    connection = _RecordingConnection(failure=ConnectionError("driver-host-secret"))
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPool(connection),
    )
    repository = PublishAttemptRepository(require_postgres=True)
    with pytest.raises(PublishAttemptStoreUnavailable) as exc_info:
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )
    assert "driver-host-secret" not in str(exc_info.value)

    connection.failure = None
    connection.row = {
        "id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
        "tenant_id": TENANT_ID,
        "acceptance_id": ACCEPTANCE_ID,
        "platform": "tiktok",
        "post_id": None,
        "content": "{",
        "status": "prepared",
        "url": None,
        "error": None,
        "created_at": "2026-07-13 00:00:00+00:00",
        "updated_at": "2026-07-13 00:00:00+00:00",
    }
    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.get_by_id(
            tenant_id=TENANT_ID,
            attempt_id=connection.row["id"],
        )


@pytest.mark.asyncio
async def test_postgres_programming_exception_is_not_mislabeled_store_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import PublishAttemptRepository

    class UnexpectedProgrammingError(Exception):
        pass

    connection = _RecordingConnection(failure=UnexpectedProgrammingError("sentinel"))
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPool(connection),
    )
    repository = PublishAttemptRepository(require_postgres=True)
    with pytest.raises(UnexpectedProgrammingError, match="sentinel"):
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )


@pytest.mark.asyncio
async def test_postgres_insert_projection_is_validated_before_transaction_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    connection = _RecordingConnection(corrupt_insert_projection=True)
    monkeypatch.setattr(
        db_module,
        "get_verified_pg_pool",
        lambda: _RecordingPool(connection),
    )
    repository = PublishAttemptRepository(require_postgres=True)
    with pytest.raises(PublishAttemptStoreUnavailable):
        await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )
    assert connection.transaction_exit_types == [PublishAttemptStoreUnavailable]


class _ColumnConnection:
    def __init__(self, missing: str | None = None) -> None:
        self.missing = missing
        self.table_checks: list[str] = []

    async def fetchval(self, query: str, table: str) -> bool:
        self.table_checks.append(table)
        return True

    async def fetch(self, query: str, table: str) -> list[dict[str, str]]:
        assert "information_schema.columns" in query
        columns = set(db_module._REQUIRED_TABLE_COLUMNS[table])
        if table == "publish_logs" and self.missing is not None:
            columns.remove(self.missing)
        return [{"column_name": column} for column in sorted(columns)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing",
    ["tenant_id", "acceptance_id", "updated_at", "receipt"],
)
async def test_pg_readiness_fails_when_publish_attempt_column_is_missing(
    missing: str,
) -> None:
    connection = _ColumnConnection(missing)
    assert await db_module._verify_pg_tables(connection) is False
    assert connection.table_checks == db_module._REQUIRED_TABLES
    assert len(db_module._REQUIRED_TABLES) == 10


@pytest.mark.asyncio
async def test_pg_readiness_accepts_complete_publish_attempt_columns() -> None:
    connection = _ColumnConnection()
    assert await db_module._verify_pg_tables(connection) is True
    assert connection.table_checks == db_module._REQUIRED_TABLES
    assert len(db_module._REQUIRED_TABLES) == 10


class _FailingSqliteConnection:
    def __init__(self, connection: sqlite3.Connection, fail_on: str) -> None:
        self.connection = connection
        self.fail_on = fail_on
        self.commits = 0
        self.rollbacks = 0

    def execute(self, query: str, args: Any = ()) -> Any:
        if self.fail_on in " ".join(query.split()):
            raise sqlite3.OperationalError("schema failure")
        return self.connection.execute(query, args)

    def commit(self) -> None:
        self.commits += 1
        self.connection.commit()

    def rollback(self) -> None:
        self.rollbacks += 1
        self.connection.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on", ["INSERT INTO publish_logs", "UPDATE publish_logs"])
async def test_sqlite_mutation_rolls_back_every_driver_exception(
    sqlite_publish_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    fail_on: str,
) -> None:
    from src.storage.publish_attempt_repository import (
        PublishAttemptRepository,
        PublishAttemptStoreUnavailable,
    )

    repository = PublishAttemptRepository(require_postgres=False)
    attempt: dict[str, Any] | None = None
    if fail_on.startswith("UPDATE"):
        attempt = await repository.create_prepared(
            tenant_id=TENANT_ID,
            acceptance_id=ACCEPTANCE_ID,
            platform="tiktok",
            route_kind="canonical",
            metadata={},
        )
    failing = _FailingSqliteConnection(sqlite_publish_db, fail_on)
    monkeypatch.setattr(db_module, "_sqlite_conn", failing)

    with pytest.raises(PublishAttemptStoreUnavailable):
        if attempt is None:
            await repository.create_prepared(
                tenant_id=TENANT_ID,
                acceptance_id=ACCEPTANCE_ID,
                platform="tiktok",
                route_kind="canonical",
                metadata={},
            )
        else:
            await repository.transition(
                tenant_id=TENANT_ID,
                attempt_id=attempt["id"],
                expected_status="prepared",
                new_status="authorization_failed",
                error_code="acceptance_not_available",
            )
    assert failing.commits == 0
    assert failing.rollbacks == 1
