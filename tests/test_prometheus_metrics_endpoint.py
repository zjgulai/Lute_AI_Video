from __future__ import annotations

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from src.api import app

    return TestClient(app)


class TestPrometheusEndpoint:

    def test_metrics_endpoint_no_auth_required(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200

    def test_metrics_returns_prometheus_content_type(self, client):
        r = client.get("/metrics")
        ct = r.headers.get("content-type", "")
        assert "text/plain" in ct
        assert "version=" in ct

    def test_metrics_body_is_prometheus_text_format(self, client):
        r = client.get("/metrics")
        body = r.text
        assert "# HELP" in body
        assert "# TYPE" in body

    def test_known_metrics_present_in_output(self, client):
        r = client.get("/metrics")
        body = r.text
        expected = [
            "pipeline_runs_total",
            "step_duration_seconds",
            "active_pipelines",
            "llm_api_errors_total",
            "llm_api_duration_seconds",
            "db_pool_available_connections",
            "admin_login_attempts_total",
            "tenant_active_count",
        ]
        for metric in expected:
            assert metric in body, f"missing metric in /metrics output: {metric}"

    def test_metrics_does_not_collide_with_video_metrics_route(self, client):
        from src.routers._deps import verify_api_key

        from src.api import app

        async def _ok() -> str:
            return "test"

        app.dependency_overrides[verify_api_key] = _ok
        try:
            r1 = client.get("/metrics")
            assert r1.status_code == 200
            assert "active_pipelines" in r1.text

            r2 = client.get("/metrics/abc-video-id")
            assert r2.status_code in (200, 503)
            if r2.status_code == 200:
                body = r2.json()
                assert "video_id" in body or "metrics" in body
        finally:
            app.dependency_overrides.clear()
