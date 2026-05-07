"""Unit tests for routing functions — conditional graph edges.

Covers every branch in every route function.
State can be either dict or VideoPipelineState (both forms used by LangGraph).
"""

import re

from datetime import datetime

import pytest

from src.graph.routing import (
    route_after_strategy,
    route_after_script,
    route_after_compliance,
    route_after_asset_sourcing,
    route_after_editing,
    route_after_thumbnail,
    _audit_guard,
    _retry_guard,
    _get_approval_status,
    _get_compliance_status,
    AUTO_APPROVE_THRESHOLD,
    AUTO_REJECT_THRESHOLD,
    MAX_RETRIES,
)
from src.models import (
    AuditReport, AuditCriterionStatus, AuditCriterion,
    HumanReview, ApprovalStatus,
    ComplianceReport, ComplianceStatus, AssetPlan, AuditCheckpoint,
)
from src.models.state import VideoPipelineState
from typing import Any


# ── Audit report fixtures ──

def make_criterion(name: str, status: str, score: float = 1.0) -> AuditCriterion:
    return AuditCriterion(
        name=name,
        status=AuditCriterionStatus(status),
        score=score,
        observation=f"Observation for {name}",
        recommendation="" if status == "PASS" else f"Improve {name}",
    )


def make_audit_report(score: float, checkpoint: str = "strategy", artifact_id: str = "ART-001") -> AuditReport:
    status = "PASS" if score >= 0.85 else "WARN" if score >= 0.50 else "FAIL"
    return AuditReport(
        audit_id=f"AUDIT-{checkpoint.upper()}-001",
        checkpoint=AuditCheckpoint(checkpoint),
        target_artifact_id=artifact_id,
        overall_score=score,
        overall_status=AuditCriterionStatus(status),
        criteria=[make_criterion("relevance", "PASS")],
        summary=f"Test audit report for {checkpoint} with score {score}",
        generated_at=datetime.utcnow(),
    )


def audit_as_dict(score: float, checkpoint: str = "strategy") -> dict[str, Any]:
    status = "PASS" if score >= 0.85 else "WARN" if score >= 0.50 else "FAIL"
    return {
        "audit_id": f"AUDIT-{checkpoint.upper()}-001",
        "checkpoint": checkpoint,
        "target_artifact_id": "ART-001",
        "overall_score": score,
        "overall_status": status,
        "criteria": [{"name": "relevance", "status": "PASS", "score": 1.0,
                       "observation": "OK", "recommendation": ""}],
        "summary": f"Test dict audit {score}",
        "generated_at": datetime.utcnow(),
    }


def audit_as_dict_no_score() -> dict[str, Any]:
    return {
        "audit_id": "AUDIT-TEST-001",
        "checkpoint": "strategy",
        "target_artifact_id": "ART-001",
        "criteria": [],
        "summary": "No overall_score",
        "generated_at": datetime.utcnow(),
    }


def make_human_review(status: ApprovalStatus, node_name: str = "test_review") -> HumanReview:
    return HumanReview(
        node=node_name,
        status=status,
        reviewer_notes="Test review",
        content_snapshot={},
    )


# ── _audit_guard ──

class TestAuditGuard:
    def test_high_score_auto_approve(self):
        state = {"audit_reports": {"strategy": make_audit_report(0.95)}}
        assert _audit_guard(state, "strategy") == "approved"  # type: ignore[arg-type]

    def test_low_score_auto_reject(self):
        state = {"audit_reports": {"strategy": make_audit_report(0.30)}}
        assert _audit_guard(state, "strategy") == "rejected"  # type: ignore[arg-type]

    def test_mid_score_returns_none(self):
        state = {"audit_reports": {"strategy": make_audit_report(0.75)}}
        assert _audit_guard(state, "strategy") is None  # type: ignore[arg-type]

    def test_exact_boundary_high_side(self):
        state = {"audit_reports": {"strategy": make_audit_report(AUTO_APPROVE_THRESHOLD + 0.001)}}
        assert _audit_guard(state, "strategy") == "approved"  # type: ignore[arg-type]

    def test_exact_boundary_low_side(self):
        state = {"audit_reports": {"strategy": make_audit_report(AUTO_REJECT_THRESHOLD - 0.001)}}
        assert _audit_guard(state, "strategy") == "rejected"  # type: ignore[arg-type]

    def test_no_report_returns_none(self):
        state = {"audit_reports": {}}
        assert _audit_guard(state, "strategy") is None  # type: ignore[arg-type]

    def test_missing_key_returns_none(self):
        state = {"audit_reports": {"script": make_audit_report(0.5)}}
        assert _audit_guard(state, "strategy") is None  # type: ignore[arg-type]

    def test_dict_report_high_score(self):
        state = {"audit_reports": {"script": audit_as_dict(0.95)}}
        assert _audit_guard(state, "script") == "approved"  # type: ignore[arg-type]

    def test_dict_report_low_score(self):
        state = {"audit_reports": {"script": audit_as_dict(0.40)}}
        assert _audit_guard(state, "script") == "rejected"  # type: ignore[arg-type]

    def test_dict_report_missing_score(self):
        state = {"audit_reports": {"script": audit_as_dict_no_score()}}
        # overall_score defaults to 0.5 from dict.get, which is < 0.60 → auto-reject
        assert _audit_guard(state, "script") == "rejected"  # type: ignore[arg-type]


# ── _retry_guard ──

class TestRetryGuard:
    def test_below_limit_returns_none(self):
        state = {"retry_counts": {"strategy": MAX_RETRIES - 1}}
        assert _retry_guard(state, "strategy") is None  # type: ignore[arg-type]

    def test_at_limit_returns_approved(self):
        state = {"retry_counts": {"strategy": MAX_RETRIES}}
        assert _retry_guard(state, "strategy") == "approved"  # type: ignore[arg-type]

    def test_exceeds_limit_returns_approved(self):
        state = {"retry_counts": {"strategy": MAX_RETRIES + 5}}
        assert _retry_guard(state, "strategy") == "approved"  # type: ignore[arg-type]

    def test_no_retry_count_returns_none(self):
        state = {}
        assert _retry_guard(state, "strategy") is None  # type: ignore[arg-type]

    def test_empty_retry_counts_returns_none(self):
        state = {"retry_counts": {}}
        assert _retry_guard(state, "strategy") is None  # type: ignore[arg-type]

    def test_different_node_does_not_interfere(self):
        state = {"retry_counts": {"script": MAX_RETRIES}}
        assert _retry_guard(state, "strategy") is None  # type: ignore[arg-type]


# ── _get_approval_status ──

class TestGetApprovalStatus:
    def test_pydantic_model_approved(self):
        review = make_human_review(ApprovalStatus.APPROVED)
        assert _get_approval_status(review) == "approved"

    def test_pydantic_model_rejected(self):
        review = make_human_review(ApprovalStatus.REJECTED)
        assert _get_approval_status(review) == "rejected"

    def test_pydantic_model_changes_requested(self):
        review = make_human_review(ApprovalStatus.CHANGES_REQUESTED)
        assert _get_approval_status(review) == "changes_requested"

    def test_dict_approved(self):
        assert _get_approval_status({"status": "approved"}) == "approved"

    def test_dict_rejected(self):
        assert _get_approval_status({"status": "rejected"}) == "rejected"

    def test_none_returns_none(self):
        assert _get_approval_status(None) is None


# ── _get_compliance_status ──

class TestGetComplianceStatus:
    def test_blocked_pydantic(self):
        report = ComplianceReport(script_id="S-001", status=ComplianceStatus.BLOCKED)
        assert _get_compliance_status(report) == "BLOCKED"

    def test_pass_pydantic(self):
        report = ComplianceReport(script_id="S-001", status=ComplianceStatus.PASS)
        assert _get_compliance_status(report) == "PASS"

    def test_blocked_dict(self):
        assert _get_compliance_status({"status": "BLOCKED"}) == "BLOCKED"

    def test_none_returns_none(self):
        assert _get_compliance_status(None) is None


# ── route_after_strategy ──

class TestRouteAfterStrategy:
    def test_audit_auto_approve_goes_to_script(self):
        state = {"audit_reports": {"strategy": make_audit_report(0.95)}}
        assert route_after_strategy(state) == "script_node"  # type: ignore[arg-type]

    def test_audit_auto_reject_goes_to_end(self):
        state = {"audit_reports": {"strategy": make_audit_report(0.30)}}
        assert route_after_strategy(state) == "__end__"  # type: ignore[arg-type]

    def test_human_approval_goes_to_script(self):
        state = {
            "audit_reports": {"strategy": make_audit_report(0.75)},
            "human_reviews": {"strategy_review": make_human_review(ApprovalStatus.APPROVED, "strategy_review")},
        }
        assert route_after_strategy(state) == "script_node"  # type: ignore[arg-type]

    def test_human_rejected_stays_at_strategy(self):
        state = {
            "audit_reports": {"strategy": make_audit_report(0.75)},
            "human_reviews": {"strategy_review": {"status": "changes_requested"}},
        }
        assert route_after_strategy(state) == "strategy_node"  # type: ignore[arg-type]

    def test_retry_guard_force_approves(self):
        state = {
            "retry_counts": {"strategy": MAX_RETRIES},
            "human_reviews": {"strategy_review": {"status": "changes_requested"}},
        }
        assert route_after_strategy(state) == "script_node"  # type: ignore[arg-type]

    def test_no_review_falls_to_strategy(self):
        state = {"audit_reports": {"strategy": make_audit_report(0.75)}}
        assert route_after_strategy(state) == "strategy_node"  # type: ignore[arg-type]


# ── route_after_script ──

class TestRouteAfterScript:
    def test_audit_auto_approve_goes_to_compliance(self):
        state = {"audit_reports": {"script": make_audit_report(0.95)}}
        assert route_after_script(state) == "compliance_node"  # type: ignore[arg-type]

    def test_audit_auto_reject_goes_to_end(self):
        state = {"audit_reports": {"script": make_audit_report(0.30)}}
        assert route_after_script(state) == "__end__"  # type: ignore[arg-type]

    def test_human_approval_goes_to_compliance(self):
        state = {
            "audit_reports": {"script": make_audit_report(0.75)},
            "human_reviews": {"script_review": make_human_review(ApprovalStatus.APPROVED, "script_review")},
        }
        assert route_after_script(state) == "compliance_node"  # type: ignore[arg-type]

    def test_human_changes_requested_stays_at_script(self):
        state = {
            "audit_reports": {"script": make_audit_report(0.75)},
            "human_reviews": {"script_review": {"status": "changes_requested"}},
        }
        assert route_after_script(state) == "script_node"  # type: ignore[arg-type]

    def test_no_review_falls_to_script(self):
        state = {"audit_reports": {"script": make_audit_report(0.75)}}
        assert route_after_script(state) == "script_node"  # type: ignore[arg-type]


# ── route_after_compliance ──

class TestRouteAfterCompliance:
    def test_no_reports_goes_to_storyboard(self):
        state = {}
        assert route_after_compliance(state) == "storyboard_node"  # type: ignore[arg-type]

    def test_empty_reports_goes_to_storyboard(self):
        state = {"compliance_reports": []}
        assert route_after_compliance(state) == "storyboard_node"  # type: ignore[arg-type]

    def test_blocked_report_goes_to_end(self):
        state = {"compliance_reports": [
            ComplianceReport(script_id="S-001", status=ComplianceStatus.PASS),
            ComplianceReport(script_id="S-002", status=ComplianceStatus.BLOCKED),
        ]}
        assert route_after_compliance(state) == "__end__"  # type: ignore[arg-type]

    def test_all_pass_goes_to_storyboard(self):
        state = {"compliance_reports": [
            {"status": "PASS"},
            {"status": "PASS"},
        ]}
        assert route_after_compliance(state) == "storyboard_node"  # type: ignore[arg-type]

    def test_single_blocked_dict_goes_to_end(self):
        state = {"compliance_reports": [{"status": "BLOCKED"}]}
        assert route_after_compliance(state) == "__end__"  # type: ignore[arg-type]


# ── route_after_asset_sourcing ──

class TestRouteAfterAssetSourcing:
    def test_no_plans_goes_to_editing(self):
        state = {}
        assert route_after_asset_sourcing(state) == "editing_node"  # type: ignore[arg-type]

    def test_empty_plans_goes_to_editing(self):
        state = {"asset_plans": []}
        assert route_after_asset_sourcing(state) == "editing_node"  # type: ignore[arg-type]

    def test_plan_with_gaps_goes_to_media_gen(self):
        plan = AssetPlan(storyboard_id="SB-001", shot_plans=[], gaps=["missing asset"])
        state = {"asset_plans": [plan]}
        assert route_after_asset_sourcing(state) == "media_generation_node"  # type: ignore[arg-type]

    def test_plan_without_gaps_goes_to_editing(self):
        plan = AssetPlan(storyboard_id="SB-001", shot_plans=[], gaps=[])
        state = {"asset_plans": [plan]}
        assert route_after_asset_sourcing(state) == "editing_node"  # type: ignore[arg-type]

    def test_plan_as_dict_with_gaps(self):
        plan = {"storyboard_id": "SB-001", "shot_plans": [], "gaps": ["missing video"]}
        state = {"asset_plans": [plan]}
        assert route_after_asset_sourcing(state) == "media_generation_node"  # type: ignore[arg-type]

    def test_plan_as_dict_without_gaps(self):
        plan = {"storyboard_id": "SB-001", "shot_plans": [], "gaps": []}
        state = {"asset_plans": [plan]}
        assert route_after_asset_sourcing(state) == "editing_node"  # type: ignore[arg-type]


# ── route_after_editing ──

class TestRouteAfterEditing:
    def test_audit_auto_approve_goes_to_audio(self):
        state = {"audit_reports": {"edit": make_audit_report(0.95)}}
        assert route_after_editing(state) == "audio_node"  # type: ignore[arg-type]

    def test_audit_auto_reject_goes_to_end(self):
        state = {"audit_reports": {"edit": make_audit_report(0.30)}}
        assert route_after_editing(state) == "__end__"  # type: ignore[arg-type]

    def test_human_approval_goes_to_audio(self):
        state = {
            "audit_reports": {"edit": make_audit_report(0.75)},
            "human_reviews": {"edit_review": make_human_review(ApprovalStatus.APPROVED, "edit_review")},
        }
        assert route_after_editing(state) == "audio_node"  # type: ignore[arg-type]

    def test_human_changes_requested_stays_at_editing(self):
        state = {
            "audit_reports": {"edit": make_audit_report(0.75)},
            "human_reviews": {"edit_review": {"status": "changes_requested"}},
        }
        assert route_after_editing(state) == "editing_node"  # type: ignore[arg-type]


# ── route_after_thumbnail ──

class TestRouteAfterThumbnail:
    def test_audit_auto_approve_goes_to_distribution(self):
        state = {"audit_reports": {"thumbnail": make_audit_report(0.95)}}
        assert route_after_thumbnail(state) == "distribution_node"  # type: ignore[arg-type]

    def test_audit_auto_reject_goes_to_end(self):
        state = {"audit_reports": {"thumbnail": make_audit_report(0.30)}}
        assert route_after_thumbnail(state) == "__end__"  # type: ignore[arg-type]

    def test_human_approval_goes_to_distribution(self):
        state = {
            "audit_reports": {"thumbnail": make_audit_report(0.75)},
            "human_reviews": {"thumbnail_review": make_human_review(ApprovalStatus.APPROVED, "thumbnail_review")},
        }
        assert route_after_thumbnail(state) == "distribution_node"  # type: ignore[arg-type]

    def test_human_changes_requested_stays_at_thumbnail(self):
        state = {
            "audit_reports": {"thumbnail": make_audit_report(0.75)},
            "human_reviews": {"thumbnail_review": {"status": "changes_requested"}},
        }
        assert route_after_thumbnail(state) == "thumbnail_node"  # type: ignore[arg-type]
