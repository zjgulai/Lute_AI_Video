"""Scenario-aware model routing for S1-S5 video pipelines.

Decision D (2026-05-13) constrains model selection to poyo.ai's catalog. This
module provides a single entry point — `select_model(scenario)` — that maps
scenario IDs to a (preferred, fallback, budget) chain plus a `next_model()`
helper for downstream degradation when a tier rejects or fails.

Design contract:
- `select_model(scenario)` returns the preferred model ID for the scenario's
  default tier ("preferred").
- `get_chain(scenario)` returns the full ModelChain (3-tier list).
- `next_model(scenario, current)` returns the next tier model after `current`,
  or None if `current` is already at the budget end of the chain.

Scenario chains mirror the per-scenario matrix in
``docs/architecture/poyo-model-matrix-stable.md`` §三, so updating the chain
here MUST be paired with a doc update + a `model_thresholds.py` review (every
chain entry needs a threshold).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.model_thresholds import _MODEL_THRESHOLDS

ScenarioId = str
ModelId = str

_DEFAULT_SCENARIO = "s1"


@dataclass(frozen=True)
class ModelChain:
    """Three-tier degradation chain for a given scenario."""

    preferred: ModelId
    fallback: ModelId
    budget: ModelId

    def as_list(self) -> list[ModelId]:
        return [self.preferred, self.fallback, self.budget]

    def next_after(self, current: ModelId) -> ModelId | None:
        """Return the next-tier model after `current`, or None at chain end."""
        chain = self.as_list()
        try:
            idx = chain.index(current)
        except ValueError:
            return self.preferred
        return chain[idx + 1] if idx + 1 < len(chain) else None


# Per-scenario model chains. Aligned with:
# - docs/architecture/poyo-model-matrix-stable.md §三
# - docs/workflows/2026-05-14-poyo-constrained-optimization-roadmap.md §三
_SCENARIO_CHAINS: dict[ScenarioId, ModelChain] = {
    "s1": ModelChain(
        preferred="seedance-2",
        fallback="kling-3-0/pro",
        budget="wan-2-7-video",
    ),
    "s2": ModelChain(
        preferred="kling-3-0/pro",
        fallback="runway-gen-4-5",
        budget="wan-2-7-video",
    ),
    "s3": ModelChain(
        preferred="kling-3-0/standard",
        fallback="seedance-2",
        budget="wan-2-6",
    ),
    "s4": ModelChain(
        preferred="seedance-2-fast",
        fallback="kling-2-5-turbo-pro",
        budget="wan-2-2-fast",
    ),
    "s5": ModelChain(
        preferred="seedance-2",
        fallback="kling-3-0/pro",
        budget="wan-2-7-video",
    ),
}


def get_chain(scenario: ScenarioId) -> ModelChain:
    """Return the full ModelChain for `scenario`. Falls back to S1 if unknown."""
    return _SCENARIO_CHAINS.get(scenario.lower(), _SCENARIO_CHAINS[_DEFAULT_SCENARIO])


def select_model(scenario: ScenarioId) -> ModelId:
    """Resolve the preferred model ID for `scenario`."""
    return get_chain(scenario).preferred


def next_model(scenario: ScenarioId, current: ModelId) -> ModelId | None:
    """Return next-tier model in `scenario`'s chain after `current`.

    Returns None when `current` is already the budget tier (no further
    degradation possible — caller should halt or surface to user).
    """
    return get_chain(scenario).next_after(current)


def all_scenarios() -> list[ScenarioId]:
    """Return supported scenario IDs."""
    return list(_SCENARIO_CHAINS.keys())


def validate_chains() -> list[str]:
    """Return list of chain entries missing a threshold in model_thresholds.

    Run at import time of this module's tests; returns empty list when every
    model in every chain is registered in `_MODEL_THRESHOLDS`. Useful as an
    SSOT enforcement check.
    """
    missing: list[str] = []
    for scenario, chain in _SCENARIO_CHAINS.items():
        for tier_name, model_id in (
            ("preferred", chain.preferred),
            ("fallback", chain.fallback),
            ("budget", chain.budget),
        ):
            if model_id not in _MODEL_THRESHOLDS:
                missing.append(f"{scenario}.{tier_name}={model_id}")
    return missing
