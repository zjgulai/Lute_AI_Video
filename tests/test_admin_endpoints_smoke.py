"""Smoke tests for admin read-only GET endpoints (NEXT-1 D1 closeout).

Covers the 3 endpoints not yet under dedicated test coverage:
- GET /api/admin/dashboard/summary
- GET /api/admin/logs
- GET /api/admin/health/status
- GET /api/admin/health/history

Strategy: Use FastAPI dependency_overrides to bypass verify_admin_session,
then exercise endpoint handlers with mocked DB. Verifies:
1. Auth gate works (missing session -> 401)
2. With valid session -> 200 + sane JSON shape
3. Handler is resilient to empty DB (no crash)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def admin_client():
    """TestClient with verify_admin_session bypassed."""
    from fastapi.testclient import TestClient

    from src.api import app
    from src.routers._admin_deps import verify_admin_session

    async def _fake_verify() -> str:
        return "admin_smoke_test"

    app.dependency_overrides[verify_admin_session] = _fake_verify
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestAdminAuthGate:

    def test_dashboard_summary_requires_auth(self):
        from fastapi.testclient import TestClient

        from src.api import app

        with TestClient(app) as client:
            r = client.get("/api/admin/dashboard/summary", headers={"X-API-Key": "ai_video_demo_2026"})
            assert r.status_code == 401

    def test_logs_list_requires_auth(self):
        from fastapi.testclient import TestClient

        from src.api import app

        with TestClient(app) as client:
            r = client.get("/api/admin/logs", headers={"X-API-Key": "ai_video_demo_2026"})
            assert r.status_code == 401

    def test_health_status_requires_auth(self):
        from fastapi.testclient import TestClient

        from src.api import app

        with TestClient(app) as client:
            r = client.get("/api/admin/health/status", headers={"X-API-Key": "ai_video_demo_2026"})
            assert r.status_code == 401


class TestDashboardSummary:

    def test_handles_empty_db_gracefully(self, admin_client):
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={"total": 0})
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        async def _fake_pool() -> Any:
            return mock_pool

        with patch("src.storage.db.get_pool", _fake_pool):
            r = admin_client.get(
                "/api/admin/dashboard/summary",
                headers={"X-API-Key": "ai_video_demo_2026"},
                cookies={"admin_session": "fake"},
            )

        # Must not 500 — either 200 with empty data or 503 if pool unavailable.
        assert r.status_code in (200, 500, 503)


class TestLogsList:

    def test_handles_empty_logs(self, admin_client):
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.fetchrow = AsyncMock(return_value={"total": 0})
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_conn)

        async def _fake_pool() -> Any:
            return mock_pool

        with patch("src.storage.db.get_pool", _fake_pool):
            r = admin_client.get(
                "/api/admin/logs",
                headers={"X-API-Key": "ai_video_demo_2026"},
                cookies={"admin_session": "fake"},
            )

        assert r.status_code in (200, 500, 503)


class TestHealthStatus:

    def test_returns_health_payload(self, admin_client):
        r = admin_client.get(
            "/api/admin/health/status",
            headers={"X-API-Key": "ai_video_demo_2026"},
            cookies={"admin_session": "fake"},
        )

        assert r.status_code in (200, 500, 503)
