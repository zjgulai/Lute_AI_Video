"""health router — extracted from api.py (P1-11)."""

from fastapi import APIRouter

try:
    from src.storage import HAS_STORAGE
    from src.storage.db import check_pg_health, is_pg_available
    from src.tools.remotion_renderer import RemotionRenderer
except ImportError:
    HAS_STORAGE = False


router = APIRouter()

@router.get("/health")
async def health():
    """Health check with persistence and Remotion status."""
    from src.tools.remotion_renderer import RemotionRenderer

    renderer = RemotionRenderer()
    remotion_env = renderer.validate_environment()

    persistence_status: dict = {"backend": "filesystem", "pg_available": False}
    if HAS_STORAGE:
        try:
            from src.storage.db import check_pg_health, is_pg_available
            persistence_status = await check_pg_health()
            persistence_status["pg_available"] = is_pg_available()
        except Exception as e:
            persistence_status["error"] = str(e)[:200]

    return {
        "status": "ok",
        "version": "0.2.0",
        "remotion": remotion_env,
        "persistence": persistence_status,
    }



