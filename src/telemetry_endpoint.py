"""FastAPI router for telemetry endpoints.

Exposes:
- GET /telemetry/metrics — returns PipelineMetrics summary
- GET /telemetry/errors?label={label} — returns ErrorCollector errors

This router is designed to be mounted by another agent in src/api.py.
"""

from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Query

    HAS_FASTAPI = True
except ImportError:
    APIRouter = None  # type: ignore
    Query = None  # type: ignore
    HAS_FASTAPI = False

from src.telemetry import error_collector, pipeline_metrics

router = APIRouter(prefix="/telemetry", tags=["telemetry"]) if HAS_FASTAPI else None

if HAS_FASTAPI and router is not None:

    @router.get("/metrics")
    async def get_metrics() -> dict[str, Any]:
        """Return PipelineMetrics summary."""
        return pipeline_metrics.get_summary()

    @router.get("/errors")
    async def get_errors(
        label: str | None = Query(None, description="Filter errors by pipeline label"),
    ) -> dict[str, Any]:
        """Return ErrorCollector errors, optionally filtered by label."""
        errors = error_collector.get_errors(label=label)
        return {
            "errors": errors,
            "count": len(errors),
            "label_filter": label,
        }
