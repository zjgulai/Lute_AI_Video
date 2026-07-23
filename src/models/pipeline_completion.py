"""Pure derivation for one durable pipeline-completion metric outcome."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, TypedDict


class PipelineCompletionFacts(TypedDict):
    """Semantic fields that must come from the current durable terminal state."""

    outcome: Literal["success", "failure"]
    error_count: int
    scenario: str


def derive_pipeline_completion_facts(
    state: Mapping[str, Any],
) -> PipelineCompletionFacts | None:
    """Return metric facts for a terminal state, otherwise ``None``."""

    lifecycle_status = state.get("lifecycle_status")
    degraded = state.get("pipeline_degraded") is True
    terminal_success = (
        lifecycle_status in {"completed_bounded", "completed_full"}
        and state.get("current_step") is None
        and not degraded
    )
    terminal_failure = degraded or lifecycle_status == "policy_blocked"
    if not terminal_success and not terminal_failure:
        return None

    errors = state.get("errors")
    error_count = len(errors) if type(errors) is list else 1
    success = terminal_success and error_count == 0
    scenario = state.get("scenario")
    if type(scenario) is not str or not scenario:
        scenario = "unknown"
    return {
        "outcome": "success" if success else "failure",
        "error_count": error_count,
        "scenario": scenario,
    }


def bind_claim_to_facts(
    proposed_claim: Mapping[str, Any],
    facts: PipelineCompletionFacts,
) -> dict[str, Any]:
    """Replace every semantic claim field with current durable facts."""

    claim = dict(proposed_claim)
    claim.update(facts)
    return claim
