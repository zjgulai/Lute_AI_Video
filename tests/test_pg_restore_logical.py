from __future__ import annotations

import importlib.util
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID

import pytest

from src.storage import db

REPO_ROOT = Path(__file__).resolve().parents[1]
RESTORE_SCRIPT = REPO_ROOT / "scripts" / "pg_restore_logical.py"
DUMP_SCRIPT = REPO_ROOT / "scripts" / "pg_dump_logical.py"
INIT_SQL = REPO_ROOT / "src" / "storage" / "migrations" / "001_init.sql"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_restored_database.py"


def _load_script_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_restore_module() -> ModuleType:
    return _load_script_module("pg_restore_logical", RESTORE_SCRIPT)


def test_restore_coerces_uuid_and_timestamp_values() -> None:
    restore = _load_restore_module()

    identifier = "12345678-1234-5678-1234-567812345678"
    assert restore._coerce_value(identifier, "uuid") == UUID(identifier)

    naive = restore._coerce_value("2026-07-10T03:04:05", "timestamp without time zone")
    assert naive == datetime(2026, 7, 10, 3, 4, 5)
    assert naive.tzinfo is None

    aware = restore._coerce_value(
        "2026-07-10T11:04:05+08:00",
        "timestamp with time zone",
    )
    assert aware == datetime(2026, 7, 10, 3, 4, 5, tzinfo=UTC)
    assert aware.tzinfo is UTC

    assert restore._coerce_value("plain text", "text") == "plain text"
    assert restore._coerce_value(None, "uuid") is None


def test_restore_rejects_unsafe_table_names(tmp_path: Path) -> None:
    restore = _load_restore_module()
    dump = tmp_path / "dump.jsonl"
    dump.write_text(
        json.dumps({"_table": "unexpected;drop", "_data": {"id": "1"}}) + "\n"
    )

    with pytest.raises(ValueError, match="invalid database identifier"):
        restore._load_rows(dump)


def test_logical_backup_discovers_current_schema_instead_of_fixed_table_set() -> None:
    dump = _load_script_module("pg_dump_logical", DUMP_SCRIPT)
    restore = _load_restore_module()

    assert not hasattr(dump, "TABLES_TO_DUMP")
    assert not hasattr(restore, "TABLES_TO_RESTORE")
    assert "information_schema.tables" in DUMP_SCRIPT.read_text()
    assert "information_schema.tables" in RESTORE_SCRIPT.read_text()
    init_sql = INIT_SQL.read_text()
    assert "CREATE TABLE IF NOT EXISTS audit_logs" in init_sql
    assert "idx_audit_ts" in init_sql
    assert "idx_audit_actor" in init_sql
    assert "idx_audit_action" in init_sql
    assert "idx_audit_resource" in init_sql


@pytest.mark.asyncio
async def test_dump_discovers_every_public_business_table_in_fk_safe_order() -> None:
    dump = _load_script_module("pg_dump_logical_discovery", DUMP_SCRIPT)

    class FakeConnection:
        async def fetch(self, query: str, *_args: object) -> list[dict[str, str]]:
            if "information_schema.tables" in query:
                return [
                    {"table_name": "children"},
                    {"table_name": "parents"},
                ]
            if "pg_catalog.pg_constraint" in query:
                return [
                    {"child_table": "children", "parent_table": "parents"},
                    {"child_table": "children", "parent_table": "parents"},
                ]
            raise AssertionError(query)

    assert await dump._discover_tables(FakeConnection()) == ["parents", "children"]


@pytest.mark.asyncio
async def test_dump_rejects_cyclic_foreign_key_table_graph() -> None:
    dump = _load_script_module("pg_dump_logical_cycle", DUMP_SCRIPT)

    class FakeConnection:
        async def fetch(self, query: str, *_args: object) -> list[dict[str, str]]:
            if "information_schema.tables" in query:
                return [{"table_name": "a"}, {"table_name": "b"}]
            if "pg_catalog.pg_constraint" in query:
                return [
                    {"child_table": "a", "parent_table": "b"},
                    {"child_table": "b", "parent_table": "a"},
                ]
            raise AssertionError(query)

    with pytest.raises(RuntimeError, match="foreign-key cycle"):
        await dump._discover_tables(FakeConnection())


@pytest.mark.asyncio
async def test_restore_discovers_public_tables_in_fk_safe_order() -> None:
    restore = _load_restore_module()

    class FakeConnection:
        async def fetch(self, query: str, *_args: object) -> list[dict[str, str]]:
            if "information_schema.tables" in query:
                return [
                    {"table_name": "children"},
                    {"table_name": "parents"},
                ]
            if "pg_catalog.pg_constraint" in query:
                return [
                    {"child_table": "children", "parent_table": "parents"},
                    {"child_table": "children", "parent_table": "parents"},
                ]
            raise AssertionError(query)

    assert await restore._discover_tables(FakeConnection()) == [
        "parents",
        "children",
    ]


@pytest.mark.parametrize("module_path", [DUMP_SCRIPT, RESTORE_SCRIPT])
def test_dynamic_table_order_rejects_unknown_edges_and_duplicate_tables(
    module_path: Path,
) -> None:
    module = _load_script_module(f"dynamic_order_{module_path.stem}", module_path)

    with pytest.raises(RuntimeError, match="undiscovered"):
        module._validated_table_order(["a"], [("a", "missing")])
    with pytest.raises(RuntimeError, match="duplicate"):
        module._validated_table_order(["a", "a"], [])


@pytest.mark.asyncio
async def test_logical_dump_reports_postgres_server_major(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dump = _load_script_module("pg_dump_logical_server_version", DUMP_SCRIPT)

    class FakeTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakeConnection:
        def transaction(self, **_kwargs: object) -> FakeTransaction:
            return FakeTransaction()

        async def fetchval(self, query: str, *_args: object) -> object:
            if "server_version_num" in query:
                return "180004"
            return True

        async def fetch(self, query: str, *_args: object) -> list[dict[str, object]]:
            if "information_schema.tables" in query:
                return [{"table_name": "threads"}]
            if "pg_catalog.pg_constraint" in query:
                return []
            if "SELECT version_num FROM alembic_version" in query:
                return [{"version_num": "c8d9e0f1a2b3"}]
            if "information_schema.columns" in query:
                return [
                    {
                        "table_name": "threads",
                        "column_name": "id",
                        "ordinal_position": 1,
                        "data_type": "text",
                        "udt_name": "text",
                        "is_nullable": "NO",
                    }
                ]
            return []

    class AcquireContext:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakePool:
        def acquire(self) -> AcquireContext:
            return AcquireContext()

    async def fake_get_pool() -> FakePool:
        return FakePool()

    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    stats = await dump.dump_to_jsonl(tmp_path / "dump.jsonl")

    assert stats["server_version_num"] == "180004"
    assert stats["server_major"] == 18
    assert re.fullmatch(r"[0-9a-f]{64}", stats["schema_signature"])
    assert stats["alembic_revision"] == "c8d9e0f1a2b3"


@pytest.mark.asyncio
async def test_restore_uses_one_transaction_and_coerces_insert_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restore = _load_restore_module()
    identifier = "12345678-1234-5678-1234-567812345678"
    dump = tmp_path / "dump.jsonl"
    dump.write_text(
        json.dumps(
            {
                "_table": "threads",
                "_data": {
                    "id": identifier,
                    "created_at": "2026-07-10T03:04:05",
                },
            }
        )
        + "\n"
    )

    class FakeTransaction:
        entered = False
        exited = False

        async def __aenter__(self) -> None:
            self.entered = True

        async def __aexit__(self, *_args: object) -> None:
            self.exited = True

    class FakeConnection:
        def __init__(self) -> None:
            self.transaction_context = FakeTransaction()
            self.executions: list[tuple[str, tuple[object, ...]]] = []

        def transaction(self) -> FakeTransaction:
            return self.transaction_context

        async def fetch(self, query: str, *args: object) -> list[dict[str, str]]:
            if "information_schema.tables" in query:
                return [{"table_name": "threads"}]
            if "pg_catalog.pg_constraint" in query:
                return []
            assert args == ("threads",)
            return [
                {"column_name": "id", "data_type": "uuid"},
                {
                    "column_name": "created_at",
                    "data_type": "timestamp without time zone",
                },
            ]

        async def execute(self, query: str, *args: object) -> None:
            self.executions.append((query, args))

    class AcquireContext:
        def __init__(self, connection: FakeConnection) -> None:
            self.connection = connection

        async def __aenter__(self) -> FakeConnection:
            return self.connection

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakePool:
        def __init__(self, connection: FakeConnection) -> None:
            self.connection = connection

        def acquire(self) -> AcquireContext:
            return AcquireContext(self.connection)

    connection = FakeConnection()

    async def fake_get_pool() -> FakePool:
        return FakePool(connection)

    monkeypatch.setattr(db, "get_pool", fake_get_pool)

    stats = await restore.restore(dump, truncate=True)

    assert connection.transaction_context.entered is True
    assert connection.transaction_context.exited is True
    assert connection.executions[0][0].startswith("TRUNCATE TABLE")
    insert_query, insert_args = connection.executions[1]
    assert 'INSERT INTO "threads"' in insert_query
    assert insert_args == (UUID(identifier), datetime(2026, 7, 10, 3, 4, 5))
    assert stats["tables"]["threads"] == {"available": 1, "inserted": 1}


@pytest.mark.asyncio
async def test_restore_rejects_valid_but_absent_schema_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restore = _load_restore_module()
    dump = tmp_path / "dump.jsonl"
    dump.write_text(
        json.dumps({"_table": "not_in_restored_schema", "_data": {"id": "1"}})
        + "\n"
    )

    class FakeTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakeConnection:
        def transaction(self) -> FakeTransaction:
            return FakeTransaction()

        async def fetch(self, query: str, *_args: object) -> list[dict[str, str]]:
            if "information_schema.tables" in query:
                return [{"table_name": "tenants"}]
            if "pg_catalog.pg_constraint" in query:
                return []
            raise AssertionError(query)

    class AcquireContext:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakePool:
        def acquire(self) -> AcquireContext:
            return AcquireContext()

    async def fake_get_pool() -> FakePool:
        return FakePool()

    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    with pytest.raises(ValueError, match="absent from restored schema"):
        await restore.restore(dump)


@pytest.mark.asyncio
async def test_verify_restored_database_requires_exact_table_count_parity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verifier = _load_script_module("verify_restored_database", VERIFY_SCRIPT)
    expected_tables = ["tenants", "legacy_jobs"]
    expected = {"tenants": {"rows": 1}, "legacy_jobs": {"rows": 0}}
    stats_path = tmp_path / "pg_dump_stats.json"
    stats_path.write_text(
        json.dumps(
            {
                "expected_tables": expected_tables,
                "tables": expected,
                "total_rows": 1,
                "alembic_revision": "c8d9e0f1a2b3",
            }
        )
        + "\n"
    )

    class FakeConnection:
        async def fetchval(self, query: str) -> int:
            return 1 if '"tenants"' in query else 0

        async def fetch(self, query: str) -> list[dict[str, str]]:
            assert query == "SELECT version_num FROM alembic_version"
            return [{"version_num": "c8d9e0f1a2b3"}]

    class AcquireContext:
        async def __aenter__(self) -> FakeConnection:
            return FakeConnection()

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FakePool:
        def acquire(self) -> AcquireContext:
            return AcquireContext()

    async def fake_get_pool() -> FakePool:
        return FakePool()

    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    result = await verifier.verify_restored_database(stats_path)

    assert result["status"] == "passed"
    assert result["table_count"] == 2
    assert result["total_rows"] == 1
    assert result["actual_counts"] == {"tenants": 1, "legacy_jobs": 0}
    assert result["alembic_revision"] == "c8d9e0f1a2b3"


def test_restore_requires_valid_alembic_revision_in_stats(tmp_path: Path) -> None:
    restore = _load_restore_module()
    stats = tmp_path / "stats.json"
    stats.write_text(json.dumps({"alembic_revision": "unsafe revision"}))

    with pytest.raises(ValueError, match="invalid Alembic revision"):
        restore._load_alembic_revision(stats)
