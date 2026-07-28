"""Regression test for the private /health Remotion probe.

Bug: src/routers/health.py used to call RemotionRenderer.validate_environment()
unconditionally, which spawns `subprocess.run(['npx', 'remotion', '--version'])`
inside the backend container. Production backend has no node binary, so the
probe always returned `available=false` even when the dedicated rendering
service was healthy — misleading the SettingsPanel UI.

Fix: when `RENDERING_SERVICE_SOCKET` is set, the backend probes the service over
a Unix Domain Socket and surfaces the real node/remotion/ffmpeg status without
opening a renderer TCP attack surface.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


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
async def test_health_uses_uds_probe_when_rendering_service_socket_set(monkeypatch):
    """/health must UDS-probe rendering service, not spawn subprocess."""
    socket_path = "/run/rendering/rendering.sock"
    monkeypatch.setenv("RENDERING_SERVICE_SOCKET", socket_path)

    from src.routers import health

    payload = {
        "status": "ok",
        "node": "v22.1.0",
        "remotion": "4.0.420",
        "ffmpeg": True,
        "ffprobe": True,
        "chromium": True,
    }

    seen: dict[str, object] = {}

    class _FakeTransport:
        def __init__(self, *, uds: str) -> None:
            seen["uds"] = uds

    def _factory(*args, **kwargs):
        seen["base_url"] = kwargs.get("base_url")
        seen["transport"] = kwargs.get("transport")
        return _FakeAsyncClient(payload)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", _FakeTransport)

    # Block any subprocess fallback so the test fails loudly if HTTP path is skipped.
    import subprocess

    def _no_subprocess(*args, **kwargs):
        raise AssertionError(
            "subprocess.run should NOT be called when RENDERING_SERVICE_SOCKET is set"
        )

    monkeypatch.setattr(subprocess, "run", _no_subprocess)

    result = await health.health()

    assert result["status"] == "ok"
    remotion = result["remotion"]
    assert remotion["available"] is True, f"expected available=True, got {remotion}"
    assert remotion["node_version"] == "v22.1.0"
    assert remotion["remotion_version"] == "4.0.420"
    assert remotion["ffmpeg_ok"] is True
    assert remotion["ffprobe_ok"] is True
    assert remotion["rendering_service_transport"] == "unix_socket"
    assert seen["uds"] == socket_path
    assert seen["base_url"] == "http://rendering"


@pytest.mark.asyncio
async def test_health_probe_marks_unavailable_on_degraded_service(monkeypatch):
    """Degraded rendering service (e.g. ffmpeg missing) → available=false with reason."""
    monkeypatch.setenv("RENDERING_SERVICE_SOCKET", "/run/rendering/rendering.sock")

    from src.routers import health

    payload = {
        "status": "ok",
        "node": "v22.1.0",
        "remotion": "4.0.420",
        "ffmpeg": False,  # degraded
        "ffprobe": True,
        "chromium": True,
    }

    def _factory(*args, **kwargs):
        return _FakeAsyncClient(payload)

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    monkeypatch.setattr(
        httpx,
        "AsyncHTTPTransport",
        lambda **_: object(),
    )

    result = await health.health()
    remotion = result["remotion"]
    assert remotion["available"] is False
    assert remotion["ffmpeg_ok"] is False
    assert any("degraded" in s for s in remotion["issues"]), remotion["issues"]


@pytest.mark.asyncio
async def test_health_uds_probe_allows_renderer_cold_start_budget(monkeypatch):
    """The backend must not time out before the renderer's 20s health probe."""
    from src.routers import health

    payload = {
        "status": "ok",
        "node": "v22.1.0",
        "remotion": "4.0.420",
        "ffmpeg": True,
        "ffprobe": True,
        "chromium": True,
    }
    seen: dict[str, object] = {}

    class _SlowFakeAsyncClient(_FakeAsyncClient):
        async def get(self, _url: str) -> _FakeResponse:
            await asyncio.sleep(3.1)
            return _FakeResponse(self._payload, self._status_code)

    def _factory(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return _SlowFakeAsyncClient(payload)

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **_: object())

    result = await health._probe_rendering_service(
        "/run/rendering/rendering.sock"
    )

    assert seen["timeout"] == 25.0
    assert result["available"] is True
