"""Partial-artifact summarizer for degraded pipeline runs (Sprint 3 P3-3).

Closes diagnostic R-DEGRADE-L2: when a step (typically assemble_final)
fails, the pipeline already records errors and may set pipeline_degraded,
but the final result dict surfaces only zero-valued fields (e.g.
final_video_path=""). Callers (UI, downstream automation, retry logic)
have no clean way to ask "what artifacts are usable from this run?".

This module provides ``summarize_partial_artifacts(final_state)`` —
a pure inspector that scans completed steps and returns a structured
summary suitable for surfacing in the API response or telemetry.

Design contract:
- INPUT: a final_state dict (post-runner.resume) with steps[*].status,
  steps[*].output, errors, pipeline_degraded, degraded_reason fields.
- OUTPUT: dict with keys (all optional except `degraded`):
    degraded: bool — True iff any step failed or pipeline_degraded is set
    degraded_reason: str | None — the step name that triggered degradation
    available_artifacts: dict[str, Any] — usable outputs by step name
    missing_artifacts: list[str] — step names that produced no output
    error_summary: list[str] — human-readable error messages
- PURE: no I/O, no LLM, no logging. Safe to call repeatedly.

Usage in pipeline.run():
    final_state = await runner.resume(label)
    partial = summarize_partial_artifacts(final_state)
    if partial["degraded"]:
        result["partial_artifacts"] = partial
"""

from __future__ import annotations

from typing import Any

# Steps whose successful output is a "deliverable" the user / downstream
# might still want even when assemble_final failed. Order = surface priority.
_DELIVERABLE_STEPS: tuple[str, ...] = (
    "scripts",
    "storyboards",
    "keyframe_images",
    "video_prompts",
    "thumbnail_prompts",
    "thumbnail_images",
    "seedance_clips",
    "tts_audio",
    "assemble_final",
    "audit",
)


def _step_has_output(step_data: dict[str, Any]) -> bool:
    """A step counts as 'producing artifacts' if it ran AND has non-empty output.

    Empty / placeholder outputs (S1 assemble_final returns ("", "") on failure,
    a tuple of empty strings) are treated as missing — they look like
    'success' but carry nothing usable. We check both empty-collection and
    all-empty-string-elements cases.

    P4-5 (TODO-13, 2026-05-15): seedance_clips with all-stub clips also count
    as missing. The skill returns success=True with is_stub=True per clip
    when API fails / mock mode, so dict non-empty alone isn't enough.
    """
    if not step_data:
        return False
    if step_data.get("status") not in ("done", "completed"):
        return False
    output = step_data.get("edited_output") if step_data.get("edited") else step_data.get("output")
    if output is None:
        return False
    if isinstance(output, str) and not output.strip():
        return False
    if isinstance(output, (list, dict)) and not output:
        return False
    if isinstance(output, tuple):
        if not output:
            return False
        if all(isinstance(v, str) and not v.strip() for v in output):
            return False
    if isinstance(output, dict) and "clip_details" in output:
        clip_details = output.get("clip_details") or []
        if clip_details and all(
            isinstance(d, dict) and d.get("is_stub", False) for d in clip_details
        ):
            return False
    return True


def summarize_partial_artifacts(final_state: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize what's usable from a (possibly degraded) pipeline run.

    Returns a dict with `degraded`, `degraded_reason`, `available_artifacts`,
    `missing_artifacts`, `error_summary`. Always callable — None / empty
    state → degraded=True with empty available, all deliverable steps in
    missing.
    """
    if not final_state:
        return {
            "degraded": True,
            "degraded_reason": "no_state",
            "available_artifacts": {},
            "missing_artifacts": list(_DELIVERABLE_STEPS),
            "error_summary": ["Pipeline state was not produced or is None."],
        }

    steps = final_state.get("steps", {}) or {}
    errors = final_state.get("errors", []) or []
    pipeline_degraded = bool(final_state.get("pipeline_degraded"))
    degraded_reason = final_state.get("degraded_reason")

    available: dict[str, Any] = {}
    missing: list[str] = []
    for step_name in _DELIVERABLE_STEPS:
        step_data = steps.get(step_name, {})
        if _step_has_output(step_data):
            output = step_data.get("edited_output") if step_data.get("edited") else step_data.get("output")
            available[step_name] = output
        else:
            missing.append(step_name)

    # Detect implicit degradation: assemble_final completed but emitted no
    # video_path. This is S1's current contract on failure (returns
    # ("", "") rather than raising), so we surface it as degradation even
    # when pipeline_degraded was never set.
    implicit_degraded = (
        not pipeline_degraded
        and "assemble_final" not in available
        and any(s in available for s in ("seedance_clips", "tts_audio"))
    )
    degraded = pipeline_degraded or implicit_degraded
    if implicit_degraded and not degraded_reason:
        degraded_reason = "assemble_final_empty_output"

    return {
        "degraded": degraded,
        "degraded_reason": degraded_reason,
        "available_artifacts": available,
        "missing_artifacts": missing,
        "error_summary": list(errors),
    }
