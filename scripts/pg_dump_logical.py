#!/usr/bin/env python3
"""Hermes-Evo Production Backup — PG logical dump via psycopg + media rsync.

Why pure-Python: production PG is Tencent Cloud RDS and the backend image has
no pg_dump client, so data rows are extracted as JSON Lines through asyncpg.
The host backup wrapper separately captures the exact production schema with
a matching-major official PostgreSQL client image.

Run inside backend container:
    docker exec ai_video_backend python /tmp/pg_dump_logical.py /tmp/pg_dump.jsonl

Restore only after applying the matching backup `pg_schema.dump`; the JSONL
file is data-only and is not a standalone recovery artifact.
"""
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/app")


TABLES_TO_DUMP = [
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


async def _schema_signature(conn: object) -> str:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, ordinal_position, data_type, udt_name,
               is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY($1::text[])
        ORDER BY table_name, ordinal_position
        """,
        TABLES_TO_DUMP,
    )
    payload = [dict(row) for row in rows]
    serialized = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


async def dump_to_jsonl(out_path: Path) -> dict:
    from src.storage.db import get_pool

    pool = await get_pool()
    stats = {
        "timestamp": datetime.now(UTC).isoformat(),
        "expected_tables": TABLES_TO_DUMP,
        "tables": {},
    }
    with out_path.open("w", encoding="utf-8") as f:
        async with pool.acquire() as conn:
            server_version_num = str(await conn.fetchval("SHOW server_version_num"))
            if not server_version_num.isdigit():
                raise RuntimeError("PostgreSQL server_version_num is invalid")
            stats["server_version_num"] = server_version_num
            stats["server_major"] = int(server_version_num) // 10000
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                stats["schema_signature"] = await _schema_signature(conn)
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


async def schema_signature_only() -> dict[str, str]:
    from src.storage.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            signature = await _schema_signature(conn)
    return {"schema_signature": signature}


async def main() -> int:
    if sys.argv[1:] == ["--schema-signature"]:
        print(json.dumps(await schema_signature_only(), sort_keys=True))
        return 0

    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/pg_dump.jsonl")
    print(f"Dumping PG to {out_path}...", file=sys.stderr)
    stats = await dump_to_jsonl(out_path)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
