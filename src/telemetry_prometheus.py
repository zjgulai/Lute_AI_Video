"""Prometheus metrics exporter for pipeline observability.

Mirrors the in-memory PipelineMetrics into Prometheus counters/histograms/gauges
so Grafana can scrape and alert on SLOs.

Usage:
    from src.telemetry_prometheus import record_pipeline_run, record_step_run

    # In router after pipeline completes:
    record_pipeline_run(scenario="s1", duration_sec=120, success=True, error_count=0)

    # After each step:
    record_step_run(scenario="s1", step="strategy", duration_sec=5, success=True)

Scrape endpoint:
    GET /telemetry/prometheus → text/plain Prometheus exposition format
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
)

# ── Pipeline-level metrics ──

pipeline_runs_total = Counter(
    "pipeline_runs_total",
    "Total pipeline runs",
    ["scenario", "status"],
)

pipeline_duration_seconds = Histogram(
    "pipeline_duration_seconds",
    "Pipeline end-to-end duration",
    ["scenario"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1200, 1800, 3600],
)

pipeline_errors_total = Counter(
    "pipeline_errors_total",
    "Total errors across all pipelines",
    ["scenario"],
)

# ── Step-level metrics ──

step_duration_seconds = Histogram(
    "step_duration_seconds",
    "Individual step execution duration",
    ["scenario", "step"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300, 600],
)

step_failures_total = Counter(
    "step_failures_total",
    "Total step execution failures",
    ["scenario", "step"],
)

# ── Runtime gauges ──

# ── HTTP and task metrics with canonical low-cardinality labels ──

api_requests_total = Counter(
    "api_requests_total",
    "HTTP requests by method, route template, and status class",
    ["method", "route", "status_class"],
)

api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "HTTP request duration by method and route template",
    ["method", "route"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30],
)

active_background_tasks = Gauge(
    "active_background_tasks",
    "Tasks currently owned by the canonical background task registry",
)


# ── Convenience helpers ──


def record_pipeline_run(
    scenario: str,
    duration_sec: float,
    success: bool,
    error_count: int,
) -> None:
    """Record a completed pipeline run."""
    status = "success" if success else "failure"
    pipeline_runs_total.labels(scenario=scenario, status=status).inc()
    pipeline_duration_seconds.labels(scenario=scenario).observe(duration_sec)
    if error_count > 0:
        pipeline_errors_total.labels(scenario=scenario).inc(error_count)


def record_step_run(
    scenario: str,
    step: str,
    duration_sec: float,
    success: bool,
) -> None:
    """Record a completed step execution."""
    step_duration_seconds.labels(scenario=scenario, step=step).observe(duration_sec)
    if not success:
        step_failures_total.labels(scenario=scenario, step=step).inc()


def record_http_request(
    method: str,
    route: str,
    status_code: int,
    duration_sec: float,
) -> None:
    """Record one request using only bounded route-template labels."""
    normalized_method = method.upper()
    if normalized_method not in _HTTP_METHODS:
        normalized_method = "OTHER"
    status_class = f"{status_code // 100}xx" if 100 <= status_code <= 599 else "unknown"
    api_requests_total.labels(
        method=normalized_method,
        route=route,
        status_class=status_class,
    ).inc()
    api_request_duration_seconds.labels(method=normalized_method, route=route).observe(
        duration_sec
    )


def update_active_background_tasks(count: int) -> None:
    """Project the exact canonical registry size into Prometheus."""
    if count < 0:
        raise ValueError("active background task count cannot be negative")
    active_background_tasks.set(count)


def prometheus_content() -> tuple[bytes, str]:
    """Return (body, content_type) for Prometheus scrape endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
