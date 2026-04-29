"""Persistent metrics repository — JSON file and SQLite backends.

Stores pipeline run metrics for cross-run analysis, trend detection,
and health alerting. Zero external dependencies (sqlite3 is stdlib).

Two backends:
  - JSON: simplest, single-file, good for dev/debug
  - SQLite: fast aggregation queries, good for local production

Both can be memory-only (path=":memory:" for SQLite, no path for JSON -> in-memory dict).

Usage:
    repo = MetricsRepository(path="data/metrics.db", backend="sqlite")
    repo.save_run(metrics.to_dict())

    summary = repo.get_summary(hours=24)
    runs = repo.list_runs(limit=10)
    run = repo.get_run(run_id)
    health = repo.check_health()
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ── Shared data types ──


@dataclass
class SummaryReport:
    """Aggregate metrics across a time window."""

    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    error_rate: float = 0.0
    avg_duration_ms: float = 0.0
    avg_node_count: float = 0.0
    total_human_reviews: int = 0
    total_re_runs: int = 0
    slowest_nodes: list[dict[str, Any]] = field(default_factory=list)
    window_hours: int = 24
    health: str = "unknown"  # "healthy" | "warn" | "critical"


@dataclass
class HealthStatus:
    """Health check result for alerting."""

    level: str = "healthy"  # "healthy" | "warn" | "critical"
    checks: list[dict[str, Any]] = field(default_factory=list)
    summary: str = "All checks passed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "checks": self.checks,
            "summary": self.summary,
            "checked_at": datetime.now(UTC).isoformat(),
        }


# ── Repository ──


class MetricsRepository:
    """Persistent metrics store with JSON and SQLite backends.

    Args:
        path: File path for persistence. ":memory:" for SQLite memory-only.
              None for JSON in-memory (not persisted).
        backend: "json" (default) or "sqlite". Auto-detected from path suffix.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        backend: str | None = None,
    ):
        self._path = str(path) if path else None

        # Auto-detect backend from path
        if backend is None and self._path:
            if self._path.endswith(".json"):
                backend = "json"
            elif self._path == ":memory:" or self._path.endswith(".db"):
                backend = "sqlite"
            else:
                backend = "json"  # default
        elif backend is None:
            backend = "json"

        self._backend = backend
        self._conn: sqlite3.Connection | None = None
        self._json_runs: list[dict[str, Any]] = []
        self._initialized = False

    # ── Lifecycle ──

    def initialize(self) -> None:
        """Idempotent init — safe to call multiple times."""
        if self._initialized:
            return
        if self._backend == "sqlite":
            self._init_sqlite()
        else:
            self._init_json()
        self._initialized = True
        logger.debug("metrics: repository initialized", backend=self._backend, path=self._path)

    def close(self) -> None:
        """Release resources."""
        if self._conn:
            self._conn.close()
            self._conn = None
        self._initialized = False

    # ── Write ──

    def save_run(self, run_data: dict[str, Any]) -> str:
        """Persist a single pipeline run. Returns run_id."""
        self.initialize()
        run_id = run_data.get("run_id", datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f"))
        run_data["run_id"] = run_id
        run_data["_saved_at"] = datetime.now(UTC).isoformat()

        if self._backend == "sqlite":
            self._save_sqlite(run_data)
        else:
            self._save_json(run_data)
        return run_id

    # ── Reads ──

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
        """List recent pipeline runs, newest first."""
        self.initialize()
        if self._backend == "sqlite":
            return self._query_sqlite(
                "SELECT data FROM pipeline_runs ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        runs = list(reversed(self._json_runs))
        return runs[offset: offset + limit]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a single run by ID."""
        self.initialize()
        if self._backend == "sqlite":
            rows = self._query_sqlite(
                "SELECT data FROM pipeline_runs WHERE json_extract(data, '$.run_id') = ?",
                (run_id,),
            )
            return rows[0] if rows else None

        for run in reversed(self._json_runs):
            if run.get("run_id") == run_id:
                return run
        return None

    def get_summary(self, hours: int = 24) -> SummaryReport:
        """Aggregate metrics across recent runs."""
        self.initialize()
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

        runs = self._filter_runs(cutoff)
        if not runs:
            return SummaryReport(window_hours=hours, health="healthy")

        total = len(runs)
        failed = sum(1 for r in runs if r.get("error_count", 0) > 0 or r.get("node_count", 0) == 0)
        successful = total - failed
        error_rate = failed / total if total > 0 else 0.0
        avg_duration = sum(r.get("total_duration_ms", 0) for r in runs) / total
        avg_nodes = sum(r.get("node_count", 0) for r in runs) / total
        total_reviews = sum(r.get("human_review_count", 0) for r in runs)
        total_reruns = sum(r.get("re_run_count", 0) for r in runs)

        # Slowest nodes across all runs
        node_agg: dict[str, list[float]] = {}
        for run in runs:
            for timing in run.get("node_timings", []):
                name = timing.get("node_name", "?")
                node_agg.setdefault(name, []).append(timing.get("duration_ms", 0))
        slowest_nodes = sorted(
            [
                {
                    "node_name": name,
                    "avg_duration_ms": round(sum(times) / len(times), 1),
                    "max_duration_ms": round(max(times), 1),
                    "call_count": len(times),
                }
                for name, times in node_agg.items()
            ],
            key=lambda x: x["avg_duration_ms"],
            reverse=True,
        )[:5]

        # Health
        health = "healthy"
        if error_rate > 0.3:
            health = "critical"
        elif error_rate > 0.1:
            health = "warn"

        return SummaryReport(
            total_runs=total,
            successful_runs=successful,
            failed_runs=failed,
            error_rate=round(error_rate, 3),
            avg_duration_ms=round(avg_duration, 1),
            avg_node_count=round(avg_nodes, 1),
            total_human_reviews=total_reviews,
            total_re_runs=total_reruns,
            slowest_nodes=slowest_nodes,
            window_hours=hours,
            health=health,
        )

    def check_health(self, hours: int = 24) -> HealthStatus:
        """Run health checks and return alert levels."""
        self.initialize()
        summary = self.get_summary(hours=hours)
        status = HealthStatus()

        checks: list[dict[str, Any]] = []

        # 1. Error rate
        if summary.error_rate > 0.3:
            checks.append({
                "name": "error_rate_high",
                "level": "critical",
                "message": f"Error rate {summary.error_rate:.1%} exceeds 30%",
            })
        elif summary.error_rate > 0.1:
            checks.append({
                "name": "error_rate_elevated",
                "level": "warn",
                "message": f"Error rate {summary.error_rate:.1%} exceeds 10%",
            })

        # 2. Consecutive failures (last 5 runs)
        recent = self.list_runs(limit=5)
        consecutive_failures = 0
        for run in recent:
            if run.get("error_count", 0) > 0:
                consecutive_failures += 1
            else:
                break
        if consecutive_failures >= 5:
            checks.append({
                "name": "consecutive_failures",
                "level": "critical",
                "message": f"{consecutive_failures} consecutive runs failed",
            })
        elif consecutive_failures >= 3:
            checks.append({
                "name": "consecutive_failures",
                "level": "warn",
                "message": f"{consecutive_failures} consecutive runs failed",
            })

        # 3. Slowest node average (check critical first, then warn)
        for node in summary.slowest_nodes:
            if node["avg_duration_ms"] > 60_000:
                checks.append({
                    "name": "slow_node",
                    "level": "critical",
                    "message": f"Node '{node['node_name']}' avg {node['avg_duration_ms']}ms exceeds 60s",
                })
            elif node["avg_duration_ms"] > 30_000:
                checks.append({
                    "name": "slow_node",
                    "level": "warn",
                    "message": f"Node '{node['node_name']}' avg {node['avg_duration_ms']}ms exceeds 30s",
                })

        # 4. Re-run rate (only meaningful with 3+ runs)
        if summary.total_runs >= 3 and summary.total_re_runs / summary.total_runs > 0.5:
            checks.append({
                "name": "high_rerun_rate",
                "level": "warn",
                "message": f"Re-run rate {summary.total_re_runs}/{summary.total_runs} exceeds 50%",
            })

        # Compute overall level
        if any(c["level"] == "critical" for c in checks):
            status.level = "critical"
            status.summary = f"{len([c for c in checks if c['level'] == 'critical'])} critical, {len([c for c in checks if c['level'] == 'warn'])} warning(s)"
        elif any(c["level"] == "warn" for c in checks):
            status.level = "warn"
            status.summary = f"{len(checks)} warning(s)"
        elif not checks:
            status.summary = f"All checks passed ({summary.total_runs} runs in {hours}h)"

        status.checks = checks
        return status

    def count_runs(self, hours: int = 24) -> int:
        """Quick count without loading full data."""
        self.initialize()
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        return len(self._filter_runs(cutoff))

    # ── JSON Backend ──

    def _init_json(self) -> None:
        self._json_runs = []
        if self._path:
            p = Path(self._path)
            if p.exists():
                try:
                    with open(p) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        self._json_runs = data
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("metrics: json load failed, starting fresh", error=str(e))

    def _save_json(self, run_data: dict[str, Any]) -> None:
        self._json_runs.append(run_data)
        if self._path:
            try:
                p = Path(self._path)
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w") as f:
                    json.dump(self._json_runs, f, default=str, indent=2)
            except OSError as e:
                logger.warning("metrics: json save failed", error=str(e))

    # ── SQLite Backend ──

    def _init_sqlite(self) -> None:
        self._conn = sqlite3.connect(self._path or ":memory:")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def _save_sqlite(self, run_data: dict[str, Any]) -> None:
        if not self._conn:
            raise RuntimeError("SQLite not initialized")
        self._conn.execute(
            "INSERT INTO pipeline_runs (data) VALUES (?)",
            (json.dumps(run_data, default=str),),
        )
        self._conn.commit()

    def _query_sqlite(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        if not self._conn or not self._initialized:
            return []
        return self._rows_to_dicts(
            self._conn.execute("SELECT data FROM pipeline_runs ORDER BY rowid DESC LIMIT ? OFFSET ?", params)
            if "LIMIT" in sql
            else self._conn.execute(sql, params)
        )

    @staticmethod
    def _rows_to_dicts(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
        return [json.loads(row[0]) for row in cursor.fetchall()]

    # ── Shared Helpers ──

    def _filter_runs(self, cutoff: str) -> list[dict[str, Any]]:
        """Filter runs newer than cutoff timestamp."""
        if self._backend == "sqlite":
            rows = self._conn.execute(
                "SELECT data FROM pipeline_runs WHERE json_extract(data, '$.started_at') >= ? ORDER BY rowid DESC",
                (cutoff,),
            )
            return self._rows_to_dicts(rows)

        return [
            r for r in reversed(self._json_runs)
            if r.get("started_at", "") >= cutoff
        ]

    def __len__(self) -> int:
        """Number of stored runs."""
        if self._backend == "sqlite" and self._conn:
            return self._conn.execute("SELECT COUNT(*) FROM pipeline_runs").fetchone()[0]
        return len(self._json_runs)

    def clear(self) -> None:
        """Clear all stored data (testing convenience)."""
        if self._backend == "sqlite" and self._conn:
            self._conn.execute("DELETE FROM pipeline_runs")
            self._conn.commit()
        else:
            self._json_runs = []
            if self._path:
                Path(self._path).unlink(missing_ok=True)
