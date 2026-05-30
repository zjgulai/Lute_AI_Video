"""Centralized telemetry — request-level tracing, pipeline metrics, and error collection.

Provides:
- generate_trace_id(): generates short UUID4 trace IDs (8 chars)
- TraceContext: dataclass for trace context with trace_id, request_path, started_at
- with_trace(): async context manager that yields a TraceContext
- log_with_trace(): wrapper that adds trace_id to every log call
- PipelineMetrics: per-step and per-pipeline timing, success/fail counters, cumulative stats
- ErrorCollector: structured error collection with FIFO (last 100)

All storage is in-memory (dict/list). No external DB needed yet.
"""

from __future__ import annotations

import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog

from src.models.runtime_contracts import TelemetryErrorEntry, TelemetryStepStats, TelemetrySummary

logger = structlog.get_logger()

# ── Trace ID generation ──


def generate_trace_id() -> str:
    """Generate a UUID4 short string (8 chars)."""
    return uuid.uuid4().hex[:8]


# ── PipelineMetrics ──


@dataclass
class StepMetric:
    """Metric for a single step execution."""

    step_name: str
    duration_ms: float
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class PipelineMetric:
    """Metric for a full pipeline run."""

    scenario: str
    total_duration_ms: float
    success: bool
    error_count: int
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class PipelineMetrics:
    """In-memory pipeline metrics collector.

    Records per-step and per-pipeline metrics with aggregated stats.
    """

    def __init__(self) -> None:
        self._step_metrics: dict[str, list[StepMetric]] = {}
        self._pipeline_metrics: dict[str, list[PipelineMetric]] = {}
        self._lock = None  # No threading lock needed for async; use simple dict

    def record_step(self, label: str, step_name: str, duration_ms: float, success: bool) -> None:
        """Record a single step execution metric.

        Args:
            label: pipeline run label
            step_name: name of the step
            duration_ms: execution duration in milliseconds
            success: whether the step succeeded
        """
        if label not in self._step_metrics:
            self._step_metrics[label] = []
        self._step_metrics[label].append(
            StepMetric(step_name=step_name, duration_ms=duration_ms, success=success)
        )
        # P4-2: Mirror to Prometheus
        try:
            from src.telemetry_prometheus import record_step_run
            record_step_run(
                scenario=label.split("_")[0] if "_" in label else "unknown",
                step=step_name,
                duration_sec=duration_ms / 1000.0,
                success=success,
            )
        except Exception as exc:
            logger.debug(
                "telemetry: prometheus step metric failed",
                label=label,
                step=step_name,
                error=str(exc)[:200],
            )

    def record_pipeline(
        self,
        label: str,
        scenario: str,
        total_duration_ms: float,
        success: bool,
        error_count: int,
    ) -> None:
        """Record a full pipeline run metric.

        Args:
            label: pipeline run label
            scenario: pipeline scenario (e.g. "product_direct", "brand_campaign")
            total_duration_ms: total execution duration in milliseconds
            success: whether the pipeline succeeded
            error_count: number of errors encountered
        """
        if label not in self._pipeline_metrics:
            self._pipeline_metrics[label] = []
        self._pipeline_metrics[label].append(
            PipelineMetric(
                scenario=scenario,
                total_duration_ms=total_duration_ms,
                success=success,
                error_count=error_count,
            )
        )
        # P4-2: Mirror to Prometheus
        try:
            from src.telemetry_prometheus import record_pipeline_run
            record_pipeline_run(
                scenario=scenario,
                duration_sec=total_duration_ms / 1000.0,
                success=success,
                error_count=error_count,
            )
        except Exception as exc:
            logger.debug(
                "telemetry: prometheus pipeline metric failed",
                label=label,
                scenario=scenario,
                error=str(exc)[:200],
            )

    def get_summary(self) -> TelemetrySummary:
        """Return aggregated stats for all recorded metrics.

        Returns:
            dict with total_runs, avg_duration_ms, success_rate, per_step_stats
        """
        total_runs = 0
        total_duration = 0.0
        total_success = 0
        total_errors = 0

        for label, metrics in self._pipeline_metrics.items():
            for m in metrics:
                total_runs += 1
                total_duration += m.total_duration_ms
                if m.success:
                    total_success += 1
                total_errors += m.error_count

        avg_duration = total_duration / total_runs if total_runs > 0 else 0.0
        success_rate = total_success / total_runs if total_runs > 0 else 0.0

        # Per-step stats
        per_step_stats: dict[str, TelemetryStepStats] = {}
        for label, steps in self._step_metrics.items():
            for s in steps:
                if s.step_name not in per_step_stats:
                    per_step_stats[s.step_name] = {
                        "total_executions": 0,
                        "success_count": 0,
                        "failure_count": 0,
                        "avg_duration_ms": 0.0,
                        "total_duration_ms": 0.0,
                    }
                stats = per_step_stats[s.step_name]
                stats["total_executions"] += 1
                if s.success:
                    stats["success_count"] += 1
                else:
                    stats["failure_count"] += 1
                stats["total_duration_ms"] += s.duration_ms
                stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["total_executions"]

        return {
            "total_runs": total_runs,
            "avg_duration_ms": round(avg_duration, 2),
            "success_rate": round(success_rate, 4),
            "total_errors": total_errors,
            "per_step_stats": per_step_stats,
            "labels": list(self._pipeline_metrics.keys()),
        }


# ── Error Persistence (Admin Panel Phase 1) ──


def _persist_error_to_db(
    label: str,
    step: str,
    error: str,
    context: dict[str, Any],
) -> None:
    """Fire-and-forget persistence to error_logs table.

    Called from ErrorCollector.collect() — never raises, never blocks.
    If the admin error_logs table doesn't exist yet (migration not run),
    this silently skips.
    """
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        loop.create_task(
            _persist_error_async(label, step, error, context)
        )
    except Exception as exc:
        logger.warning(
            "telemetry: error log persistence scheduling failed",
            label=label,
            step=step,
            error=str(exc)[:200],
        )


async def _persist_error_async(
    label: str,
    step: str,
    error: str,
    context: dict[str, Any],
) -> None:
    """Async DB insert for error log persistence."""
    try:
        from src.storage.db import get_pool, is_pg_available

        if not is_pg_available():
            return

        tenant_id = context.get("tenant_id")
        scenario = context.get("scenario")
        error_code = context.get("error_code", "UNKNOWN")
        traceback_text = context.get("traceback")

        pool = await get_pool()
        assert pool is not None
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO error_logs
                    (tenant_id, scenario, error_code, message, traceback)
                VALUES ($1, $2, $3, $4, $5)
                """,
                tenant_id,
                scenario,
                error_code,
                error[:2000],  # Truncate very long messages
                traceback_text[:5000] if traceback_text else None,
            )
    except Exception as exc:
        logger.warning(
            "telemetry: error log persistence failed",
            label=label,
            step=step,
            error=str(exc)[:200],
        )


# ── ErrorCollector ──


class ErrorCollector:
    """Structured error collector with FIFO (last 100 errors).

    Thread-safe for single-threaded async usage.
    """

    _MAX_ERRORS = 100

    def __init__(self) -> None:
        self._errors: deque[TelemetryErrorEntry] = deque(maxlen=self._MAX_ERRORS)

    def collect(
        self,
        label: str,
        trace_id: str,
        step: str,
        error: str,
        context: dict[str, Any],
    ) -> None:
        """Store a structured error.

        Args:
            label: pipeline run label
            trace_id: trace ID
            step: step/node name where error occurred
            error: error message
            context: additional context dict
        """
        timestamp = datetime.now(UTC)
        self._errors.append(
            {
                "label": label,
                "trace_id": trace_id,
                "step": step,
                "error": error,
                "context": dict(context),
                "timestamp": timestamp.isoformat(),
            }
        )
        # Persist to admin error_logs table (fire-and-forget, never blocks)
        _persist_error_to_db(label, step, error, dict(context))

    def get_errors(self, label: str | None = None) -> list[TelemetryErrorEntry]:
        """Return filtered errors.

        Args:
            label: optional label to filter by. If None, returns all errors.

        Returns:
            list of error dicts
        """
        errors_list = list(self._errors)
        if label is not None:
            errors_list = [e for e in errors_list if e["label"] == label]
        return errors_list


# ── Node timing decorator ──


def timed_node(func):
    """Decorator that records execution time and errors for pipeline nodes.

    Supports both sync and async functions. Usage:
        @timed_node
        def strategy_node(state):
            ...

        @timed_node
        async def async_node(state):
            ...
    """
    import asyncio
    import functools

    @functools.wraps(func)
    def wrapper(state: dict[str, Any], *args, **kwargs) -> Any:
        node_name = func.__name__
        trace_id = state.get("trace_id", generate_trace_id())
        start = time.time()

        def _record(success: bool, exc: Exception | None = None) -> None:
            duration_ms = (time.time() - start) * 1000
            pipeline_metrics.record_step(
                label=trace_id,
                step_name=node_name,
                duration_ms=duration_ms,
                success=success,
            )
            if exc is not None:
                error_collector.collect(
                    label=trace_id,
                    trace_id=trace_id,
                    step=node_name,
                    error=str(exc),
                    context={"node": node_name},
                )

        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*a, **kw):
                try:
                    result = await func(*a, **kw)
                    _record(success=True)
                    return result
                except Exception as exc:
                    _record(success=False, exc=exc)
                    raise
            return async_wrapper(state, *args, **kwargs)
        else:
            try:
                result = func(state, *args, **kwargs)
                _record(success=True)
                return result
            except Exception as exc:
                _record(success=False, exc=exc)
                raise

    return wrapper


# ── Global singletons ──

# Shared instances for use across the application
pipeline_metrics = PipelineMetrics()
error_collector = ErrorCollector()
