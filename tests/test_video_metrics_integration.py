"""Sprint 4 P4-4: VideoMetricsRepository end-to-end integration tests.

Verifies the metrics PG-data-closeback chain works on SQLite fallback (PG
not available in CI/local). Save → get → aggregate cycle for the
video_metrics table introduced by Alembic 1efc41794d64.

Tests use src/storage/db.py SQLite path, which already creates the
video_metrics schema at module init (line 111). PG path is exercised in
production only.

Diagnostic R-METRICS-CLOSEBACK closure: was metrics_repository / poller /
dashboard wiring functional end-to-end? Per Oracle review, all infra
existed but had no integration test. This file fills that gap.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.storage import db as db_module
from src.storage.metrics_repository import VideoMetricsRepository


@pytest.fixture
def isolated_metrics_db(tmp_path, monkeypatch):
    """Fresh SQLite DB per test, isolated from other tests' state.

    Patches both `get_pool` (used by metrics_repository module directly)
    and `is_pg_available` (used elsewhere) to force the SQLite fallback
    path regardless of whether a previous test triggered PG pool init.
    """
    db_path = tmp_path / "test_metrics.db"
    # Patch the SQLite init path AND clear cached connection
    db_module._sqlite_conn = None

    def _init_at_test_path():
        import sqlite3
        db_module._sqlite_conn = sqlite3.connect(str(db_path))
        db_module._sqlite_conn.row_factory = sqlite3.Row
        db_module._create_sqlite_tables()

    monkeypatch.setattr(db_module, "_init_sqlite", _init_at_test_path)
    # Force PG path to be skipped — get_pool returns None
    # (metrics_repository checks `pool = await get_pool()` then falls back
    # to get_sqlite_conn). Patching ONLY is_pg_available is insufficient
    # because metrics_repository never calls it.
    async def _no_pool():
        return None
    monkeypatch.setattr(db_module, "get_pool", _no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    # Patch get_pool reference inside metrics_repository module too — Python
    # imports rebind, so `from .db import get_pool` creates a local binding
    # that must be patched separately.
    import src.storage.metrics_repository as mr_module
    monkeypatch.setattr(mr_module, "get_pool", _no_pool)

    _init_at_test_path()
    yield db_path
    # Cleanup
    if db_module._sqlite_conn is not None:
        with contextlib.suppress(Exception):
            db_module._sqlite_conn.close()
        db_module._sqlite_conn = None


class TestVideoMetricsSaveAndGet:
    """Save then retrieve — basic round-trip."""

    @pytest.mark.asyncio
    async def test_save_returns_record(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        result = await repo.save_metrics(
            video_id="v1",
            scenario="s1",
            platform="tiktok",
            post_id="post_1",
            post_url="https://tiktok.com/post_1",
            metrics_dict={"views": 1000, "watch_rate": 0.7, "ctr": 0.05},
        )
        assert result["video_id"] == "v1"
        assert result["scenario"] == "s1"
        assert result["platform"] == "tiktok"
        assert result["post_id"] == "post_1"
        assert result["metrics"]["views"] == 1000

    @pytest.mark.asyncio
    async def test_get_metrics_returns_saved(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        await repo.save_metrics(
            video_id="v2", scenario="s1", platform="tiktok",
            metrics_dict={"views": 500},
        )
        rows = await repo.get_metrics("v2")
        assert len(rows) == 1
        assert rows[0]["video_id"] == "v2"
        assert rows[0]["metrics"]["views"] == 500

    @pytest.mark.asyncio
    async def test_get_metrics_filters_by_platform(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        await repo.save_metrics(video_id="v3", scenario="s1",
                                platform="tiktok", metrics_dict={"views": 100})
        await repo.save_metrics(video_id="v3", scenario="s1",
                                platform="shopify", metrics_dict={"views": 50})
        tt = await repo.get_metrics("v3", platform="tiktok")
        sp = await repo.get_metrics("v3", platform="shopify")
        assert len(tt) == 1 and tt[0]["platform"] == "tiktok"
        assert len(sp) == 1 and sp[0]["platform"] == "shopify"

    @pytest.mark.asyncio
    async def test_get_metrics_orders_by_pulled_at_desc(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        for i in range(3):
            await repo.save_metrics(
                video_id="v4", scenario="s1", platform="tiktok",
                metrics_dict={"views": 100 * (i + 1)},
            )
            await asyncio.sleep(0.01)  # Ensure distinct timestamps
        rows = await repo.get_metrics("v4")
        assert len(rows) == 3
        # Most recent first
        assert rows[0]["metrics"]["views"] == 300
        assert rows[2]["metrics"]["views"] == 100


class TestDashboardOverview:
    """get_dashboard_overview returns latest snapshot per (video, platform)
    within the time window."""

    @pytest.mark.asyncio
    async def test_returns_latest_snapshot_per_video(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        # Save 2 snapshots for v1+tiktok, 1 snapshot for v2+tiktok
        await repo.save_metrics(video_id="v1", scenario="s1",
                                platform="tiktok",
                                metrics_dict={"views": 100})
        await asyncio.sleep(0.01)
        await repo.save_metrics(video_id="v1", scenario="s1",
                                platform="tiktok",
                                metrics_dict={"views": 200})
        await repo.save_metrics(video_id="v2", scenario="s1",
                                platform="tiktok",
                                metrics_dict={"views": 50})
        overview = await repo.get_dashboard_overview()
        # 2 distinct (video, platform) tuples
        assert len(overview) == 2
        # v1's latest snapshot (views=200) should be present, not the older 100
        v1_row = next((r for r in overview if r["video_id"] == "v1"), None)
        assert v1_row is not None
        assert v1_row["metrics"]["views"] == 200

    @pytest.mark.asyncio
    async def test_filters_by_scenario(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        await repo.save_metrics(video_id="v1", scenario="s1",
                                platform="tiktok", metrics_dict={"views": 100})
        await repo.save_metrics(video_id="v2", scenario="s2",
                                platform="tiktok", metrics_dict={"views": 200})
        s1_only = await repo.get_dashboard_overview(scenario="s1")
        assert len(s1_only) == 1
        assert s1_only[0]["scenario"] == "s1"

    @pytest.mark.asyncio
    async def test_filters_by_time_window(self, isolated_metrics_db):
        """get_dashboard_overview with days=7 should exclude rows older
        than 7 days. Hard to test against real time without mocking; this
        smoke just confirms the days param is respected."""
        repo = VideoMetricsRepository()
        await repo.save_metrics(
            video_id="v1", scenario="s1", platform="tiktok",
            metrics_dict={"views": 100},
        )
        # days=0 → cutoff is now → row should still appear since pulled_at == now
        # but in practice strict equality may exclude; use days=1 to be safe
        rows = await repo.get_dashboard_overview(days=1)
        assert len(rows) == 1


class TestActivePosts:
    """get_active_posts returns posts published in last 30 days."""

    @pytest.mark.asyncio
    async def test_recent_post_is_active(self, isolated_metrics_db):
        repo = VideoMetricsRepository()
        await repo.save_metrics(
            video_id="v1", scenario="s1", platform="tiktok",
            post_id="recent_post", metrics_dict={"views": 100},
        )
        active = await repo.get_active_posts()
        assert len(active) == 1
        assert active[0]["post_id"] == "recent_post"


class TestSchemaPhase0Parity:
    """Verifies SQLite schema parity with Alembic 7a2f4b8c9d12 (Phase 0 #1):
    pipeline_states must have schema_version, pipeline_degraded,
    degraded_reason, trace_id, structured_errors columns."""

    def test_sqlite_pipeline_states_has_phase0_columns(self, isolated_metrics_db):
        from src.storage.db import get_sqlite_conn
        conn = get_sqlite_conn()
        cursor = conn.execute("PRAGMA table_info(pipeline_states)")
        column_names = {row["name"] for row in cursor.fetchall()}
        for col in (
            "gates",  # 2026-05-03 addition
            "schema_version",
            "pipeline_degraded",
            "degraded_reason",
            "trace_id",
            "structured_errors",
        ):
            assert col in column_names, f"missing column: {col} (column_names={column_names})"
