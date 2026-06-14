"""Tests for Mock Quality Degradation Layer — verifying audit score distribution.

Validates that the 3 quality levels (perfect/medium/poor) produce
audit scores in the expected ranges, and that the routing logic
correctly handles each score band.

Key assertions:
  - PERFECT: strategy audit > 0.90 (auto-approve)
  - MEDIUM: strategy audit 0.50-0.89 (requires human review)
  - POOR: strategy audit < 0.60 (auto-reject)

Also tests script, thumbnail, and edit audit scores against their
respective quality-degraded inputs.
"""

import pytest

from src.agents.auditor import AuditorAgent
from src.data.mock_quality import (
    QualityLevel,
    degrade_edits,
    degrade_scripts,
    degrade_strategy,
    degrade_thumbnails,
)
from src.models import (
    AuditCheckpoint,
    AuditReport,
)

# ── Shared fixture ──

auditor = AuditorAgent()


# ═══════════════════════════════════════════
# Strategy Audit Score Validation
# ═══════════════════════════════════════════


@pytest.mark.parametrize(
    "level,expected_min,expected_max,expected_route",
    [
        (QualityLevel.PERFECT, 0.90, 1.0, "auto_approve"),
        (QualityLevel.MEDIUM, 0.60, 0.89, "human_review"),
        (QualityLevel.POOR, 0.0, 0.59, "auto_reject_or_human"),
    ],
)
def test_strategy_audit_score_ranges(
    level: QualityLevel,
    expected_min: float,
    expected_max: float,
    expected_route: str,
):
    calendar = degrade_strategy(level)
    target_platforms = ["tiktok", "facebook", "youtube_shorts", "shopify"]
    brand_guidelines = {"tone": "warm", "usps": ["hands-free", "quiet", "hospital-grade"]}

    report = auditor.audit_strategy(calendar, target_platforms, brand_guidelines)

    assert isinstance(report, AuditReport)
    assert report.checkpoint == AuditCheckpoint.STRATEGY
    assert expected_min <= report.overall_score <= expected_max, (
        f"{level.value}: score {report.overall_score:.3f} not in [{expected_min}, {expected_max}]"
    )

    # Verify routing implications
    if expected_route == "auto_approve":
        assert report.overall_score > 0.90, (
            f"{level.value}: score {report.overall_score:.3f} should be > 0.90 for auto-approve"
        )
    elif expected_route == "auto_reject_or_human":
        assert report.overall_score < 0.90, (
            f"{level.value}: score {report.overall_score:.3f} should be < 0.90"
        )


@pytest.mark.parametrize(
    "level,audience_specificity_low,competitor_low,seasonal_low",
    [
        (QualityLevel.PERFECT, False, False, False),
        (QualityLevel.MEDIUM, True, True, True),
        (QualityLevel.POOR, True, True, True),
    ],
)
def test_strategy_audit_criterion_degradation(
    level: QualityLevel,
    audience_specificity_low: bool,
    competitor_low: bool,
    seasonal_low: bool,
):
    """Verify specific criteria degrade as expected at each quality level."""
    calendar = degrade_strategy(level)
    target_platforms = ["tiktok", "facebook", "youtube_shorts", "shopify"]
    brand_guidelines = {"tone": "warm", "usps": ["hands-free", "quiet", "hospital-grade"]}

    report = auditor.audit_strategy(calendar, target_platforms, brand_guidelines)
    criteria_map = {c.name: c for c in report.criteria}

    aud_score = criteria_map["Audience Specificity"].score
    if audience_specificity_low:
        assert aud_score <= 0.6, f"Audience Specificity should be low ({aud_score:.2f})"
    else:
        assert aud_score >= 0.8, f"Audience Specificity should be high ({aud_score:.2f})"

    comp_score = criteria_map["Competitor / Trend Anchoring"].score
    if competitor_low:
        assert comp_score <= 0.5, f"Competitor score should be low ({comp_score:.2f})"
    else:
        assert comp_score >= 0.8, f"Competitor score should be high ({comp_score:.2f})"

    seas_score = criteria_map["Seasonal Relevance"].score
    if seasonal_low:
        assert seas_score <= 0.5, f"Seasonal score should be low ({seas_score:.2f})"
    else:
        assert seas_score >= 0.8, f"Seasonal score should be high ({seas_score:.2f})"


# ═══════════════════════════════════════════
# Script Audit Score Validation
# ═══════════════════════════════════════════


@pytest.mark.parametrize(
    "level,expected_hook_score,expected_cta_score,expected_completeness",
    [
        (QualityLevel.PERFECT, 1.0, 1.0, 1.0),
        (QualityLevel.MEDIUM, 0.5, 0.5, 0.8),
        (QualityLevel.POOR, 0.0, 0.0, 0.6),
    ],
)
def test_script_audit_scores(
    level: QualityLevel,
    expected_hook_score: float,
    expected_cta_score: float,
    expected_completeness: float,
):
    brief_ids = ["BRIEF-001"]
    scripts = degrade_scripts(level)
    brand_guidelines = {"tone_of_voice": {"keywords": ["warm", "empowering", "real"]}}

    reports = [auditor.audit_script(s, brand_guidelines) for s in scripts]

    for report in reports:
        assert isinstance(report, AuditReport)
        assert report.checkpoint == AuditCheckpoint.SCRIPT

        criteria_map = {c.name: c for c in report.criteria}

        hook_score = criteria_map["Hook Strength"].score
        assert hook_score == expected_hook_score, (
            f"{level.value}: Hook Strength = {hook_score}, expected {expected_hook_score}"
        )

        cta_score = criteria_map["CTA Clarity"].score
        assert cta_score == expected_cta_score, (
            f"{level.value}: CTA Clarity = {cta_score}, expected {expected_cta_score}"
        )

        compl_score = criteria_map["Segment Completeness"].score
        assert compl_score == expected_completeness, (
            f"{level.value}: Segment Completeness = {compl_score}, expected {expected_completeness}"
        )


# ═══════════════════════════════════════════
# Thumbnail Audit Score Validation
# ═══════════════════════════════════════════


@pytest.mark.parametrize(
    "level,expected_diversity_min,expected_ctr_min",
    [
        (QualityLevel.PERFECT, 0.75, 0.60),
        (QualityLevel.MEDIUM, 0.50, 0.0),
        (QualityLevel.POOR, 0.25, 0.0),
    ],
)
def test_thumbnail_audit_scores(
    level: QualityLevel,
    expected_diversity_min: float,
    expected_ctr_min: float,
):
    script_ids = ["SCRIPT-BRIEF-001-EN"]
    thumbnail_sets = degrade_thumbnails(level)

    reports = [auditor.audit_thumbnail(ts) for ts in thumbnail_sets]

    for report in reports:
        criteria_map = {c.name: c for c in report.criteria}

        div_score = criteria_map["Variant Diversity"].score
        assert div_score >= expected_diversity_min, (
            f"{level.value}: Variant Diversity = {div_score:.2f}, expected >= {expected_diversity_min}"
        )

        ctr_score = criteria_map["CTR Potential"].score
        assert ctr_score >= expected_ctr_min, (
            f"{level.value}: CTR Potential = {ctr_score:.2f}, expected >= {expected_ctr_min}"
        )


# ═══════════════════════════════════════════
# Edit Audit Score Validation
# ═══════════════════════════════════════════


@pytest.mark.parametrize(
    "level,expected_continuity,expected_asset_coverage,expected_aspect,expected_transitions",
    [
        (QualityLevel.PERFECT, 1.0, 1.0, 1.0, True),
        (QualityLevel.MEDIUM, 0.67, 0.67, 1.0, False),
        (QualityLevel.POOR, 1.0, 0.33, 0.0, False),
    ],
)
def test_edit_audit_scores(
    level: QualityLevel,
    expected_continuity: float,
    expected_asset_coverage: float,
    expected_aspect: float,
    expected_transitions: bool,
):
    script_ids = ["SCRIPT-BRIEF-001-EN"]
    compositions = degrade_edits(level)

    reports = [auditor.audit_edit(c) for c in compositions]

    for report in reports:
        criteria_map = {c.name: c for c in report.criteria}

        cont_score = criteria_map["Shot Continuity"].score
        assert cont_score == pytest.approx(expected_continuity, abs=0.01), (
            f"{level.value}: Shot Continuity = {cont_score}, expected {expected_continuity}"
        )

        cov_score = criteria_map["Asset Coverage"].score
        assert cov_score == pytest.approx(expected_asset_coverage, abs=0.01), (
            f"{level.value}: Asset Coverage = {cov_score}, expected {expected_asset_coverage}"
        )

        aspect_score = criteria_map["Aspect Ratio"].score
        assert aspect_score == expected_aspect, (
            f"{level.value}: Aspect Ratio = {aspect_score}, expected {expected_aspect}"
        )

        trans_score = criteria_map["Transition Quality"].score
        has_mixed_transitions = trans_score >= 0.5
        assert has_mixed_transitions == expected_transitions, (
            f"{level.value}: Transition Quality = {trans_score:.2f}, expected mix={expected_transitions}"
        )


# ═══════════════════════════════════════════
# Routing Simulation — verify thresholds match
# ═══════════════════════════════════════════


@pytest.mark.parametrize(
    "level,should_auto_approve,should_auto_reject",
    [
        (QualityLevel.PERFECT, True, False),
        (QualityLevel.MEDIUM, False, False),
        (QualityLevel.POOR, False, True),
    ],
)
def test_routing_thresholds(
    level: QualityLevel,
    should_auto_approve: bool,
    should_auto_reject: bool,
):
    """Simulate the routing decision logic from routing.py without importing it.

    Uses the same thresholds:
      - score > 0.90 -> auto-approve
      - score < 0.60 -> auto-reject
    """
    calendar = degrade_strategy(level)
    target_platforms = ["tiktok", "facebook", "youtube_shorts", "shopify"]
    brand_guidelines = {"tone": "warm", "usps": ["hands-free", "quiet", "hospital-grade"]}

    report = auditor.audit_strategy(calendar, target_platforms, brand_guidelines)
    score = report.overall_score

    auto_approve = score > 0.90
    auto_reject = score < 0.60

    assert auto_approve == should_auto_approve, (
        f"{level.value}: score={score:.3f}, auto_approve={auto_approve}, expected={should_auto_approve}"
    )
    assert auto_reject == should_auto_reject, (
        f"{level.value}: score={score:.3f}, auto_reject={auto_reject}, expected={should_auto_reject}"
    )

    # Verify human_review fallback
    needs_human = not auto_approve and not auto_reject
    if level == QualityLevel.MEDIUM:
        assert needs_human, f"MEDIUM score={score:.3f} should require human review (score must be in 0.60-0.90 range)"


# ═══════════════════════════════════════════
# Quality Level Factory Consistency
# ═══════════════════════════════════════════


def test_all_levels_produce_valid_pydantic_models():
    """Every quality level must produce valid Pydantic models."""
    for level in QualityLevel:
        # Strategy
        cal = degrade_strategy(level)
        assert len(cal.briefs) > 0 or level == QualityLevel.POOR, f"{level.value}: at least 0 briefs"

        # Scripts
        brief_ids = [b.id for b in cal.briefs]
        scripts = degrade_scripts(level)
        assert len(scripts) > 0, f"{level.value}: scripts should have content"

        for s in scripts:
            assert s.id.startswith("SCRIPT-")
            assert s.platform is not None
            assert s.language is not None

        # Thumbnails
        script_ids = [s.id for s in scripts]
        thumbs = degrade_thumbnails(level)
        assert len(thumbs) == 5

        for ts in thumbs:
            assert len(ts.variants) > 0
            for v in ts.variants:
                assert v.variant_id in ("A", "B", "C", "D") or level in (
                    QualityLevel.MEDIUM,
                    QualityLevel.POOR,
                ), f"Unexpected variant_id: {v.variant_id}"

        # Edits
        edits = degrade_edits(level)
        assert len(edits) == 5
        for e in edits:
            assert len(e.timeline) > 0
