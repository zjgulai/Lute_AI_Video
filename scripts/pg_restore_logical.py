#!/usr/bin/env python3
"""Restore an AI Video logical JSONL backup into initialized PostgreSQL."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, "/app")

TABLES_TO_RESTORE = [
    "tenants",
    "admin_accounts",
    "api_keys",
    "admin_sessions",
    "threads",
    "pipeline_states",
    "brand_packages",
    "influencers",
    "video_metrics",
    "publish_logs",
    "error_logs",
    "audit_logs",
]
ALLOWED_TABLES = frozenset(TABLES_TO_RESTORE)
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(identifier: str) -> str:
    if not IDENTIFIER_RE.fullmatch(identifier):
        raise ValueError("invalid database identifier in backup")
    return f'"{identifier}"'


def _load_rows(in_path: Path) -> dict[str, list[dict]]:
    by_table: dict[str, list[dict]] = defaultdict(list)
    with in_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError(f"invalid backup record at line {line_number}")

            table = record.get("_table")
            data = record.get("_data")
            if table not in ALLOWED_TABLES:
                raise ValueError(f"unknown table in backup at line {line_number}")
            if not isinstance(data, dict) or not data:
                raise ValueError(f"invalid row payload at line {line_number}")
            for column in data:
                _quote_identifier(column)
            by_table[table].append(data)
    return by_table


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


async def _column_types(conn: object, table: str) -> dict[str, str]:
    rows = await conn.fetch(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {row["column_name"]: row["data_type"] for row in rows}


async def restore(in_path: Path, truncate: bool = False) -> dict:
    from src.storage.db import get_pool

    by_table = _load_rows(in_path)
    pool = await get_pool()
    stats: dict = {"tables": {}}

    async with pool.acquire() as conn:
        async with conn.transaction():
            if truncate:
                table_list = ", ".join(
                    _quote_identifier(table) for table in TABLES_TO_RESTORE
                )
                await conn.execute(f"TRUNCATE TABLE {table_list} CASCADE")

            for table in TABLES_TO_RESTORE:
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
    positional = [arg for arg in args if not arg.startswith("--")]
    if not positional:
        print(
            "Usage: pg_restore_logical.py <dump.jsonl> [--truncate-first]",
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
        stats = await restore(in_path, truncate=truncate)
    except Exception as exc:
        print(f"ERROR: restore failed ({type(exc).__name__})", file=sys.stderr)
        return 1

    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
