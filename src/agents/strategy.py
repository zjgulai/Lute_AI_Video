"""Strategy Agent — generates weekly content briefs.

Phase 1 MVP: calls LLM with structured prompt.
Falls back to sensible mock data when API key is unavailable.
"""

from __future__ import annotations

import json

import structlog

from src.agents.prompts.strategy_en import (
    STRATEGY_SYSTEM_PROMPT_EN,
    STRATEGY_USER_MESSAGE_TEMPLATE,
)
from src.models import Brief, Language, Platform, VideoType, WeeklyCalendar
from src.tools.llm_client import llm

logger = structlog.get_logger()

# Mock fallback briefs for development without API keys
_MOCK_BRIEFS = [
    Brief(
        id="BRIEF-001",
        video_type=VideoType.TUTORIAL,
        topic="How to clean your wearable pump at the office in 2 minutes",
        target_audience="Working moms 25-35",
        target_platforms=[Platform.TIKTOK, Platform.YOUTUBE_SHORTS],
        target_languages=[Language.EN],
        key_message="Discreet cleaning that fits into your workday",
        usp_priority=["portable", "easy-clean", "quiet"],
        competitor_reference="Elvie Stride cleaning video (2.3M views)",
        seasonal_hook="Back-to-office pumping tips",
    ),
    Brief(
        id="BRIEF-002",
        video_type=VideoType.CUSTOMER_TESTIMONIAL,
        topic="Real mom: 'I pumped during a board meeting and nobody knew'",
        target_audience="Corporate moms 28-40",
        target_platforms=[Platform.TIKTOK, Platform.FACEBOOK],
        target_languages=[Language.EN],
        key_message="True hands-free discretion — even in high-stakes settings",
        usp_priority=["discreet", "quiet", "hands-free"],
        competitor_reference=None,
        seasonal_hook=None,
    ),
    Brief(
        id="BRIEF-003",
        video_type=VideoType.PRODUCT_USAGE,
        topic="Side-by-side: traditional pump setup vs X1 wearable (speed test)",
        target_audience="First-time moms researching pumps",
        target_platforms=[Platform.TIKTOK, Platform.SHOPIFY],
        target_languages=[Language.EN],
        key_message="Setup in 30 seconds vs 5 minutes — your time matters",
        usp_priority=["easy-setup", "portable", "time-saving"],
        competitor_reference="Traditional flange-and-bottle setup comparison",
        seasonal_hook=None,
    ),
    Brief(
        id="BRIEF-004",
        video_type=VideoType.INDUSTRY_INSIGHT,
        topic="The hidden cost of pumping at work: what 500 moms told us",
        target_audience="HR professionals + working moms",
        target_platforms=[Platform.FACEBOOK, Platform.YOUTUBE_SHORTS],
        target_languages=[Language.EN],
        key_message="Better pumping solutions benefit both moms and employers",
        usp_priority=["portable", "time-saving", "quiet"],
        competitor_reference=None,
        seasonal_hook="Mental Health Awareness Month tie-in",
    ),
    Brief(
        id="BRIEF-005",
        video_type=VideoType.UNBOXING,
        topic="Unboxing the X1: what's actually in the box + first impression",
        target_audience="Moms 25-40 researching wearable pumps",
        target_platforms=[Platform.TIKTOK, Platform.SHOPIFY],
        target_languages=[Language.EN],
        key_message="Everything you need, nothing you don't — ready in under a minute",
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

    def _load_scenario_config(self) -> dict:
        """Load scenario config, fallback to empty dict."""
        try:
            from strategy_source import load_scenario
            return load_scenario(self.content_scenario)
        except Exception:
            logger.warning("strategy_agent: scenario config not found", scenario=self.content_scenario)
            return {}

    async def run(
        self,
        product_catalog: dict,
        brand_guidelines: dict,
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
                from src.data.mock_quality import degrade_strategy, QualityLevel
                try:
                    level = QualityLevel(self.quality_level)
                    calendar = degrade_strategy(level, week=week)
                    briefs = calendar.briefs
                except Exception:
                    briefs = _MOCK_BRIEFS.copy()
            else:
                briefs = _MOCK_BRIEFS.copy()

            # Override each brief's target_platforms with user-selected platforms
            if platform_objs:
                import copy
                briefs = [copy.copy(b) for b in briefs]  # shallow copy so we don't mutate module globals
                for b in briefs:
                    b.target_platforms = platform_objs

            return WeeklyCalendar(week=week, briefs=briefs)

        if self.use_skills:
            from src.skills.registry import SkillRegistry
            import src.skills.product_strategy  # noqa: F401
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
            return WeeklyCalendar(week=week, briefs=_MOCK_BRIEFS)
