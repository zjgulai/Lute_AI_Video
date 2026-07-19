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
import heapq
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, "/app")


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ALEMBIC_REVISION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def _validated_table_order(
    tables: list[str],
    foreign_keys: list[tuple[str, str]],
) -> list[str]:
    if not tables:
        raise RuntimeError("no public business tables were discovered")
    if len(tables) != len(set(tables)):
        raise RuntimeError("duplicate public table discovered")
    if any(not IDENTIFIER_RE.fullmatch(table) for table in tables):
        raise RuntimeError("unsafe public table identifier discovered")

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
        raise RuntimeError("public table foreign-key cycle prevents safe restore ordering")
    return ordered


async def _discover_tables(conn: object) -> list[str]:
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


async def _read_alembic_revision(conn: object) -> str:
    rows = await conn.fetch("SELECT version_num FROM alembic_version")
    if len(rows) != 1:
        raise RuntimeError("alembic_version must contain exactly one revision row")
    revision = rows[0]["version_num"]
    if not isinstance(revision, str) or not ALEMBIC_REVISION_RE.fullmatch(revision):
        raise RuntimeError("alembic_version contains an invalid revision")
    return revision


async def _schema_signature(conn: object, tables: list[str]) -> str:
    rows = await conn.fetch(
        """
        SELECT table_name, column_name, ordinal_position, data_type, udt_name,
               is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = ANY($1::text[])
        ORDER BY table_name, ordinal_position
        """,
        tables,
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
    stats: dict[str, object] = {"timestamp": datetime.now(UTC).isoformat()}
    with out_path.open("w", encoding="utf-8") as f:
        async with pool.acquire() as conn:
            server_version_num = str(await conn.fetchval("SHOW server_version_num"))
            if not server_version_num.isdigit():
                raise RuntimeError("PostgreSQL server_version_num is invalid")
            stats["server_version_num"] = server_version_num
            stats["server_major"] = int(server_version_num) // 10000
            async with conn.transaction(isolation="repeatable_read", readonly=True):
                tables = await _discover_tables(conn)
                stats["expected_tables"] = tables
                stats["tables"] = {}
                stats["alembic_revision"] = await _read_alembic_revision(conn)
                stats["schema_signature"] = await _schema_signature(conn, tables)
                for table in tables:
                    rows = await conn.fetch(f'SELECT * FROM "{table}"')
                    count = 0
                    for row in rows:
                        record = {"_table": table, "_data": dict(row)}
                        f.write(json.dumps(record, default=str, ensure_ascii=False) + "\n")
                        count += 1
                    stats["tables"][table] = {"rows": count}
    table_stats = stats["tables"]
    assert isinstance(table_stats, dict)
    stats["total_rows"] = sum(t.get("rows", 0) for t in table_stats.values())
    stats["file_size"] = out_path.stat().st_size
    return stats


async def schema_signature_only() -> dict[str, str]:
    from src.storage.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction(isolation="repeatable_read", readonly=True):
            tables = await _discover_tables(conn)
            signature = await _schema_signature(conn, tables)
            revision = await _read_alembic_revision(conn)
    return {"schema_signature": signature, "alembic_revision": revision}


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
