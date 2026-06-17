"""metrics router — extracted from api.py (P1-11)."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

try:
    from src.storage import HAS_STORAGE
except ImportError:
    HAS_STORAGE = False

from src.routers._deps import _safe_error, get_auth_context, verify_api_key

router = APIRouter()


def _metrics_tenant_filter() -> str | None:
    ctx = get_auth_context()
    if ctx is None or ctx.tenant_id in {"default", "test-bundle"}:
        return None
    return ctx.tenant_id


def _metric_number(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key, 0)
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_dashboard_overview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Shape repository rows into the contract consumed by PerformanceDashboard."""
    videos: list[dict[str, Any]] = []
    scenarios: dict[str, dict[str, float]] = {}
    platforms: dict[str, dict[str, Any]] = {}

    for row in rows:
        raw_metrics = row.get("metrics")
        metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
        video_id = str(row.get("video_id") or metrics.get("video_id") or "")
        scenario = str(row.get("scenario") or metrics.get("scenario") or "unknown")
        platform = str(row.get("platform") or metrics.get("platform") or "unknown")
        title = str(metrics.get("title") or metrics.get("video_title") or video_id)

        ctr = _metric_number(metrics, "ctr")
        cvr = _metric_number(metrics, "cvr")
        watch_rate = _metric_number(metrics, "watch_rate")
        followers_gained = _metric_number(metrics, "followers_gained")
        sales = _metric_number(metrics, "sales")
        views = _metric_number(metrics, "views")

        history = metrics.get("history")
        video: dict[str, Any] = {
            "video_id": video_id,
            "title": title,
            "scenario": scenario,
            "platform": platform,
            "ctr": ctr,
            "cvr": cvr,
            "watch_rate": watch_rate,
            "followers_gained": followers_gained,
            "sales": sales,
            "views": views,
        }
        if isinstance(history, list):
            video["history"] = history
        videos.append(video)

        scenario_bucket = scenarios.setdefault(
            scenario,
            {
                "count": 0.0,
                "watch_rate": 0.0,
                "ctr": 0.0,
                "cvr": 0.0,
                "sales": 0.0,
            },
        )
        scenario_bucket["count"] += 1
        scenario_bucket["watch_rate"] += watch_rate
        scenario_bucket["ctr"] += ctr
        scenario_bucket["cvr"] += cvr
        scenario_bucket["sales"] += sales

        platform_bucket = platforms.setdefault(
            platform,
            {
                "count": 0.0,
                "watch_rate": 0.0,
                "ctr": 0.0,
                "cvr": 0.0,
                "views": 0.0,
                "scenario_breakdown": {},
            },
        )
        platform_bucket["count"] += 1
        platform_bucket["watch_rate"] += watch_rate
        platform_bucket["ctr"] += ctr
        platform_bucket["cvr"] += cvr
        platform_bucket["views"] += views

        breakdown = platform_bucket["scenario_breakdown"]
        scenario_platform = breakdown.setdefault(
            scenario,
            {"count": 0.0, "watch_rate": 0.0, "ctr": 0.0, "cvr": 0.0},
        )
        scenario_platform["count"] += 1
        scenario_platform["watch_rate"] += watch_rate
        scenario_platform["ctr"] += ctr
        scenario_platform["cvr"] += cvr

    scenario_cards = [
        {
            "scenario": scenario,
            "avg_watch_rate": bucket["watch_rate"] / bucket["count"],
            "avg_ctr": bucket["ctr"] / bucket["count"],
            "avg_cvr": bucket["cvr"] / bucket["count"],
            "total_videos": int(bucket["count"]),
            "total_sales": bucket["sales"],
        }
        for scenario, bucket in sorted(scenarios.items())
        if bucket["count"]
    ]

    platform_cards: list[dict[str, Any]] = []
    for platform, bucket in sorted(platforms.items()):
        if not bucket["count"]:
            continue
        scenario_breakdown = {
            scenario: {
                "avg_watch_rate": values["watch_rate"] / values["count"],
                "avg_ctr": values["ctr"] / values["count"],
                "avg_cvr": values["cvr"] / values["count"],
            }
            for scenario, values in sorted(bucket["scenario_breakdown"].items())
            if values["count"]
        }
        platform_cards.append(
            {
                "platform": platform,
                "avg_ctr": bucket["ctr"] / bucket["count"],
                "avg_cvr": bucket["cvr"] / bucket["count"],
                "avg_watch_rate": bucket["watch_rate"] / bucket["count"],
                "total_views": bucket["views"],
                "scenario_breakdown": scenario_breakdown,
            }
        )

    return {
        "videos": videos,
        "scenarios": scenario_cards,
        "platforms": platform_cards,
    }


@router.get("/metrics/{video_id}", dependencies=[Depends(verify_api_key)])
async def get_video_metrics(video_id: str, platform: str | None = None):
    """Get metrics snapshots for a video. Optional platform filter."""
    if not HAS_STORAGE:
        raise HTTPException(status_code=503, detail="Metrics storage not available")

    try:
        from src.storage.metrics_repository import VideoMetricsRepository
        repo = VideoMetricsRepository()
        rows = await repo.get_metrics(video_id, platform=platform, tenant_id=_metrics_tenant_filter())
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
            scenario=scenario, platform=platform, days=days, tenant_id=_metrics_tenant_filter()
        )
        return {
            "scenario": scenario,
            "platform": platform,
            "days": days,
            "data": rows,
            **_format_dashboard_overview(rows),
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
