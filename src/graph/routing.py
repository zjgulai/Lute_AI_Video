"""Conditional routing functions for the pipeline graph.

Each function inspects state and returns the next node name.
Handles both Pydantic models and dict forms (LangGraph serializes to dicts).

Retry limit: if a node has been re-executed >= MAX_RETRIES times,
CHANGES_REQUESTED is treated as APPROVED to prevent infinite loops.
"""

from __future__ import annotations

import contextvars
from typing import Any

import structlog

from src.models.state import VideoPipelineState

MAX_RETRIES = 3
logger = structlog.get_logger()

# D10: Per-request override for human review decisions.
# LangGraph's checkpoint recovery does not preserve update_state across
# the astream boundary in interrupt_after resume scenarios, so the routing
# function cannot read newly-written human_reviews from state.
# This override is set by submit_review (api.py) before astream resume,
# and read by routing functions here.
#
# Using contextvars.ContextVar instead of a plain module-level dict ensures
# that concurrent pipeline runs (multiple asyncio tasks) are isolated from
# each other — each task gets its own copy of the override map.
_HUMAN_REVIEW_OVERRIDE: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "human_review_override", default={}
)
# ^ Keyed by checkpoint key ("strategy"/"script"/"edit"/"thumbnail"), value = {"node_key": ..., "status": ...}


def _get_override(checkpoint_key: str) -> dict[str, Any] | None:
    """Read the D10 routing override for a checkpoint (thread-safe)."""
    return _HUMAN_REVIEW_OVERRIDE.get().get(checkpoint_key)


def _set_override(checkpoint_key: str, value: dict[str, Any]) -> None:
    """Set the D10 routing override for a checkpoint (thread-safe)."""
    current = dict(_HUMAN_REVIEW_OVERRIDE.get())
    current[checkpoint_key] = value
    _HUMAN_REVIEW_OVERRIDE.set(current)


def _pop_override(checkpoint_key: str) -> None:
    """Remove the D10 routing override for a checkpoint (thread-safe)."""
    current = dict(_HUMAN_REVIEW_OVERRIDE.get())
    current.pop(checkpoint_key, None)
    _HUMAN_REVIEW_OVERRIDE.set(current)

# -- Audit-driven decision thresholds (defaults) --
# Per-checkpoint thresholds can be overridden by strategy_source/<scenario>/quality_thresholds.json
# Score > threshold: skip human review, auto-approve
# Score < threshold: shut down pipeline, auto-reject
AUTO_APPROVE_THRESHOLD = 0.90
AUTO_REJECT_THRESHOLD = 0.60


def _get_approval_status(review) -> str | None:
    """Extract approval status from either dict or Pydantic model."""
    if review is None:
        return None
    if hasattr(review, "status"):
        return review.status.value if hasattr(review.status, "value") else str(review.status)
    if isinstance(review, dict):
        return review.get("status")
    return None


def _retry_guard(state: VideoPipelineState, node_key: str) -> str | None:
    """Check if a node has exhausted retries.

    Returns the overridden status ('approved') if retries exceeded,
    None otherwise so the caller falls through to normal routing.
    """
    retry_counts = state.get("retry_counts", {})
    count = retry_counts.get(node_key, 0)
    if count >= MAX_RETRIES:
        return "approved"
    return None


def _audit_guard(state: VideoPipelineState, checkpoint_key: str) -> str | None:
    """Check audit score for automatic decisions.

    Uses scenario-specific thresholds from state['content_scenario'].
    Falls back to global (0.90/0.60) if scenario config not available.

    If the audit report exists and has a score:
      - score > auto_approve_threshold: return 'approved' (skip human review)
      - score < auto_reject_threshold: return 'rejected' (shut down pipeline)

    Otherwise returns None (fall through to normal human review).
    """
    reports = state.get("audit_reports", {})
    report = reports.get(checkpoint_key)
    if report is None:
        return None

    # Determine thresholds — try scenario config first, fall back to globals
    auto_approve = AUTO_APPROVE_THRESHOLD
    auto_reject = AUTO_REJECT_THRESHOLD
    scenario = state.get("content_scenario", "general")
    if scenario != "general":
        try:
            from strategy_source import load_scenario
            cfg = load_scenario(scenario)
            thresholds = cfg.get("quality_thresholds", {}).get(checkpoint_key, {})
            if thresholds:
                auto_approve = thresholds.get("auto_approve", auto_approve)
                auto_reject = thresholds.get("auto_reject", auto_reject)
        except Exception as exc:
            logger.warning(
                "routing: scenario threshold load failed",
                scenario=scenario,
                checkpoint=checkpoint_key,
                error=str(exc)[:200],
            )

    # Handle both Pydantic model and dict form
    if hasattr(report, "overall_score"):
        score = report.overall_score
    elif isinstance(report, dict):
        score = report.get("overall_score", 0.5)
    else:
        return None

    if score > auto_approve:
        return "approved"
    if score < auto_reject:
        return "rejected"

    # Middle ground: needs human review
    return None


def _degraded_guard(state: VideoPipelineState) -> str | None:
    """P0-2: If any upstream node failed, terminate the pipeline immediately.

    Returns '__end__' if pipeline_degraded is set, None otherwise.
    Must be checked FIRST in every routing function before any other logic.
    """
    if state.get("pipeline_degraded"):
        return "__end__"
    return None


def _get_compliance_status(report) -> str | None:
    """Extract compliance status from either dict or Pydantic model."""
    if report is None:
        return None
    if hasattr(report, "status"):
        return report.status.value if hasattr(report.status, "value") else str(report.status)
    if isinstance(report, dict):
        return report.get("status")
    return None


def route_after_strategy(state: VideoPipelineState) -> str:
    """After strategy produces briefs: human review FIRST, then audit.

    Priority order:
      0. Degraded guard: upstream node failed -> terminate
      1. Human review: explicit rejection or changes-requested overrides auto-approve
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
      4. Default: re-loop to strategy_node
    """
    # P0-2: Terminate if any upstream node failed
    degraded = _degraded_guard(state)
    if degraded:
        return degraded

    # D10: Check global routing override first (bypasses checkpoint recovery issue)
    d10_override = _get_override("strategy")
    if d10_override:
        user_status = d10_override.get("status", "")
        if user_status == "approved":
            _pop_override("strategy")
            return "script_node"
        elif user_status == "rejected":
            _pop_override("strategy")
            return "__end__"
        elif user_status == "changes_requested":
            _pop_override("strategy")
            return "strategy_node"

    # Check human review FIRST -- explicit user action overrides auto decisions
    review = state.get("human_reviews", {}).get("strategy_review")
    override = _retry_guard(state, "strategy")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "script_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "strategy_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "strategy")
    if audit_verdict == "approved":
        return "script_node"
    if audit_verdict == "rejected":
        return "__end__"

    # Middle ground: needs human review
    return "strategy_node"


def route_after_script(state: VideoPipelineState) -> str:
    """After script: human review FIRST, then audit.

    Priority order:
      0. Degraded guard: upstream node failed -> terminate
      1. Global routing override (D10)
      2. Human review: explicit user action overrides auto decisions
      3. Retry guard: exhausted retries -> force-approve
      4. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
    """
    # P0-2: Terminate if any upstream node failed
    degraded = _degraded_guard(state)
    if degraded:
        return degraded

    # D10: Check global routing override first
    d10_override = _get_override("script")
    if d10_override:
        user_status = d10_override.get("status", "")
        if user_status == "approved":
            _pop_override("script")
            return "compliance_node"
        elif user_status == "rejected":
            _pop_override("script")
            return "__end__"
        elif user_status == "changes_requested":
            _pop_override("script")
            return "script_node"

    # Check human review FIRST
    review = state.get("human_reviews", {}).get("script_review")
    override = _retry_guard(state, "script")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "compliance_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "script_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "script")
    if audit_verdict == "approved":
        return "compliance_node"
    if audit_verdict == "rejected":
        return "__end__"

    return "script_node"


def route_after_compliance(state: VideoPipelineState) -> str:
    """Check compliance results: proceed or halt."""
    # P0-2: Terminate if any upstream node failed
    degraded = _degraded_guard(state)
    if degraded:
        return degraded

    reports = state.get("compliance_reports", [])
    if not reports:
        return "storyboard_node"

    blocked = any(_get_compliance_status(r) == "BLOCKED" for r in reports)
    if blocked:
        return "__end__"

    return "storyboard_node"


def route_after_asset_sourcing(state: VideoPipelineState) -> str:
    """If gaps exist -> AI generation, else skip to editing."""
    # P0-2: Terminate if any upstream node failed
    degraded = _degraded_guard(state)
    if degraded:
        return degraded

    asset_plans = state.get("asset_plans", [])
    has_gaps = False
    for plan in asset_plans:
        gaps = plan.gaps if hasattr(plan, "gaps") else plan.get("gaps", [])  # type: ignore[attr-defined]
        if gaps:
            has_gaps = True
            break
    if has_gaps:
        return "media_generation_node"
    return "editing_node"


def route_after_editing(state: VideoPipelineState) -> str:
    """After editing: human review FIRST, then audit.

    Priority order:
      0. Degraded guard: upstream node failed -> terminate
      1. Human review: explicit user action overrides auto decisions
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
    """
    # P0-2: Terminate if any upstream node failed
    degraded = _degraded_guard(state)
    if degraded:
        return degraded

    # D10: Check global routing override first
    d10_override = _get_override("edit")
    if d10_override:
        user_status = d10_override.get("status", "")
        if user_status == "approved":
            _pop_override("edit")
            return "audio_node"
        elif user_status == "rejected":
            _pop_override("edit")
            return "__end__"
        elif user_status == "changes_requested":
            _pop_override("edit")
            return "editing_node"

    # Check human review FIRST
    review = state.get("human_reviews", {}).get("edit_review")
    override = _retry_guard(state, "edit")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "audio_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "editing_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "edit")
    if audit_verdict == "approved":
        return "audio_node"
    if audit_verdict == "rejected":
        return "__end__"

    return "editing_node"


def route_after_thumbnail(state: VideoPipelineState) -> str:
    """After thumbnails: human review FIRST, then audit.

    Priority order:
      0. Degraded guard: upstream node failed -> terminate
      1. Human review: explicit user action overrides auto decisions
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
    """
    # P0-2: Terminate if any upstream node failed
    degraded = _degraded_guard(state)
    if degraded:
        return degraded

    # D10: Check global routing override first
    d10_override = _get_override("thumbnail")
    if d10_override:
        user_status = d10_override.get("status", "")
        if user_status == "approved":
            _pop_override("thumbnail")
            return "distribution_node"
        elif user_status == "rejected":
            _pop_override("thumbnail")
            return "__end__"
        elif user_status == "changes_requested":
            _pop_override("thumbnail")
            return "thumbnail_node"

    # Check human review FIRST
    review = state.get("human_reviews", {}).get("thumbnail_review")
    override = _retry_guard(state, "thumbnail")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "distribution_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "thumbnail_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "thumbnail")
    if audit_verdict == "approved":
        return "distribution_node"
    if audit_verdict == "rejected":
        return "__end__"

    return "thumbnail_node"
