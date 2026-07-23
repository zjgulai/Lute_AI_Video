"""health router — extracted from api.py (P1-11)."""

import os
import re
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src._version import APP_VERSION

try:
    from src.storage.db import (  # noqa: F401  # availability sentinel; reimported inside body
        check_pg_health,
        is_pg_available,
    )
    HAS_STORAGE = True
except ImportError:
    HAS_STORAGE = False


router = APIRouter()


@router.get("/health/live")
async def liveness() -> dict[str, Any]:
    """Process-only liveness; never probes dependencies."""

    return {"status": "alive", "version": APP_VERSION}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    """Side-effect-free persistence readiness with fail-closed HTTP status."""

    if not HAS_STORAGE:
        database = {
            "ready": False,
            "backend": "unavailable",
            "status": "storage_module_unavailable",
        }
    else:
        from src.storage.db import check_database_readiness

        database = await check_database_readiness()
    ready = database.get("ready") is True
    payload = _sanitize_health_payload(
        {
            "status": "ready" if ready else "not_ready",
            "version": APP_VERSION,
            "persistence": database,
        }
    )
    return JSONResponse(status_code=200 if ready else 503, content=payload)


_SENSITIVE_ENV_NAME_PARTS = (
    "API_KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "DATABASE_URL",
    "DSN",
)
_DATABASE_URL_RE = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|redis|mongodb|sqlite)://[^\s\"'`,;]+",
    re.IGNORECASE,
)
_CREDENTIAL_URL_RE = re.compile(
    r"\b([a-z][a-z0-9+.-]*://)([^/\s:@]+):([^@\s/]+)@",
    re.IGNORECASE,
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b([A-Z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|DATABASE_URL|DSN)[A-Z0-9_]*)"
    r"\s*[:=]\s*([^\s,;\"']+)",
    re.IGNORECASE,
)
_INTERNAL_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9])/(?:Users|home|root|app|workspace|var|tmp|opt|srv|mnt)/[^\s\"'`,;]+"
)


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


def _sensitive_env_values() -> list[str]:
    values: set[str] = set()
    for key, value in os.environ.items():
        if not value or len(value) < 6:
            continue
        key_upper = key.upper()
        if any(part in key_upper for part in _SENSITIVE_ENV_NAME_PARTS):
            values.add(value)
    return sorted(values, key=len, reverse=True)


def _sanitize_health_text(value: str) -> str:
    sanitized = value
    for secret_value in _sensitive_env_values():
        sanitized = sanitized.replace(secret_value, "[redacted]")
    sanitized = _DATABASE_URL_RE.sub("[redacted]", sanitized)
    sanitized = _CREDENTIAL_URL_RE.sub(r"\1[redacted]@", sanitized)
    sanitized = _SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=[redacted]", sanitized)
    return _INTERNAL_PATH_RE.sub("[internal-path]", sanitized)


def _sanitize_health_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_health_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_health_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_health_payload(item) for item in value]
    if isinstance(value, str):
        return _sanitize_health_text(value)
    return value


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

    try:
        media_tools["clip_available"] = _check_clip_imports_only()
    except Exception:
        media_tools["clip_available"] = False

    return _sanitize_health_payload({
        "status": "ok",
        "version": APP_VERSION,
        "remotion": remotion_env,
        "persistence": persistence_status,
        "media_tools": media_tools,
    })


def _check_clip_imports_only() -> bool:
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        return False
