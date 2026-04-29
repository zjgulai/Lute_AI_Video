"""Metrics poller — fetches video performance data from platforms periodically.

The poller checks for active posts (published within 30 days) and fetches fresh
metrics from each platform's API according to an adaptive polling schedule:

    - 0-24h  after publish: every 2 hours
    - 24-72h after publish: every 6 hours
    - 3d+    after publish: every 12 hours
    - 30d+   : no further polling

Designed to be invoked from a FastAPI BackgroundTask or an asyncio loop.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from ..storage.metrics_repository import VideoMetricsRepository

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hours_since(dt: Optional[datetime]) -> float:
    """Return the number of hours between *now* and *dt* (0 if dt is None)."""
    if dt is None:
        return 0.0
    delta = _now() - dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else _now() - dt
    return max(0.0, delta.total_seconds() / 3600.0)


class MetricsPoller:
    """Periodically fetch and store video performance metrics from platforms."""

    def __init__(self) -> None:
        self.repo = VideoMetricsRepository()

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def pull_all(self) -> None:
        """Fetch metrics for all active posts (published within 30 days).

        Called by a background scheduler (e.g. FastAPI lifespan task).
        Skips posts that are not yet due for their next poll interval.
        """
        logger.info("metrics_poller: pull_all started")
        posts = await self.repo.get_active_posts()
        if not posts:
            logger.info("metrics_poller: no active posts found")
            return
        pulled = 0
        skipped = 0
        for post in posts:
            pulled_ok = await self.pull_single(post)
            if pulled_ok:
                pulled += 1
            else:
                skipped += 1
        logger.info(
            "metrics_poller: pull_all finished — %d pulled, %d skipped",
            pulled,
            skipped,
        )

    async def pull_single(self, post: dict) -> bool:
        """Fetch and store metrics for a single post row.

        Returns True if a new metrics snapshot was saved, False if skipped.
        """
        published_at: Optional[datetime] = post.get("published_at")
        if published_at is None:
            logger.debug("metrics_poller: post %s has no published_at — skipping", post.get("id"))
            return False

        age_hours = _hours_since(published_at)
        if age_hours > 720:  # 30 days
            logger.debug(
                "metrics_poller: post %s is %.1f hours old (>720) — skipping",
                post.get("id"),
                age_hours,
            )
            return False

        # Determine poll frequency based on age
        if age_hours < 24:
            interval_hours = 2
        elif age_hours < 72:
            interval_hours = 6
        else:
            interval_hours = 12

        # Check if enough time has passed since last pull
        pulled_at: Optional[datetime] = post.get("pulled_at")
        last_pull = pulled_at or published_at
        hours_since_last = _hours_since(last_pull)
        if hours_since_last < interval_hours:
            logger.debug(
                "metrics_poller: post %s last pulled %.1f hours ago (<%.0f) — skipping",
                post.get("id"),
                hours_since_last,
                interval_hours,
            )
            return False

        # Time to poll
        platform: str = post.get("platform", "")
        post_id: Optional[str] = post.get("post_id")
        if not post_id:
            logger.warning("metrics_poller: post %s has no post_id — skipping", post.get("id"))
            return False

        try:
            metrics = await self._fetch_from_platform(platform, post_id)
            await self.repo.save_metrics(
                video_id=post["video_id"],
                scenario=post["scenario"],
                platform=platform,
                post_id=post_id,
                post_url=post.get("post_url"),
                metrics_dict=metrics,
            )
            logger.info(
                "metrics_poller: pulled metrics for %s (%s / %s) — %s",
                post_id,
                platform,
                post.get("scenario", "?"),
                list(metrics.keys()) if metrics else "empty",
            )
            return True
        except Exception as e:
            logger.warning(
                "metrics_poller: pull failed for %s", post_id, exc_info=e
            )
            return False

    # ------------------------------------------------------------------
    # Platform-specific fetchers (mock stubs — replace with real API calls)
    # ------------------------------------------------------------------

    async def _fetch_from_platform(self, platform: str, post_id: str) -> dict:
        """Route to the correct platform fetcher based on *platform* name."""
        platform_lower = platform.strip().lower()
        if platform_lower == "tiktok":
            return await self._fetch_from_tiktok(post_id)
        elif platform_lower == "shopify":
            return await self._fetch_from_shopify(post_id)
        logger.warning("metrics_poller: unknown platform %r — returning empty", platform)
        return {}

    async def _fetch_from_tiktok(self, post_id: str) -> dict:
        """Fetch metrics from TikTok Insights API.

        Returns a dict of metrics or empty dict on failure.
        (Stub — replace with real TikTok connector call.)
        """
        # TODO: Replace with real call via TikTok connector
        # e.g. from src.connectors.tiktok_connector import get_insights
        # return await get_insights(post_id)
        logger.debug("metrics_poller: _fetch_from_tiktok(%s) — stub returning empty", post_id)
        return {}

    async def _fetch_from_shopify(self, post_id: str) -> dict:
        """Fetch metrics from Shopify Analytics API.

        Returns a dict of metrics or empty dict on failure.
        (Stub — replace with real Shopify connector call.)
        """
        # TODO: Replace with real call via Shopify connector
        # e.g. from src.connectors.shopify_connector import get_analytics
        # return await get_analytics(post_id)
        logger.debug("metrics_poller: _fetch_from_shopify(%s) — stub returning empty", post_id)
        return {}
