"""distribution router — extracted from api.py (P1-11)."""

from fastapi import APIRouter, HTTPException, Depends

try:
    from src.storage import HAS_STORAGE
    from src.storage.repository import PublishLogRepository
except ImportError:
    HAS_STORAGE = False

from src.routers._deps import _safe_error, verify_api_key


router = APIRouter()

@router.post("/distribution/publish", dependencies=[Depends(verify_api_key)])
async def distribution_publish(body: dict):
    """Publish content to a platform (TikTok or Shopify).

    Request body:
        platform: "tiktok" | "shopify"
        content: dict with platform-specific fields

    Returns:
        Publish result dict from the connector.
    """
    from src.connectors.registry import publish_to_platform

    try:
        result = await publish_to_platform(body["platform"], body["content"])
        if HAS_STORAGE:
            repo = PublishLogRepository()
            await repo.create({
                "platform": body["platform"],
                "post_id": result.get("post_id"),
                "content": body["content"],
                "status": "published" if result.get("success") else "failed",
                "url": result.get("url"),
                "error": result.get("error"),
            })
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_safe_error(e))
    except Exception as e:
        import logging
        logging.error("distribution publish failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/distribution/status/{platform}/{post_id}", dependencies=[Depends(verify_api_key)])
async def distribution_status(platform: str, post_id: str):
    """Get publish status for a post on a platform.

    Returns:
        Status dict from the connector.
    """
    from src.connectors.registry import get_connector

    try:
        connector = get_connector(platform)
        result = await connector.get_status(post_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=_safe_error(e))
    except Exception as e:
        import logging
        logging.error("distribution status failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))


@router.get("/distribution/platforms", dependencies=[Depends(verify_api_key)])
async def distribution_platforms():
    """List available distribution platforms and their connection status.

    Returns:
        Array of platform metadata dicts.
    """
    from src.connectors.shopify_connector import _is_mock_mode as _shopify_mock
    from src.connectors.tiktok_connector import _is_mock_mode as _tiktok_mock
    return [
        {"id": "tiktok", "name": "TikTok", "connected": not _tiktok_mock()},
        {"id": "shopify", "name": "Shopify", "connected": not _shopify_mock()},
    ]


@router.post("/publish/{video_id}", dependencies=[Depends(verify_api_key)])
async def publish_video(video_id: str, body: dict):
    """Publish a video to selected platforms.

    Request body:
        platforms: ["tiktok", "shopify"]
        metadata: { hook, hashtags, product_name, ... }

    Returns:
        [{ platform, success, post_id, post_url, error }]
    """
    from src.connectors.publish_engine import PublishEngine

    platforms = body.get("platforms", [])
    metadata = body.get("metadata", {})

    if not platforms:
        raise HTTPException(status_code=400, detail="No platforms specified")

    from src.config import OUTPUT_DIR

    video_path = metadata.get("video_path", "")
    if not video_path:
        candidates = list(OUTPUT_DIR.rglob(f"{video_id}.*"))
        if candidates:
            video_path = str(candidates[0])
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Video file for '{video_id}' not found",
            )

    metadata["video_path"] = video_path

    engine = PublishEngine()
    results = await engine.publish(video_path, metadata, platforms)

    if HAS_STORAGE:
        try:
            repo = PublishLogRepository()
            for r in results:
                await repo.create({
                    "platform": r.platform,
                    "post_id": r.post_id,
                    "content": {"video_id": video_id, "metadata": metadata},
                    "status": "published" if r.success else "failed",
                    "url": r.post_url,
                    "error": r.error,
                })
        except Exception as exc:
            import logging
            logging.warning("Failed to log publish result: %s", exc)

    return [
        {
            "platform": r.platform,
            "success": r.success,
            "post_id": r.post_id,
            "post_url": r.post_url,
            "error": r.error,
        }
        for r in results
    ]


