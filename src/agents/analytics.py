"""Analytics Agent — performance report generation.

MVP: outputs template report with mock data.
Phase 2+: platform API data ingestion, feedback loop to Strategy Agent.
"""

import structlog

from src.models import AnalyticsReport, Script, VideoMetrics

logger = structlog.get_logger()


class AnalyticsAgent:
    """Generates analytics reports with optimization recommendations."""

    async def run(self, scripts: list[Script], week: str) -> list[AnalyticsReport]:
        metrics = []
        for script in scripts:
            metrics.append(
                VideoMetrics(
                    script_id=script.id,
                    platform=script.platform,
                    views=0,
                    completion_rate=0.0,
                    engagement_rate=0.0,
                    conversion_rate=0.0,
                )
            )

        report = AnalyticsReport(
            week=week,
            metrics=metrics,
            recommendations=[
                "MVP: Analytics data will populate after videos are published and platform APIs are connected.",
                "Priority metrics: completion_rate > engagement_rate > conversion_rate",
            ],
        )
        logger.info("analytics: done (mock)")
        return [report]
