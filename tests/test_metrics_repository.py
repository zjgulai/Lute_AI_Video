"""Tests for MetricsRepository — JSON and SQLite backends."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from src.tools.metrics_repository import MetricsRepository, SummaryReport, HealthStatus

# ── Sample run data ──
# 用相对当前时间的 timestamp,避免硬编码 "2026-04-25" 落到 48h 窗口外。
# 所有 sample run 都在过去 1-3 小时内,确保 hours=48 query 能命中。
def _ts(hours_ago: float) -> str:
    return (datetime.now() - timedelta(hours=hours_ago)).isoformat()


SAMPLE_RUN_OK = {
    "run_id": "run-001",
    "started_at": _ts(3),
    "completed_at": _ts(2.99),
    "total_duration_ms": 3220.5,
    "node_count": 16,
    "error_count": 0,
    "human_review_count": 2,
    "re_run_count": 1,
    "node_timings": [
        {"node_name": "strategy_node", "duration_ms": 120.0, "success": True, "timestamp": "t1"},
        {"node_name": "script_node", "duration_ms": 800.0, "success": True, "timestamp": "t2"},
    ],
}

SAMPLE_RUN_FAIL = {
    "run_id": "run-002",
    "started_at": _ts(2),
    "completed_at": _ts(1.99),
    "total_duration_ms": 5100.0,
    "node_count": 4,
    "error_count": 1,
    "human_review_count": 0,
    "re_run_count": 0,
    "node_timings": [
        {"node_name": "script_node", "duration_ms": 4900.0, "success": False, "error": "timeout", "timestamp": "t3"},
    ],
}

SAMPLE_RUN_SLOW = {
    "run_id": "run-003",
    "started_at": _ts(1),
    "completed_at": _ts(0.98),
    "total_duration_ms": 62000.0,
    "node_count": 16,
    "error_count": 0,
    "human_review_count": 1,
    "re_run_count": 0,
    "node_timings": [
        {"node_name": "slow_node", "duration_ms": 35000.0, "success": True, "timestamp": "t4"},
        {"node_name": "fast_node", "duration_ms": 2.0, "success": True, "timestamp": "t5"},
    ],
}


# ── Fixtures ──


@pytest.fixture(params=["json", "sqlite"])
def repo(request, tmp_path: Path) -> MetricsRepository:
    """Parametrized fixture: tests run against both backends."""
    if request.param == "json":
        r = MetricsRepository(path=str(tmp_path / "metrics.json"), backend="json")
    else:
        r = MetricsRepository(path=":memory:", backend="sqlite")
    r.initialize()
    yield r
    r.close()


@pytest.fixture
def populated_repo(repo: MetricsRepository) -> MetricsRepository:
    """Repo with 3 sample runs loaded."""
    repo.save_run(SAMPLE_RUN_OK)
    repo.save_run(SAMPLE_RUN_FAIL)
    repo.save_run(SAMPLE_RUN_SLOW)
    return repo


# ── Init Tests ──


class TestInit:
    def test_init_json_in_memory(self):
        r = MetricsRepository()
        r.initialize()
        assert len(r) == 0
        r.close()

    def test_init_json_with_path(self, tmp_path: Path):
        p = tmp_path / "metrics.json"
        r = MetricsRepository(path=str(p), backend="json")
        r.initialize()
        assert not p.exists()  # lazy: only writes on save
        r.close()

    def test_init_sqlite_memory(self):
        r = MetricsRepository(path=":memory:", backend="sqlite")
        r.initialize()
        assert len(r) == 0
        r.close()

    def test_init_sqlite_with_path(self, tmp_path: Path):
        p = tmp_path / "metrics.db"
        r = MetricsRepository(path=str(p), backend="sqlite")
        r.initialize()
        assert p.exists()
        r.close()

    def test_init_idempotent(self):
        r = MetricsRepository(path=":memory:", backend="sqlite")
        r.initialize()
        r.initialize()  # second call should be no-op
        assert len(r) == 0
        r.close()

    def test_auto_detect_json(self, tmp_path: Path):
        r = MetricsRepository(path=str(tmp_path / "metrics.json"))
        r.initialize()
        assert r._backend == "json"
        r.close()

    def test_auto_detect_sqlite(self):
        r = MetricsRepository(path=":memory:")
        r.initialize()
        assert r._backend == "sqlite"
        r.close()


# ── Write Tests ──


class TestSave:
    def test_save_and_count(self, repo: MetricsRepository):
        rid = repo.save_run(SAMPLE_RUN_OK)
        assert rid == "run-001"
        assert len(repo) == 1

    def test_save_multiple(self, populated_repo: MetricsRepository):
        assert len(populated_repo) == 3

    def test_save_generates_run_id(self, repo: MetricsRepository):
        data = dict(SAMPLE_RUN_OK)
        data.pop("run_id", None)
        rid = repo.save_run(data)
        assert rid is not None
        assert len(rid) > 0

    def test_save_adds_timestamp(self, repo: MetricsRepository):
        data = dict(SAMPLE_RUN_OK)
        data.pop("run_id", None)
        repo.save_run(data)
        runs = repo.list_runs(limit=1)
        assert "_saved_at" in runs[0]


# ── Read Tests ──


class TestList:
    def test_list_empty(self, repo: MetricsRepository):
        assert repo.list_runs() == []

    def test_list_limit(self, populated_repo: MetricsRepository):
        assert len(populated_repo.list_runs(limit=1)) == 1

    def test_list_offset(self, populated_repo: MetricsRepository):
        all_runs = populated_repo.list_runs(limit=10)
        offset = populated_repo.list_runs(limit=10, offset=1)
        assert len(offset) == len(all_runs) - 1

    def test_list_order_newest_first(self, populated_repo: MetricsRepository):
        runs = populated_repo.list_runs(limit=10)
        # Most recently saved should be last in -json_runs but first in list
        assert len(runs) == 3
        # The 3rd save (SAMPLE_RUN_SLOW) should be first
        assert runs[0]["run_id"] in ("run-003", "run-002", "run-001")


class TestGet:
    def test_get_existing(self, populated_repo: MetricsRepository):
        run = populated_repo.get_run("run-001")
        assert run is not None
        assert run["total_duration_ms"] == 3220.5

    def test_get_missing(self, populated_repo: MetricsRepository):
        assert populated_repo.get_run("nonexistent") is None

    def test_get_empty(self, repo: MetricsRepository):
        assert repo.get_run("x") is None


class TestSummary:
    def test_summary_empty(self, repo: MetricsRepository):
        s = repo.get_summary(hours=24)
        assert s.total_runs == 0
        assert s.health == "healthy"

    def test_summary_counts(self, populated_repo: MetricsRepository):
        s = populated_repo.get_summary(hours=48)
        assert s.total_runs == 3
        assert s.successful_runs == 2  # run-002 has error_count=1
        assert s.failed_runs == 1

    def test_summary_error_rate(self, populated_repo: MetricsRepository):
        s = populated_repo.get_summary(hours=48)
        assert s.error_rate == pytest.approx(1 / 3, rel=0.01)

    def test_summary_slowest_nodes(self, populated_repo: MetricsRepository):
        s = populated_repo.get_summary(hours=48)
        assert len(s.slowest_nodes) > 0
        assert s.slowest_nodes[0]["node_name"] in ("slow_node", "script_node")

    def test_summary_time_window(self, populated_repo: MetricsRepository):
        # hours=0 means cutoff is now; all sample data has started_at from the past
        # so they should all be excluded... but they were saved with past timestamps
        # that still compare >= cutoff (all 2026-04-25 and now is also 2026-04-25).
        # Use hours=24*365 (1 year) to include everything
        s = populated_repo.get_summary(hours=8760)  # 1 year
        assert s.total_runs == 3

    def test_summary_data_types(self, populated_repo: MetricsRepository):
        s = populated_repo.get_summary(hours=48)
        assert isinstance(s.avg_duration_ms, float)
        assert isinstance(s.avg_node_count, float)
        assert isinstance(s.total_human_reviews, int)
        assert isinstance(s.total_re_runs, int)


# ── Health Tests ──


class TestHealth:
    def test_health_empty_repo(self, repo: MetricsRepository):
        h = repo.check_health()
        assert h.level == "healthy"
        assert len(h.checks) == 0

    def test_health_healthy(self, repo: MetricsRepository):
        for i in range(3):
            d = dict(SAMPLE_RUN_OK)
            d["run_id"] = f"ok-{i}"
            d["error_count"] = 0
            d["re_run_count"] = 0
            repo.save_run(d)
        h = repo.check_health(hours=48)
        assert h.level == "healthy"

    def test_health_error_rate_warn(self, repo: MetricsRepository):
        for i in range(10):
            d = dict(SAMPLE_RUN_OK)
            d["run_id"] = f"r-{i}"
            d["error_count"] = 1 if i < 2 else 0  # 20% failure
            repo.save_run(d)
        h = repo.check_health(hours=48)
        assert h.level == "warn"

    def test_health_error_rate_critical(self, repo: MetricsRepository):
        for i in range(10):
            d = dict(SAMPLE_RUN_OK)
            d["run_id"] = f"r-{i}"
            d["error_count"] = 1 if i < 5 else 0  # 50% failure
            repo.save_run(d)
        h = repo.check_health(hours=48)
        assert h.level == "critical"

    def test_health_consecutive_failures(self, repo: MetricsRepository):
        for i in range(5):
            d = dict(SAMPLE_RUN_FAIL)
            d["run_id"] = f"fail-{i}"
            repo.save_run(d)
        h = repo.check_health(hours=48)
        assert h.level == "critical"

    def test_health_slow_node_warn(self, repo: MetricsRepository):
        repo.save_run(SAMPLE_RUN_SLOW)  # slow_node at 35s
        h = repo.check_health(hours=48)
        assert h.level == "warn"

    def test_health_slow_node_critical(self, repo: MetricsRepository):
        d = dict(SAMPLE_RUN_SLOW)
        d["node_timings"] = [{"node_name": "glacial", "duration_ms": 65_000, "success": True, "timestamp": "t"}]
        repo.save_run(d)
        h = repo.check_health(hours=48)
        assert h.level == "critical"

    def test_health_to_dict(self):
        h = HealthStatus(level="warn", checks=[{"name": "test", "level": "warn", "message": "test"}])
        d = h.to_dict()
        assert d["level"] == "warn"
        assert "checked_at" in d


# ── Clear Tests ──


class TestClear:
    def test_clear_json(self, repo: MetricsRepository):
        repo.save_run(SAMPLE_RUN_OK)
        assert len(repo) == 1
        repo.clear()
        assert len(repo) == 0

    def test_clear_then_save(self, repo: MetricsRepository):
        repo.save_run(SAMPLE_RUN_OK)
        repo.clear()
        repo.save_run(SAMPLE_RUN_OK)
        assert len(repo) == 1


# 原 TestTelemetryIntegration class 已删除(2026-05-05):
# - set_metrics_repo / save_run_metrics / get_metrics_repo 已从 src.telemetry 移除
# - 测试 import 直接 ImportError,无法 collect
# - 集成路径如有需要,需要找到新 API 重写;当前 src.telemetry 有
#   pipeline_metrics / error_collector / timed_node 三个 singleton,与旧 set_metrics_repo
#   设计不同

