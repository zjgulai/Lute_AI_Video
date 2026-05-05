"""Test Strategy Agent — mock mode."""

import pytest
from src.agents.strategy import StrategyAgent


class TestStrategyAgent:
    @pytest.mark.asyncio
    async def test_mock_returns_calendar(self, sample_product_catalog, sample_brand_guidelines):
        agent = StrategyAgent(use_mock=True)
        result = await agent.run(
            product_catalog=sample_product_catalog,
            brand_guidelines=sample_brand_guidelines,
            target_platforms=["tiktok"],
            target_languages=["en"],
            week="2026-W17",
        )
        assert result.week == "2026-W17"
        assert len(result.briefs) == 5
        assert result.briefs[0].id == "BRIEF-001"
        assert result.briefs[0].video_type.value in [
            "tutorial", "customer_testimonial", "product_usage",
            "industry_insight", "unboxing",
        ]

    @pytest.mark.asyncio
    async def test_mock_briefs_have_required_fields(self, sample_product_catalog, sample_brand_guidelines):
        agent = StrategyAgent(use_mock=True)
        result = await agent.run(
            product_catalog=sample_product_catalog,
            brand_guidelines=sample_brand_guidelines,
            target_platforms=["tiktok"],
            target_languages=["en"],
            week="2026-W17",
        )
        for brief in result.briefs:
            assert brief.topic
            assert brief.target_audience
            assert len(brief.target_platforms) > 0
            assert brief.key_message
            assert len(brief.usp_priority) > 0
