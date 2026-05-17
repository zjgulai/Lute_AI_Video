from __future__ import annotations

from fastapi import APIRouter, Response

from src.telemetry_prometheus import prometheus_content

router = APIRouter()


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    body, content_type = prometheus_content()
    return Response(content=body, media_type=content_type)
