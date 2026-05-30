"""Tests for L3.1: ScriptWriterAgent quality signal propagation.

Verifies that strategy audit reports produce actionable adaptations
in the generated scripts — the foundational inter-node feature pipeline.
"""

import pytest

from src.agents.script_writer import ScriptWriterAgent
from src.models import (
    AuditCheckpoint,
    AuditCriterion,
    AuditCriterionStatus,
    AuditReport,
    Brief,
    Language,
    Platform,
    VideoType,
)


@pytest.fixture
def agent():
    return ScriptWriterAgent()


@pytest.fixture
def sample_audit():
    """A strategy audit with specific weaknesses that scripts should compensate for."""
    return AuditReport(
        audit_id="AUDIT-STRATEGY-2026-W17",
        checkpoint=AuditCheckpoint.STRATEGY,
        target_artifact_id="2026-W17",
        overall_score=0.62,
        overall_status=AuditCriterionStatus.WARN,
        criteria=[
            AuditCriterion(
                name="Audience Specificity", status=AuditCriterionStatus.WARN,
                score=0.67,
                observation="2/3 briefs have specific target audience",
                recommendation="Avoid vague audiences like 'everyone' — target a specific persona",
            ),
            AuditCriterion(
                name="Seasonal Relevance", status=AuditCriterionStatus.FAIL,
                score=0.30,
                observation="0/3 briefs use seasonal/temporal hook",
                recommendation="Add at least one seasonal or time-sensitive angle",
            ),
            AuditCriterion(
                name="Competitor / Trend Anchoring", status=AuditCriterionStatus.WARN,
                score=0.33,
                observation="1/3 briefs reference competitor or seasonal trend",
                recommendation="Anchor at least 30% of briefs to competitor or cultural moment",
            ),
            AuditCriterion(
                name="Platform Coverage", status=AuditCriterionStatus.PASS,
                score=1.0,
                observation="All target platforms covered",
            ),
        ],
        summary="Week 2026-W17: 3 briefs scored 62% overall (WARN). ⚠️ Needs attention before review",
    )


@pytest.fixture
def sample_briefs():
    return [
        Brief(
            id="BRIEF-001",
            video_type=VideoType.TUTORIAL,
            topic="How to clean wearable pump at the office",
            target_audience="Working moms 25-35",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="Clean in 2 minutes",
            usp_priority=["portable", "quiet"],
        ),
        Brief(
            id="BRIEF-003",
            video_type=VideoType.PRODUCT_USAGE,
            topic="Speed test comparison",
            target_audience="First-time moms",
            target_platforms=[Platform.TIKTOK],
            target_languages=[Language.EN],
            key_message="Setup in 30 seconds",
            usp_priority=["easy-setup", "portable"],
        ),
    ]


class TestExtractQualitySignals:
    def test_returns_empty_for_no_audit(self, agent):
        assert agent._extract_quality_signals(None) == {}

    def test_extracts_low_criteria(self, agent, sample_audit):
        signals = agent._extract_quality_signals(sample_audit)
        assert "overall_score" in signals
        assert signals["overall_score"] == 0.62
        assert signals["overall_status"] == "WARN"

        # Should ONLY include WARN/FAIL criteria, not PASS
        names_in_low = [c for c in signals["low_scoring_criteria"]]
        assert any("Audience Specificity" in c for c in names_in_low)
        assert any("Seasonal Relevance" in c for c in names_in_low)
        assert any("Competitor / Trend Anchoring" in c for c in names_in_low)
        # Platform Coverage is PASS — should NOT be in low_scoring
        assert all("Platform Coverage" not in c for c in names_in_low)

    def test_extracts_actionable_fixes(self, agent, sample_audit):
        signals = agent._extract_quality_signals(sample_audit)
        fixes = signals["actionable_fixes"]
        assert len(fixes) >= 2  # At least audience + seasonal
        assert any("Audience" in f for f in fixes)
        assert any("Seasonal" in f for f in fixes)


class TestAdaptTemplate:
    """Verify that quality signals actually modify script content."""

    BASE_TEMPLATE = {
        "hook": "Pumping at work doesn't have to mean hiding.",
        "hook_visual": "Desk scene",
        "hook_overlay": "Clean in 2 min?",
        "pain": "Finding a clean space is hard enough.",
        "pain_visual": "Office sink",
        "pain_overlay": "The struggle",
        "solution": "The X1 rinses clean in 30 seconds.",
        "solution_visual": "Product demo",
        "solution_overlay": "30 sec rinse",
        "trust": "FDA cleared. 280mmHg. 50K+ moms.",
        "trust_visual": "FDA badge",
        "trust_overlay": "FDA Cleared",
        "cta": "Shop at link in bio.",
        "cta_visual": "Product shot",
        "cta_overlay": "Shop Now",
        "cta_text": "Shop X1",
        "hashtags": ["#test"],
    }

    def test_no_signals_returns_unchanged(self):
        result = ScriptWriterAgent._adapt_template(self.BASE_TEMPLATE, Platform.TIKTOK)
        assert result == self.BASE_TEMPLATE

    def test_audience_fix_injects_into_hook(self):
        signals = {
            "overall_score": 0.62,
            "overall_status": "WARN",
            "actionable_fixes": [
                "Audience Specificity — Avoid vague audiences like 'everyone' — target a specific persona",
            ],
        }
        result = ScriptWriterAgent._adapt_template(
            self.BASE_TEMPLATE, Platform.TIKTOK, signals
        )
        # Hook should be modified with audience fix
        assert "Audience Specificity" in result["hook"]
        assert "Avoid vague audiences" in result["hook"]
        # Other fields should remain intact
        assert result["solution"] == self.BASE_TEMPLATE["solution"]
        assert result["cta"] == self.BASE_TEMPLATE["cta"]

    def test_seasonal_fix_injects_into_pain(self):
        signals = {
            "overall_score": 0.62,
            "overall_status": "WARN",
            "actionable_fixes": [
                "Seasonal Relevance — Add time-sensitive angles",
            ],
        }
        result = ScriptWriterAgent._adapt_template(
            self.BASE_TEMPLATE, Platform.TIKTOK, signals
        )
        assert "this week matters" in result["pain"]

    def test_multiple_fixes_compound(self):
        signals = {
            "overall_score": 0.62,
            "overall_status": "WARN",
            "actionable_fixes": [
                "Audience Specificity — target specific persona",
                "Seasonal Relevance — add seasonal angle",
            ],
        }
        result = ScriptWriterAgent._adapt_template(
            self.BASE_TEMPLATE, Platform.TIKTOK, signals
        )
        # Both should be applied
        assert "Audience Specificity" in result["hook"]
        assert "this week matters" in result["pain"]

    def test_very_low_score_adds_urgency_to_cta(self):
        signals = {
            "overall_score": 0.35,
            "overall_status": "FAIL",
            "actionable_fixes": [],
        }
        result = ScriptWriterAgent._adapt_template(
            self.BASE_TEMPLATE, Platform.TIKTOK, signals
        )
        assert result["cta"].startswith("This video needs urgent attention")
        assert result["cta_text"].startswith("URGENT")


class TestIntegrationMockScripts:
    """Test end-to-end: agent.run() with audit → modified scripts."""

    @pytest.mark.asyncio
    async def test_without_audit_produces_normal_scripts(self, agent, sample_briefs):
        """No audit = standard templates, no adaptations."""
        scripts = await agent.run(sample_briefs, {}, strategy_audit=None)
        assert len(scripts) == 2  # 2 briefs, 1 platform each
        for s in scripts:
            hook = s.segments[0].voiceover
            assert "Audience Specificity" not in hook
            assert "this week matters" not in hook

    @pytest.mark.asyncio
    async def test_with_audit_produces_adapted_scripts(self, agent, sample_briefs, sample_audit):
        """With audit = scripts adapted per quality signals."""
        scripts = await agent.run(sample_briefs, {}, strategy_audit=sample_audit)
        assert len(scripts) == 2  # Same count

        # At least one script should have adaptations
        hooks_adapted = sum(1 for s in scripts if "Audience Specificity" in s.segments[0].voiceover)
        assert hooks_adapted >= 1, "No scripts had audience fix — signal propagation broken"

        # Log what happened for self-audit
        for s in scripts:
            print(f"  [{s.id}] hook: {s.segments[0].voiceover[:80]}...")
            print(f"  [{s.id}] cta: {s.cta_text[:60]}")
