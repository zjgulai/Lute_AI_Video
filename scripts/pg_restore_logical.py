#!/usr/bin/env python3
"""Hermes-Evo Production Restore — pair with pg_dump_logical.py.

Reads JSONL where each line is {"_table": str, "_data": dict} and INSERTs
back into the matching public.* table. Designed for **disaster recovery
into a freshly-initialized PG** (i.e. tables exist but are empty).

WARNING: by default appends rows. To replace, pass --truncate-first.
Run inside backend container with PG access:
    docker exec ai_video_backend python /tmp/pg_restore_logical.py /tmp/pg_dump.jsonl
"""
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/app")


async def restore(in_path: Path, truncate: bool = False) -> dict:
    from src.storage.db import get_pool

    by_table: dict[str, list[dict]] = defaultdict(list)
    with in_path.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            by_table[rec["_table"]].append(rec["_data"])

    pool = await get_pool()
    stats: dict = {"tables": {}}
    async with pool.acquire() as conn:
        for table, rows in by_table.items():
            if truncate:
                await conn.execute(f'TRUNCATE TABLE "{table}" CASCADE')
            inserted = 0
            for row in rows:
                cols = list(row.keys())
                placeholders = ", ".join(f"${i+1}" for i in range(len(cols)))
                col_list = ", ".join(f'"{c}"' for c in cols)
                try:
                    await conn.execute(
                        f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                        *row.values(),
                    )
                    inserted += 1
                except Exception as exc:
                    stats.setdefault("errors", []).append({"table": table, "error": str(exc)[:200]})
            stats["tables"][table] = {"available": len(rows), "inserted": inserted}
    return stats


async def main() -> int:
    args = sys.argv[1:]
    truncate = "--truncate-first" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        print("Usage: pg_restore_logical.py <dump.jsonl> [--truncate-first]")
        return 1
    in_path = Path(args[0])
    if not in_path.exists():
        print(f"ERROR: {in_path} not found")
        return 1
    print(f"Restoring {in_path} (truncate_first={truncate})...")
    stats = await restore(in_path, truncate=truncate)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
