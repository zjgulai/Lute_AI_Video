"""Script Writer Agent — converts briefs into platform-adapted scripts.

Phase 2: Multi-language support (ES/FR/DE).
Falls back to mock data when API key unavailable.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.models import AuditCriterionStatus, AuditReport, Brief, Language, Script, ScriptSegment
from src.models.provider_cost import ProviderCostContractError
from src.tools.llm_client import llm

logger = structlog.get_logger()


class ScriptWriterAgent:
    """Writes production-ready short video scripts from content briefs."""

    _mock_generated = False

    def __init__(self, use_mock: bool = False, use_skills: bool = False):
        self.use_mock = use_mock
        self.use_skills = use_skills

    async def run(
        self,
        briefs: list[Brief],
        brand_guidelines: dict[str, Any],
        strategy_audit: AuditReport | None = None,
        target_languages: list[str] | None = None,
    ) -> list[Script]:
        """Generate scripts, optionally in multiple languages.

        Args:
            briefs: Content briefs to write scripts for.
            brand_guidelines: Brand tone/voice/colors.
            strategy_audit: Optional audit report for quality signal injection.
            target_languages: List of language codes. Defaults to DEFAULT_LANGUAGES.

        Returns:
            List of scripts — one per brief per platform per language.
        """
        # Multi-language backend support removed (v0.3); locked to English.
        # target_languages argument is kept for API compatibility.
        lang_code = "en"
        quality_signals = self._extract_quality_signals(strategy_audit)
        briefs_json = json.dumps(
            [b.model_dump(mode="json") for b in briefs], indent=2, default=str
        )

        if self.use_skills:
            import src.skills.script_writer  # noqa: F401
            from src.skills.registry import SkillRegistry
            result = await SkillRegistry().execute("script-writer-skill", {
                "briefs": [b.model_dump(mode="json") for b in briefs],
                "brand_guidelines": brand_guidelines,
                "target_languages": [lang_code],
                "quality_signals": quality_signals,
            })
            if result.success and result.data:
                from src.models import Script
                raw_scripts = result.data.get("scripts", [])
                return [Script(**s) for s in raw_scripts]
            logger.warning("script-writer: skill failed, falling back to LLM", error=result.error)

        return await self._run_for_language(
            briefs, briefs_json, brand_guidelines, quality_signals, lang_code
        )

    async def _run_for_language(
        self,
        briefs: list[Brief],
        briefs_json: str,
        brand_guidelines: dict[str, Any],
        quality_signals: dict[str, Any],
        lang_code: str,
    ) -> list[Script]:
        """Run script generation for a single language (locked to EN)."""
        if self.use_mock:
            from src.config import ALLOW_MOCK_MODE
            if not ALLOW_MOCK_MODE:
                raise RuntimeError(
                    "Mock mode is disabled (ALLOW_MOCK_MODE=false). "
                    "Set use_mock=False and ensure API keys are configured."
                )
            return self._mock_scripts(briefs, quality_signals=quality_signals, language_code=lang_code)

        from src.agents.prompts.script_writer_en import (
            SCRIPT_WRITER_SYSTEM_PROMPT_EN,
            SCRIPT_WRITER_USER_MESSAGE_TEMPLATE,
        )
        user_message = SCRIPT_WRITER_USER_MESSAGE_TEMPLATE.format(
            brand_guidelines_json=json.dumps(brand_guidelines, indent=2),
            briefs_json=briefs_json,
            quality_signals_json=json.dumps(quality_signals, indent=2) if quality_signals else "{}",
        )

        try:
            raw_data = await llm.invoke_json(
                SCRIPT_WRITER_SYSTEM_PROMPT_EN,
                user_message,
                model="deepseek-v4-flash",
                operation_key="agent.script_writer",
                operation_instance=f"language.{lang_code.lower().replace('-', '_')}",
            )
            scripts: list[Script] = []
            if isinstance(raw_data, list):
                for raw_script in raw_data:
                    if isinstance(raw_script, dict):
                        raw_script["id"] = raw_script.get("id", "")
                        raw_script["language"] = lang_code
                        try:
                            scripts.append(Script(**raw_script))  # type: ignore[arg-type]
                        except Exception:
                            logger.warning("script_writer: failed to parse script", raw=raw_script)
            return scripts
        except ProviderCostContractError:
            raise
        except Exception as e:
            logger.error("script_writer: LLM call failed", error=str(e), lang=lang_code)
            from src.config import ALLOW_MOCK_MODE
            if not ALLOW_MOCK_MODE:
                raise RuntimeError(
                    f"Script generation failed and mock fallback is disabled: {e}"
                ) from e
            return self._mock_scripts(briefs, quality_signals=quality_signals, language_code=lang_code)

    _SCRIPT_TEMPLATES = {
        "BRIEF-001": {  # Tutorial: clean pump at office
            "hook": "Pumping at work doesn't have to mean hiding in a supply closet.",
            "hook_visual": "Split screen: woman at desk smiling vs empty storage room",
            "hook_overlay": "Clean in 2 min? Yes.",
            "pain": "Finding a clean space to pump is hard enough. Cleaning everything after? Even harder. Sinks in public bathrooms, carrying wet parts around.",
            "pain_visual": "Close up of pump parts being washed in office sink, woman checking over shoulder",
            "pain_overlay": "The cleaning struggle is real",
            "solution": "The X1's spill-proof design and silicone parts rinse clean in under 30 seconds. No fridge required. No awkward bathroom trips. Just rinse, dry, and toss back in your bag.",
            "solution_visual": "Hands rinsing X1 parts under faucet, quick cut to putting dry parts into tote bag",
            "solution_overlay": "30 second rinse. Done.",
            "trust": "Hospital-grade 280mmHg suction. FDA cleared. Used by 50,000+ moms who pump at work every day. 2.5 hour battery means you're covered for a full shift.",
            "trust_visual": "FDA badge overlay on product close-up, then grid of mom testimonials",
            "trust_overlay": "FDA Cleared | 280mmHg",
            "cta": "Stop hiding in the supply closet. Grab the X1 at the link in bio. Your pumping break just got a whole lot simpler.",
            "cta_visual": "Woman walking out of office confidently, bag over shoulder, product visible in hand",
            "cta_overlay": "Shop X1 Now",
            "cta_text": "Shop the Wearable Pump X1 — link in bio",
            "hashtags": ["#pumpingatwork", "#wearablepump", "#workingmom", "#pumphack"],
        },
        "BRIEF-002": {  # Customer testimonial: board meeting
            "hook": "I pumped during a board meeting and nobody had the slightest clue.",
            "hook_visual": "Professional woman at long conference table, subtle chest-level shot",
            "hook_overlay": "She's pumping. Right now.",
            "pain": "Before the X1, I was sneaking off to the mother's room 3 times a day. Missing key decisions. Feeling like I had to choose between my career and feeding my baby.",
            "pain_visual": "Woman slipping out of meeting room, looking back wistfully, clock on wall ticking",
            "pain_overlay": "3x a day. 20 min each.",
            "solution": "Now the X1 fits completely inside my bra. Silent motor, less than 40 decibels. I join every meeting, take every call, and still pump on schedule. My team has no idea.",
            "solution_visual": "Woman at laptop in blazer, discreet product outline under blouse, nobody notices",
            "solution_overlay": "100% discreet. 0% sacrifice.",
            "trust": "The X1 isn't just quiet — it's hospital-grade. 280mmHg suction, FDA cleared, and designed by moms who've been in those meetings. 50,000+ moms agree.",
            "trust_visual": "Split: product spec close-up + montage of women in professional settings",
            "trust_overlay": "FDA Cleared | 50K+ Moms",
            "cta": "You don't have to choose between your career and your baby. The X1 is waiting at the link in bio. Freedom to feed, wherever life takes you.",
            "cta_visual": "Woman walking confidently out of office building, smiling, phone in hand showing product page",
            "cta_overlay": "Freedom to Feed ↑",
            "cta_text": "Get the X1 — freedom to pump anywhere",
            "hashtags": ["#boardroompumping", "#workingmom", "#wearablepump", "#momlife"],
        },
        "BRIEF-003": {  # Product usage: speed test comparison
            "hook": "5 minutes of setup vs 30 seconds. Guess which one I'm switching to.",
            "hook_visual": "Two side-by-side timers starting, traditional pump on left, X1 on right",
            "hook_overlay": "5 min vs 30 sec",
            "pain": "Traditional pumps mean untangling tubes, finding an outlet, attaching flanges that don't fit in your bag, and spending half your break just getting set up. By the time you start, you've lost precious pumping time.",
            "pain_visual": "Montage of traditional pump setup: tubes tangling, searching for outlet, bulky bag contents spilling",
            "pain_overlay": "So much setup. So little time.",
            "solution": "The X1 snaps together in three pieces. No tubes. No cords. No outlet needed. Pop it in your bra, turn it on, and you're pumping in under 30 seconds. It's that simple.",
            "solution_visual": "Fast-motion close-up: snapping X1 pieces together, placing in bra, pressing power button",
            "solution_overlay": "Snap. Place. Pump.",
            "trust": "Same hospital-grade suction as the big machines. 220g light. 2.5 hour battery. And quiet enough that nobody around you will ever know.",
            "trust_visual": "Scale showing X1 next to traditional pump, sound meter showing <40dB, battery icon",
            "trust_overlay": "Same power. 1/10 the size.",
            "cta": "Your time is valuable. Stop wasting it on setup. Grab the X1 at the link in bio and start pumping in 30 seconds flat.",
            "cta_visual": "Product centered, glowing, text floating beside it",
            "cta_overlay": "30s Setup → Link in Bio",
            "cta_text": "Save 4.5 minutes every pump session — shop X1",
            "hashtags": ["#pumptips", "#wearablepump", "#pumpcomparison", "#efficiency"],
        },
        "BRIEF-004": {  # Industry insight: hidden cost
            "hook": "500 moms told us the real cost of pumping at work. It's not what you think.",
            "hook_visual": "Woman in office looking at calculator app, numbers adding up on screen overlay",
            "hook_overlay": "The hidden cost of pumping",
            "pain": "Lost productivity. Missed opportunities. The average pumping mom loses 45 minutes of work time per day to setup, cleanup, and walking to the mother's room. That's nearly 4 hours a week. 200 hours a year.",
            "pain_visual": "Animated infographic: calendar filling up with 'pump break' blocks, then crossing out with 'missed meeting' overlays",
            "pain_overlay": "45 min/day lost to pumping logistics",
            "solution": "Companies that provide wearable pumps see 3x higher return-to-work retention. Moms with hands-free pumps pump 2x longer — which means healthier babies and more focused employees.",
            "solution_visual": "Bar chart: retention rates comparison, then cut to happy mom pumping at desk while working",
            "solution_overlay": "3x retention. 2x pumping duration.",
            "trust": "The X1 wearable pump is the #1 choice for corporate pumping programs. Hospital-grade suction, FDA cleared, and completely invisible under business attire.",
            "trust_visual": "Product shot with corporate brochure aesthetic, 'FDA Cleared' badge, workplace wellness logo",
            "trust_overlay": "The #1 choice for corporate wellness",
            "cta": "HR leaders: the X1 corporate program is live. Give your team the freedom to pump and work. Link in bio for the whitepaper.",
            "cta_visual": "Split: HR professional at desk + product on clean white surface, contact form overlay",
            "cta_overlay": "Corporate Program → Bio",
            "cta_text": "Corporate pumping program — request whitepaper",
            "hashtags": ["#corporatewellness", "#pumpingatwork", "#hr", "#womenintheworkplace"],
        },
        "BRIEF-005": {  # Unboxing
            "hook": "What's actually in the box? Let's find out together.",
            "hook_visual": "Hands pulling open minimalist box, soft lighting, ASMR-style close-up",
            "hook_overlay": "Unboxing the X1",
            "pain": "Most breast pump unboxings are overwhelming. 47 pieces. A manual thicker than your hand. Parts you don't even recognize. You end up watching three YouTube tutorials before your first pump.",
            "pain_visual": "Traditional pump box with dozens of small parts spilling out, overwhelmed expression",
            "pain_overlay": "47 pieces. Zero clue where to start.",
            "solution": "X1 box: pump unit x2, flanges x2, USB-C charging cable, quick start card. That's it. 7 total pieces. Everything fits in the palm of your hand. You'll be pumping before you finish reading this sentence.",
            "solution_visual": "Items laid out neatly one by one on white surface, hand assembling in real time, product fully assembled in under 10 seconds",
            "solution_overlay": "7 pieces. 30 seconds to first pump.",
            "trust": "Backed by FDA clearance, 50,000+ moms, and a 2-year warranty. Each unit tested for suction consistency. And if anything goes wrong, our support team answers in under 2 minutes.",
            "trust_visual": "Warranty card close-up, support chat window showing fast response time, mom smiling while using product",
            "trust_overlay": "2yr Warranty | 2min Support",
            "cta": "Ready to experience the simplest unboxing of your life? The X1 is at the link in bio. What are you waiting for?",
            "cta_visual": "Product fully assembled on clean background, warm lighting, 'Shop Now' text floating beside",
            "cta_overlay": "Shop the X1 ↑",
            "cta_text": "Order the X1 — 7 pieces, 30 seconds to pump",
            "hashtags": ["#unboxing", "#wearablepump", "#momhack", "#newmom"],
        },
    }

    @staticmethod
    def _extract_quality_signals(audit: AuditReport | None) -> dict[str, Any]:
        """Extract actionable quality signals from a strategy audit report."""
        if not audit:
            return {}

        low_criteria = []
        fixes = []
        for c in audit.criteria:
            if c.status in (AuditCriterionStatus.WARN, AuditCriterionStatus.FAIL):
                low_criteria.append(f"{c.name}: {c.score:.2f} ({c.status.value})")
                if c.recommendation:
                    fixes.append(f"{c.name} — {c.recommendation}")

        return {
            "overall_score": audit.overall_score,
            "overall_status": audit.overall_status.value,
            "low_scoring_criteria": low_criteria,
            "actionable_fixes": fixes,
        }

    @staticmethod
    def _adapt_template(template: dict[str, Any], platform, quality_signals: dict[str, Any] | None = None) -> dict[str, Any]:
        """Apply quality signal adaptations to a base script template."""
        adapted = dict(template)

        if not quality_signals:
            return adapted

        fixes = quality_signals.get("actionable_fixes", [])

        audience_fixes = [f for f in fixes if "Audience" in f or "Specificity" in f]
        if audience_fixes:
            adaptation_suffix = f" (Made for: {', '.join(audience_fixes)})"
            adapted["hook"] = adapted["hook"].rstrip(".!?") + adaptation_suffix + "."

        seasonal_fixes = [f for f in fixes if "Seasonal" in f or "seasonal" in f]
        if seasonal_fixes:
            adapted["pain"] = adapted["pain"].rstrip(".!?") + " — this week matters more than you think."

        trend_fixes = [f for f in fixes if "Competitor" in f or "Trend" in f or "Anchoring" in f]
        if trend_fixes:
            adapted["trust"] += " Everyone's talking about it this week."

        overall_status = quality_signals.get("overall_status", "PASS")
        overall_score = quality_signals.get("overall_score", 1.0)
        if overall_status == "FAIL" or overall_score < 0.5:
            adapted["cta"] = f"This video needs urgent attention — {adapted['cta']}"
            adapted["cta_text"] = f"URGENT — {adapted['cta_text']}"

        return adapted

    def _mock_scripts(
        self,
        briefs: list[Brief],
        quality_signals: dict[str, Any] | None = None,
        language_code: str = "en",
    ) -> list[Script]:
        """Generate natural-language mock scripts, one per brief per platform.

        Multi-language support removed (v0.3); locked to English.
        """
        lang_suffix = language_code.upper()

        scripts = []
        for brief in briefs:
            template = dict(self._SCRIPT_TEMPLATES.get(brief.id, {}))
            if not template:
                logger.warning("script_writer: no template for brief", brief_id=brief.id)
                continue

            for platform in brief.target_platforms:
                adapted = self._adapt_template(template, platform, quality_signals)
                script_id = f"SCRIPT-{brief.id}-{lang_suffix}"
                script = Script(
                    id=script_id,
                    brief_id=brief.id,
                    platform=platform,
                    language=Language.EN,
                    total_duration=45.0,
                    segments=[
                        ScriptSegment(
                            segment_type="hook",
                            start_time=0.0, end_time=3.0,
                            voiceover=adapted["hook"],
                            visual_description=adapted["hook_visual"],
                            text_overlay=adapted["hook_overlay"],
                        ),
                        ScriptSegment(
                            segment_type="pain_point",
                            start_time=3.0, end_time=8.0,
                            voiceover=adapted["pain"],
                            visual_description=adapted["pain_visual"],
                            text_overlay=adapted["pain_overlay"],
                        ),
                        ScriptSegment(
                            segment_type="solution",
                            start_time=8.0, end_time=20.0,
                            voiceover=adapted["solution"],
                            visual_description=adapted["solution_visual"],
                            text_overlay=adapted["solution_overlay"],
                        ),
                        ScriptSegment(
                            segment_type="trust_building",
                            start_time=20.0, end_time=35.0,
                            voiceover=adapted["trust"],
                            visual_description=adapted["trust_visual"],
                            text_overlay=adapted["trust_overlay"],
                        ),
                        ScriptSegment(
                            segment_type="cta",
                            start_time=35.0, end_time=45.0,
                            voiceover=adapted["cta"],
                            visual_description=adapted["cta_visual"],
                            text_overlay=adapted["cta_overlay"],
                        ),
                    ],
                    hashtags=adapted["hashtags"],
                    cta_text=adapted["cta_text"],
                )
                scripts.append(script)

        logger.info(
            "script_writer: generated mock scripts",
            count=len(scripts),
            lang=language_code,
        )
        return scripts
