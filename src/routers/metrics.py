"""metrics router — extracted from api.py (P1-11)."""

from fastapi import APIRouter, Depends, HTTPException

try:
    from src.storage import HAS_STORAGE
except ImportError:
    HAS_STORAGE = False

from src.routers._deps import _safe_error, verify_api_key

router = APIRouter()

@router.get("/metrics/{video_id}", dependencies=[Depends(verify_api_key)])
async def get_video_metrics(video_id: str, platform: str | None = None):
    """Get metrics snapshots for a video. Optional platform filter."""
    if not HAS_STORAGE:
        raise HTTPException(status_code=503, detail="Metrics storage not available")

    try:
        from src.storage.metrics_repository import VideoMetricsRepository
        repo = VideoMetricsRepository()
        rows = await repo.get_metrics(video_id, platform=platform)
        return {"video_id": video_id, "metrics": rows}
    except Exception as e:
        import logging
        logging.error("get_video_metrics failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/dashboard/overview", dependencies=[Depends(verify_api_key)])
async def get_dashboard_overview(scenario: str | None = None, platform: str | None = None, days: int = 7):
    """Get aggregated dashboard data.

    Query params:
        scenario (optional): "S1", "S2", or "S3"
        platform (optional): "tiktok" or "shopify"
        days     (optional): time window in days (default 7)
    """
    if not HAS_STORAGE:
        raise HTTPException(status_code=503, detail="Metrics storage not available")

    try:
        from src.storage.metrics_repository import VideoMetricsRepository
        repo = VideoMetricsRepository()
        rows = await repo.get_dashboard_overview(
            scenario=scenario, platform=platform, days=days
        )
        return {
            "scenario": scenario,
            "platform": platform,
            "days": days,
            "data": rows,
        }
    except Exception as e:
        import logging
        logging.error("get_dashboard_overview failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.post("/metrics/pull", dependencies=[Depends(verify_api_key)])
async def trigger_metrics_pull():
    """Manually trigger metrics poll (debug endpoint)."""
    if not HAS_STORAGE:
        raise HTTPException(status_code=503, detail="Metrics storage not available")

    try:
        from src.tasks.metrics_poller import MetricsPoller
        poller = MetricsPoller()
        await poller.pull_all()
        return {"status": "ok", "message": "Metrics pull triggered successfully"}
    except ImportError:
        raise HTTPException(status_code=501, detail="MetricsPoller not yet implemented")
    except Exception as e:
        import logging
        logging.error("trigger_metrics_pull failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


