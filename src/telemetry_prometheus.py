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

active_pipelines = Gauge(
    "active_pipelines",
    "Currently running pipelines (incremented by caller)",
)


# ── External LLM API metrics (MASTER-PLAN TODO-C4 + C5, 2026-05-16) ──

llm_api_errors_total = Counter(
    "llm_api_errors_total",
    "Total errors from external LLM/media API calls, partitioned by provider",
    ["provider", "error_kind"],
)

llm_api_duration_seconds = Histogram(
    "llm_api_duration_seconds",
    "External LLM/media API call duration, partitioned by provider",
    ["provider"],
    buckets=[0.5, 1, 2, 5, 10, 30, 60, 120, 300],
)


# ── DB pool metrics (MASTER-PLAN TODO-C6, 2026-05-16) ──

db_pool_available_connections = Gauge(
    "db_pool_available_connections",
    "Free asyncpg connections in the pool (PG only). 0 = saturation.",
)

db_pool_size = Gauge(
    "db_pool_size",
    "Configured maximum pool size for asyncpg.",
)


# ── Admin / tenant metrics (MASTER-PLAN TODO-C7, 2026-05-16) ──

admin_login_attempts_total = Counter(
    "admin_login_attempts_total",
    "Admin panel login attempts, partitioned by outcome",
    ["outcome"],
)

tenant_active_count = Gauge(
    "tenant_active_count",
    "Currently active (non-disabled) tenants in the system",
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


def record_llm_call(
    provider: str,
    duration_sec: float,
    success: bool,
    error_kind: str | None = None,
) -> None:
    """Record an external LLM/media API call. provider: 'deepseek'|'poyo'|'siliconflow'|'openai'|etc."""
    llm_api_duration_seconds.labels(provider=provider).observe(duration_sec)
    if not success:
        llm_api_errors_total.labels(
            provider=provider,
            error_kind=error_kind or "unknown",
        ).inc()


def record_admin_login(outcome: str) -> None:
    """Record an admin login attempt. outcome: 'success'|'invalid_creds'|'rate_limited'|'db_error'."""
    admin_login_attempts_total.labels(outcome=outcome).inc()


def update_db_pool_stats(available: int, size: int) -> None:
    """Update DB pool gauges. Called periodically by background task or on each acquire."""
    db_pool_available_connections.set(available)
    db_pool_size.set(size)


def update_tenant_active_count(count: int) -> None:
    """Update the active tenant gauge. Called by tenant CRUD events or periodic refresh."""
    tenant_active_count.set(count)


def prometheus_content() -> tuple[bytes, str]:
    """Return (body, content_type) for Prometheus scrape endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
