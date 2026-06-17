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
    assert resp["videos"] == []
    assert resp["scenarios"] == []
    assert resp["platforms"] == []


@pytest.mark.asyncio
async def test_dashboard_overview_returns_frontend_contract(monkeypatch):
    """The API shape must match PerformanceDashboard's videos/scenarios/platforms contract."""
    from src.routers import metrics as metrics_router

    class _FakeRepo:
        async def get_dashboard_overview(self, scenario=None, platform=None, days=7, tenant_id=None):
            return [
                {
                    "video_id": "video-1",
                    "scenario": "S1",
                    "platform": "tiktok",
                    "metrics": {
                        "title": "Launch clip",
                        "ctr": 0.12,
                        "cvr": 0.04,
                        "watch_rate": 0.73,
                        "followers_gained": 10,
                        "sales": 3,
                        "views": 1000,
                    },
                },
                {
                    "video_id": "video-2",
                    "scenario": "S1",
                    "platform": "shopify",
                    "metrics": {
                        "ctr": "0.08",
                        "cvr": "0.02",
                        "watch_rate": "0.67",
                        "followers_gained": None,
                        "sales": 5,
                        "views": 500,
                    },
                },
            ]

    def _fake_ctor(self=None):
        return _FakeRepo()

    from src.storage import metrics_repository

    monkeypatch.setattr(metrics_repository, "VideoMetricsRepository", _fake_ctor)
    monkeypatch.setattr(metrics_router, "HAS_STORAGE", True)

    resp = await metrics_router.get_dashboard_overview(days=7)

    assert resp["data"][0]["video_id"] == "video-1"
    assert resp["videos"] == [
        {
            "video_id": "video-1",
            "title": "Launch clip",
            "scenario": "S1",
            "platform": "tiktok",
            "ctr": 0.12,
            "cvr": 0.04,
            "watch_rate": 0.73,
            "followers_gained": 10.0,
            "sales": 3.0,
            "views": 1000.0,
        },
        {
            "video_id": "video-2",
            "title": "video-2",
            "scenario": "S1",
            "platform": "shopify",
            "ctr": 0.08,
            "cvr": 0.02,
            "watch_rate": 0.67,
            "followers_gained": 0.0,
            "sales": 5.0,
            "views": 500.0,
        },
    ]
    assert resp["scenarios"] == [
        {
            "scenario": "S1",
            "avg_watch_rate": 0.7,
            "avg_ctr": 0.1,
            "avg_cvr": 0.03,
            "total_videos": 2,
            "total_sales": 8.0,
        }
    ]
    assert {p["platform"] for p in resp["platforms"]} == {"shopify", "tiktok"}
    tiktok = next(p for p in resp["platforms"] if p["platform"] == "tiktok")
    assert tiktok["scenario_breakdown"]["S1"] == {
        "avg_watch_rate": 0.73,
        "avg_ctr": 0.12,
        "avg_cvr": 0.04,
    }


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


@pytest.mark.asyncio
async def test_metrics_pull_disabled_by_default(monkeypatch):
    from fastapi import HTTPException

    from src import config
    from src.routers import metrics as metrics_router

    monkeypatch.setattr(metrics_router, "HAS_STORAGE", True)
    monkeypatch.setattr(config, "METRICS_PULL_ENABLED", False)

    with pytest.raises(HTTPException) as exc_info:
        await metrics_router.trigger_metrics_pull()

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Metrics pull is disabled"


@pytest.mark.asyncio
async def test_metrics_pull_enabled_invokes_poller(monkeypatch):
    from src import config
    from src.routers import metrics as metrics_router
    from src.tasks import metrics_poller

    monkeypatch.setattr(metrics_router, "HAS_STORAGE", True)
    monkeypatch.setattr(config, "METRICS_PULL_ENABLED", True)

    calls = 0

    class _FakePoller:
        async def pull_all(self) -> None:
            nonlocal calls
            calls += 1

    monkeypatch.setattr(metrics_poller, "MetricsPoller", _FakePoller)

    resp = await metrics_router.trigger_metrics_pull()

    assert calls == 1
    assert resp == {"status": "ok", "message": "Metrics pull triggered successfully"}
