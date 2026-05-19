"""Smoke tests for /metrics/* and /dashboard/overview endpoints.

Confirms the metrics router returns sensible empty responses when the
video_metrics table exists but has no rows, and 503 when HAS_STORAGE
is False. Does NOT test the MetricsPoller scheduling path (that's
explicit Sprint 2 scope in NEXT-STEPS-2026-05-11.md).
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_dashboard_overview_returns_empty_list_when_no_metrics(monkeypatch):
    """When the video_metrics table is empty, /dashboard/overview returns
    scenario=None, platform=None, days=7, metrics=[] (empty list)."""
    from src.routers import metrics as metrics_router

    class _FakeRepo:
        async def get_dashboard_overview(self, scenario=None, platform=None, days=7, tenant_id=None):
            return []

    def _fake_ctor(self=None):
        return _FakeRepo()

    from src.storage import metrics_repository

    monkeypatch.setattr(metrics_repository, "VideoMetricsRepository", _fake_ctor)
    monkeypatch.setattr(metrics_router, "HAS_STORAGE", True)

    resp = await metrics_router.get_dashboard_overview(days=7)
    assert resp["scenario"] is None
    assert resp["platform"] is None
    assert resp["days"] == 7
    assert resp["data"] == []


@pytest.mark.asyncio
async def test_dashboard_overview_503_when_storage_disabled(monkeypatch):
    from fastapi import HTTPException

    from src.routers import metrics as metrics_router

    monkeypatch.setattr(metrics_router, "HAS_STORAGE", False)

    with pytest.raises(HTTPException) as exc_info:
        await metrics_router.get_dashboard_overview(days=7)
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_video_metrics_503_when_storage_disabled(monkeypatch):
    from fastapi import HTTPException

    from src.routers import metrics as metrics_router

    monkeypatch.setattr(metrics_router, "HAS_STORAGE", False)

    with pytest.raises(HTTPException) as exc_info:
        await metrics_router.get_video_metrics("v_123", platform="tiktok")
    assert exc_info.value.status_code == 503
