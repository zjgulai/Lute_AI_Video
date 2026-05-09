"""Publish engine — orchestrates video publishing to multiple platforms.

Provides a unified interface for publishing videos to TikTok and Shopify.
Each platform method delegates to the corresponding real connector, which
falls back to mock mode when credentials are absent.
"""

import logging
from dataclasses import dataclass
from typing import Any

from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    """Result of publishing a video to a single platform."""

    platform: str = ""
    success: bool = False
    post_id: str = ""
    post_url: str = ""
    error: str = ""


class PublishEngine:
    """Orchestrates video publishing to multiple platforms."""

    def __init__(self) -> None:
        self._tiktok = TikTokConnector()
        self._shopify = ShopifyConnector()

    async def publish(
        self, video_path: str, metadata: dict[str, Any], platforms: list[str]
    ) -> list[PublishResult]:
        """Publish a video to the given platforms.

        Args:
            video_path:  Absolute or relative path to the video file on disk.
            metadata:    Dict that may include keys such as
                         * hook             — short text used as TikTok description
                         * hashtags         — list of str
                         * product_name     — Shopify product to associate with
            platforms:   List of platform identifiers, e.g. ["tiktok", "shopify"].

        Returns:
            One PublishResult per platform, in the same order as *platforms*.
        """
        results: list[PublishResult] = []
        for platform in platforms:
            platform_lower = platform.strip().lower()
            if platform_lower == "tiktok":
                result = await self.publish_to_tiktok(video_path, metadata)
            elif platform_lower == "shopify":
                result = await self.publish_to_shopify(video_path, metadata)
            else:
                result = PublishResult(
                    platform=platform,
                    success=False,
                    error=f"Unsupported platform: {platform}",
                )
            results.append(result)
        return results

    async def publish_to_tiktok(
        self, video_path: str, metadata: dict[str, Any]
    ) -> PublishResult:
        """Publish a video to TikTok.

        Reads metadata keys:
          * hook       — used as the video description / title.
          * hashtags   — list of str appended to the description.

        Delegates to TikTokConnector.publish() which calls the real TikTok
        Content Posting API when TIKTOK_ACCESS_TOKEN is set, otherwise falls
        back to mock mode.
        """
        title = metadata.get("hook", "AI-generated video")
        tags = metadata.get("hashtags", [])
        if isinstance(tags, list):
            tag_str = " ".join(f"#{t}" for t in tags)
        else:
            tag_str = str(tags) if tags else ""

        description = title
        if tag_str:
            description = f"{title}\n{tag_str}"

        content: dict[str, Any] = {
            "title": title,
            "description": description,
            "video_path": video_path,
            "tags": tags,
        }

        try:
            connector_result = await self._tiktok.publish(content)
            pr = PublishResult(platform="tiktok")
            if connector_result.get("success"):
                pr.success = True
                pr.post_id = connector_result.get("post_id", "")
                pr.post_url = connector_result.get("url", "")
            else:
                pr.error = connector_result.get("error", "TikTok publish failed")
            return pr
        except Exception as exc:
            logger.exception("TikTok publish error")
            return PublishResult(
                platform="tiktok", success=False, error=str(exc)
            )

    async def publish_to_shopify(
        self, video_path: str, metadata: dict[str, Any]
    ) -> PublishResult:
        """Publish a video to Shopify.

        Reads metadata keys:
          * product_name — the store product to associate the video with.
          * hook         — used as a fallback title.

        Delegates to ShopifyConnector.publish() which calls the real Shopify
        Admin API when SHOPIFY_API_KEY is set, otherwise falls back to mock.
        """
        product_name = metadata.get("product_name", "")
        title = metadata.get("hook", "AI-generated video")

        content: dict[str, Any] = {
            "title": title,
            "video_path": video_path,
            "product_name": product_name,
        }

        try:
            connector_result = await self._shopify.publish(content)
            pr = PublishResult(platform="shopify")
            if connector_result.get("success"):
                pr.success = True
                pr.post_id = connector_result.get("post_id", "")
                pr.post_url = connector_result.get("url", "")
            else:
                pr.error = connector_result.get("error", "Shopify publish failed")
            return pr
        except Exception as exc:
            logger.exception("Shopify publish error")
            return PublishResult(
                platform="shopify", success=False, error=str(exc)
            )
