"""Metrics poller — fetches video performance data from platforms periodically.

The poller checks for active posts (published within 30 days) and fetches fresh
metrics from each platform's API according to an adaptive polling schedule:

    - 0-24h  after publish: every 2 hours
    - 24-72h after publish: every 6 hours
    - 3d+    after publish: every 12 hours
    - 30d+   : no further polling

Designed to be invoked from a FastAPI BackgroundTask or an asyncio loop.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from ..storage.metrics_repository import VideoMetricsRepository

logger = logging.getLogger(__name__)

PlatformMetricsFetcher = Callable[[str], Awaitable[dict[str, Any]]]
MetricErrorCategory = Literal[
    "auth",
    "rate_limit",
    "not_found",
    "schema_drift",
    "transient",
    "not_implemented",
]

METRIC_PAYLOAD_KEYS = {
    "views",
    "watch_rate",
    "ctr",
    "cvr",
    "followers_gained",
    "sales",
    "likes",
    "comments",
    "shares",
    "orders",
    "revenue",
}


class PlatformMetricsError(RuntimeError):
    """Classified platform metrics pull failure.

    The poller keeps live pulls fail-closed: classified failures never write an
    empty metrics snapshot and never masquerade as successful ingestion.
    """

    def __init__(self, category: MetricErrorCategory, message: str) -> None:
        super().__init__(message)
        self.category = category


def classify_platform_http_status(status_code: int) -> MetricErrorCategory:
    """Map platform HTTP status to the contract categories used by the poller."""
    if status_code in {401, 403}:
        return "auth"
    if status_code == 429:
        return "rate_limit"
    if status_code == 404:
        return "not_found"
    if status_code >= 500:
        return "transient"
    return "schema_drift"


def _now() -> datetime:
    return datetime.now(UTC)


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("metrics_poller: invalid timestamp %r", value)
        return None


def _hours_since(dt: datetime | str | None) -> float:
    """Return the number of hours between *now* and *dt* (0 if dt is None)."""
    parsed = _coerce_datetime(dt)
    if parsed is None:
        return 0.0
    delta = _now() - parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else _now() - parsed
    return max(0.0, delta.total_seconds() / 3600.0)


def _poll_interval_hours(age_hours: float) -> int:
    if age_hours < 24:
        return 2
    if age_hours < 72:
        return 6
    return 12


def _normalize_metrics_payload(
    platform: str,
    post_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload:
        raise PlatformMetricsError(
            "schema_drift",
            f"{platform} metrics payload for {post_id} is empty or not an object",
        )
    if not (METRIC_PAYLOAD_KEYS & set(payload)):
        raise PlatformMetricsError(
            "schema_drift",
            f"{platform} metrics payload for {post_id} has no recognized metric keys",
        )
    return payload


class MetricsPoller:
    """Periodically fetch and store video performance metrics from platforms."""

    def __init__(
        self,
        max_concurrency: int = 3,
        repo: VideoMetricsRepository | None = None,
        platform_fetchers: Mapping[str, PlatformMetricsFetcher] | None = None,
    ) -> None:
        self.repo = repo or VideoMetricsRepository()
        self.max_concurrency = max(1, max_concurrency)
        if platform_fetchers is None:
            platform_fetchers = {
                "tiktok": self._fetch_from_tiktok,
                "shopify": self._fetch_from_shopify,
            }
        self.platform_fetchers = {
            platform.strip().lower(): fetcher
            for platform, fetcher in platform_fetchers.items()
        }

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
        sem = asyncio.Semaphore(self.max_concurrency)

        async def _pull_guarded(post: dict[str, Any]) -> bool:
            async with sem:
                return await self.pull_single(post)

        results = await asyncio.gather(
            *(_pull_guarded(post) for post in posts),
            return_exceptions=True,
        )
        pulled = sum(1 for r in results if r is True)
        skipped = len(results) - pulled
        for r in results:
            if isinstance(r, Exception):
                logger.warning("metrics_poller: pull task failed", exc_info=r)
        logger.info(
            "metrics_poller: pull_all finished — %d pulled, %d skipped",
            pulled,
            skipped,
        )

    async def pull_single(self, post: dict[str, Any]) -> bool:
        """Fetch and store metrics for a single post row.

        Returns True if a new metrics snapshot was saved, False if skipped.
        """
        published_at: datetime | None = post.get("published_at")
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

        interval_hours = _poll_interval_hours(age_hours)

        # Check if enough time has passed since last pull
        pulled_at: datetime | None = post.get("pulled_at")
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
        post_id: str | None = post.get("post_id")
        if not post_id:
            logger.warning("metrics_poller: post %s has no post_id — skipping", post.get("id"))
            return False

        try:
            metrics = await self._fetch_from_platform(platform, post_id)
            if not metrics:
                logger.warning(
                    "metrics_poller: no metrics returned for %s (%s) — skipping save",
                    post_id,
                    platform,
                )
                return False
            await self.repo.save_metrics(
                video_id=post["video_id"],
                scenario=post["scenario"],
                platform=platform,
                tenant_id=post.get("tenant_id"),
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
        except PlatformMetricsError as e:
            logger.warning(
                "metrics_poller: pull blocked for %s (%s): category=%s message=%s",
                post_id,
                platform,
                e.category,
                str(e),
            )
            return False
        except Exception as e:
            logger.warning(
                "metrics_poller: pull failed for %s", post_id, exc_info=e
            )
            return False

    # ------------------------------------------------------------------
    # Readiness and dry-run inspection
    # ------------------------------------------------------------------

    async def dry_run_due_posts(
        self,
        allowlisted_post_ids: set[str] | None = None,
    ) -> dict[str, Any]:
        """Inspect active posts without fetching or saving platform metrics."""
        allowlist = {str(post_id) for post_id in allowlisted_post_ids or set()}
        posts = await self.repo.get_active_posts()
        due_posts: list[dict[str, Any]] = []
        allowlisted_due_posts: list[dict[str, Any]] = []
        skipped: dict[str, int] = {}

        for post in posts:
            decision = self._post_due_decision(post)
            if decision["due"]:
                due_posts.append({**post, "_dry_run": decision})
                if not allowlist or str(post.get("post_id") or "") in allowlist:
                    allowlisted_due_posts.append({**post, "_dry_run": decision})
                elif allowlist:
                    skipped["not_allowlisted"] = skipped.get("not_allowlisted", 0) + 1
                continue
            reason = str(decision["reason"])
            skipped[reason] = skipped.get(reason, 0) + 1

        if not posts:
            readiness = "blocked_by_no_active_post"
        elif allowlist and not allowlisted_due_posts:
            readiness = "blocked_by_no_allowlisted_active_post"
        elif not due_posts:
            readiness = "blocked_by_no_due_post"
        else:
            readiness = "ready_for_single_post_pilot"

        return {
            "readiness": readiness,
            "active_post_count": len(posts),
            "due_post_count": len(due_posts),
            "allowlisted_due_post_count": len(allowlisted_due_posts),
            "skipped": skipped,
            "candidates": allowlisted_due_posts,
        }

    def _post_due_decision(self, post: dict[str, Any]) -> dict[str, Any]:
        published_at = _coerce_datetime(post.get("published_at"))
        if published_at is None:
            return {"due": False, "reason": "missing_published_at"}

        age_hours = _hours_since(published_at)
        if age_hours > 720:
            return {"due": False, "reason": "expired_post", "age_hours": age_hours}

        platform = str(post.get("platform") or "").strip().lower()
        if platform not in self.platform_fetchers:
            return {"due": False, "reason": "unknown_platform", "platform": platform}

        post_id = str(post.get("post_id") or "").strip()
        if not post_id:
            return {"due": False, "reason": "missing_post_id", "platform": platform}

        interval_hours = _poll_interval_hours(age_hours)
        last_pull = post.get("pulled_at") or published_at
        hours_since_last = _hours_since(last_pull)
        if hours_since_last < interval_hours:
            return {
                "due": False,
                "reason": "not_due",
                "platform": platform,
                "post_id": post_id,
                "age_hours": age_hours,
                "interval_hours": interval_hours,
                "hours_since_last": hours_since_last,
            }
        return {
            "due": True,
            "reason": "due",
            "platform": platform,
            "post_id": post_id,
            "age_hours": age_hours,
            "interval_hours": interval_hours,
            "hours_since_last": hours_since_last,
        }

    # ------------------------------------------------------------------
    # Platform-specific fetchers
    # ------------------------------------------------------------------

    async def _fetch_from_platform(self, platform: str, post_id: str) -> dict[str, Any] | None:
        """Route to the correct platform fetcher based on *platform* name."""
        platform_lower = platform.strip().lower()
        fetcher = self.platform_fetchers.get(platform_lower)
        if fetcher is not None:
            payload = await fetcher(post_id)
            return _normalize_metrics_payload(platform_lower, post_id, payload)
        logger.warning("metrics_poller: unknown platform %r — returning empty", platform)
        return None

    async def _fetch_from_tiktok(self, post_id: str) -> dict[str, Any]:
        """Fetch metrics from TikTok Insights API.

        Default path is fail-closed until the TikTok connector implements a
        real metrics method. Tests may inject a fake fetcher for no-provider
        contract coverage.
        """
        from src.connectors.tiktok_connector import TikTokConnector

        return await self._fetch_via_connector(TikTokConnector(), post_id, "tiktok")

    async def _fetch_from_shopify(self, post_id: str) -> dict[str, Any]:
        """Fetch metrics from Shopify Analytics API.

        Default path is fail-closed until the Shopify connector implements a
        real metrics method. Tests may inject a fake fetcher for no-provider
        contract coverage.
        """
        from src.connectors.shopify_connector import ShopifyConnector

        return await self._fetch_via_connector(ShopifyConnector(), post_id, "shopify")

    async def _fetch_via_connector(
        self,
        connector: Any,
        post_id: str,
        platform: str,
    ) -> dict[str, Any]:
        fetch_metrics = getattr(connector, "fetch_metrics", None)
        if not callable(fetch_metrics):
            raise PlatformMetricsError(
                "not_implemented",
                f"{platform} connector has no fetch_metrics method",
            )
        try:
            return await fetch_metrics(post_id)
        except NotImplementedError as exc:
            raise PlatformMetricsError("not_implemented", str(exc)) from exc
        except PlatformMetricsError:
            raise
        except Exception as exc:
            raise PlatformMetricsError(
                "transient",
                f"{platform} metrics fetch failed: {exc}",
            ) from exc
