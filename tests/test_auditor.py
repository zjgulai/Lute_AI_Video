"""Unit tests for self-audit AuditorAgent — 4 checkpoints, 6-7 criteria each."""

import pytest
from datetime import datetime

from src.agents.auditor import AuditorAgent, _score_to_status, _overall_status
from src.models import (
    AuditCriterionStatus,
    AuditCheckpoint,
    AuditReport,
    WeeklyCalendar,
    Brief,
    VideoType,
    Platform,
    Language,
    Script,
    ScriptSegment,
    EditComposition,
    EditTimelineEvent,
    ThumbnailSet,
    ThumbnailVariant,
)


@pytest.fixture
def auditor():
    return AuditorAgent()


@pytest.fixture
def sample_briefs():
    return [
        Brief(
            id="BRIEF-001",
            video_type=VideoType.TUTORIAL,
            topic="How to use wearable pump at work",
            target_audience="Working moms 25-35",
            target_platforms=[Platform.TIKTOK, Platform.FACEBOOK],
            target_languages=[Language.EN],
            key_message="Discreet pumping anywhere",
            usp_priority=["hands-free", "quiet", "portable"],
            competitor_reference="vs traditional electric pumps",
            seasonal_hook="Back to office season",
        ),
        Brief(
            id="BRIEF-002",
            video_type=VideoType.PRODUCT_REVIEW,
            topic="X1 vs. Spectra: honest comparison",
            target_audience="First-time moms researching pumps",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="X1 is 1/3 the size, same suction power",
            usp_priority=["hospital-grade", "compact", "quiet"],
        ),
        Brief(
            id="BRIEF-003",
            video_type=VideoType.SHORT_VIDEO_SALES,
            topic="Limited time bundle deal",
            target_audience="everyone",
            target_platforms=[Platform.FACEBOOK],
            target_languages=[Language.EN],
            key_message="Save $30 this week only",
            usp_priority=["affordable", "hands-free"],
            seasonal_hook="Mother's Day special",
        ),
    ]


@pytest.fixture
def sample_calendar(sample_briefs):
    return WeeklyCalendar(week="2026-W17", briefs=sample_briefs)


@pytest.fixture
def sample_good_script():
    return Script(
        id="SCRIPT-001-EN",
        brief_id="BRIEF-001",
        platform=Platform.TIKTOK,
        language=Language.EN,
        total_duration=45.0,
        segments=[
            ScriptSegment(
                segment_type="hook",
                start_time=0.0, end_time=2.5,
                voiceover="Pumping at work shouldn't feel like hiding.",
                visual_description="Desk setup",
                text_overlay="Pumping at work?",
            ),
            ScriptSegment(
                segment_type="pain_point",
                start_time=2.5, end_time=8.0,
                voiceover="3 times a day. 20 minutes each. Where do you go?",
                visual_description="Clock ticking",
                text_overlay="3x a day",
            ),
            ScriptSegment(
                segment_type="solution",
                start_time=8.0, end_time=25.0,
                voiceover="The X1 fits in your bra. Silent. Hospital-grade. No one knows.",
                visual_description="Product demo",
                text_overlay="100% hands-free",
            ),
            ScriptSegment(
                segment_type="trust_building",
                start_time=25.0, end_time=38.0,
                voiceover="FDA cleared. 280mmHg suction. Used by 50,000+ moms.",
                visual_description="FDA badge + reviews",
                text_overlay="FDA Cleared ✅",
            ),
            ScriptSegment(
                segment_type="cta",
                start_time=38.0, end_time=45.0,
                voiceover="Shop the link in bio. Freedom to feed, anywhere.",
                visual_description="Product + happy mom",
                text_overlay="Shop Now ↑",
            ),
        ],
        hashtags=["#breastpumping", "#workingmom"],
        cta_text="Shop the link in bio",
    )


@pytest.fixture
def sample_bad_script():
    """A script with deliberate quality issues."""
    return Script(
        id="SCRIPT-BAD-001-EN",
        brief_id="BRIEF-001",
        platform=Platform.TIKTOK,
        language=Language.EN,
        total_duration=200.0,  # Too long for TikTok
        segments=[
            ScriptSegment(
                segment_type="hook",
                start_time=0.0, end_time=6.0,  # Hook too long (>3s)
                voiceover="This product is the best in the world and guaranteed to work 100% of the time for cure.",
                visual_description="Product shot",
            ),
            # Missing: pain_point, solution, trust_building, cta
        ],
        hashtags=["#bestpump"],
        cta_text="",
    )


@pytest.fixture
def sample_composition():
    return EditComposition(
        script_id="SCRIPT-001-EN",
        total_duration=45.0,
        aspect_ratio="9:16",
        timeline=[
            EditTimelineEvent(shot_id=1, asset_id="A001", start_time=0.0, end_time=2.5, transition="dissolve"),
            EditTimelineEvent(shot_id=2, asset_id="A002", start_time=2.5, end_time=8.0, transition="cut"),
            EditTimelineEvent(shot_id=3, asset_id="A003", start_time=8.0, end_time=25.0, transition="zoom"),
            EditTimelineEvent(shot_id=4, asset_id="A004", start_time=25.0, end_time=38.0, transition="slide"),
            EditTimelineEvent(shot_id=5, asset_id="A005", start_time=38.0, end_time=45.0, transition="dissolve"),
        ],
    )


@pytest.fixture
def sample_thumbnail_set():
    return ThumbnailSet(
        script_id="SCRIPT-001-EN",
        variants=[
            ThumbnailVariant(
                variant_id="A",
                concept="Curiosity gap: 'She's pumping right now and no one knows' with product partially visible, high contrast dark background",
                prompt="A woman at her desk smiling, partially visible wearable breast pump under blouse, text 'She's pumping RIGHT NOW', dark background, bold vibrant colors, 9:16",
            ),
            ThumbnailVariant(
                variant_id="B",
                concept="Product hero shot on bright white background with FDA badge overlay",
                prompt="Wearable breast pump on white background, clean product photography, FDA cleared badge overlay, professional lighting, 9:16",
            ),
            ThumbnailVariant(
                variant_id="C",
                concept="Before/after split: tangled wires vs hands-free freedom, emotional",
                prompt="Split screen: left side tangled pump wires and tubes, right side woman walking freely with wearable pump, emotional contrast, 9:16",
            ),
            ThumbnailVariant(
                variant_id="D",
                concept="Question hook: 'Still pumping in a supply closet?' bold text over frustrated expression",
                prompt="Text overlay 'Still pumping in a supply closet?' in bold white letters, woman looking frustrated in office setting, high contrast, 9:16",
            ),
        ],
    )


# ═══════════════════════════════════════════
# Unit: Scoring helpers
# ═══════════════════════════════════════════


class TestScoringHelpers:
    def test_score_to_status_pass(self):
        assert _score_to_status(0.85) == AuditCriterionStatus.PASS
        assert _score_to_status(0.80) == AuditCriterionStatus.PASS

    def test_score_to_status_warn(self):
        assert _score_to_status(0.79) == AuditCriterionStatus.WARN
        assert _score_to_status(0.50) == AuditCriterionStatus.WARN

    def test_score_to_status_fail(self):
        assert _score_to_status(0.49) == AuditCriterionStatus.FAIL
        assert _score_to_status(0.0) == AuditCriterionStatus.FAIL

    def test_overall_status_all_pass(self):
        from src.models import AuditCriterion
        criteria = [
            AuditCriterion(name="A", status=AuditCriterionStatus.PASS, score=0.9, observation="ok"),
            AuditCriterion(name="B", status=AuditCriterionStatus.PASS, score=0.85, observation="ok"),
        ]
        assert _overall_status(criteria) == AuditCriterionStatus.PASS

    def test_overall_status_one_warn(self):
        from src.models import AuditCriterion
        criteria = [
            AuditCriterion(name="A", status=AuditCriterionStatus.PASS, score=0.9, observation="ok"),
            AuditCriterion(name="B", status=AuditCriterionStatus.WARN, score=0.6, observation="hmm"),
        ]
        assert _overall_status(criteria) == AuditCriterionStatus.WARN

    def test_overall_status_one_fail(self):
        from src.models import AuditCriterion
        criteria = [
            AuditCriterion(name="A", status=AuditCriterionStatus.PASS, score=0.9, observation="ok"),
            AuditCriterion(name="B", status=AuditCriterionStatus.FAIL, score=0.3, observation="bad"),
        ]
        assert _overall_status(criteria) == AuditCriterionStatus.FAIL


# ═══════════════════════════════════════════
# Strategy Audit Tests
# ═══════════════════════════════════════════


class TestStrategyAudit:
    def test_audit_good_calendar(self, auditor, sample_calendar):
        report = auditor.audit_strategy(
            sample_calendar,
            target_platforms=["tiktok", "facebook"],
        )
        assert isinstance(report, AuditReport)
        assert report.checkpoint == AuditCheckpoint.STRATEGY
        assert report.target_artifact_id == "2026-W17"
        assert len(report.criteria) == 6
        assert report.overall_score > 0
        assert report.overall_status in (AuditCriterionStatus.PASS, AuditCriterionStatus.WARN)

    def test_audit_empty_calendar(self, auditor):
        calendar = WeeklyCalendar(week="2026-W18", briefs=[])
        report = auditor.audit_strategy(calendar, target_platforms=["tiktok"])
        assert report.overall_score >= 0
        # Empty calendar should score low on platform coverage, type diversity, etc.
        assert any(c.status == AuditCriterionStatus.FAIL for c in report.criteria)

    def test_audit_missing_platforms(self, auditor, sample_calendar):
        """Calendar covers tiktok+facebook, but target includes youtube_shorts."""
        report = auditor.audit_strategy(
            sample_calendar,
            target_platforms=["tiktok", "facebook", "youtube_shorts"],
        )
        platform_crit = next(c for c in report.criteria if c.name == "Platform Coverage")
        assert platform_crit.status == AuditCriterionStatus.WARN
        assert "youtube_shorts" in platform_crit.observation

    def test_vague_audience_detected(self, auditor, sample_calendar):
        """BRIEF-003 has target_audience='everyone'."""
        report = auditor.audit_strategy(sample_calendar, target_platforms=["tiktok"])
        audience_crit = next(c for c in report.criteria if c.name == "Audience Specificity")
        # 2/3 specific = ~0.67 score → WARN
        assert audience_crit.score < 0.8

    def test_audit_all_criteria_present(self, auditor, sample_calendar):
        report = auditor.audit_strategy(sample_calendar, target_platforms=["tiktok"])
        criterion_names = {c.name for c in report.criteria}
        expected = {
            "Platform Coverage",
            "Type Diversity",
            "USP Mapping",
            "Audience Specificity",
            "Competitor / Trend Anchoring",
            "Seasonal Relevance",
        }
        assert criterion_names == expected


# ═══════════════════════════════════════════
# Script Audit Tests
# ═══════════════════════════════════════════


class TestScriptAudit:
    def test_audit_good_script(self, auditor, sample_good_script):
        report = auditor.audit_script(sample_good_script)
        assert isinstance(report, AuditReport)
        assert report.checkpoint == AuditCheckpoint.SCRIPT
        assert len(report.criteria) == 9
        # Good script should have decent score
        assert report.overall_score >= 0.6

    def test_audit_bad_script(self, auditor, sample_bad_script):
        report = auditor.audit_script(sample_bad_script)
        # Bad script should have low score
        assert report.overall_score < 0.5 or report.overall_status == AuditCriterionStatus.FAIL

        # Hook too long (>3s)
        hook_crit = next(c for c in report.criteria if c.name == "Hook Strength")
        assert hook_crit.status == AuditCriterionStatus.FAIL
        assert "6.0s" in hook_crit.observation

        # Duration outside TikTok range (200s > 180s max)
        dur_crit = next(c for c in report.criteria if c.name == "Duration Fit")
        assert dur_crit.status == AuditCriterionStatus.FAIL

        # Missing segments
        seg_crit = next(c for c in report.criteria if c.name == "Segment Completeness")
        assert seg_crit.status == AuditCriterionStatus.FAIL

    def test_compliance_precheck_flags(self, auditor, sample_bad_script):
        report = auditor.audit_script(sample_bad_script)
        precheck = next(c for c in report.criteria if c.name == "Compliance Pre-check")
        # "guaranteed", "100%", "best in the world", "cure" should all be flagged
        assert precheck.score < 0.8
        assert "guaranteed" in precheck.observation.lower() or "100%" in precheck.observation

    def test_no_cta_detected(self, auditor, sample_bad_script):
        report = auditor.audit_script(sample_bad_script)
        cta_crit = next(c for c in report.criteria if c.name == "CTA Clarity")
        assert cta_crit.status == AuditCriterionStatus.FAIL

    def test_brand_voice_matching(self, auditor, sample_good_script):
        guidelines = {
            "brand_name": "TestBrand",
            "tone_of_voice": {
                "keywords": ["freedom", "feed", "anywhere"]
            },
        }
        report = auditor.audit_script(sample_good_script, brand_guidelines=guidelines)
        voice_crit = next(c for c in report.criteria if c.name == "Brand Voice")
        # "freedom" and "feed" and "anywhere" are in the good script
        assert voice_crit.score > 0.5

    def test_all_script_criteria_present(self, auditor, sample_good_script):
        report = auditor.audit_script(sample_good_script)
        criterion_names = {c.name for c in report.criteria}
        expected = {
            "Hook Strength",
            "Segment Completeness",
            "Duration Fit",
            "Voiceover Clarity",
            "Brand Voice",
            "CTA Clarity",
            "Compliance Pre-check",
            "Information Density",
            "Emotional Arc",
        }
        assert criterion_names == expected


# ═══════════════════════════════════════════
# Edit Audit Tests
# ═══════════════════════════════════════════


class TestEditAudit:
    def test_audit_good_composition(self, auditor, sample_composition):
        report = auditor.audit_edit(sample_composition)
        assert isinstance(report, AuditReport)
        assert report.checkpoint == AuditCheckpoint.EDIT
        assert len(report.criteria) == 6

    def test_shot_continuity_no_gaps(self, auditor, sample_composition):
        report = auditor.audit_edit(sample_composition)
        cont = next(c for c in report.criteria if c.name == "Shot Continuity")
        assert cont.status == AuditCriterionStatus.PASS

    def test_shot_continuity_with_gaps(self, auditor):
        comp = EditComposition(
            script_id="TEST-001",
            total_duration=30.0,
            aspect_ratio="9:16",
            timeline=[
                EditTimelineEvent(shot_id=1, asset_id="A1", start_time=0.0, end_time=5.0),
                EditTimelineEvent(shot_id=2, asset_id="A2", start_time=7.0, end_time=12.0),  # 2s gap
                EditTimelineEvent(shot_id=3, asset_id="A3", start_time=14.0, end_time=20.0),  # 2s gap
            ],
        )
        report = auditor.audit_edit(comp)
        cont = next(c for c in report.criteria if c.name == "Shot Continuity")
        assert cont.status != AuditCriterionStatus.PASS

    def test_all_cut_transitions_score_low(self, auditor):
        comp = EditComposition(
            script_id="TEST-002",
            total_duration=20.0,
            aspect_ratio="9:16",
            timeline=[
                EditTimelineEvent(shot_id=1, asset_id="A1", start_time=0.0, end_time=5.0, transition="cut"),
                EditTimelineEvent(shot_id=2, asset_id="A2", start_time=5.0, end_time=10.0, transition="cut"),
                EditTimelineEvent(shot_id=3, asset_id="A3", start_time=10.0, end_time=20.0, transition="cut"),
            ],
        )
        report = auditor.audit_edit(comp)
        trans = next(c for c in report.criteria if c.name == "Transition Quality")
        assert trans.score == 0.4  # All "cut" = low score

    def test_wrong_aspect_ratio(self, auditor):
        comp = EditComposition(
            script_id="TEST-003",
            total_duration=30.0,
            aspect_ratio="16:9",
            timeline=[EditTimelineEvent(shot_id=1, asset_id="A1", start_time=0.0, end_time=30.0)],
        )
        report = auditor.audit_edit(comp)
        ar = next(c for c in report.criteria if c.name == "Aspect Ratio")
        assert ar.status == AuditCriterionStatus.FAIL
        assert ar.score == 0.0

    def test_all_edit_criteria_present(self, auditor, sample_composition):
        report = auditor.audit_edit(sample_composition)
        criterion_names = {c.name for c in report.criteria}
        expected = {
            "Shot Continuity",
            "Asset Coverage",
            "Duration Accuracy",
            "Transition Quality",
            "Aspect Ratio",
            "Pace Variation",
        }
        assert criterion_names == expected


# ═══════════════════════════════════════════
# Thumbnail Audit Tests
# ═══════════════════════════════════════════


class TestThumbnailAudit:
    def test_audit_good_thumbnail_set(self, auditor, sample_thumbnail_set):
        report = auditor.audit_thumbnail(sample_thumbnail_set)
        assert isinstance(report, AuditReport)
        assert report.checkpoint == AuditCheckpoint.THUMBNAIL
        assert len(report.criteria) == 6

    def test_variant_diversity(self, auditor, sample_thumbnail_set):
        report = auditor.audit_thumbnail(sample_thumbnail_set)
        div = next(c for c in report.criteria if c.name == "Variant Diversity")
        # 4 variants with distinct concepts
        assert div.score > 0.7

    def test_ctr_potential(self, auditor, sample_thumbnail_set):
        report = auditor.audit_thumbnail(sample_thumbnail_set)
        ctr = next(c for c in report.criteria if c.name == "CTR Potential")
        # "curiosity", "question", "emotion" in concepts
        assert ctr.score > 0.3

    def test_no_banned_content(self, auditor, sample_thumbnail_set):
        report = auditor.audit_thumbnail(sample_thumbnail_set)
        compliance = next(c for c in report.criteria if c.name == "Platform Compliance")
        assert compliance.status == AuditCriterionStatus.PASS

    def test_banned_content_detected(self, auditor):
        bad_set = ThumbnailSet(
            script_id="BAD-001",
            variants=[
                ThumbnailVariant(
                    variant_id="A",
                    concept="Product with violence theme",
                    prompt="Woman holding weapon next to breast pump, dark alley",
                ),
            ],
        )
        report = auditor.audit_thumbnail(bad_set)
        compliance = next(c for c in report.criteria if c.name == "Platform Compliance")
        assert compliance.status == AuditCriterionStatus.FAIL

    def test_all_thumbnail_criteria_present(self, auditor, sample_thumbnail_set):
        report = auditor.audit_thumbnail(sample_thumbnail_set)
        criterion_names = {c.name for c in report.criteria}
        expected = {
            "Variant Diversity",
            "CTR Potential",
            "Brand Presence",
            "Text Readability",
            "Platform Compliance",
            "Visual Contrast",
        }
        assert criterion_names == expected


# ═══════════════════════════════════════════
# Async wrappers
# ═══════════════════════════════════════════


class TestAsyncWrappers:
    @pytest.mark.asyncio
    async def test_run_strategy_audit(self, auditor, sample_calendar):
        report = await auditor.run_strategy_audit(sample_calendar, ["tiktok"])
        assert isinstance(report, AuditReport)

    @pytest.mark.asyncio
    async def test_run_script_audit(self, auditor, sample_good_script):
        reports = await auditor.run_script_audit([sample_good_script])
        assert len(reports) == 1
        assert isinstance(reports[0], AuditReport)

    @pytest.mark.asyncio
    async def test_run_edit_audit(self, auditor, sample_composition):
        reports = await auditor.run_edit_audit([sample_composition])
        assert len(reports) == 1

    @pytest.mark.asyncio
    async def test_run_thumbnail_audit(self, auditor, sample_thumbnail_set):
        reports = await auditor.run_thumbnail_audit([sample_thumbnail_set])
        assert len(reports) == 1
