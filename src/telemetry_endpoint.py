"""FastAPI router for telemetry endpoints.

Exposes:
- GET /telemetry/metrics — returns PipelineMetrics summary
- GET /telemetry/errors?label={label} — returns ErrorCollector errors

This router is designed to be mounted by another agent in src/api.py.
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter as _APIRouter
    from fastapi import Query as _Query

    HAS_FASTAPI = True
except ImportError:
    _APIRouter = None
    _Query = None
    HAS_FASTAPI = False

from src.models.runtime_contracts import TelemetryErrorsResponse, TelemetrySummary
from src.telemetry import error_collector, pipeline_metrics

if HAS_FASTAPI:
    assert _APIRouter is not None
    assert _Query is not None
    router = _APIRouter(prefix="/telemetry", tags=["telemetry"])

    @router.get("/metrics")
    async def get_metrics() -> TelemetrySummary:
        """Return PipelineMetrics summary."""
        return pipeline_metrics.get_summary()

    @router.get("/errors")
    async def get_errors(
        label: str | None = _Query(None, description="Filter errors by pipeline label"),
    ) -> TelemetryErrorsResponse:
        """Return ErrorCollector errors, optionally filtered by label."""
        errors = error_collector.get_errors(label=label)
        return {
            "errors": errors,
            "count": len(errors),
            "label_filter": label,
        }

    @router.get("/prometheus")
    async def get_prometheus() -> Any:
        """Return Prometheus exposition format metrics for Grafana scraping."""
        from fastapi import Response

        from src.telemetry_prometheus import prometheus_content

        body, content_type = prometheus_content()
        return Response(content=body, media_type=content_type)
else:
    router = None
