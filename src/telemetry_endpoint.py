"""FastAPI router for telemetry endpoints.

Exposes:
- GET /telemetry/metrics — returns PipelineMetrics summary
- GET /telemetry/errors?label={label} — returns ErrorCollector errors

This router is designed to be mounted by another agent in src/api.py.
"""

from __future__ import annotations

from typing import Any, cast

try:
    from fastapi import APIRouter as _APIRouter, Query as _Query

    HAS_FASTAPI = True
except ImportError:
    _APIRouter = None  # type: ignore[misc,assignment]
    _Query = None  # type: ignore[misc,assignment]
    HAS_FASTAPI = False

from src.telemetry import error_collector, pipeline_metrics

router = cast("APIRouter", _APIRouter(prefix="/telemetry", tags=["telemetry"])) if HAS_FASTAPI else None  # type: ignore[valid-type]

if HAS_FASTAPI and router is not None:
    _router = router

    @_router.get("/metrics")
    async def get_metrics() -> dict[str, Any]:
        """Return PipelineMetrics summary."""
        return pipeline_metrics.get_summary()

    @_router.get("/errors")
    async def get_errors(
        label: str | None = cast("Any", _Query)(None, description="Filter errors by pipeline label"),  # type: ignore[operator]
    ) -> dict[str, Any]:
        """Return ErrorCollector errors, optionally filtered by label."""
        errors = error_collector.get_errors(label=label)
        return {
            "errors": errors,
            "count": len(errors),
            "label_filter": label,
        }

    @_router.get("/prometheus")
    async def get_prometheus() -> Any:
        """Return Prometheus exposition format metrics for Grafana scraping."""
        from fastapi import Response
        from src.telemetry_prometheus import prometheus_content

        body, content_type = prometheus_content()
        return Response(content=body, media_type=content_type)
