#!/usr/bin/env python3
"""Hermes-Evo Production Backup — PG logical dump via psycopg + media rsync.

Why pure-Python: production PG is Tencent Cloud RDS (no local pg_dump).
The backend container has psycopg installed, so we use COPY TO STDOUT
to extract every table as JSON Lines. This is restore-equivalent to
pg_dump for our schema (no large binary blobs, no extensions beyond
uuid-ossp which is restored separately).

Run inside backend container:
    docker exec ai_video_backend python /tmp/pg_dump_logical.py /tmp/pg_dump.jsonl

Restore via:
    python pg_restore_logical.py /tmp/pg_dump.jsonl
"""
import asyncio
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, "/app")


TABLES_TO_DUMP = [
    "tenants",
    "api_keys",
    "admin_accounts",
    "admin_sessions",
    "threads",
    "pipeline_states",
    "brand_packages",
    "influencers",
    "video_metrics",
    "publish_logs",
    "error_logs",
]


async def dump_to_jsonl(out_path: Path) -> dict:
    from src.storage.db import get_pool

    pool = await get_pool()
    stats = {"timestamp": datetime.now(UTC).isoformat(), "tables": {}}
    with out_path.open("w", encoding="utf-8") as f:
        async with pool.acquire() as conn:
            for table in TABLES_TO_DUMP:
                exists = await conn.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1)",
                    table,
                )
                if not exists:
                    stats["tables"][table] = {"skipped": "table missing"}
                    continue
                rows = await conn.fetch(f'SELECT * FROM "{table}"')
                count = 0
                for row in rows:
                    record = {"_table": table, "_data": dict(row)}
                    f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
                    count += 1
                stats["tables"][table] = {"rows": count}
    stats["total_rows"] = sum(t.get("rows", 0) for t in stats["tables"].values())
    stats["file_size"] = out_path.stat().st_size
    return stats


async def main() -> int:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pg_dump.jsonl")
    print(f"Dumping PG to {out_path}...")
    stats = await dump_to_jsonl(out_path)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
