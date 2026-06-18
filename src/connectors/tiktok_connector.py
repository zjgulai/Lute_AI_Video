"""TikTok connector — publish content to TikTok via the Content Posting API.

Uses the TikTok Business API (Content Posting API) for video uploads.
Falls back to mock mode when TIKTOK_ACCESS_TOKEN is not set.
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx

from src.config import TIKTOK_API_BASE_URL, TIKTOK_API_UPLOAD_URL
from src.connectors.base import PlatformConnector
from src.tasks.metrics_poller import PlatformMetricsError, classify_platform_http_status

logger = logging.getLogger(__name__)

# TikTok Content Posting API endpoints
# Docs: https://developers.tiktok.com/doc/content-posting-api-overview/
_TIKTOK_UPLOAD_URL = TIKTOK_API_UPLOAD_URL + "/video/upload/"
_TIKTOK_PUBLISH_URL = TIKTOK_API_UPLOAD_URL + "/video/publish/"
_TIKTOK_QUERY_URL = TIKTOK_API_UPLOAD_URL + "/video/query/"
_TIKTOK_METRICS_QUERY_URL = TIKTOK_API_BASE_URL.rstrip("/") + "/v2/video/query/"
_TIKTOK_METRIC_FIELDS = "id,view_count,like_count,comment_count,share_count"


def _is_mock_mode() -> bool:
    """Return True when no real TikTok API credentials are available."""
    token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
    return not token


def _classify_tiktok_error(code: str, message: str) -> str:
    value = f"{code} {message}".lower()
    if any(marker in value for marker in ("auth", "token", "scope", "permission")):
        return "auth"
    if any(marker in value for marker in ("rate", "quota", "too many")):
        return "rate_limit"
    if any(marker in value for marker in ("not_found", "not found", "does not exist")):
        return "not_found"
    if any(marker in value for marker in ("invalid", "field", "schema", "param")):
        return "schema_drift"
    return "transient"


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_tiktok_video_metrics(video: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    field_map = {
        "view_count": "views",
        "like_count": "likes",
        "comment_count": "comments",
        "share_count": "shares",
    }
    for source, target in field_map.items():
        value = _coerce_int(video.get(source))
        if value is not None:
            metrics[target] = value
    return metrics


class TikTokConnector(PlatformConnector):
    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._http_client = http_client

    async def fetch_metrics(self, post_id: str) -> dict[str, Any]:
        """Fetch performance metrics for a TikTok post.

        Uses TikTok's official `/v2/video/query/` endpoint. The endpoint
        verifies ownership of the requested video for the authorized user and
        returns the requested video object fields.
        """
        token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
        if not token:
            raise PlatformMetricsError(
                "auth",
                "TIKTOK_ACCESS_TOKEN is required for TikTok metrics",
            )

        resp = await self._post_metrics_query(token, post_id)
        if resp.status_code != 200:
            raise PlatformMetricsError(
                classify_platform_http_status(resp.status_code),
                f"TikTok metrics HTTP {resp.status_code}",
            )

        data = resp.json()
        error = data.get("error") or {}
        error_code = str(error.get("code") or "").lower()
        if error and error_code not in {"", "ok", "0"}:
            raise PlatformMetricsError(
                _classify_tiktok_error(error_code, str(error.get("message") or "")),
                f"TikTok metrics error {error_code}: {error.get('message', '')}",
            )

        videos = data.get("data", {}).get("videos")
        if not isinstance(videos, list):
            raise PlatformMetricsError(
                "schema_drift",
                "TikTok metrics response missing data.videos list",
            )
        video = next(
            (item for item in videos if str(item.get("id")) == str(post_id)),
            videos[0] if videos else None,
        )
        if not isinstance(video, dict):
            raise PlatformMetricsError(
                "not_found",
                f"TikTok video {post_id} was not returned by metrics query",
            )

        metrics = _normalize_tiktok_video_metrics(video)
        if not metrics:
            raise PlatformMetricsError(
                "schema_drift",
                "TikTok video object has no supported metric fields",
            )
        return metrics

    async def _post_metrics_query(self, token: str, post_id: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"filters": {"video_ids": [str(post_id)]}}
        params = {"fields": _TIKTOK_METRIC_FIELDS}
        if self._http_client is not None:
            return await self._http_client.post(
                _TIKTOK_METRICS_QUERY_URL,
                headers=headers,
                params=params,
                json=payload,
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(
                _TIKTOK_METRICS_QUERY_URL,
                headers=headers,
                params=params,
                json=payload,
            )

    async def publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Publish content to TikTok.

        Accepts content with fields:
            title        (str)  — video title
            description  (str)  — full description with hashtags
            video_path   (str)  — local file path to the video
            tags         (list) — list of hashtag strings

        Returns dict with keys:
            success, post_id, url, status, error, platform, published_at
        """
        token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")

        if not token:
            logger.info("TIKTOK_ACCESS_TOKEN not set — using mock publish")
            return await self._mock_publish(content)

        video_path = content.get("video_path", "")
        description = content.get("description", content.get("title", ""))

        if not video_path or not os.path.isfile(video_path):
            logger.warning("Video file not found at %s", video_path)
            return {
                "success": False,
                "error": f"Video file not found: {video_path}",
                "status": "failed",
                "platform": "tiktok",
            }

        try:
            # Step 1: Upload the video file
            upload_result = await self._upload_video(token, video_path)
            if not upload_result.get("success"):
                return {
                    "success": False,
                    "error": upload_result.get("error", "Upload failed"),
                    "status": "failed",
                    "platform": "tiktok",
                }

            publish_id = upload_result.get("publish_id", "")

            # Step 2: Publish the uploaded video with description
            publish_result = await self._publish_video(
                token, publish_id, description
            )
            if not publish_result.get("success"):
                return {
                    "success": False,
                    "error": publish_result.get("error", "Publish failed"),
                    "status": "failed",
                    "platform": "tiktok",
                }

            return {
                "success": True,
                "post_id": publish_result.get("post_id", publish_id),
                "url": publish_result.get(
                    "url",
                    f"https://tiktok.com/@{os.environ.get('TIKTOK_USERNAME', 'user')}/video/{publish_id}",
                ),
                "status": "published",
                "platform": "tiktok",
                "published_at": datetime.now().isoformat(),
            }
        except Exception as exc:
            logger.exception("TikTok API publish error")
            return {
                "success": False,
                "error": str(exc),
                "status": "failed",
                "platform": "tiktok",
            }

    async def _upload_video(
        self, token: str, video_path: str
    ) -> dict[str, Any]:
        """Upload a video file to TikTok's Content Posting API.

        Returns dict with keys: success, publish_id, error.
        """
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                with open(video_path, "rb") as f:
                    files = {"video": (os.path.basename(video_path), f, "video/mp4")}
                    headers = {
                        "Authorization": f"Bearer {token}",
                    }
                    resp = await client.post(
                        _TIKTOK_UPLOAD_URL,
                        headers=headers,
                        files=files,
                    )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data", {}).get("error_code") == 0:
                        return {
                            "success": True,
                            "publish_id": data["data"].get("publish_id", ""),
                        }
                    error_msg = data.get("data", {}).get(
                        "error_message", "Unknown TikTok upload error"
                    )
                    logger.error("TikTok upload error: %s", error_msg)
                    return {"success": False, "error": error_msg}

                logger.error(
                    "TikTok upload HTTP %s: %s",
                    resp.status_code,
                    resp.text[:500],
                )
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }
        except Exception as exc:
            logger.exception("TikTok upload exception")
            return {"success": False, "error": str(exc)}

    async def _publish_video(
        self, token: str, publish_id: str, description: str
    ) -> dict[str, Any]:
        """Publish an uploaded video with the given description.

        Returns dict with keys: success, post_id, url, error.
        """
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "publish_id": publish_id,
                    "description": description,
                }
                resp = await client.post(
                    _TIKTOK_PUBLISH_URL,
                    headers=headers,
                    json=payload,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data", {}).get("error_code") == 0:
                        post_id = data["data"].get("post_id", publish_id)
                        return {
                            "success": True,
                            "post_id": post_id,
                            "url": f"https://tiktok.com/@{os.environ.get('TIKTOK_USERNAME', 'user')}/video/{post_id}",
                        }
                    error_msg = data.get("data", {}).get(
                        "error_message", "Unknown TikTok publish error"
                    )
                    logger.error("TikTok publish error: %s", error_msg)
                    return {"success": False, "error": error_msg}

                logger.error(
                    "TikTok publish HTTP %s: %s",
                    resp.status_code,
                    resp.text[:500],
                )
                return {
                    "success": False,
                    "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                }
        except Exception as exc:
            logger.exception("TikTok publish exception")
            return {"success": False, "error": str(exc)}

    async def get_status(self, post_id: str) -> dict[str, Any]:
        """Get publish status for a TikTok post.

        Calls the TikTok Video Query API when credentials are available,
        otherwise returns mock data.
        """
        token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")

        if not token:
            return self._mock_status(post_id)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                payload = {"post_id": post_id}
                resp = await client.post(
                    _TIKTOK_QUERY_URL, headers=headers, json=payload
                )

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("data", {}).get("error_code") == 0:
                        video_data = data.get("data", {}).get("video", {})
                        return {
                            "post_id": post_id,
                            "status": video_data.get("status", "published"),
                            "views": video_data.get("view_count", 0),
                            "likes": video_data.get("like_count", 0),
                            "comments": video_data.get("comment_count", 0),
                            "shares": video_data.get("share_count", 0),
                        }
                return {
                    "post_id": post_id,
                    "status": "unknown",
                    "views": 0,
                    "likes": 0,
                }
        except Exception:
            logger.exception("TikTok status query error")
            return self._mock_status(post_id)

    # ------------------------------------------------------------------
    # Mock fallback
    # ------------------------------------------------------------------

    async def _mock_publish(self, content: dict[str, Any]) -> dict[str, Any]:
        """Simulate a TikTok publish (used when credentials are absent)."""
        await asyncio.sleep(1.5)

        mock_id = f"tt_mock_{uuid4().hex[:8]}"
        return {
            "success": True,
            "post_id": mock_id,
            "url": f"https://tiktok.com/@mock_user/video/{mock_id}",
            "status": "published",
            "platform": "tiktok",
            "published_at": datetime.now().isoformat(),
        }

    def _mock_status(self, post_id: str) -> dict[str, Any]:
        """Return mock publish status."""
        return {
            "post_id": post_id,
            "status": "published",
            "views": 1234,
            "likes": 56,
        }
