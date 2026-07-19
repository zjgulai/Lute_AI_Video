"""Publish engine — orchestrates video publishing to multiple platforms.

Provides a unified interface for publishing videos to TikTok and Shopify.
Each platform method delegates to the corresponding real connector.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.connectors.base import ConnectorOutcomeAmbiguous
from src.connectors.shopify_connector import ShopifyConnector
from src.connectors.tiktok_connector import TikTokConnector
from src.models.publish_attempt import PublishReceiptV1


@dataclass
class PublishResult:
    """Result of publishing a video to a single platform."""

    platform: str = ""
    success: bool = False
    simulated: bool = False
    post_id: str | None = None
    post_url: str | None = None
    receipt: dict[str, Any] | None = None
    error: str = ""


_MISSING = object()


def _project_connector_result(
    *,
    platform: str,
    connector_result: object,
) -> PublishResult:
    if not isinstance(connector_result, Mapping):
        raise ConnectorOutcomeAmbiguous
    simulated = connector_result.get("simulated", _MISSING)
    if type(simulated) is not bool:
        raise ConnectorOutcomeAmbiguous
    if simulated is True:
        return PublishResult(
            platform=platform,
            success=False,
            simulated=True,
            error="publish_connector_simulated",
        )
    success = connector_result.get("success", _MISSING)
    if type(success) is not bool:
        raise ConnectorOutcomeAmbiguous
    if success is False:
        return PublishResult(
            platform=platform,
            success=False,
            simulated=False,
            error="publish_connector_failed",
        )
    reported_platform = connector_result.get("platform")
    if reported_platform != platform:
        raise ConnectorOutcomeAmbiguous
    raw_receipt = connector_result.get("receipt")
    if not isinstance(raw_receipt, Mapping):
        raise ConnectorOutcomeAmbiguous
    try:
        receipt = PublishReceiptV1.model_validate(dict(raw_receipt))
        receipt.validate_published()
    except (TypeError, ValueError):
        raise ConnectorOutcomeAmbiguous from None
    if (
        receipt.platform != platform
        or connector_result.get("post_id") != receipt.post_id
        or connector_result.get("url") != receipt.post_url
    ):
        raise ConnectorOutcomeAmbiguous
    return PublishResult(
        platform=platform,
        success=True,
        simulated=False,
        post_id=receipt.post_id,
        post_url=receipt.post_url,
        receipt=receipt.model_dump(mode="json"),
    )


def _platform_options(metadata: Mapping[str, Any], platform: str) -> object:
    options = metadata.get("platform_options")
    if isinstance(options, Mapping) and options.get("platform") == platform:
        return dict(options)
    if isinstance(options, Mapping):
        selected = options.get(platform)
        if isinstance(selected, Mapping):
            return dict(selected)
    return options


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
                    simulated=False,
                    error="unsupported_platform",
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

        Delegates to TikTokConnector.publish().
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
            "platform_options": _platform_options(metadata, "tiktok"),
        }

        preflight = await self._tiktok.preflight(content)
        connector_result = await self._tiktok.publish(
            content,
            preflight=preflight,
        )
        return _project_connector_result(
            platform="tiktok",
            connector_result=connector_result,
        )

    async def publish_to_shopify(
        self, video_path: str, metadata: dict[str, Any]
    ) -> PublishResult:
        """Publish a video to Shopify.

        Reads metadata keys:
          * product_name — the store product to associate the video with.
          * hook         — used as a fallback title.

        Delegates to ShopifyConnector.publish().
        """
        product_name = metadata.get("product_name", "")
        title = metadata.get("hook", "AI-generated video")

        content: dict[str, Any] = {
            "title": title,
            "video_path": video_path,
            "product_name": product_name,
            "platform_options": _platform_options(metadata, "shopify"),
        }

        preflight = await self._shopify.preflight(content)
        connector_result = await self._shopify.publish(
            content,
            preflight=preflight,
        )
        return _project_connector_result(
            platform="shopify",
            connector_result=connector_result,
        )
