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


def test_restore_rejects_unknown_tables(tmp_path: Path) -> None:
    restore = _load_restore_module()
    dump = tmp_path / "dump.jsonl"
    dump.write_text(
        json.dumps({"_table": "unexpected", "_data": {"id": "1"}}) + "\n"
    )

    with pytest.raises(ValueError, match="unknown table"):
        restore._load_rows(dump)


def test_fresh_postgres_init_covers_logical_backup_table_set() -> None:
    dump = _load_script_module("pg_dump_logical", DUMP_SCRIPT)
    restore = _load_restore_module()
    init_sql = INIT_SQL.read_text()
    initialized_tables = set(
        re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)", init_sql)
    )

    assert set(dump.TABLES_TO_DUMP) == set(restore.TABLES_TO_RESTORE)
    assert set(restore.TABLES_TO_RESTORE) <= initialized_tables
    assert "CREATE TABLE IF NOT EXISTS audit_logs" in init_sql
    assert "idx_audit_ts" in init_sql
    assert "idx_audit_actor" in init_sql
    assert "idx_audit_action" in init_sql
    assert "idx_audit_resource" in init_sql


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

        async def fetch(self, _query: str, table: str) -> list[dict[str, str]]:
            assert table == "threads"
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
    assert stats["tables"]["audit_logs"] == {"available": 0, "inserted": 0}
