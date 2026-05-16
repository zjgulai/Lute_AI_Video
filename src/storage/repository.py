"""Repository pattern for PostgreSQL with SQLite fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import asyncpg

from .db import get_pool, get_sqlite_conn

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with CRUD operations using asyncpg or SQLite fallback."""

    def __init__(self, table_name: str):
        self.table_name = table_name

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def _to_json(self, value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=self._json_default)
        if hasattr(value, "isoformat"):
            return json.dumps(value.isoformat())
        if isinstance(value, (bool, int, float, str)) or value is None:
            return value
        return json.dumps(value, default=self._json_default)

    @staticmethod
    def _json_default(obj: Any) -> str:
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return str(obj)

    def _from_json(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return value

    async def _fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        # SQLite fallback — run in thread pool to avoid blocking the event loop
        conn = get_sqlite_conn()
        if conn is None:
            return None

        def _sync_fetchrow():
            cursor = conn.execute(query, args)
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

        return await asyncio.to_thread(_sync_fetchrow)  # type: ignore[return-type]

    async def _fetch(self, query: str, *args) -> list[Any]:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                return await conn.fetch(query, *args)
        # SQLite fallback — run in thread pool to avoid blocking the event loop
        conn = get_sqlite_conn()
        if conn is None:
            return []

        def _sync_fetch():
            cursor = conn.execute(query, args)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        return await asyncio.to_thread(_sync_fetch)

    async def _execute(self, query: str, *args) -> None:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                await conn.execute(query, *args)
            return
        # SQLite fallback — run in thread pool to avoid blocking the event loop
        conn = get_sqlite_conn()
        if conn is not None:

            def _sync_execute():
                conn.execute(query, args)
                conn.commit()

            await asyncio.to_thread(_sync_execute)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        record_id = self._generate_id()
        data["id"] = record_id
        columns = list(data.keys())
        placeholders = [f"${i + 1}" for i in range(len(columns))]
        query = f"""
            INSERT INTO {self.table_name} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            RETURNING *
        """
        values = [self._to_json(v) for v in data.values()]
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *values)
                return dict(row)
        # SQLite fallback — run in thread pool to avoid blocking the event loop
        conn = get_sqlite_conn()
        if conn is not None:
            def _sync_create():
                placeholders_sql = ["?" for _ in columns]
                query_sql = f"""
                    INSERT INTO {self.table_name} ({', '.join(columns)})
                    VALUES ({', '.join(placeholders_sql)})
                """
                conn.execute(query_sql, values)
                conn.commit()
                cursor = conn.execute(
                    f"SELECT * FROM {self.table_name} WHERE id = ?", (record_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else data
            return await asyncio.to_thread(_sync_create)
        return data

    async def get_by_id(self, id: str) -> dict[str, Any] | None:
        query = f"SELECT * FROM {self.table_name} WHERE id = $1"
        row = await self._fetchrow(query, id)
        if row is None:
            return None
        result = dict(row)
        # Deserialize JSON columns
        for key in result:
            result[key] = self._from_json(result[key])
        return result

    # Allowed fields for each table — used by get_by_field() to validate
    # that WHERE-clause column names are safe. This is a defense-in-depth
    # measure on top of the parameterised queries that asyncpg provides.
    _ALLOWED_FIELDS: dict[str, set[str]] = {
        "threads": {"id", "thread_id", "state", "current_step", "pipeline_complete", "created_at", "updated_at"},
        "pipeline_states": {"id", "label", "scenario", "config", "steps", "current_step", "mode", "errors", "media_synthesis_errors", "gates", "schema_version", "pipeline_degraded", "degraded_reason", "trace_id", "structured_errors", "regenerate_chain", "created_at", "updated_at"},
        "brand_packages": {"id", "name", "brand_guidelines", "assets", "created_at", "updated_at"},
        "influencers": {"id", "name", "platform", "profile", "contact_info", "created_at", "updated_at"},
        "publish_logs": {"id", "platform", "post_id", "content", "status", "url", "error", "created_at"},
    }

    async def get_by_field(self, field: str, value: Any) -> dict[str, Any] | None:
        allowed = self._ALLOWED_FIELDS.get(self.table_name, set())
        if field not in allowed:
            raise ValueError(f"Invalid field name: {field!r}")
        query = f"SELECT * FROM {self.table_name} WHERE {field} = $1"
        row = await self._fetchrow(query, value)
        if row is None:
            return None
        result = dict(row)
        for key in result:
            result[key] = self._from_json(result[key])
        return result

    async def update(self, id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if not data:
            return await self.get_by_id(id)
        columns = list(data.keys())
        set_clause = ", ".join([f"{col} = ${i + 2}" for i, col in enumerate(columns)])
        query = f"""
            UPDATE {self.table_name}
            SET {set_clause}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        values = [id] + [self._to_json(v) for v in data.values()]
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *values)
                return dict(row) if row else None
        # SQLite fallback — run in thread pool to avoid blocking the event loop
        conn = get_sqlite_conn()
        if conn is not None:
            def _sync_update():
                set_clause_sql = ", ".join([f"{col} = ?" for col in columns])
                query_sql = f"""
                    UPDATE {self.table_name}
                    SET {set_clause_sql}, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """
                conn.execute(query_sql, [self._to_json(v) for v in data.values()] + [id])
                conn.commit()
            await asyncio.to_thread(_sync_update)
            return await self.get_by_id(id)
        return None

    async def delete(self, id: str) -> bool:
        query = f"DELETE FROM {self.table_name} WHERE id = $1"
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                result = await conn.execute(query, id)
                return "DELETE 1" in result
        # SQLite fallback — run in thread pool to avoid blocking the event loop
        conn = get_sqlite_conn()
        if conn is not None:
            def _sync_delete():
                cursor = conn.execute(f"DELETE FROM {self.table_name} WHERE id = ?", (id,))
                conn.commit()
                return cursor.rowcount > 0
            return await asyncio.to_thread(_sync_delete)
        return False

    async def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        query = f"SELECT * FROM {self.table_name} ORDER BY created_at DESC LIMIT $1"
        rows = await self._fetch(query, limit)
        results = []
        for row in rows:
            result = dict(row)
            for key in result:
                result[key] = self._from_json(result[key])
            results.append(result)
        return results


class ThreadRepository(BaseRepository):
    def __init__(self):
        super().__init__("threads")

    async def get_by_thread_id(self, thread_id: str) -> dict[str, Any] | None:
        return await self.get_by_field("thread_id", thread_id)


class PipelineStateRepository(BaseRepository):
    def __init__(self):
        super().__init__("pipeline_states")

    async def get_by_label(self, label: str) -> dict[str, Any] | None:
        return await self.get_by_field("label", label)


class BrandPackageRepository(BaseRepository):
    def __init__(self):
        super().__init__("brand_packages")


class InfluencerRepository(BaseRepository):
    def __init__(self):
        super().__init__("influencers")


class PublishLogRepository(BaseRepository):
    def __init__(self):
        super().__init__("publish_logs")
