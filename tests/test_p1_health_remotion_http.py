"""Regression test for /health remotion probe.

Bug: src/routers/health.py used to call RemotionRenderer.validate_environment()
unconditionally, which spawns `subprocess.run(['npx', 'remotion', '--version'])`
inside the backend container. Production backend has no node binary, so the
probe always returned `available=false` even when the dedicated `rendering:3001`
service was healthy — misleading the SettingsPanel UI.

Fix: when `RENDERING_SERVICE_URL` is set (production via docker-compose), the
/health endpoint now HTTP-probes that service's own /health and surfaces the
real node/remotion/ffmpeg status.
"""

from __future__ import annotations

import pytest
from typing import Any


class _FakeResponse:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """Stub httpx.AsyncClient that returns a canned response on .get()."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200, **_: object) -> None:
        self._payload = payload
        self._status_code = status_code

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, _url: str) -> _FakeResponse:
        return _FakeResponse(self._payload, self._status_code)


@pytest.mark.asyncio
async def test_health_uses_http_probe_when_rendering_service_url_set(monkeypatch):
    """/health must HTTP-probe rendering service, not spawn subprocess."""
    monkeypatch.setenv("RENDERING_SERVICE_URL", "http://rendering:3001")

    from src.routers import health

    payload = {
        "status": "ok",
        "node": "v22.1.0",
        "remotion": "4.0.420",
        "ffmpeg": True,
        "chromium": True,
        "output_dir": "/app/output",
    }

    def _factory(*args, **kwargs):
        return _FakeAsyncClient(payload)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _factory)

    # Block any subprocess fallback so the test fails loudly if HTTP path is skipped.
    import subprocess

    def _no_subprocess(*args, **kwargs):
        raise AssertionError(
            "subprocess.run should NOT be called when RENDERING_SERVICE_URL is set"
        )

    monkeypatch.setattr(subprocess, "run", _no_subprocess)

    result = await health.health()

    assert result["status"] == "ok"
    remotion = result["remotion"]
    assert remotion["available"] is True, f"expected available=True, got {remotion}"
    assert remotion["node_version"] == "v22.1.0"
    assert remotion["remotion_version"] == "4.0.420"
    assert remotion["ffmpeg_ok"] is True
    assert remotion["rendering_service_url"] == "http://rendering:3001"


@pytest.mark.asyncio
async def test_health_probe_marks_unavailable_on_degraded_service(monkeypatch):
    """Degraded rendering service (e.g. ffmpeg missing) → available=false with reason."""
    monkeypatch.setenv("RENDERING_SERVICE_URL", "http://rendering:3001")

    from src.routers import health

    payload = {
        "status": "ok",
        "node": "v22.1.0",
        "remotion": "4.0.420",
        "ffmpeg": False,  # degraded
        "chromium": True,
        "output_dir": "/app/output",
    }

    def _factory(*args, **kwargs):
        return _FakeAsyncClient(payload)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _factory)

    result = await health.health()
    remotion = result["remotion"]
    assert remotion["available"] is False
    assert remotion["ffmpeg_ok"] is False
    assert any("degraded" in s for s in remotion["issues"]), remotion["issues"]
