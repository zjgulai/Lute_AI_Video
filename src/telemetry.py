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
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog


# ── Trace ID generation ──


def generate_trace_id() -> str:
    """Generate a UUID4 short string (8 chars)."""
    return uuid.uuid4().hex[:8]


# ── TraceContext dataclass ──


@dataclass
class TraceContext:
    """Request-level trace context."""

    trace_id: str
    request_path: str
    started_at: datetime


# ── Async context manager for tracing ──


@asynccontextmanager
async def with_trace(trace_id: str | None = None, request_path: str = "") -> TraceContext:
    """Async context manager that yields a TraceContext.

    Usage:
        async with with_trace(request_path="/pipeline/start") as ctx:
            ...
    """
    ctx = TraceContext(
        trace_id=trace_id or generate_trace_id(),
        request_path=request_path,
        started_at=datetime.now(timezone.utc),
    )
    try:
        yield ctx
    finally:
        pass


# ── Log with trace_id ──


def log_with_trace(logger, trace_id: str, event: str, **kwargs) -> None:
    """Wrapper that adds trace_id to every log call.

    Args:
        logger: structlog logger instance
        trace_id: trace ID to bind
        event: log event name
        **kwargs: additional log fields
    """
    logger.bind(trace_id=trace_id).info(event, **kwargs)


# ── PipelineMetrics ──


@dataclass
class StepMetric:
    """Metric for a single step execution."""

    step_name: str
    duration_ms: float
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PipelineMetric:
    """Metric for a full pipeline run."""

    scenario: str
    total_duration_ms: float
    success: bool
    error_count: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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

    def get_summary(self) -> dict[str, Any]:
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
        per_step_stats: dict[str, dict[str, Any]] = {}
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


# ── ErrorCollector ──


class ErrorCollector:
    """Structured error collector with FIFO (last 100 errors).

    Thread-safe for single-threaded async usage.
    """

    _MAX_ERRORS = 100

    def __init__(self) -> None:
        self._errors: deque[dict[str, Any]] = deque(maxlen=self._MAX_ERRORS)

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
        self._errors.append(
            {
                "label": label,
                "trace_id": trace_id,
                "step": step,
                "error": error,
                "context": dict(context),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def get_errors(self, label: str | None = None) -> list[dict[str, Any]]:
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

    Usage:
        @timed_node
        def strategy_node(state):
            ...
    """
    import functools

    @functools.wraps(func)
    def wrapper(state: dict, *args, **kwargs) -> dict:
        node_name = func.__name__
        trace_id = state.get("trace_id", generate_trace_id())
        start = time.time()
        try:
            result = func(state, *args, **kwargs)
            duration_ms = (time.time() - start) * 1000
            pipeline_metrics.record_step(
                label=trace_id,
                step_name=node_name,
                duration_ms=duration_ms,
                success=True,
            )
            return result
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000
            pipeline_metrics.record_step(
                label=trace_id,
                step_name=node_name,
                duration_ms=duration_ms,
                success=False,
            )
            error_collector.collect(
                label=trace_id,
                trace_id=trace_id,
                step=node_name,
                error=str(exc),
                context={"node": node_name},
            )
            raise

    return wrapper


# ── Global singletons ──

# Shared instances for use across the application
pipeline_metrics = PipelineMetrics()
error_collector = ErrorCollector()
