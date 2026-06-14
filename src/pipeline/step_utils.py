"""Shared step utility functions — used across pipeline modules and routers.

Canonical implementations of common helpers that were previously duplicated
across s1_product_pipeline.py, s3_remix_pipeline.py, s4_live_shoot_pipeline.py,
s5_brand_vlog_pipeline.py, step_runner.py, gate_manager.py, and routers/_state.py.

Ref: debt-audit-report-2026-06-09.md items D1
"""

from __future__ import annotations

from typing import Any


def get_step_output(steps: dict[str, Any], step_name: str) -> Any:
    """Retrieve output from a step, preferring edited_output if edited.

    This is the canonical implementation. Previously duplicated across
    5 pipeline modules + routers/_state.py + gate_manager.py + step_runner.py.
    """
    step_data = steps.get(step_name, {})
    if step_data.get("edited") and step_data.get("edited_output") is not None:
        return step_data["edited_output"]
    return step_data.get("output")


def get_step_output_from_state(state: dict[str, Any], step_name: str) -> Any:
    """Convenience wrapper that reads ``state["steps"]`` first.

    Use this when the caller already has the full pipeline state dict
    rather than just the ``steps`` sub-dict.
    """
    return get_step_output(state.get("steps", {}), step_name)
