"""Strategy Agent — generates weekly content briefs.

Phase 1 MVP: calls LLM with structured prompt.
Falls back to sensible mock data when API key is unavailable.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.agents.prompts.strategy_en import (
    STRATEGY_SYSTEM_PROMPT_EN,
    STRATEGY_USER_MESSAGE_TEMPLATE,
)
from src.config import MOCK_PRODUCT_CATEGORY, MOCK_PRODUCT_NAME
from src.models import Brief, Language, Platform, VideoType, WeeklyCalendar
from src.tools.llm_client import llm

logger = structlog.get_logger()


def _make_mock_briefs() -> list[Brief]:
    """Generate mock briefs using the configured product theme.

    Replaces hard-coded breast pump content with parameterized values
    from MOCK_PRODUCT_NAME / MOCK_PRODUCT_CATEGORY env vars.
    """
    pn = MOCK_PRODUCT_NAME
    pc = MOCK_PRODUCT_CATEGORY
    return [
        Brief(
            id="BRIEF-001",
            video_type=VideoType.TUTORIAL,
            topic=f"How to use your {pc} in daily life — 2-minute guide",
            target_audience="New users 25-40",
            target_platforms=[Platform.TIKTOK, Platform.YOUTUBE_SHORTS],
            target_languages=[Language.EN],
            key_message=f"Seamless integration — {pc} fits your lifestyle",
            usp_priority=["portable", "easy-use", "quiet"],
            competitor_reference="Top competitor tutorial (2.3M views)",
            seasonal_hook="Everyday usage tips",
        ),
        Brief(
            id="BRIEF-002",
            video_type=VideoType.CUSTOMER_TESTIMONIAL,
            topic=f"Real user: 'I used {pn} at work and nobody noticed'",
            target_audience="Professionals 28-45",
            target_platforms=[Platform.TIKTOK, Platform.FACEBOOK],
            target_languages=[Language.EN],
            key_message="Discreet and effective — even in busy environments",
            usp_priority=["discreet", "quiet", "hands-free"],
            competitor_reference=None,
            seasonal_hook=None,
        ),
        Brief(
            id="BRIEF-003",
            video_type=VideoType.PRODUCT_USAGE,
            topic=f"Side-by-side: traditional {pc} vs {pn} (speed test)",
            target_audience=f"First-time buyers researching {pc}",
            target_platforms=[Platform.TIKTOK, Platform.SHOPIFY],
            target_languages=[Language.EN],
            key_message="Setup in 30 seconds vs 5 minutes — your time matters",
            usp_priority=["easy-setup", "portable", "time-saving"],
            competitor_reference="Traditional setup comparison",
            seasonal_hook=None,
        ),
        Brief(
            id="BRIEF-004",
            video_type=VideoType.INDUSTRY_INSIGHT,
            topic=f"The real cost of using {pc}: insights from 500 users",
            target_audience="Industry professionals + target users",
            target_platforms=[Platform.FACEBOOK, Platform.YOUTUBE_SHORTS],
            target_languages=[Language.EN],
            key_message=f"Better {pc} solutions benefit both users and businesses",
            usp_priority=["portable", "time-saving", "quiet"],
            competitor_reference=None,
            seasonal_hook="User awareness month tie-in",
        ),
        Brief(
            id="BRIEF-005",
            video_type=VideoType.UNBOXING,
            topic=f"Unboxing the {pn}: what's inside + first impressions",
            target_audience=f"Users 25-40 researching {pc}",
            target_platforms=[Platform.TIKTOK, Platform.SHOPIFY],
            target_languages=[Language.EN],
            key_message="Everything you need — ready in under a minute",
            usp_priority=["easy-setup", "portable", "complete-kit"],
            competitor_reference=None,
            seasonal_hook=None,
        ),
    ]


class StrategyAgent:
    """Generates weekly content calendars from product + brand inputs.

    Supports quality-controlled mock data via the quality_level parameter
    (requires the use_mock=True flag or no API keys available).
    """

    def __init__(self, use_mock: bool = False, quality_level: str | None = None, content_scenario: str = "general", use_skills: bool = False):
        self.use_skills = use_skills
        self.use_mock = use_mock or (not use_skills and not llm.is_configured())
        self.quality_level = quality_level
        self.content_scenario = content_scenario
        # Load scenario configuration from strategy_source/
        self.scenario_config = self._load_scenario_config()

    def _load_scenario_config(self) -> dict[str, Any]:
        """Load scenario config, fallback to empty dict."""
        try:
            from strategy_source import load_scenario
            return load_scenario(self.content_scenario)
        except Exception:
            logger.warning("strategy_agent: scenario config not found", scenario=self.content_scenario)
            return {}

    async def run(
        self,
        product_catalog: dict[str, Any],
        brand_guidelines: dict[str, Any],
        target_platforms: list[str],
        target_languages: list[str],
        week: str,
    ) -> WeeklyCalendar:
        if self.use_mock:
            from src.config import ALLOW_MOCK_MODE, ENVIRONMENT
            if not ALLOW_MOCK_MODE:
                raise RuntimeError(
                    f"Mock mode is disabled (ALLOW_MOCK_MODE=false, ENVIRONMENT={ENVIRONMENT}). "
                    f"Set use_mock=False and ensure API keys are configured."
                )
            logger.info("strategy_agent: using mock data", quality_level=self.quality_level)
            # Build platform set once — must use state's target_platforms
            # Frontend sends lowercase strings ('shopify', 'amazon') but Platform enum keys are uppercase ('SHOPIFY')
            platform_objs: list[Platform] = []
            for p in target_platforms:
                try:
                    # Try value-based lookup first (e.g. Platform('shopify'))
                    platform_objs.append(Platform(p))
                except ValueError:
                    pass
            if not platform_objs:
                platform_objs = [Platform.TIKTOK, Platform.SHOPIFY, Platform.AMAZON, Platform.REDDIT]

            briefs: list[Brief]
            if self.quality_level:
                from src.data.mock_quality import QualityLevel, degrade_strategy
                try:
                    level = QualityLevel(self.quality_level)
                    calendar = degrade_strategy(level, week=week)
                    briefs = calendar.briefs
                except Exception:
                    briefs = _make_mock_briefs().copy()
            else:
                briefs = _make_mock_briefs().copy()

            # Override each brief's target_platforms with user-selected platforms
            if platform_objs:
                import copy
                briefs = [copy.copy(b) for b in briefs]  # shallow copy so we don't mutate module globals
                for b in briefs:
                    b.target_platforms = platform_objs

            return WeeklyCalendar(week=week, briefs=briefs)

        if self.use_skills:
            import src.skills.product_strategy  # noqa: F401
            from src.skills.registry import SkillRegistry
            result = await SkillRegistry().execute("product-to-video-strategy", {
                "product_catalog": product_catalog,
                "brand_guidelines": brand_guidelines,
                "target_platforms": target_platforms,
                "target_languages": target_languages,
                "content_calendar_week": week,
                "content_scenario": self.content_scenario,
            })
            if result.success and result.data:
                briefs = [Brief(**b) for b in result.data.get("briefs", [])]
                return WeeklyCalendar(week=week, briefs=briefs)
            logger.warning("strategy_agent: skill failed, falling back to LLM", error=result.error)

        user_message = STRATEGY_USER_MESSAGE_TEMPLATE.format(
            product_catalog_json=json.dumps(product_catalog, indent=2),
            brand_guidelines_json=json.dumps(brand_guidelines, indent=2),
            platforms=', '.join(target_platforms),
            languages=', '.join(target_languages),
            week=week,
            content_scenario=self.content_scenario,
        )

        try:
            # Build system prompt: base + scenario-specific addendum
            system_prompt = STRATEGY_SYSTEM_PROMPT_EN
            addendum = self.scenario_config.get("system_prompt_addendum", "")
            if addendum:
                system_prompt = system_prompt + "\n\n" + addendum

            data = await llm.invoke_json(system_prompt, user_message)
            briefs = [Brief(**b) for b in data["briefs"]]
            return WeeklyCalendar(week=data.get("week", week), briefs=briefs)
        except Exception as e:
            logger.error("strategy_agent: LLM call failed", error=str(e))
            logger.info("strategy_agent: falling back to mock data")
            return WeeklyCalendar(week=week, briefs=_make_mock_briefs())
