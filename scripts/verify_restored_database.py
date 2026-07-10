#!/usr/bin/env python3
"""Verify exact row-count parity after an isolated logical restore."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

TABLES_TO_VERIFY = [
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


async def verify_restored_database(stats_path: Path) -> dict[str, object]:
    from src.storage.db import get_pool

    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    table_stats = stats.get("tables")
    if not isinstance(table_stats, dict) or set(table_stats) != set(TABLES_TO_VERIFY):
        raise ValueError("backup stats table set does not match restore contract")
    expected = {
        table: int(table_stats[table].get("rows", -1))
        for table in TABLES_TO_VERIFY
    }
    if any(count < 0 for count in expected.values()):
        raise ValueError("backup stats contain an invalid row count")

    pool = await get_pool()
    actual: dict[str, int] = {}
    async with pool.acquire() as conn:
        for table in TABLES_TO_VERIFY:
            actual[table] = int(await conn.fetchval(f'SELECT count(*) FROM "{table}"'))

    if actual != expected:
        raise ValueError("restored table counts do not match backup stats")
    total_rows = sum(actual.values())
    if total_rows != stats.get("total_rows"):
        raise ValueError("restored total row count does not match backup stats")

    return {
        "status": "passed",
        "table_count": len(TABLES_TO_VERIFY),
        "total_rows": total_rows,
        "actual_counts": actual,
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
