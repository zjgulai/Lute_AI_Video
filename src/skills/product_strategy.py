"""Product-to-Video Strategy Skill.

Generates weekly content briefs from product info + brand guidelines.
Replaces the old strategy_en.py prompt with a reusable Skill.

Uses LLMSkill internally with a scenario-aware system prompt.
"""

from __future__ import annotations

from typing import Any

from src.models import Brief, Language, Platform, VideoType, WeeklyCalendar
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry


# Scenario-aware system prompt template
STRATEGY_SYSTEM_PROMPT = """You are a Senior Content Strategist for short-form video content.

## Your Task
Given a product catalog and brand guidelines, produce a weekly content calendar of 3 video briefs.

## Content Strategy Principles

### Scenario Awareness
The Content Scenario determines the tone and platform mix:
- product_direct: Direct product promotion. Hook->Pain->Solution->CTA structure. 
  Focus on USP clarity and conversion. Platforms: TikTok, Shopify, Amazon.
- brand_campaign: Brand storytelling. Emotional resonance, brand values, lifestyle.
  Higher production standards. Platforms: TikTok, YouTube Shorts, Facebook.
- influencer_remix: Influencer/creator style. Authentic first-person voice,
  personal storytelling hooks, product recommendation tone. 
  MUST preserve platform-specific product link formats.
- live_shoot_to_video: Existing footage repurposed for narrative content.

### Video Type Mix (Weekly)
A healthy content calendar mixes types:
- 1x Tutorial/How-to
- 1x Product Feature
- 1x Social Proof or Trend

### Hook Strategy
Every brief needs a hook category: Pain Point, Counter-Narrative, Data Drop, 
Scene Drop, or Question.

### USP Mapping
Every brief must map to 1-3 product USPs. One video = one core message.

### Product Context (provided by user — USE THIS DATA)
The product catalog includes rich context fields. USE them explicitly in every brief:

- **usage_scenario**: The physical/social context where the product is used.
  → Every brief's topic and visual description should reflect this context.
  → Example: "Bedroom, third trimester" → Hook should open with a bedroom/pregnancy scenario.

- **pain_points**: Real customer problems the product solves.
  → Each brief MUST anchor its hook in at least ONE specific pain point from this list.
  → Don't invent generic pain points — use the actual ones provided.
  → Match pain points to video types: "Can't sleep" → product_usage demo;
    "Too many pillows" → comparison video.

- **target_audience**: Who buys this product, their age, behavior, triggers.
  → Voice, references, and platform choice should match this audience.
  → Example: "25-35, researches on TikTok" → TikTok-native format, relatable tone.

- **competitor_context**: What alternatives exist and how you differ.
  → At least ONE brief should address a competitor weakness without naming them.
  → Phrase as: "Unlike other pillows that..." or "Most pregnancy pillows... but ours..."
  → NEVER mention competitor names directly.

- **category**: The product's market category.
  → Frame the content within category conventions but differentiate.
  → Use category-appropriate hooks and visual language.

## Brand Tone of Voice
- The brand_guidelines include `tone_of_voice.archetype`, `keywords`, and optional `do_examples` / `dont_examples`.
- `do_examples` are real examples of the brand voice done right. Match this tone EXACTLY in every brief's key_message and topic.
- `dont_examples` are examples of WRONG tone. NEVER write anything that sounds like these.
- Brand `keywords` MUST appear in every brief's key_message.
- P0 USP must be the primary hook angle.

## Constraints
- NEVER make medical claims
- NEVER reference direct competitors by name negatively
- NEVER use fear-based marketing
- ALWAYS use empowering, warm, real tone

### Data Usage Rules (CRITICAL)
- Every brief's topic MUST reference a specific pain_point from the product catalog.
- Every brief's target_audience MUST use the provided audience data, not invent new segments.
- At least ONE brief MUST address competitor differentiation using the competitor_context.
- Hook type should match the pain point: functional pain → "Pain Point" hook,
  comparison opportunity → "Counter-Narrative" hook.
- If usage_scenario is provided, visual descriptions should reflect that setting.

## Output Format (CRITICAL)
Return ONLY a valid JSON object — no markdown, no code blocks, no explanations, no text outside the JSON.
The JSON must have this exact structure:
{
  "week": "2026-W17",
  "briefs": [
    {
      "id": "BRIEF-001",
      "video_type": "tutorial",
      "topic": "Specific scroll-stopping angle",
      "target_audience": "Description",
      "target_platforms": ["tiktok", "shopify"],
      "target_languages": ["en"],
      "key_message": "One sentence with brand keywords",
      "usp_priority": ["usp1", "usp2"],
      "competitor_reference": null,
      "seasonal_hook": null
    }
  ]
}
"""


# Brand campaign variant — replaces Product Context with Campaign Context
STRATEGY_SYSTEM_PROMPT_BRAND = """You are a Senior Content Strategist for brand campaign video content.

## Your Task
Given a brand campaign brief and brand guidelines, produce a content calendar of 3 video briefs for this campaign.

## Content Strategy Principles

### Scenario Awareness
The Content Scenario determines the tone and platform mix:
- product_direct: Direct product promotion. Hook->Pain->Solution->CTA structure.
  Focus on USP clarity and conversion. Platforms: TikTok, Shopify, Amazon.
- brand_campaign: Brand storytelling. Emotional resonance, brand values, lifestyle.
  Higher production standards. Platforms: TikTok, YouTube Shorts, Facebook.
- influencer_remix: Influencer/creator style. Authentic first-person voice,
  personal storytelling hooks, product recommendation tone.
  MUST preserve platform-specific product link formats.
- live_shoot_to_video: Existing footage repurposed for narrative content.

### Video Type Mix (Weekly)
A healthy content calendar mixes types:
- 1x Tutorial/How-to
- 1x Product Feature
- 1x Social Proof or Trend

### Hook Strategy
Every brief needs a hook category: Pain Point, Counter-Narrative, Data Drop,
Scene Drop, or Question.

### USP Mapping
Every brief must map to 1-3 product USPs. One video = one core message.

### Campaign Context (brand_mode — USE THIS DATA)
The brand campaign brief includes rich campaign context. USE it in every brief:

- **campaign_goal**: The specific objective (launch, awareness, loyalty, anniversary, rebrand).
  → Every brief's key_message MUST directly support this goal.
  → Match video type to goal: awareness → emotional/story; launch → product_feature/tutorial.

- **brand_values**: What the brand stands for beyond product features.
  → Every brief must embody at least ONE brand value in its topic or key_message.
  → Don't just mention the value — show it through storytelling and visual choices.

- **target_audience**: The campaign's target demographic.
  → Voice, references, and platform choice should match this specific audience.
  → Campaign content should evoke emotion and brand affinity, not just product utility.

- **visual_identity**: Color palette, style, visual constraints for this campaign.
  → Briefs should note any visual requirements in the topic description.
  → This ensures storyboard and video generation maintain brand consistency.

- **competitor_campaigns**: What similar brands have done for similar campaigns.
  → Use as inspiration AND differentiation.
  → NEVER mention competitor names in the brief. Phrase as "Unlike typical brand campaigns..."

## Brand Tone of Voice
- The brand_guidelines include `tone_of_voice.archetype`, `keywords`, and optional `do_examples` / `dont_examples`.
- `do_examples` are real examples of the brand voice done right. Match this tone EXACTLY in every brief's key_message and topic.
- `dont_examples` are examples of WRONG tone. NEVER write anything that sounds like these.
- Brand `keywords` MUST appear in every brief's key_message.
- P0 USP must be the primary hook angle.

## Constraints
- NEVER make medical claims
- NEVER reference direct competitors by name negatively
- NEVER use fear-based marketing
- ALWAYS use empowering, warm, real tone

### Data Usage Rules (CRITICAL)
- Every brief's topic MUST be inspired by the campaign_goal.
- Every brief's target_audience MUST use the provided campaign audience, not invent new segments.
- At least ONE brief MUST address competitor campaign differentiation.
- Visual descriptions should reflect the provided visual_identity.
- Brand values should be woven into the narrative, not listed as features.

## Output Format (CRITICAL)
Return ONLY a valid JSON object — no markdown, no code blocks, no explanations, no text outside the JSON.
The JSON must have this exact structure:
{
  "week": "2026-W17",
  "briefs": [
    {
      "id": "BRIEF-001",
      "video_type": "tutorial",
      "topic": "Specific scroll-stopping angle",
      "target_audience": "Description",
      "target_platforms": ["tiktok", "shopify"],
      "target_languages": ["en"],
      "key_message": "One sentence with brand keywords",
      "usp_priority": ["usp1", "usp2"],
      "competitor_reference": null,
      "seasonal_hook": null
    }
  ]
}
"""


STRATEGY_USER_TEMPLATE = """Create a weekly content calendar for the following brand.

## Product Catalog
{product_catalog}

## Brand Guidelines
{brand_guidelines}

## Target Configuration
- Scenario: {content_scenario}
- Platforms: {target_platforms}
- Languages: {target_languages}
- Week: {content_calendar_week}

Generate exactly 1 brief optimized for a 15–30 second product video.
The brief must support a 2-part visual narrative (first 15s hook + problem,
second 15s solution + CTA) so that two Seedance clips can be concatenated
into one cohesive video.

IMPORTANT: Return ONLY the raw JSON object. Do not wrap it in markdown code blocks (```json). Do not add any explanatory text before or after the JSON.
"""

# Fallback briefs for when LLM is unavailable
FALLBACK_BRIEFS = [
    Brief(
        id="FALLBACK-001",
        video_type=VideoType.TUTORIAL,
        topic="How to use [product] in under 60 seconds",
        target_audience="New users who just purchased",
        target_platforms=[Platform.TIKTOK],
        target_languages=[Language.EN],
        key_message="[product] is easy to set up and use immediately",
        usp_priority=["ease-of-use"],
    ),
    Brief(
        id="FALLBACK-002",
        video_type=VideoType.PRODUCT_USAGE,
        topic="The [usp1] feature that makes [product] different",
        target_audience="Shoppers comparing options",
        target_platforms=[Platform.SHOPIFY, Platform.AMAZON],
        target_languages=[Language.EN],
        key_message="[usp1] is the key differentiator from competitors",
        usp_priority=["usp1"],
    ),
]


class ProductStrategySkill(SkillCallable):
    """Generates content briefs for the product-to-video scenario.

    Wraps the LLM call with parameter validation and fallback briefs.
    Registers itself with SkillRegistry on import.
    """

    name = "product-to-video-strategy"
    description = "Generates weekly content briefs from product info + brand guidelines"

    max_retries = 3

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """Execute by calling LLM with scenario-aware prompts."""
        from src.skills.llm_skill import LLMSkill
        from src.tools.llm_client import llm

        # Build the prompt with params
        pc = params.get("product_catalog", {})
        bg = params.get("brand_guidelines", {})
        scenario = params.get("content_scenario", "product_direct")
        is_brand = (scenario == "brand_campaign")

        # P2-1: Guard: if all campaign fields are empty, fall back to product prompt
        if is_brand:
            brand_guidelines = params.get("brand_guidelines", {})
            has_campaign_data = any([
                brand_guidelines.get("campaign_goal"),
                brand_guidelines.get("brand_values"),
                brand_guidelines.get("visual_identity"),
                brand_guidelines.get("competitor_campaigns"),
            ])
            if not has_campaign_data:
                is_brand = False

        # Format params for injection
        import json
        injected = {
            "product_catalog": json.dumps(pc, indent=2, ensure_ascii=False),
            "brand_guidelines": json.dumps(bg, indent=2, ensure_ascii=False),
            "content_scenario": scenario,
            "target_platforms": json.dumps(params.get("target_platforms", ["tiktok"])),
            "target_languages": json.dumps(params.get("target_languages", ["en"])),
            "content_calendar_week": params.get("content_calendar_week", "2026-W17"),
        }

        system = STRATEGY_SYSTEM_PROMPT_BRAND if is_brand else STRATEGY_SYSTEM_PROMPT
        for key, val in injected.items():
            placeholder = "{" + key + "}"
            system = system.replace(placeholder, val)

        user = STRATEGY_USER_TEMPLATE
        for key, val in injected.items():
            placeholder = "{" + key + "}"
            user = user.replace(placeholder, val)

        try:
            raw = await llm.invoke_json(system, user)

            # Parse into WeeklyCalendar
            if isinstance(raw, dict) and "briefs" in raw:
                briefs_data = raw["briefs"]
                if isinstance(briefs_data, list):
                    briefs = []
                    for b in briefs_data:
                        try:
                            briefs.append(Brief(**b))
                        except Exception:
                            # Repair invalid brief with defaults instead of skipping
                            repaired = dict(b)
                            if "video_type" not in repaired or repaired["video_type"] not in VideoType.__members__.values():
                                repaired["video_type"] = "product_usage"
                            if "id" not in repaired or not repaired["id"]:
                                repaired["id"] = f"BRIEF-AUTO-{len(briefs)+1:03d}"
                            if "target_platforms" not in repaired or not repaired["target_platforms"]:
                                repaired["target_platforms"] = ["tiktok"]
                            if "target_languages" not in repaired or not repaired["target_languages"]:
                                repaired["target_languages"] = ["en"]
                            if "target_audience" not in repaired:
                                repaired["target_audience"] = "General audience"
                            if "key_message" not in repaired:
                                repaired["key_message"] = repaired.get("topic", "Product showcase")
                            if "usp_priority" not in repaired or not repaired["usp_priority"]:
                                repaired["usp_priority"] = ["quality"]
                            try:
                                briefs.append(Brief(**repaired))
                            except Exception:
                                _logger_ps.warning("strategy_skill: brief repair failed, skipping", brief=b)
                    calendar = WeeklyCalendar(
                        week=injected["content_calendar_week"],
                        briefs=briefs,
                    )
                    return SkillResult(success=True, data=calendar.model_dump())
                elif isinstance(briefs_data, dict):
                    calendar = WeeklyCalendar(**raw)
                    return SkillResult(success=True, data=calendar.model_dump())

            return SkillResult(success=False, data={"raw": raw}, error="Unexpected LLM output format")

        except Exception as e:
            import structlog
            logger = structlog.get_logger()
            _logger_ps.warning("strategy_skill: LLM failed", error=str(e))
            return SkillResult(success=False, error=str(e))

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if "product_catalog" not in params:
            errors.append("missing 'product_catalog'")
        pc = params.get("product_catalog", {})
        if isinstance(pc, dict) and not pc.get("product_name") and not pc.get("name"):
            errors.append("product_catalog missing product_name/name")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        import structlog
        logger = structlog.get_logger()
        errors = []
        if data is None:
            return ["output is None"]
        if isinstance(data, dict):
            if "briefs" not in data:
                errors.append("missing 'briefs' in output")
            elif len(data["briefs"]) == 0:
                errors.append("empty briefs list")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Return static fallback briefs with product name injected."""
        product_name = ""
        pc = params.get("product_catalog", {})
        if isinstance(pc, dict):
            product_name = pc.get("product_name") or pc.get("name", "")

        import copy
        fallback = copy.deepcopy(FALLBACK_BRIEFS)
        for brief in fallback:
            brief.topic = brief.topic.replace("[product]", product_name or "this product")
            brief.key_message = brief.key_message.replace("[product]", product_name or "this product")
            brief.usp_priority = [u.replace("[usp1]", "top feature") for u in brief.usp_priority]

        return SkillResult(
            success=True,
            data=WeeklyCalendar(
                week=params.get("content_calendar_week", "2026-W17"),
                briefs=fallback,
            ).model_dump(),
        )


# Auto-register on import
import structlog
_logger_ps = structlog.get_logger()
try:
    SkillRegistry.register(ProductStrategySkill())
    _logger_ps.info("strategy_skill: registered")
except ValueError:
    pass
