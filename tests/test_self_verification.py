"""Tests for L4.4 rejection feedback injection + L5.x self-verification.

Tests audit nodes directly with pre-built mock state — no pipeline compile needed.
"""

import pytest

from src.graph.nodes import (
    strategy_audit_node,
    script_audit_node,
    editing_audit_node,
    thumbnail_audit_node,
    _inject_rejection_feedback,
    _make_self_verification,
)


# ── L5.x: _make_self_verification unit tests ──


class TestMakeSelfVerification:
    def test_all_checks_pass(self):
        result = _make_self_verification("test_node", {"a": True, "b": True}, "2 things done")
        assert result["node_name"] == "test_node"
        assert result["quality_thresholds_met"] is True
        assert result["output_summary"] == "2 things done"

    def test_any_check_fails(self):
        result = _make_self_verification("test_node", {"a": True, "b": False}, "1 of 2")
        assert result["quality_thresholds_met"] is False

    def test_all_checks_fail(self):
        result = _make_self_verification("test_node", {"a": False}, "nothing")
        assert result["quality_thresholds_met"] is False

    def test_empty_checks_still_met(self):
        result = _make_self_verification("test_node", {}, "empty")
        assert result["quality_thresholds_met"] is True


# ── L4.4: _inject_rejection_feedback unit tests ──


class TestInjectRejectionFeedback:
    def test_no_review_returns_empty(self):
        result = _inject_rejection_feedback({"human_reviews": {}}, "strategy_review", "strategy")
        assert result == {}

    def test_review_without_notes_does_not_inject(self):
        state = {"human_reviews": {"strategy_review": {"status": "changes_requested", "reviewer_notes": ""}}}
        result = _inject_rejection_feedback(state, "strategy_review", "strategy")
        assert result == {}

    def test_review_with_notes_injects(self):
        state = {"human_reviews": {"strategy_review": {"status": "changes_requested", "reviewer_notes": "Too vague"}}}
        result = _inject_rejection_feedback(state, "strategy_review", "strategy")
        assert result == {"strategy": "Too vague"}

    def test_already_injected_does_not_overwrite(self):
        state = {
            "rejection_feedback": {"strategy": "Previous feedback"},
            "human_reviews": {"strategy_review": {"reviewer_notes": "New feedback"}},
        }
        result = _inject_rejection_feedback(state, "strategy_review", "strategy")
        assert result == {"strategy": "Previous feedback"}

    def test_review_as_pydantic_model(self):
        from src.models import HumanReview, ApprovalStatus
        state = {"human_reviews": {"script_review": HumanReview(
            node="script_review",
            status=ApprovalStatus.CHANGES_REQUESTED,
            reviewer_notes="Missing CTA",
        )}}
        result = _inject_rejection_feedback(state, "script_review", "script")
        assert result == {"script": "Missing CTA"}

    def test_diff_review_key_does_not_inject(self):
        state = {"human_reviews": {"strategy_review": {"reviewer_notes": "Bad strategy"}}}
        result = _inject_rejection_feedback(state, "script_review", "script")
        assert result == {}


# ── L5.x: Self-verification audit node tests ──
# These call audit nodes directly with pre-built mock state


def _make_weekly_calendar():
    from src.models import WeeklyCalendar, Brief, VideoType, Platform, Language
    return WeeklyCalendar(
        week="2026-W18",
        briefs=[
            Brief(
                id="BRIEF-001",
                video_type=VideoType.PRODUCT_USAGE,
                topic="Test topic",
                target_audience="Developers",
                target_platforms=[Platform.TIKTOK],
                target_languages=[Language.EN],
                key_message="Test",
                usp_priority=["speed"],
            ),
        ],
    )


def _make_scripts():
    from src.models import Script, ScriptSegment, Platform, Language
    return [
        Script(
            id="S-001",
            brief_id="BRIEF-001",
            platform=Platform.TIKTOK,
            language=Language.EN,
            total_duration=30.0,
            segments=[ScriptSegment(segment_type="hook", start_time=0.0, end_time=3.0,
                                    voiceover="Hey!", visual_description="Test")],
            hashtags=["#test"],
            cta_text="Buy now",
        ),
    ]


def _make_compositions():
    from src.models import EditComposition, EditTimelineEvent
    return [
        EditComposition(
            script_id="S-001",
            total_duration=30.0,
            timeline=[
                EditTimelineEvent(shot_id=1, asset_id="a", start_time=0.0, end_time=3.0, transition="dissolve"),
                EditTimelineEvent(shot_id=2, asset_id="b", start_time=3.0, end_time=30.0),
            ],
        ),
    ]


def _make_thumbnail_sets():
    from src.models import ThumbnailSet, ThumbnailVariant
    return [
        ThumbnailSet(
            script_id="S-001",
            variants=[
                ThumbnailVariant(variant_id="A", concept="Hook", prompt="Show product"),
                ThumbnailVariant(variant_id="B", concept="Result", prompt="Show result"),
            ],
            selected_variant_id="A",
        ),
    ]


class TestStrategyAuditSelfVerification:
    @pytest.mark.asyncio
    async def test_normal_path_has_self_verification(self):
        state = {
            "weekly_calendar": _make_weekly_calendar(),
            "target_platforms": ["tiktok"],
            "current_step": "strategy_complete",
        }
        result = await strategy_audit_node(state)
        assert "self_verifications" in result
        sv = result["self_verifications"].get("strategy_node")
        assert sv is not None
        assert sv["node_name"] == "strategy_node"
        assert sv["quality_thresholds_met"] is True
        assert sv["verification_details"]["has_briefs"] is True
        assert sv["verification_details"]["has_platforms"] is True

    @pytest.mark.asyncio
    async def test_empty_calendar_returns_error(self):
        state = {"current_step": "strategy_complete"}
        result = await strategy_audit_node(state)
        assert "errors" in result


class TestScriptAuditSelfVerification:
    @pytest.mark.asyncio
    async def test_normal_path_has_self_verification(self):
        state = {
            "scripts": _make_scripts(),
            "current_step": "script_complete",
        }
        result = await script_audit_node(state)
        assert "self_verifications" in result
        sv = result["self_verifications"].get("script_node")
        assert sv is not None
        assert sv["quality_thresholds_met"] is True
        assert sv["verification_details"]["all_have_cta"] is True

    @pytest.mark.asyncio
    async def test_empty_scripts_returns_error(self):
        state = {"current_step": "script_complete"}
        result = await script_audit_node(state)
        assert "errors" in result


class TestEditAuditSelfVerification:
    @pytest.mark.asyncio
    async def test_normal_path_has_self_verification(self):
        state = {
            "edit_compositions": _make_compositions(),
            "current_step": "editing_complete",
        }
        result = await editing_audit_node(state)
        assert "self_verifications" in result
        sv = result["self_verifications"].get("editing_node")
        assert sv is not None
        assert sv["quality_thresholds_met"] is True
        assert sv["verification_details"]["has_varied_transitions"] is True

    @pytest.mark.asyncio
    async def test_empty_compositions_returns_error(self):
        state = {"current_step": "editing_complete"}
        result = await editing_audit_node(state)
        assert "errors" in result


class TestThumbnailAuditSelfVerification:
    @pytest.mark.asyncio
    async def test_normal_path_has_self_verification(self):
        state = {
            "thumbnail_sets": _make_thumbnail_sets(),
            "current_step": "thumbnail_complete",
        }
        result = await thumbnail_audit_node(state)
        assert "self_verifications" in result
        sv = result["self_verifications"].get("thumbnail_node")
        assert sv is not None
        assert sv["quality_thresholds_met"] is True
        assert sv["verification_details"]["has_selection"] is True

    @pytest.mark.asyncio
    async def test_empty_thumbnail_sets_returns_error(self):
        state = {"current_step": "thumbnail_complete"}
        result = await thumbnail_audit_node(state)
        assert "errors" in result


# ── L4.4: Rejection feedback injection tests ──


class TestStrategyAuditRejectionInjection:
    @pytest.mark.asyncio
    async def test_rejection_notes_injected_on_reentry(self):
        state = {
            "weekly_calendar": _make_weekly_calendar(),
            "target_platforms": ["tiktok"],
            "current_step": "strategy_complete",
            "human_reviews": {"strategy_review": {
                "status": "changes_requested",
                "reviewer_notes": "Needs more platforms",
            }},
        }
        result = await strategy_audit_node(state)
        assert result["rejection_feedback"].get("strategy") == "Needs more platforms"

    @pytest.mark.asyncio
    async def test_no_notes_no_injection(self):
        state = {
            "weekly_calendar": _make_weekly_calendar(),
            "target_platforms": ["tiktok"],
            "current_step": "strategy_complete",
            "human_reviews": {"strategy_review": {
                "status": "approved",
                "reviewer_notes": "",
            }},
        }
        result = await strategy_audit_node(state)
        assert "strategy" not in result["rejection_feedback"]


class TestScriptAuditRejectionInjection:
    @pytest.mark.asyncio
    async def test_rejection_notes_injected_on_reentry(self):
        state = {
            "scripts": _make_scripts(),
            "current_step": "script_complete",
            "human_reviews": {"script_review": {
                "reviewer_notes": "Weak hook",
            }},
        }
        result = await script_audit_node(state)
        assert result["rejection_feedback"].get("script") == "Weak hook"


class TestEditAuditRejectionInjection:
    @pytest.mark.asyncio
    async def test_rejection_notes_injected_on_reentry(self):
        state = {
            "edit_compositions": _make_compositions(),
            "current_step": "editing_complete",
            "human_reviews": {"edit_review": {
                "reviewer_notes": "Transitions too slow",
            }},
        }
        result = await editing_audit_node(state)
        assert result["rejection_feedback"].get("edit") == "Transitions too slow"


class TestThumbnailAuditRejectionInjection:
    @pytest.mark.asyncio
    async def test_rejection_notes_injected_on_reentry(self):
        state = {
            "thumbnail_sets": _make_thumbnail_sets(),
            "current_step": "thumbnail_complete",
            "human_reviews": {"thumbnail_review": {
                "reviewer_notes": "Add more variants",
            }},
        }
        result = await thumbnail_audit_node(state)
        assert result["rejection_feedback"].get("thumbnail") == "Add more variants"
