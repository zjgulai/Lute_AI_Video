"""Video metrics repository — CRUD for video_metrics table.

Follows the dual-backend pattern from repository.py: PostgreSQL (asyncpg) with
SQLite fallback. All queries are parameterised to prevent injection.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import asyncpg

from .db import get_pool, get_sqlite_conn, is_pg_available

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _generate_id() -> str:
    return str(uuid.uuid4())


def _to_json(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value if isinstance(value, str) else json.dumps(value)


def _from_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _deserialize_row(row: dict) -> dict:
    """Deserialize JSONB columns in a row returned from the database."""
    result = dict(row)
    for key in ("metrics",):
        if key in result:
            result[key] = _from_json(result[key])
    return result


class VideoMetricsRepository:
    """CRUD operations for the video_metrics table."""

    TABLE = "video_metrics"

    # ------------------------------------------------------------------
    # Internal helpers (PG-first, SQLite fallback)
    # ------------------------------------------------------------------

    async def _fetchrow(self, query: str, *args) -> Optional[dict]:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(query, *args)
                return dict(row) if row else None
        conn = get_sqlite_conn()
        if conn is None:
            return None
        cursor = conn.execute(query, args)
        row = cursor.fetchone()
        return dict(row) if row else None

    async def _fetch(self, query: str, *args) -> list[dict]:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(r) for r in rows]
        conn = get_sqlite_conn()
        if conn is None:
            return []
        cursor = conn.execute(query, args)
        return [dict(row) for row in cursor.fetchall()]

    async def _execute(self, query: str, *args) -> None:
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                await conn.execute(query, *args)
            return
        conn = get_sqlite_conn()
        if conn is not None:
            conn.execute(query, args)
            conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def save_metrics(
        self,
        video_id: str,
        scenario: str,
        platform: str,
        post_id: Optional[str] = None,
        post_url: Optional[str] = None,
        metrics_dict: Optional[dict] = None,
    ) -> dict:
        """Insert a new metrics snapshot row."""
        record_id = _generate_id()
        now_ts = _now()
        metrics_json = _to_json(metrics_dict or {})

        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    INSERT INTO video_metrics
                        (id, video_id, scenario, platform, post_id, post_url,
                         metrics, pulled_at, published_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $8, $8)
                    RETURNING *
                    """,
                    record_id,
                    video_id,
                    scenario,
                    platform,
                    post_id,
                    post_url,
                    metrics_json,
                    now_ts,
                )
                return _deserialize_row(dict(row))

        # SQLite fallback
        conn = get_sqlite_conn()
        if conn is not None:
            conn.execute(
                """
                INSERT INTO video_metrics
                    (id, video_id, scenario, platform, post_id, post_url,
                     metrics, pulled_at, published_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    video_id,
                    scenario,
                    platform,
                    post_id,
                    post_url,
                    metrics_json,
                    now_ts,
                    now_ts,
                    now_ts,
                ),
            )
            conn.commit()
            cursor = conn.execute(
                "SELECT * FROM video_metrics WHERE id = ?", (record_id,)
            )
            row = cursor.fetchone()
            return _deserialize_row(dict(row)) if row else {}

        return {}

    async def get_metrics(
        self,
        video_id: str,
        platform: Optional[str] = None,
    ) -> list[dict]:
        """Get all metrics snapshots for a video, optionally filtered by platform.

        Results are ordered by pulled_at descending (newest first).
        """
        if platform:
            query = """
                SELECT * FROM video_metrics
                WHERE video_id = $1 AND platform = $2
                ORDER BY pulled_at DESC
            """
            rows = await self._fetch(query, video_id, platform)
        else:
            query = """
                SELECT * FROM video_metrics
                WHERE video_id = $1
                ORDER BY pulled_at DESC
            """
            rows = await self._fetch(query, video_id)
        return [_deserialize_row(r) for r in rows]

    async def get_dashboard_overview(
        self,
        scenario: Optional[str] = None,
        platform: Optional[str] = None,
        days: int = 7,
    ) -> list[dict]:
        """Get aggregated dashboard data: latest metrics per video.

        For each video returns the single most recent metrics snapshot,
        filtered by scenario / platform / time window.
        """
        cutoff = _now() - timedelta(days=days)
        conditions = ["vm.pulled_at >= $1"]
        params: list = [cutoff]
        idx = 2

        if scenario:
            conditions.append(f"vm.scenario = ${idx}")
            params.append(scenario)
            idx += 1
        if platform:
            conditions.append(f"vm.platform = ${idx}")
            params.append(platform)
            idx += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT DISTINCT ON (vm.video_id, vm.platform)
                vm.id,
                vm.video_id,
                vm.scenario,
                vm.platform,
                vm.post_id,
                vm.post_url,
                vm.metrics,
                vm.pulled_at,
                vm.published_at
            FROM video_metrics vm
            WHERE {where_clause}
            ORDER BY vm.video_id, vm.platform, vm.pulled_at DESC
        """
        rows = await self._fetch(query, *params)
        return [_deserialize_row(r) for r in rows]

    async def get_active_posts(self) -> list[dict]:
        """Get all posts that need polling (published within 30 days).

        Returns the latest snapshot row per (video_id, platform) so that
        callers can check pulled_at to decide whether a new pull is due.
        """
        cutoff = _now() - timedelta(days=30)
        query = """
            SELECT DISTINCT ON (vm.video_id, vm.platform)
                vm.id,
                vm.video_id,
                vm.scenario,
                vm.platform,
                vm.post_id,
                vm.post_url,
                vm.metrics,
                vm.pulled_at,
                vm.published_at
            FROM video_metrics vm
            WHERE vm.published_at >= $1
            ORDER BY vm.video_id, vm.platform, vm.pulled_at DESC
        """
        rows = await self._fetch(query, cutoff)
        return [_deserialize_row(r) for r in rows]

    async def get_scenario_aggregates(self, days: int = 7) -> list[dict]:
        """Average metrics grouped by scenario over the given time window.

        Returns rows like:
            {"scenario": "S1", "avg_watch_rate": 0.72, "avg_ctr": 0.042, ...}
        """
        cutoff = _now() - timedelta(days=days)
        pool = await get_pool()
        if pool is not None:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (vm.video_id, vm.platform)
                            vm.id, vm.scenario, vm.metrics
                        FROM video_metrics vm
                        WHERE vm.pulled_at >= $1
                        ORDER BY vm.video_id, vm.platform, vm.pulled_at DESC
                    )
                    SELECT
                        scenario,
                        COUNT(*)                                          AS post_count,
                        AVG(CAST(metrics->>'watch_rate' AS NUMERIC))      AS avg_watch_rate,
                        AVG(CAST(metrics->>'ctr' AS NUMERIC))             AS avg_ctr,
                        AVG(CAST(metrics->>'cvr' AS NUMERIC))             AS avg_cvr,
                        SUM(CAST(metrics->>'followers_gained' AS INT))    AS total_followers,
                        SUM(CAST(metrics->>'sales' AS INT))               AS total_sales,
                        SUM(CAST(metrics->>'views' AS INT))               AS total_views
                    FROM latest
                    GROUP BY scenario
                    ORDER BY scenario
                    """,
                    cutoff,
                )
                return [dict(r) for r in rows]

        # SQLite fallback — JSON extraction is via json_extract()
        conn = get_sqlite_conn()
        if conn is None:
            return []

        cursor = conn.execute(
            """
            WITH latest AS (
                SELECT vm.id, vm.scenario, vm.metrics,
                       ROW_NUMBER() OVER (
                           PARTITION BY vm.video_id, vm.platform
                           ORDER BY vm.pulled_at DESC
                       ) AS rn
                FROM video_metrics vm
                WHERE vm.pulled_at >= ?
            )
            SELECT
                scenario,
                COUNT(*)                                                AS post_count,
                AVG(CAST(json_extract(metrics, '$.watch_rate') AS REAL)) AS avg_watch_rate,
                AVG(CAST(json_extract(metrics, '$.ctr') AS REAL))        AS avg_ctr,
                AVG(CAST(json_extract(metrics, '$.cvr') AS REAL))        AS avg_cvr,
                SUM(CAST(json_extract(metrics, '$.followers_gained') AS INTEGER)) AS total_followers,
                SUM(CAST(json_extract(metrics, '$.sales') AS INTEGER))           AS total_sales,
                SUM(CAST(json_extract(metrics, '$.views') AS INTEGER))          AS total_views
            FROM latest
            WHERE rn = 1
            GROUP BY scenario
            ORDER BY scenario
            """,
            (cutoff,),
        )
        return [dict(row) for row in cursor.fetchall()]

    async def get_platform_comparison(
        self,
        scenario: Optional[str] = None,
        days: int = 7,
    ) -> list[dict]:
        """Metrics grouped by platform, optionally filtered by scenario.

        Returns rows like:
            {"platform": "tiktok", "scenario": "S1",
             "avg_watch_rate": ..., "avg_ctr": ..., ...}
        """
        cutoff = _now() - timedelta(days=days)
        pool = await get_pool()

        scenario_filter = ""
        params: list = [cutoff]
        if scenario:
            scenario_filter = " AND vm.scenario = $2"
            params.append(scenario)

        pg_query = f"""
            WITH latest AS (
                SELECT DISTINCT ON (vm.video_id, vm.platform)
                    vm.id, vm.scenario, vm.platform, vm.metrics
                FROM video_metrics vm
                WHERE vm.pulled_at >= $1{scenario_filter}
                ORDER BY vm.video_id, vm.platform, vm.pulled_at DESC
            )
            SELECT
                platform,
                scenario,
                COUNT(*)                                          AS post_count,
                AVG(CAST(metrics->>'watch_rate' AS NUMERIC))      AS avg_watch_rate,
                AVG(CAST(metrics->>'ctr' AS NUMERIC))             AS avg_ctr,
                AVG(CAST(metrics->>'cvr' AS NUMERIC))             AS avg_cvr,
                SUM(CAST(metrics->>'followers_gained' AS INT))    AS total_followers,
                SUM(CAST(metrics->>'sales' AS INT))               AS total_sales,
                SUM(CAST(metrics->>'views' AS INT))               AS total_views
            FROM latest
            GROUP BY platform, scenario
            ORDER BY platform, scenario
        """

        if pool is not None:
            async with pool.acquire() as conn:
                rows = await conn.fetch(pg_query, *params)
                return [dict(r) for r in rows]

        # SQLite fallback
        conn = get_sqlite_conn()
        if conn is None:
            return []

        sqlite_query = f"""
            WITH latest AS (
                SELECT vm.id, vm.scenario, vm.platform, vm.metrics,
                       ROW_NUMBER() OVER (
                           PARTITION BY vm.video_id, vm.platform
                           ORDER BY vm.pulled_at DESC
                       ) AS rn
                FROM video_metrics vm
                WHERE vm.pulled_at >= ?{scenario_filter.replace('$2', '?')}
            )
            SELECT
                platform,
                scenario,
                COUNT(*)                                                AS post_count,
                AVG(CAST(json_extract(metrics, '$.watch_rate') AS REAL)) AS avg_watch_rate,
                AVG(CAST(json_extract(metrics, '$.ctr') AS REAL))        AS avg_ctr,
                AVG(CAST(json_extract(metrics, '$.cvr') AS REAL))        AS avg_cvr,
                SUM(CAST(json_extract(metrics, '$.followers_gained') AS INTEGER)) AS total_followers,
                SUM(CAST(json_extract(metrics, '$.sales') AS INTEGER))           AS total_sales,
                SUM(CAST(json_extract(metrics, '$.views') AS INTEGER))          AS total_views
            FROM latest
            WHERE rn = 1
            GROUP BY platform, scenario
            ORDER BY platform, scenario
        """
        cursor = conn.execute(sqlite_query, params)
        return [dict(row) for row in cursor.fetchall()]
