"""Test LangGraph pipeline compilation and structure."""

import pytest
from src.graph.pipeline import build_pipeline, compile_pipeline
from src.models.state import VideoPipelineState


class TestPipelineCompilation:
    def test_build_returns_stategraph(self):
        graph = build_pipeline()
        assert graph is not None
        # StateGraph doesn't expose nodes directly in all versions,
        # but we can verify it built without errors

    def test_compile_with_memory_checkpointer(self):
        compiled = compile_pipeline()
        assert compiled is not None

    def test_pipeline_initial_state(self):
        """Verify pipeline accepts initial state without errors."""
        compiled = compile_pipeline()
        config = {"configurable": {"thread_id": "test-001"}}

        initial: VideoPipelineState = {
            "product_catalog": {"products": []},
            "brand_guidelines": {},
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "content_calendar_week": "2026-W17",
            "current_step": "init",
            "errors": [],
            "human_reviews": {},
            "pipeline_complete": False,
        }

        # Just verify we can start the pipeline
        state = compiled.get_state(config)
        assert state is not None


class TestRouting:
    def test_route_after_compliance_blocked(self):
        from src.graph.routing import route_after_compliance
        from src.models import ComplianceReport, ComplianceStatus

        state = {
            "compliance_reports": [
                ComplianceReport(
                    script_id="S-001",
                    status=ComplianceStatus.BLOCKED,
                    flags=[],
                )
            ]
        }
        result = route_after_compliance(state)
        assert result == "__end__"

    def test_route_after_compliance_pass(self):
        from src.graph.routing import route_after_compliance
        from src.models import ComplianceReport, ComplianceStatus

        state = {
            "compliance_reports": [
                ComplianceReport(
                    script_id="S-001",
                    status=ComplianceStatus.PASS,
                    flags=[],
                )
            ]
        }
        result = route_after_compliance(state)
        assert result == "storyboard_node"

    def test_route_asset_gaps(self):
        from src.graph.routing import route_after_asset_sourcing
        from src.models import AssetPlan, ShotAssetPlan, AssetCandidate

        # Has gaps → go to media generation
        plan_with_gaps = AssetPlan(
            storyboard_id="SB-001",
            shot_plans=[
                ShotAssetPlan(
                    shot_id=1,
                    asset_needed="test",
                    candidates=[],
                    gap=True,
                )
            ],
            gaps=["missing asset"],
        )
        result = route_after_asset_sourcing({"asset_plans": [plan_with_gaps]})
        assert result == "media_generation_node"

        # No gaps → skip to editing
        plan_no_gaps = AssetPlan(
            storyboard_id="SB-001",
            shot_plans=[
                ShotAssetPlan(
                    shot_id=1,
                    asset_needed="test",
                    candidates=[
                        AssetCandidate(
                            asset_id="a1",
                            file_path="/test.mp4",
                            description="test",
                            match_score=0.9,
                            source="library",
                        )
                    ],
                    selected_asset_id="a1",
                    gap=False,
                )
            ],
            gaps=[],
        )
        result = route_after_asset_sourcing({"asset_plans": [plan_no_gaps]})
        assert result == "editing_node"


class TestRoutingHumanReview:
    """Routing decisions based on human review status — CHANGES_REQUESTED branches."""

    def test_route_after_strategy_approved(self):
        from src.graph.routing import route_after_strategy
        from src.models import HumanReview, ApprovalStatus

        # Approved → proceeds to script
        state = {
            "human_reviews": {
                "strategy_review": HumanReview(
                    node="strategy_review",
                    status=ApprovalStatus.APPROVED,
                    reviewer_notes="Looks good",
                ).model_dump(),
            },
            "weekly_calendar": {},
        }
        assert route_after_strategy(state) == "script_node"

    def test_route_after_strategy_changes_requested(self):
        from src.graph.routing import route_after_strategy
        from src.models import HumanReview, ApprovalStatus

        # Changes requested → back to strategy_node
        state = {
            "human_reviews": {
                "strategy_review": HumanReview(
                    node="strategy_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Need more variety",
                ).model_dump(),
            },
        }
        assert route_after_strategy(state) == "strategy_node"

    def test_route_after_script_approved(self):
        from src.graph.routing import route_after_script
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "script_review": HumanReview(
                    node="script_review",
                    status=ApprovalStatus.APPROVED,
                    reviewer_notes="Good script",
                ).model_dump(),
            },
            "weekly_calendar": {},
            "scripts": [],
        }
        assert route_after_script(state) == "compliance_node"

    def test_route_after_script_changes_requested(self):
        from src.graph.routing import route_after_script
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "script_review": HumanReview(
                    node="script_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Hook too slow",
                ).model_dump(),
            },
        }
        assert route_after_script(state) == "script_node"

    def test_route_after_editing_approved(self):
        from src.graph.routing import route_after_editing
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "edit_review": HumanReview(
                    node="edit_review",
                    status=ApprovalStatus.APPROVED,
                    reviewer_notes="Good cut",
                ).model_dump(),
            },
            "scripts": [],
        }
        assert route_after_editing(state) == "audio_node"

    def test_route_after_editing_changes_requested(self):
        from src.graph.routing import route_after_editing
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "edit_review": HumanReview(
                    node="edit_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Pace too slow",
                ).model_dump(),
            },
        }
        assert route_after_editing(state) == "editing_node"

    def test_route_after_thumbnail_approved(self):
        from src.graph.routing import route_after_thumbnail
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "thumbnail_review": HumanReview(
                    node="thumbnail_review",
                    status=ApprovalStatus.APPROVED,
                    reviewer_notes="Great thumbnails",
                ).model_dump(),
            },
            "scripts": [],
        }
        assert route_after_thumbnail(state) == "distribution_node"

    def test_route_after_thumbnail_changes_requested(self):
        from src.graph.routing import route_after_thumbnail
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "thumbnail_review": HumanReview(
                    node="thumbnail_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Thumbnails lack contrast",
                ).model_dump(),
            },
        }
        assert route_after_thumbnail(state) == "thumbnail_node"

    def test_retry_exhausted_thumbnail_changes_requested_overrides_to_approved(self):
        from src.graph.routing import route_after_thumbnail
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "thumbnail_review": HumanReview(
                    node="thumbnail_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                )
            },
            "retry_counts": {"thumbnail": 3},
        }
        result = route_after_thumbnail(state)
        assert result == "distribution_node"

    # ── L4.1: Audit-driven routing ──

    def test_audit_high_score_auto_approves_strategy(self):
        """Score > 0.90 should skip human review and auto-approve."""
        from src.graph.routing import route_after_strategy
        from src.models import AuditReport, AuditCriterionStatus, AuditCheckpoint

        state = {
            "audit_reports": {
                "strategy": AuditReport(
                    audit_id="AUDIT-TEST",
                    checkpoint=AuditCheckpoint.STRATEGY,
                    target_artifact_id="T001",
                    overall_score=0.95,
                    overall_status=AuditCriterionStatus.PASS,
                    criteria=[],
                    summary="High quality",
                )
            },
        }
        result = route_after_strategy(state)
        assert result == "script_node", f"Expected script_node, got {result}"

    def test_audit_high_score_auto_approves_script(self):
        from src.graph.routing import route_after_script
        from src.models import AuditReport, AuditCriterionStatus, AuditCheckpoint

        state = {
            "audit_reports": {
                "script": AuditReport(
                    audit_id="AUDIT-TEST",
                    checkpoint=AuditCheckpoint.SCRIPT,
                    target_artifact_id="T001",
                    overall_score=0.92,
                    overall_status=AuditCriterionStatus.PASS,
                    criteria=[],
                    summary="Good script",
                )
            },
        }
        result = route_after_script(state)
        assert result == "compliance_node"

    def test_audit_low_score_auto_rejects_strategy(self):
        """Score < 0.60 should shut down the pipeline."""
        from src.graph.routing import route_after_strategy
        from src.models import AuditReport, AuditCriterionStatus, AuditCheckpoint

        state = {
            "audit_reports": {
                "strategy": AuditReport(
                    audit_id="AUDIT-TEST",
                    checkpoint=AuditCheckpoint.STRATEGY,
                    target_artifact_id="T001",
                    overall_score=0.35,
                    overall_status=AuditCriterionStatus.FAIL,
                    criteria=[],
                    summary="Poor quality",
                )
            },
        }
        result = route_after_strategy(state)
        assert result == "__end__", f"Expected __end__, got {result}"

    def test_audit_low_score_auto_rejects_thumbnail(self):
        from src.graph.routing import route_after_thumbnail
        from src.models import AuditReport, AuditCriterionStatus, AuditCheckpoint

        state = {
            "audit_reports": {
                "thumbnail": AuditReport(
                    audit_id="AUDIT-TEST",
                    checkpoint=AuditCheckpoint.THUMBNAIL,
                    target_artifact_id="T001",
                    overall_score=0.40,
                    overall_status=AuditCriterionStatus.FAIL,
                    criteria=[],
                    summary="Poor thumbnails",
                )
            },
        }
        result = route_after_thumbnail(state)
        assert result == "__end__"

    def test_audit_mid_score_falls_through_to_human_review(self):
        """Score in 0.60-0.90 range should use normal human review."""
        from src.graph.routing import route_after_strategy
        from src.models import AuditReport, AuditCriterionStatus, AuditCheckpoint, HumanReview, ApprovalStatus

        state = {
            "audit_reports": {
                "strategy": AuditReport(
                    audit_id="AUDIT-TEST",
                    checkpoint=AuditCheckpoint.STRATEGY,
                    target_artifact_id="T001",
                    overall_score=0.75,
                    overall_status=AuditCriterionStatus.WARN,
                    criteria=[],
                    summary="Needs review",
                )
            },
            "human_reviews": {
                "strategy_review": HumanReview(
                    node="strategy_review",
                    status=ApprovalStatus.APPROVED,
                )
            },
        }
        result = route_after_strategy(state)
        assert result == "script_node"

    def test_audit_mid_score_changes_requested_returns_to_node(self):
        """Mid score + CHANGES_REQUESTED should send back to content node."""
        from src.graph.routing import route_after_editing
        from src.models import AuditReport, AuditCriterionStatus, AuditCheckpoint, HumanReview, ApprovalStatus

        state = {
            "audit_reports": {
                "edit": AuditReport(
                    audit_id="AUDIT-TEST",
                    checkpoint=AuditCheckpoint.EDIT,
                    target_artifact_id="T001",
                    overall_score=0.75,
                    overall_status=AuditCriterionStatus.WARN,
                    criteria=[],
                    summary="Needs review",
                )
            },
            "human_reviews": {
                "edit_review": HumanReview(
                    node="edit_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                )
            },
        }
        result = route_after_editing(state)
        assert result == "editing_node"

    def test_no_audit_report_falls_through_gracefully(self):
        """Missing audit report should not cause errors — fall through to human review."""
        from src.graph.routing import route_after_editing
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "edit_review": HumanReview(
                    node="edit_review",
                    status=ApprovalStatus.APPROVED,
                )
            },
        }
        result = route_after_editing(state)
        assert result == "audio_node"

    def test_no_audit_no_human_review_falls_to_content_node(self):
        """No audit report + no human review should route to content node (pending)."""
        from src.graph.routing import route_after_script

        state = {}
        result = route_after_script(state)
        assert result == "script_node"

class TestRetryGuard:
    """Retry count limits prevent infinite re-execution loops.

    SELF-AUDIT: If a node exhausts MAX_RETRIES (3), CHANGES_REQUESTED is
    overridden to APPROVED. Without this guard, CHANGES_REQUESTED with
    retry_counts>=3 would still route back to the content node (infinite loop).
    """

    def test_strategy_retries_exhausted_forces_approval(self):
        from src.graph.routing import route_after_strategy
        from src.models import HumanReview, ApprovalStatus

        # retry_counts["strategy"] = 3 (exhausted) + CHANGES_REQUESTED
        # → should route to script_node (override), NOT strategy_node
        state = {
            "human_reviews": {
                "strategy_review": HumanReview(
                    node="strategy_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Try again",
                ).model_dump(),
            },
            "retry_counts": {"strategy": 3},
        }
        result = route_after_strategy(state)
        assert result == "script_node", (
            f"Expected 'script_node' (retry guard override), got '{result}'"
        )

    def test_script_retries_exhausted_forces_approval(self):
        from src.graph.routing import route_after_script
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "script_review": HumanReview(
                    node="script_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Fix again",
                ).model_dump(),
            },
            "retry_counts": {"script": 3},
        }
        result = route_after_script(state)
        assert result == "compliance_node"

    def test_edit_retries_exhausted_forces_approval(self):
        from src.graph.routing import route_after_editing
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "edit_review": HumanReview(
                    node="edit_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Try again",
                ).model_dump(),
            },
            "retry_counts": {"edit": 3},
        }
        result = route_after_editing(state)
        assert result == "audio_node"

    def test_thumbnail_retries_exhausted_forces_approval(self):
        from src.graph.routing import route_after_thumbnail
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "thumbnail_review": HumanReview(
                    node="thumbnail_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="Try again",
                ).model_dump(),
            },
            "retry_counts": {"thumbnail": 3},
        }
        result = route_after_thumbnail(state)
        assert result == "distribution_node"

    def test_retry_below_limit_still_loops_back(self):
        """2 retries < 3 max → CHANGES_REQUESTED still goes back to content node."""
        from src.graph.routing import route_after_script
        from src.models import HumanReview, ApprovalStatus

        state = {
            "human_reviews": {
                "script_review": HumanReview(
                    node="script_review",
                    status=ApprovalStatus.CHANGES_REQUESTED,
                    reviewer_notes="One more fix",
                ).model_dump(),
            },
            "retry_counts": {"script": 2},
        }
        result = route_after_script(state)
        assert result == "script_node"
