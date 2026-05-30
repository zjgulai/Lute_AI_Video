"""State editing support for the step-by-step pipeline.

Provides functions to:
- `invalidate_downstream(label, step_name)` — marks all steps after step_name as "pending"
- `update_step_output(label, step_name, updates)` — deep-merges updates into step data

Both work with the dual-write persistence (filesystem + PG).
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime
from typing import Any

from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.state_manager import PipelineStateManager

logger = logging.getLogger(__name__)

# Backward-compatible default for callers/tests that still read this module-level
# constant directly. Real invalidation now reads the persisted state's scenario.
STEP_ORDER = get_scenario_step_order("s1")


def _get_step_order(scenario: str) -> list[str]:
    """Return the canonical step order for a scenario."""
    return get_scenario_step_order(scenario)


def _get_downstream_steps(step_name: str, scenario: str) -> list[str]:
    """Return all step names after the given step in the pipeline order."""
    order = _get_step_order(scenario)
    try:
        idx = order.index(step_name)
        return order[idx + 1:]
    except ValueError:
        raise ValueError(f"Unknown step name: {step_name}")


async def invalidate_downstream(
    label: str,
    step_name: str,
    state_manager: PipelineStateManager | None = None,
) -> dict[str, Any]:
    """Mark all steps after step_name as 'pending' (invalidates downstream).

    This is called when a step is regenerated — downstream steps need to be
    re-executed because their inputs may have changed.

    Args:
        label: Pipeline run label.
        step_name: The step that was regenerated. Steps after this are invalidated.
        state_manager: Optional PipelineStateManager instance. Creates one if not provided.

    Returns:
        The updated state dict.

    Raises:
        ValueError: If state is not found for the given label.
    """
    if state_manager is None:
        state_manager = PipelineStateManager()

    state = await state_manager.load(label)
    if state is None:
        raise ValueError(f"State not found for label: {label}")

    scenario = state.get("scenario", "s1")
    steps = state.get("steps", {})
    downstream = _get_downstream_steps(step_name, scenario)

    for ds in downstream:
        if ds in steps:
            steps[ds] = {
                "status": "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
                "started_at": "",
                "completed_at": "",
                "invalidated_by": step_name,
            }
        else:
            steps[ds] = {
                "status": "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
                "started_at": "",
                "completed_at": "",
                "invalidated_by": step_name,
            }

    # Advance current_step if it was one of the invalidated steps
    current = state.get("current_step")
    if current and current in downstream:
        # Find the first pending step to be the new current_step
        for s in _get_step_order(scenario):
            sd = steps.get(s, {})
            if sd.get("status") == "pending":
                state["current_step"] = s
                break
        else:
            state["current_step"] = None

    state["steps"] = steps
    await state_manager.save(label, state)
    logger.info(
        "step_editor: invalidated downstream %s %s: %s",
        label,
        step_name,
        downstream,
    )
    return state


async def update_step_output(
    label: str,
    step_name: str,
    updates: Any,
    state_manager: PipelineStateManager | None = None,
) -> dict[str, Any]:
    """Deep-merge updates into a step's output data.

    Sets `edited=True` and stores the merged result in `edited_output`.
    The original `output` is preserved for reference.

    Args:
        label: Pipeline run label.
        step_name: The step to update.
        updates: The new data to merge into the step output. Can be any JSON-serializable value.
        state_manager: Optional PipelineStateManager instance.

    Returns:
        The updated state dict.

    Raises:
        ValueError: If state or step is not found.
    """
    if state_manager is None:
        state_manager = PipelineStateManager()

    state = await state_manager.load(label)
    if state is None:
        raise ValueError(f"State not found for label: {label}")

    steps = state.get("steps", {})
    if step_name not in steps:
        raise ValueError(f"Step not found: {step_name}")

    step_data = steps[step_name]

    # If step was never run, initialize output
    if step_data.get("output") is None:
        step_data["output"] = updates
        step_data["status"] = "done"
        step_data["completed_at"] = datetime.now().isoformat()
        step_data["started_at"] = step_data.get("started_at") or datetime.now().isoformat()

    # Deep-merge updates into the current best output
    current_best = step_data.get("output")
    if current_best is None:
        merged = copy.deepcopy(updates)
    elif isinstance(current_best, dict) and isinstance(updates, dict):
        merged = copy.deepcopy(current_best)
        _deep_merge(merged, updates)
    else:
        # For non-dict types, just replace entirely
        merged = copy.deepcopy(updates)

    step_data["edited_output"] = merged
    step_data["edited"] = True
    step_data["completed_at"] = datetime.now().isoformat()

    steps[step_name] = step_data
    state["steps"] = steps
    await state_manager.save(label, state)

    logger.info(
        "step_editor: updated step output %s %s",
        label,
        step_name,
    )
    return state


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> None:
    """Recursively merge updates into base dict (in-place)."""
    for key, value in updates.items():
        if isinstance(value, dict) and key in base and isinstance(base[key], dict):
            _deep_merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
