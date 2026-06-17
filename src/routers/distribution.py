"""distribution router — extracted from api.py (P1-11)."""

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException

try:
    from src.storage import HAS_STORAGE
    from src.storage.repository import PublishLogRepository
except ImportError:
    HAS_STORAGE = False
    PublishLogRepository = None  # type: ignore[misc,assignment]

if TYPE_CHECKING:
    pass

from src.routers._deps import _safe_error, verify_api_key

router = APIRouter()


def _as_mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _extract_publish_authorization(body: Mapping[str, Any]) -> Mapping[str, Any]:
    content = _as_mapping(body.get("content"))
    metadata = _as_mapping(body.get("metadata"))
    for candidate in (
        body.get("delivery_acceptance"),
        content.get("delivery_acceptance"),
        metadata.get("delivery_acceptance"),
    ):
        if isinstance(candidate, Mapping):
            return candidate
    return {}


def _require_human_publish_authorization(body: Mapping[str, Any]) -> None:
    acceptance = _extract_publish_authorization(body)
    if not acceptance:
        raise HTTPException(
            status_code=403,
            detail="Human delivery acceptance is required before publishing",
        )

    source = str(
        acceptance.get("source")
        or acceptance.get("decision_source")
        or acceptance.get("confirmed_by_type")
        or ""
    ).strip().lower()
    if source != "human":
        raise HTTPException(
            status_code=403,
            detail="Publish authorization must come from a human decision source",
        )

    if acceptance.get("delivery_accepted") is not True:
        raise HTTPException(
            status_code=403,
            detail="delivery_accepted=true is required before publishing",
        )
    if acceptance.get("publish_allowed") is not True:
        raise HTTPException(
            status_code=403,
            detail="publish_allowed=true is required before publishing",
        )
    if acceptance.get("approved_brand_token_write") is True:
        raise HTTPException(
            status_code=403,
            detail="Publishing cannot write or imply approved brand token approval",
        )

    reviewer = str(
        acceptance.get("reviewer")
        or acceptance.get("reviewer_id")
        or acceptance.get("accepted_by")
        or ""
    ).strip()
    if not reviewer:
        raise HTTPException(
            status_code=403,
            detail="Human reviewer identity is required before publishing",
        )


@router.post("/distribution/publish", dependencies=[Depends(verify_api_key)])
async def distribution_publish(body: dict[str, Any]):
    """Publish content to a platform (TikTok or Shopify).

    Request body:
        platform: "tiktok" | "shopify"
        content: dict with platform-specific fields

    Returns:
        Publish result dict from the connector.
    """
    from src.connectors.registry import publish_to_platform

    _require_human_publish_authorization(body)

    try:
        result = await publish_to_platform(body["platform"], body["content"])
        if HAS_STORAGE and PublishLogRepository is not None:
            repo = PublishLogRepository()  # type: ignore[misc]
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
async def publish_video(video_id: str, body: dict[str, Any]):
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

    _require_human_publish_authorization(body)

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

    if HAS_STORAGE and PublishLogRepository is not None:
        try:
            repo = PublishLogRepository()  # type: ignore[misc]
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
