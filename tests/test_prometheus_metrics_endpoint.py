from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client():
    from src.api import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


class TestPrometheusEndpoint:

    async def test_metrics_endpoint_no_auth_required(self, client):
        r = await client.get("/metrics")
        assert r.status_code == 200

    async def test_metrics_returns_prometheus_content_type(self, client):
        r = await client.get("/metrics")
        ct = r.headers.get("content-type", "")
        assert "text/plain" in ct
        assert "version=" in ct

    async def test_metrics_body_is_prometheus_text_format(self, client):
        r = await client.get("/metrics")
        body = r.text
        assert "# HELP" in body
        assert "# TYPE" in body

    async def test_known_metrics_present_in_output(self, client):
        await client.get("/health")
        r = await client.get("/metrics")
        body = r.text
        expected = [
            "pipeline_runs_total",
            "step_duration_seconds",
            "api_requests_total",
            "api_request_duration_seconds",
            "active_background_tasks",
        ]
        for metric in expected:
            assert metric in body, f"missing metric in /metrics output: {metric}"

    async def test_metrics_does_not_collide_with_video_metrics_route(self, client):
        from src.api import app
        from src.routers._deps import verify_api_key

        async def _ok() -> str:
            return "test"

        app.dependency_overrides[verify_api_key] = _ok
        try:
            r1 = await client.get("/metrics")
            assert r1.status_code == 200
            assert "active_background_tasks" in r1.text

            r2 = await client.get("/metrics/abc-video-id")
            assert r2.status_code in (200, 503)
            if r2.status_code == 200:
                body = r2.json()
                assert "video_id" in body or "metrics" in body
        finally:
            app.dependency_overrides.clear()

    async def test_http_metrics_use_route_template_not_raw_identifier(self, client):
        await client.get("/metrics/raw-video-identifier")
        body = (await client.get("/metrics")).text

        assert 'route="/metrics/{video_id}"' in body
        assert 'route="/metrics/raw-video-identifier"' not in body
        assert 'status_class="4xx"' in body or 'status_class="5xx"' in body
