"""Mock quality degradation layer — produces controlled-quality test data.

This is the foundation for verifying pipeline routing behavior under
realistic audit score distributions.

Three quality levels:
  - "perfect": current mock data (audit scores > 0.95, all auto-approve)
  - "medium": some fields degraded (audit scores 0.65-0.85, needs human review)
  - "poor": critically degraded (audit scores < 0.60, triggers auto-reject)

Each degrader function returns a dict of overrides to apply on top of
the base mock data. The pipeline agent's `use_mock=True` mode should
call these functions to produce degraded output.

Usage:
    from src.data.mock_quality import degrade_strategy, QualityLevel
    degraded_briefs = degrade_strategy(QualityLevel.POOR)
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from src.models import (
    Brief,
    EditComposition,
    EditTimelineEvent,
    Language,
    Platform,
    Script,
    ScriptSegment,
    ThumbnailSet,
    ThumbnailVariant,
    VideoType,
    WeeklyCalendar,
)


class QualityLevel(StrEnum):
    PERFECT = "perfect"
    MEDIUM = "medium"
    POOR = "poor"


# ═══════════════════════════════════════════
# Strategy Agent — WeeklyCalendar quality degradation
# ═══════════════════════════════════════════


def _build_perfect_briefs() -> list[Brief]:
    """Return the standard 5 perfect-quality briefs."""
    return [
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


def _build_medium_briefs() -> list[Brief]:
    """Return 5 briefs with mild degradation that drops audit score to 0.65-0.85.

    Degradation applied:
    - 3 briefs have target_audience="everyone" (Audience Specificity = 0.40)
    - 1 competitor_reference only (Competitor score = 0.50)
    - 1 seasonal_hook only (Seasonal score = 0.40)
    - USP keywords match 2/3 brand usps for 2 briefs (USP Mapping ~0.50)
    - Only 3 video types (Type Diversity = 0.75)
    - Missing 1 target platform (Platform Coverage = 0.75)
    - Expected overall: ~0.55 but above 0.60 due to scoring variance
    """
    return [
        Brief(
            id="BRIEF-001",
            video_type=VideoType.TUTORIAL,
            topic="How to clean your wearable pump",
            target_audience="everyone",
            target_platforms=[Platform.TIKTOK, Platform.YOUTUBE_SHORTS],
            target_languages=[Language.EN],
            key_message="Discreet cleaning for working moms",
            usp_priority=["portable", "quiet"],
            competitor_reference=None,
            seasonal_hook=None,
        ),
        Brief(
            id="BRIEF-002",
            video_type=VideoType.TUTORIAL,
            topic="Tips for pumping at work",
            target_audience="everyone",
            target_platforms=[Platform.TIKTOK, Platform.FACEBOOK],
            target_languages=[Language.EN],
            key_message="Make pumping at work easier",
            usp_priority=["discreet"],
            competitor_reference=None,
            seasonal_hook=None,
        ),
        Brief(
            id="BRIEF-003",
            video_type=VideoType.PRODUCT_USAGE,
            topic="How to use the X1 wearable pump",
            target_audience="everyone",
            target_platforms=[Platform.TIKTOK, Platform.SHOPIFY],
            target_languages=[Language.EN],
            key_message="Setup in 30 seconds",
            usp_priority=["hands-free", "hospital-grade"],
            competitor_reference="Traditional pump comparison",
            seasonal_hook="New year resolution",
        ),
        Brief(
            id="BRIEF-004",
            video_type=VideoType.PRODUCT_USAGE,
            topic="X1 pump review from a real mom",
            target_audience="Moms researching pumps",
            target_platforms=[Platform.YOUTUBE_SHORTS],
            target_languages=[Language.EN],
            key_message="Good alternative to traditional pumps",
            usp_priority=["quiet"],
            competitor_reference=None,
            seasonal_hook=None,
        ),
        Brief(
            id="BRIEF-005",
            video_type=VideoType.UNBOXING,
            topic="Unboxing the new wearable pump",
            target_audience="Moms 25-40",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="What's in the box",
            usp_priority=["easy-setup"],
            competitor_reference=None,
            seasonal_hook=None,
        ),
    ]


def _build_poor_briefs() -> list[Brief]:
    """Return only 2 briefs with severe quality degradation (score < 0.60).

    Degradation applied:
    - Only 2 briefs (hurts Platform Coverage — 4 missing targets)
    - Both have "everyone" as audience (Audience Specificity score = 0)
    - No competitor references (Competitor score = 0)
    - No seasonal hooks (Seasonal score = 0)
    - Only 2 video types (Type Diversity score = 0.5)
    - USP keywords don't match brand guidelines at all
    """
    return [
        Brief(
            id="BRIEF-001",
            video_type=VideoType.TUTORIAL,
            topic="How to use a breast pump",
            target_audience="everyone",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="It works",
            usp_priority=[],
            competitor_reference=None,
            seasonal_hook=None,
        ),
        Brief(
            id="BRIEF-002",
            video_type=VideoType.TUTORIAL,
            topic="Breast pump tips",
            target_audience="everyone",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="Pumping is good",
            usp_priority=[],
            competitor_reference=None,
            seasonal_hook=None,
        ),
    ]


def degrade_strategy(level: QualityLevel, week: str = "2026-W17") -> WeeklyCalendar:
    """Produce a WeeklyCalendar at the specified quality level.

    Call this from StrategyAgent.run(use_mock=True) to get
    quality-controlled test data.
    """
    builders = {
        QualityLevel.PERFECT: _build_perfect_briefs,
        QualityLevel.MEDIUM: _build_medium_briefs,
        QualityLevel.POOR: _build_poor_briefs,
    }
    briefs = builders[level]()
    return WeeklyCalendar(week=week, briefs=briefs)


# ═══════════════════════════════════════════
# Script Writer — Script quality degradation
# ═══════════════════════════════════════════


def _mock_segment(
    seg_type: str,
    voiceover: str,
    visual: str,
    overlay: str = "",
    start: float = 0.0,
    end: float = 9.0,
) -> ScriptSegment:
    return ScriptSegment(
        segment_type=seg_type,  # type: ignore[arg-type]
        start_time=start,
        end_time=end,
        voiceover=voiceover,
        visual_description=visual,
        text_overlay=overlay,
    )


def degrade_scripts(level: QualityLevel) -> list[Script]:
    """Produce scripts at the specified quality level (fixed count, no upstream dependency).

    Returns fixed count regardless of how many briefs generated upstream:
      - PERFECT: 5 scripts
      - MEDIUM:  3 scripts
      - POOR:    2 scripts

    Used by ScriptWriterAgent._mock_scripts when quality_degradation
    is enabled.
    """
    if level == QualityLevel.PERFECT:
        return _perfect_scripts()
    elif level == QualityLevel.MEDIUM:
        return _medium_scripts()
    else:
        return _poor_scripts()


def _perfect_scripts() -> list[Script]:
    """Return 5 mock Scripts, all segments present, CTA > 20 chars."""
    ids = [f"BRIEF-{i:03d}" for i in range(1, 6)]
    perfect_hook = _mock_segment(
        "hook",
        "Pumping at work doesn't have to mean hiding in a supply closet.",
        "Split screen: woman at desk smiling vs empty storage room",
        "Clean in 2 min? Yes.",
        start=0.0, end=3.0,
    )
    perfect_pain = _mock_segment(
        "pain_point",
        "Finding a clean space to pump is hard enough. Cleaning everything after? Even harder.",
        "Close up of pump parts being washed in office sink",
        "The cleaning struggle is real",
        start=3.0, end=8.0,
    )
    perfect_solution = _mock_segment(
        "solution",
        "The X1's spill-proof design and silicone parts rinse clean in under 30 seconds.",
        "Hands rinsing X1 parts under faucet",
        "30 second rinse. Done.",
        start=8.0, end=20.0,
    )
    perfect_trust = _mock_segment(
        "trust_building",
        "Hospital-grade 280mmHg suction. FDA cleared. Used by 50,000+ moms.",
        "FDA badge overlay on product close-up",
        "FDA Cleared | 280mmHg",
        start=20.0, end=35.0,
    )
    perfect_cta = _mock_segment(
        "cta",
        "Stop hiding in the supply closet. Grab the X1 at the link in bio.",
        "Woman walking out of office confidently",
        "Shop X1 Now",
        start=35.0, end=45.0,
    )
    return [
        Script(
            id=f"SCRIPT-{bid}-EN",
            brief_id=bid,
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=45.0,
            segments=[perfect_hook, perfect_pain, perfect_solution, perfect_trust, perfect_cta],
            hashtags=["#pumpingatwork", "#wearablepump"],
            cta_text="Shop the Wearable Pump X1 — link in bio",
        )
        for bid in ids
    ]


def _medium_scripts() -> list[Script]:
    """Return 3 mock Scripts with medium quality degradation.

    Degradation:
    - Hook segment runs 5 seconds instead of <=3
    - Intro riff is audible but slightly off-beat
    - CTA text only 15 chars (CTA Clarity = 0.5)
    - Brand keywords not matched
    - Banned term "guaranteed" present (Compliance Pre-check = 0.8)
    """
    ids = [f"BRIEF-{i:03d}" for i in range(1, 4)]
    long_hook = _mock_segment(
        "hook",
        "Let me show you a breast pump that might help with your pumping needs at work",
        "Woman talking to camera",
        "Check this out",
        start=0.0, end=5.0,
    )
    pain = _mock_segment(
        "pain_point",
        "Pumping at work is hard, but this pump guarantees a better experience.",
        "Generic office scene",
        "Guaranteed better",
        start=5.0, end=10.0,
    )
    solution = _mock_segment(
        "solution",
        "The X1 is a wearable breast pump that fits in your bra.",
        "Product on desk",
        "Wearable pump",
        start=10.0, end=22.0,
    )
    cta = _mock_segment(
        "cta",
        "Buy it now at our website for more info.",
        "Website screenshot",
        "Shop now",
        start=22.0, end=30.0,
    )
    return [
        Script(
            id=f"SCRIPT-{bid}-EN",
            brief_id=bid,
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=30.0,
            segments=[long_hook, pain, solution, cta],
            hashtags=["#pump"],
            cta_text="Buy now",
        )
        for bid in ids
    ]


def _poor_scripts() -> list[Script]:
    """Return 2 mock Scripts with critical quality degradation (score < 0.60).

    Degradation:
    - Hook voiceover is empty (Voiceover Clarity = 0.3)
    - Missing pain_point and trust_building segments (Completeness = 0.6)
    - CTA completely empty (CTA Clarity = 0)
    - Duration is 180s (Duration Fit = 0.5)
    - Banned terms: "100%", "cure", "best in the world" present
    - No hashtags
    """
    ids = [f"BRIEF-{i:03d}" for i in range(1, 3)]
    empty_hook = _mock_segment(
        "hook", "", "Blank screen", "", start=0.0, end=10.0,
    )
    weak_solution = _mock_segment(
        "solution",
        "100% cure for all your pumping needs — best in the world technology.",
        "Blurry product photo",
        "100% cure",
        start=10.0, end=90.0,
    )
    cta_empty = _mock_segment(
        "cta", "", "Fade to black", "", start=90.0, end=180.0,
    )
    return [
        Script(
            id=f"SCRIPT-{bid}-EN",
            brief_id=bid,
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=180.0,
            segments=[empty_hook, weak_solution, cta_empty],
            hashtags=[],
            cta_text="",
        )
        for bid in ids
    ]


# ═══════════════════════════════════════════
# Thumbnail — ThumbnailSet quality degradation
# ═══════════════════════════════════════════


def degrade_thumbnails(level: QualityLevel) -> list[ThumbnailSet]:
    """Produce ThumbnailSets at the specified quality level."""
    if level == QualityLevel.PERFECT:
        return _perfect_thumbnails()
    elif level == QualityLevel.MEDIUM:
        return _medium_thumbnails()
    else:
        return _poor_thumbnails()


def _perfect_thumbnails() -> list[ThumbnailSet]:
    """4 unique variants, CTR keywords present, text overlay signals included."""
    concepts = [
        ThumbnailVariant(variant_id="A", concept="Product centered with bold title and price tag", prompt='clean ecom product shot, warm pink background, wearable pump centered, minimalist style, 9:16, "text overlay: bold title + price"'),
        ThumbnailVariant(variant_id="B", concept="Lifestyle scene with emotional before/after contrast", prompt='split screen showing frustrated woman vs confident woman, emotional contrast, warm lighting, 9:16, "text overlay: before vs after"'),
        ThumbnailVariant(variant_id="C", concept="Close-up reaction face with curiosity hook", prompt='close-up woman face surprised expression, bold question text overlay area, high contrast, 9:16, "text overlay: big question mark"'),
        ThumbnailVariant(variant_id="D", concept="Minimal product shot with single bold hook line", prompt='minimal white background, product floating, single bold text area at bottom, clean modern, 9:16, "text overlay: product name"'),
    ]
    return [
        ThumbnailSet(script_id=f"sid-{sid}", variants=[ThumbnailVariant(**v.model_dump()) for v in concepts])
        for sid in range(5)
    ]


def _medium_thumbnails() -> list[ThumbnailSet]:
    """3 variants, 2 share same concept (Variant Diversity hurt), no CTR keywords, but text overlays present."""
    variants = [
        ThumbnailVariant(variant_id="A", concept="Product on white background", prompt='product photo white background 9:16, "text overlay"'),
        ThumbnailVariant(variant_id="B", concept="Product on white background", prompt='product photo white background 9:16, "text overlay"'),
        ThumbnailVariant(variant_id="C", concept="Woman using product", prompt='woman using breast pump 9:16, "text overlay"'),
    ]
    return [
        ThumbnailSet(script_id=f"sid-{sid}", variants=[ThumbnailVariant(**v.model_dump()) for v in variants])
        for sid in range(5)
    ]


def _poor_thumbnails() -> list[ThumbnailSet]:
    """Only 2 variants, both same concept, no CTR signals."""
    variants = [
        ThumbnailVariant(variant_id="A", concept="Breast pump", prompt="pump image"),
        ThumbnailVariant(variant_id="B", concept="Breast pump", prompt="pump image"),
    ]
    return [
        ThumbnailSet(script_id=f"sid-{sid}", variants=[ThumbnailVariant(**v.model_dump()) for v in variants])
        for sid in range(5)
    ]


# ═══════════════════════════════════════════
# Edit — EditComposition quality degradation
# ═══════════════════════════════════════════


def degrade_edits(level: QualityLevel) -> list[EditComposition]:
    """Produce EditCompositions at the specified quality level."""
    if level == QualityLevel.PERFECT:
        return _perfect_edits()
    elif level == QualityLevel.MEDIUM:
        return _medium_edits()
    else:
        return _poor_edits()


def _perfect_edits() -> list[EditComposition]:
    """No gaps, 5+ unique assets, mixed transitions, 9:16."""
    timeline = [
        EditTimelineEvent(shot_id=1, asset_id="asset-001", start_time=0.0, end_time=3.0, transition="cut"),
        EditTimelineEvent(shot_id=2, asset_id="asset-002", start_time=3.0, end_time=8.0, transition="dissolve"),
        EditTimelineEvent(shot_id=3, asset_id="asset-003", start_time=8.0, end_time=20.0, transition="slide"),
        EditTimelineEvent(shot_id=4, asset_id="asset-004", start_time=20.0, end_time=35.0, transition="cut"),
        EditTimelineEvent(shot_id=5, asset_id="asset-005", start_time=35.0, end_time=45.0, transition="zoom"),
    ]
    return [
        EditComposition(script_id=f"sid-{sid}", total_duration=45.0, timeline=[
            EditTimelineEvent(**e.model_dump()) for e in timeline
        ])
        for sid in range(5)
    ]


def _medium_edits() -> list[EditComposition]:
    """Timing gaps, only cut transitions, 2 unique assets."""
    timeline = [
        EditTimelineEvent(shot_id=1, asset_id="asset-001", start_time=0.0, end_time=4.0, transition="cut"),
        EditTimelineEvent(shot_id=2, asset_id="asset-001", start_time=6.0, end_time=10.0, transition="cut"),
        EditTimelineEvent(shot_id=3, asset_id="asset-002", start_time=10.0, end_time=25.0, transition="cut"),
    ]
    return [
        EditComposition(script_id=f"sid-{sid}", total_duration=45.0, timeline=[
            EditTimelineEvent(**e.model_dump()) for e in timeline
        ])
        for sid in range(5)
    ]


def _poor_edits() -> list[EditComposition]:
    """Single shot, no transitions, wrong aspect ratio."""
    timeline = [
        EditTimelineEvent(shot_id=1, asset_id="asset-001", start_time=0.0, end_time=300.0, transition="cut"),
    ]
    return [
        EditComposition(script_id=f"sid-{sid}", total_duration=300.0, aspect_ratio="4:3", timeline=[
            EditTimelineEvent(**e.model_dump()) for e in timeline
        ])
        for sid in range(5)
    ]


# ═══════════════════════════════════════════
# Quality level builder — produce all artifacts at once
# ═══════════════════════════════════════════


def build_full_mock_state(level: QualityLevel) -> dict[str, Any]:
    """Build a complete pipeline input state at the specified quality level.

    This is the main entry point. Returns a dict you can pass directly
    to compiled.astream() as initial_state.

    Usage:
        from src.data.mock_quality import build_full_mock_state, QualityLevel
        state = build_full_mock_state(QualityLevel.POOR)
        async for event in compiled.astream(state, config):
            ...
    """
    base = {
        "mock_quality": level.value if isinstance(level, str) else level.value,
        "product_catalog": {
            "product_name": "Wearable Breast Pump X1",
            "category": "baby",
            "usps": ["hands-free", "hospital-grade suction", "quiet <40dB"],
        },
        "brand_guidelines": {
            "tone": "warm",
            "colors": ["pink", "white"],
            "usps": ["hands-free", "quiet", "hospital-grade"],
        },
        "target_platforms": ["tiktok", "facebook", "youtube_shorts", "shopify"],
        "target_languages": ["en"],
        "content_calendar_week": "2026-W17",
        "content_scenario": "general",
        "current_step": "init",
        "errors": [],
        "structured_errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    return base
    # Removed: weekly_calendar injection — strategy_node will produce it in mock mode
