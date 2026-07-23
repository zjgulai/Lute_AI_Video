"""Repository pattern for PostgreSQL with SQLite fallback."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

import asyncpg

from .db import get_pool, get_sqlite_conn, get_sqlite_lock

logger = logging.getLogger(__name__)
_PG_PARAM_RE = re.compile(r"\$(\d+)")


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

    def _to_sqlite_query(self, query: str, args: tuple[Any, ...]) -> tuple[str, tuple[Any, ...]]:
        ordered_args: list[Any] = []

        def _replace(match: re.Match[str]) -> str:
            index = int(match.group(1)) - 1
            ordered_args.append(args[index])
            return "?"

        query_sql = _PG_PARAM_RE.sub(_replace, query)
        return query_sql, tuple(ordered_args) if ordered_args else args

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
            with get_sqlite_lock():
                query_sql, args_sql = self._to_sqlite_query(query, args)
                cursor = conn.execute(query_sql, args_sql)
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
            with get_sqlite_lock():
                query_sql, args_sql = self._to_sqlite_query(query, args)
                cursor = conn.execute(query_sql, args_sql)
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
                with get_sqlite_lock():
                    query_sql, args_sql = self._to_sqlite_query(query, args)
                    conn.execute(query_sql, args_sql)
                    conn.commit()

            await asyncio.to_thread(_sync_execute)

    async def create(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("id"):
            data["id"] = self._generate_id()
        record_id = data["id"]
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
                with get_sqlite_lock():
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
        "pipeline_states": {"id", "label", "scenario", "config", "steps", "current_step", "mode", "errors", "media_synthesis_errors", "gates", "schema_version", "pipeline_degraded", "degraded_reason", "trace_id", "structured_errors", "regenerate_chain", "soft_degraded_reasons", "transparency", "tenant_id", "created_at", "updated_at"},
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
                with get_sqlite_lock():
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
                with get_sqlite_lock():
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

    async def update(
        self,
        id: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Keep the completion claim immutable across every state update."""

        return await self.update_preserving_pipeline_completion(id, data)

    async def update_preserving_pipeline_completion(
        self,
        id: str,
        data: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Update state without allowing a stale caller to delete its claim."""

        if not data:
            return await self.get_by_id(id)
        incoming_config = data.get("config")
        if type(incoming_config) is not dict:
            raise ValueError("pipeline completion config is invalid")
        claim_key = "pipeline_completion_metric_v1"
        columns = list(data)
        values: list[Any] = [id]
        assignments: list[str] = []
        for column in columns:
            values.append(self._to_json(data[column]))
            parameter = len(values)
            if column == "config":
                assignments.append(
                    "config = CASE "
                    f"WHEN COALESCE(config, '{{}}'::jsonb) ? '{claim_key}' "
                    f"THEN jsonb_set(${parameter}::jsonb, "
                    "'{pipeline_completion_metric_v1}', "
                    f"COALESCE(config, '{{}}'::jsonb) -> '{claim_key}', true) "
                    f"ELSE ${parameter}::jsonb END"
                )
            else:
                assignments.append(f"{column} = ${parameter}")
        query = f"""
            UPDATE pipeline_states
            SET {", ".join(assignments)}, updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *values)
            if row is None:
                return None
            result = dict(row)
            result["config"] = self._from_json(result.get("config"))
            return result

        conn = get_sqlite_conn()
        if conn is None:
            return None

        def _sync_update() -> dict[str, Any] | None:
            with get_sqlite_lock():
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        "SELECT config FROM pipeline_states WHERE id = ?",
                        (id,),
                    ).fetchone()
                    if row is None:
                        conn.commit()
                        return None
                    current_config = self._from_json(row["config"])
                    if type(current_config) is not dict:
                        raise RuntimeError("pipeline completion config is invalid")
                    merged_data = dict(data)
                    merged_config = dict(incoming_config)
                    if claim_key in current_config:
                        merged_config[claim_key] = current_config[claim_key]
                    merged_data["config"] = merged_config
                    set_clause = ", ".join(f"{column} = ?" for column in columns)
                    conn.execute(
                        f"""
                        UPDATE pipeline_states
                        SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        [self._to_json(merged_data[column]) for column in columns]
                        + [id],
                    )
                    updated = conn.execute(
                        "SELECT * FROM pipeline_states WHERE id = ?",
                        (id,),
                    ).fetchone()
                    conn.commit()
                    if updated is None:
                        return None
                    result = dict(updated)
                    result["config"] = self._from_json(result.get("config"))
                    return result
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise

        return await asyncio.to_thread(_sync_update)

    async def claim_pipeline_completion(
        self,
        label: str,
        claim: dict[str, Any],
    ) -> dict[str, Any] | bool | None:
        """Atomically bind one claim to the current durable terminal state.

        Returns ``None`` only when neither PostgreSQL nor SQLite persistence is
        configured, ``False`` when no new terminal claim can be created, and
        the winning claim otherwise. A configured store never degrades to a
        non-atomic write.
        """

        from src.models.pipeline_completion import (
            bind_claim_to_facts,
            derive_pipeline_completion_facts,
        )

        def _durable_state(row: Any, config: dict[str, Any]) -> dict[str, Any]:
            raw_degraded = row["pipeline_degraded"]
            if type(raw_degraded) is bool:
                degraded = raw_degraded
            elif type(raw_degraded) is int and raw_degraded in {0, 1}:
                degraded = bool(raw_degraded)
            else:
                raise RuntimeError("pipeline completion state is invalid")
            lifecycle = config.get("execution_lifecycle")
            lifecycle_status = (
                lifecycle.get("lifecycle_status")
                if type(lifecycle) is dict
                else None
            )
            return {
                "scenario": row["scenario"],
                "lifecycle_status": lifecycle_status,
                "current_step": row["current_step"],
                "pipeline_degraded": degraded,
                "errors": self._from_json(row["errors"]),
            }

        claim_key = "pipeline_completion_metric_v1"
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        """
                        SELECT scenario, config, current_step, errors,
                               pipeline_degraded
                        FROM pipeline_states
                        WHERE label = $1
                        FOR UPDATE
                        """,
                        label,
                    )
                    if row is None:
                        raise RuntimeError("pipeline completion state is missing")
                    config = self._from_json(row["config"])
                    if type(config) is not dict:
                        raise RuntimeError("pipeline completion config is invalid")
                    if claim_key in config:
                        return False
                    durable_facts = derive_pipeline_completion_facts(
                        _durable_state(row, config)
                    )
                    if durable_facts is None:
                        return False
                    winning_claim = bind_claim_to_facts(claim, durable_facts)
                    updated = await conn.fetchrow(
                        """
                        UPDATE pipeline_states
                        SET config = jsonb_set(
                            COALESCE(config, '{}'::jsonb),
                            '{pipeline_completion_metric_v1}',
                            $2::jsonb,
                            true
                        ),
                        updated_at = NOW()
                        WHERE label = $1
                          AND NOT (
                            COALESCE(config, '{}'::jsonb)
                            ? 'pipeline_completion_metric_v1'
                          )
                        RETURNING id
                        """,
                        label,
                        json.dumps(winning_claim, default=self._json_default),
                    )
                    if updated is None:
                        return False
                    return winning_claim

        conn = get_sqlite_conn()
        if conn is None:
            return None

        def _sync_claim() -> dict[str, Any] | bool:
            with get_sqlite_lock():
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(
                        """
                        SELECT scenario, config, current_step, errors,
                               pipeline_degraded
                        FROM pipeline_states
                        WHERE label = ?
                        """,
                        (label,),
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("pipeline completion state is missing")
                    raw_config = row["config"]
                    config = self._from_json(raw_config)
                    if not isinstance(config, dict):
                        raise RuntimeError("pipeline completion config is invalid")
                    if claim_key in config:
                        conn.commit()
                        return False
                    durable_facts = derive_pipeline_completion_facts(
                        _durable_state(row, config)
                    )
                    if durable_facts is None:
                        conn.commit()
                        return False
                    winning_claim = bind_claim_to_facts(claim, durable_facts)
                    config = dict(config)
                    config[claim_key] = winning_claim
                    conn.execute(
                        """
                        UPDATE pipeline_states
                        SET config = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE label = ?
                        """,
                        (json.dumps(config, default=self._json_default), label),
                    )
                    conn.commit()
                    return winning_claim
                except Exception:
                    if conn.in_transaction:
                        conn.rollback()
                    raise

        return await asyncio.to_thread(_sync_claim)


class BrandPackageRepository(BaseRepository):
    def __init__(self):
        super().__init__("brand_packages")


class InfluencerRepository(BaseRepository):
    def __init__(self):
        super().__init__("influencers")


class PublishLogRepository(BaseRepository):
    def __init__(self):
        super().__init__("publish_logs")
