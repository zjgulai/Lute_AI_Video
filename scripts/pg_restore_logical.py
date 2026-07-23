#!/usr/bin/env python3
"""Restore an AI Video logical JSONL backup into initialized PostgreSQL."""

from __future__ import annotations

import asyncio
import heapq
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID

sys.path.insert(0, "/app")

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALEMBIC_REVISION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError("invalid database identifier in backup")
    return f'"{identifier}"'


def _load_rows(in_path: Path) -> dict[str, list[dict[str, object]]]:
    by_table: dict[str, list[dict[str, object]]] = {}
    with in_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"invalid backup record at line {line_number}")

            table = record.get("_table")
            data = record.get("_data")
            if not isinstance(table, str):
                raise ValueError(f"invalid backup table at line {line_number}")
            _quote_identifier(table)
            if not isinstance(data, dict) or not data:
                raise ValueError(f"invalid row payload at line {line_number}")
            for column in data:
                if not isinstance(column, str):
                    raise ValueError(f"invalid backup column at line {line_number}")
                _quote_identifier(column)
            by_table.setdefault(table, []).append(cast(dict[str, object], data))
    return by_table


def _validated_table_order(
    tables: list[str],
    foreign_keys: list[tuple[str, str]],
) -> list[str]:
    if not tables:
        raise RuntimeError("restored schema has no public business tables")
    if len(tables) != len(set(tables)):
        raise RuntimeError("restored schema contains duplicate public tables")
    for table in tables:
        _quote_identifier(table)

    table_set = set(tables)
    children: dict[str, set[str]] = {table: set() for table in tables}
    indegree = {table: 0 for table in tables}
    for child, parent in foreign_keys:
        if child == parent:
            continue
        if child not in table_set or parent not in table_set:
            raise RuntimeError("foreign key references an undiscovered public table")
        if child not in children[parent]:
            children[parent].add(child)
            indegree[child] += 1

    ready = [table for table, degree in indegree.items() if degree == 0]
    heapq.heapify(ready)
    ordered: list[str] = []
    while ready:
        table = heapq.heappop(ready)
        ordered.append(table)
        for child in sorted(children[table]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(ready, child)
    if len(ordered) != len(tables):
        raise RuntimeError("restored table foreign-key cycle prevents safe insert ordering")
    return ordered


async def _discover_tables(conn: Any) -> list[str]:
    table_rows = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND table_name <> 'alembic_version'
        ORDER BY table_name
        """
    )
    foreign_key_rows = await conn.fetch(
        """
        SELECT child.relname AS child_table,
               parent.relname AS parent_table
        FROM pg_catalog.pg_constraint AS constraint_row
        JOIN pg_catalog.pg_class AS child
          ON child.oid = constraint_row.conrelid
        JOIN pg_catalog.pg_namespace AS child_namespace
          ON child_namespace.oid = child.relnamespace
        JOIN pg_catalog.pg_class AS parent
          ON parent.oid = constraint_row.confrelid
        JOIN pg_catalog.pg_namespace AS parent_namespace
          ON parent_namespace.oid = parent.relnamespace
        WHERE constraint_row.contype = 'f'
          AND child_namespace.nspname = 'public'
          AND parent_namespace.nspname = 'public'
        ORDER BY child_table, parent_table
        """
    )
    return _validated_table_order(
        [str(row["table_name"]) for row in table_rows],
        [
            (str(row["child_table"]), str(row["parent_table"]))
            for row in foreign_key_rows
            if row["child_table"] != "alembic_version"
            and row["parent_table"] != "alembic_version"
        ],
    )


def _load_restore_contract(
    stats_path: Path,
    by_table: dict[str, list[dict[str, object]]],
) -> tuple[list[str], str]:
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    expected_tables = stats.get("expected_tables")
    if (
        not isinstance(expected_tables, list)
        or not expected_tables
        or len(expected_tables) != len(set(expected_tables))
        or any(
            not isinstance(table, str) or not IDENTIFIER_RE.fullmatch(table)
            for table in expected_tables
        )
    ):
        raise ValueError("backup stats expected table set is invalid")
    table_stats = stats.get("tables")
    if not isinstance(table_stats, dict) or set(table_stats) != set(expected_tables):
        raise ValueError("backup stats table set does not match restore contract")

    expected_counts: dict[str, int] = {}
    for table in expected_tables:
        result = table_stats.get(table)
        if not isinstance(result, dict):
            raise ValueError("backup stats contain invalid table results")
        count = result.get("rows")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("backup stats contain an invalid row count")
        expected_counts[table] = count

    if set(by_table) - set(expected_tables):
        raise ValueError("backup dump contains a table outside backup stats")
    actual_counts = {table: len(by_table.get(table, [])) for table in expected_tables}
    if actual_counts != expected_counts:
        raise ValueError("backup dump row counts do not match backup stats")
    total_rows = stats.get("total_rows")
    if (
        isinstance(total_rows, bool)
        or not isinstance(total_rows, int)
        or total_rows != sum(expected_counts.values())
    ):
        raise ValueError("backup stats total row count is invalid")

    revision = stats.get("alembic_revision")
    if not isinstance(revision, str) or not ALEMBIC_REVISION_RE.fullmatch(revision):
        raise ValueError("backup stats contain an invalid Alembic revision")
    return expected_tables, revision


def _coerce_value(value: object, data_type: str) -> object:
    """Convert JSON-safe dump values back to asyncpg-native scalar types."""
    if value is None:
        return None
    if data_type == "uuid" and not isinstance(value, UUID):
        return UUID(str(value))
    if data_type not in {"timestamp without time zone", "timestamp with time zone"}:
        return value
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if data_type == "timestamp without time zone":
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(UTC).replace(tzinfo=None)
        return parsed
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def _column_types(conn: Any, table: str) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {row["column_name"]: row["data_type"] for row in rows}


async def restore(
    in_path: Path,
    stats_path: Path,
    truncate: bool = False,
) -> dict[str, Any]:
    from src.storage.db import get_pool

    by_table = _load_rows(in_path)
    restore_tables, alembic_revision = _load_restore_contract(stats_path, by_table)
    pool = await get_pool()
    if pool is None:
        raise RuntimeError("PostgreSQL pool is unavailable")
    stats: dict[str, Any] = {"tables": {}}

    async with pool.acquire() as conn:
        async with conn.transaction():
            tables = await _discover_tables(conn)
            if set(tables) != set(restore_tables):
                raise ValueError("restore target table set does not match backup stats")
            current_revisions = await conn.fetch(
                "SELECT version_num FROM alembic_version"
            )
            if current_revisions:
                raise ValueError("restore target Alembic revision is not empty")
            await conn.execute(
                "INSERT INTO alembic_version (version_num) VALUES ($1)",
                alembic_revision,
            )
            if truncate:
                table_list = ", ".join(
                    _quote_identifier(table) for table in reversed(tables)
                )
                await conn.execute(f"TRUNCATE TABLE {table_list} CASCADE")

            for table in tables:
                rows = by_table.get(table, [])
                inserted = 0
                column_types = await _column_types(conn, table) if rows else {}
                for row in rows:
                    columns = list(row)
                    unknown_columns = set(columns) - column_types.keys()
                    if unknown_columns:
                        raise ValueError(f"unknown column in backup table {table}")
                    placeholders = ", ".join(
                        f"${index + 1}" for index in range(len(columns))
                    )
                    column_list = ", ".join(
                        _quote_identifier(column) for column in columns
                    )
                    await conn.execute(
                        f"INSERT INTO {_quote_identifier(table)} "
                        f"({column_list}) VALUES ({placeholders})",
                        *(
                            _coerce_value(row[column], column_types[column])
                            for column in columns
                        ),
                    )
                    inserted += 1
                stats["tables"][table] = {
                    "available": len(rows),
                    "inserted": inserted,
                }

    return stats


async def main() -> int:
    args = sys.argv[1:]
    truncate = "--truncate-first" in args
    if "--stats" not in args:
        print("ERROR: --stats is required", file=sys.stderr)
        return 1
    stats_index = args.index("--stats")
    if stats_index + 1 >= len(args):
        print("ERROR: --stats requires a path", file=sys.stderr)
        return 1
    stats_path = Path(args[stats_index + 1])
    del args[stats_index : stats_index + 2]
    positional = [arg for arg in args if not arg.startswith("--")]
    if not positional:
        print(
            "Usage: pg_restore_logical.py <dump.jsonl> --stats <stats.json> "
            "[--truncate-first]",
            file=sys.stderr,
        )
        return 1

    in_path = Path(positional[0])
    if not in_path.is_file():
        print("ERROR: backup file not found", file=sys.stderr)
        return 1

    print(
        f"Restoring logical backup (truncate_first={truncate})...",
        file=sys.stderr,
    )
    try:
        stats = await restore(in_path, truncate=truncate, stats_path=stats_path)
    except Exception as exc:
        print(f"ERROR: restore failed ({type(exc).__name__})", file=sys.stderr)
        return 1

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
