#!/usr/bin/env python3
"""Verify exact row-count parity after an isolated logical restore."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app")

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALEMBIC_REVISION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


async def verify_restored_database(stats_path: Path) -> dict[str, object]:
    from src.storage.db import get_pool

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
    expected: dict[str, int] = {}
    for table in expected_tables:
        result = table_stats.get(table)
        if not isinstance(result, dict) or set(result) != {"rows"}:
            raise ValueError("backup stats contain an invalid row count")
        count = result["rows"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("backup stats contain an invalid row count")
        expected[table] = count
    expected_total = stats.get("total_rows")
    if (
        isinstance(expected_total, bool)
        or not isinstance(expected_total, int)
        or expected_total < 0
        or expected_total != sum(expected.values())
    ):
        raise ValueError("backup stats contain an invalid total row count")
    expected_revision = stats.get("alembic_revision")
    if not isinstance(expected_revision, str) or not ALEMBIC_REVISION_RE.fullmatch(
        expected_revision
    ):
        raise ValueError("backup stats contain an invalid Alembic revision")

    pool = await get_pool()
    if pool is None:
        raise RuntimeError("PostgreSQL pool is unavailable")
    actual: dict[str, int] = {}
    async with pool.acquire() as conn:
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
        restored_tables = [str(row["table_name"]) for row in table_rows]
        if (
            len(restored_tables) != len(set(restored_tables))
            or any(not IDENTIFIER_RE.fullmatch(table) for table in restored_tables)
            or set(restored_tables) != set(expected_tables)
        ):
            raise ValueError("restored database table set does not match backup stats")
        for table in expected_tables:
            count = await conn.fetchval(f'SELECT count(*) FROM "{table}"')
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("restored database returned an invalid row count")
            actual[table] = count
        revision_rows = await conn.fetch("SELECT version_num FROM alembic_version")

    if len(revision_rows) != 1 or revision_rows[0]["version_num"] != expected_revision:
        raise ValueError("restored Alembic revision does not match backup stats")

    if actual != expected:
        raise ValueError("restored table counts do not match backup stats")
    total_rows = sum(actual.values())
    if total_rows != expected_total:
        raise ValueError("restored total row count does not match backup stats")

    return {
        "status": "passed",
        "table_count": len(expected_tables),
        "total_rows": total_rows,
        "actual_counts": actual,
        "alembic_revision": expected_revision,
    }


async def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: verify_restored_database.py <pg_dump_stats.json>", file=sys.stderr)
        return 1
    try:
        result = await verify_restored_database(Path(sys.argv[1]))
    except Exception as exc:
        print(f"ERROR: restore verification failed ({type(exc).__name__})", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
