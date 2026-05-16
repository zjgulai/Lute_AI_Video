"""health router — extracted from api.py (P1-11)."""

import os
from typing import Any

from fastapi import APIRouter

try:
    from src.storage.db import (  # noqa: F401  # availability sentinel; reimported inside body
        check_pg_health,
        is_pg_available,
    )
    HAS_STORAGE = True
except ImportError:
    HAS_STORAGE = False


router = APIRouter()


async def _probe_rendering_service(url: str, timeout: float = 3.0) -> dict[str, Any]:
    """HTTP-probe the dedicated rendering service.

    Why: backend container has no node/npx; the legacy
    `subprocess.run(['npx', 'remotion', '--version'])` check always
    returned `available=false` even when `rendering:3001` was healthy,
    misleading the SettingsPanel UI. When `RENDERING_SERVICE_URL` is
    set we ask the rendering container itself.

    Returns the same shape as `RemotionRenderer.validate_environment()`
    so /health response stays compatible.
    """
    import httpx

    info: dict[str, Any] = {
        "available": False,
        "node_version": None,
        "remotion_version": None,
        "render_script_exists": True,
        "node_modules_exist": True,
        "rendering_service_url": url,
        "issues": [],
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{url}/health")
        if resp.status_code != 200:
            info["issues"].append(
                f"rendering service returned HTTP {resp.status_code}"
            )
            return info
        data = resp.json()
        info["node_version"] = data.get("node")
        info["remotion_version"] = data.get("remotion")
        info["ffmpeg_ok"] = bool(data.get("ffmpeg"))
        info["chromium_ok"] = bool(data.get("chromium"))
        info["available"] = bool(
            data.get("status") == "ok"
            and data.get("node")
            and data.get("remotion")
            and data.get("ffmpeg")
        )
        if not info["available"]:
            info["issues"].append(f"rendering service degraded: {data}")
    except Exception as e:
        info["issues"].append(f"rendering service probe error: {str(e)[:200]}")
    return info


@router.get("/health")
async def health():
    """Health check with persistence and Remotion status."""
    rendering_url = os.environ.get("RENDERING_SERVICE_URL", "").rstrip("/")

    if rendering_url:
        remotion_env = await _probe_rendering_service(rendering_url)
    else:
        from src.tools.remotion_renderer import RemotionRenderer
        renderer = RemotionRenderer()
        remotion_env = renderer.validate_environment()

    persistence_status: dict[str, Any] = {"backend": "filesystem", "pg_available": False}
    if HAS_STORAGE:
        try:
            from src.storage.db import check_pg_health, is_pg_available
            persistence_status = await check_pg_health()
            persistence_status["pg_available"] = is_pg_available()
        except Exception as e:
            persistence_status["error"] = str(e)[:200]

    media_tools: dict[str, Any] = {}
    try:
        from src.tools.video_downloader import VideoDownloader
        downloader = VideoDownloader()
        media_tools["ytdlp_available"] = downloader._ytdlp_available
        media_tools["whisper_available"] = downloader._whisper_available
    except Exception as e:
        media_tools["error"] = str(e)[:200]
        media_tools["ytdlp_available"] = False
        media_tools["whisper_available"] = False

    return {
        "status": "ok",
        "version": "0.2.5",
        "remotion": remotion_env,
        "persistence": persistence_status,
        "media_tools": media_tools,
    }
