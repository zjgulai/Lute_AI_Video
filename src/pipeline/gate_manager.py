"""Gate state management for Expert Studio approval workflow.

Expert Studio mode lets users approve or reject at 4 Gate points during
pipeline execution. Each gate generates 3 candidate outputs with different
variants (standard/creative/conservative), scores them via AI, and lets the
user select 1-2 candidates to continue.

Gate 1: Select Script   (after scripts step)
Gate 2: Review Frames   (after keyframe_images step)
Gate 3: Select Clips    (after seedance_clips step)
Gate 4: Final Review     (after assemble_final step)
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any, Literal

import structlog

from src.pipeline.candidate_scorer import score_candidate
from src.pipeline.state_manager import PipelineStateManager
from src.skills.registry import SkillRegistry
from src.config import DEFAULT_LANGUAGES

logger = structlog.get_logger()

# ── Gate Definitions (per-scenario) ──

VariantType = Literal["standard", "creative", "conservative"]

# S1 / S2 share the same gate definitions
_S1_GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gate_1_script": {
        "after_step": "scripts",
        "label": "Select Script",
        "candidate_step": "scripts",
        "max_selections": 2,
    },
    "gate_2_keyframe": {
        "after_step": "keyframe_images",
        "label": "Review Keyframes",
        "candidate_step": "keyframe_images",
        "max_selections": 1,
    },
    "gate_3_clips": {
        "after_step": "seedance_clips",
        "label": "Select Clips",
        "candidate_step": "seedance_clips",
        "max_selections": 1,
    },
    "gate_4_final": {
        "after_step": "assemble_final",
        "label": "Final Review",
        "candidate_step": None,
        "max_selections": 1,
    },
}

# S3: Influencer Remix — remix_script replaces scripts
_S3_GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gate_1_script": {
        "after_step": "remix_script",
        "label": "Select Remix Script",
        "candidate_step": "remix_script",
        "max_selections": 2,
    },
    "gate_2_keyframe": {
        "after_step": "keyframe_images",
        "label": "Review Keyframes",
        "candidate_step": "keyframe_images",
        "max_selections": 1,
    },
    "gate_3_clips": {
        "after_step": "seedance_clips",
        "label": "Select Clips",
        "candidate_step": "seedance_clips",
        "max_selections": 1,
    },
    "gate_4_final": {
        "after_step": "assemble_final",
        "label": "Final Review",
        "candidate_step": None,
        "max_selections": 1,
    },
}

# S4: Live Shoot — scripts, video_prompts, thumbnails
_S4_GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gate_1_script": {
        "after_step": "scripts",
        "label": "Select Script",
        "candidate_step": "scripts",
        "max_selections": 2,
    },
    "gate_2_prompts": {
        "after_step": "video_prompts",
        "label": "Review Video Prompts",
        "candidate_step": "video_prompts",
        "max_selections": 1,
    },
    "gate_3_thumbnails": {
        "after_step": "thumbnails",
        "label": "Review Thumbnails",
        "candidate_step": None,
        "max_selections": 1,
    },
}

# S5: Brand VLOG — vlog_strategy, seedance_clips, assemble_final
_S5_GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "gate_1_strategy": {
        "after_step": "vlog_strategy",
        "label": "Select Strategy",
        "candidate_step": "vlog_strategy",
        "max_selections": 2,
    },
    "gate_2_clips": {
        "after_step": "seedance_clips",
        "label": "Select Clips",
        "candidate_step": "seedance_clips",
        "max_selections": 1,
    },
    "gate_3_final": {
        "after_step": "assemble_final",
        "label": "Final Review",
        "candidate_step": None,
        "max_selections": 1,
    },
}

SCENARIO_GATE_DEFINITIONS: dict[str, dict[str, dict[str, Any]]] = {
    "s1": _S1_GATE_DEFINITIONS,
    "s2": _S1_GATE_DEFINITIONS,  # S2 is S1 with brand_mode=True
    "s3": _S3_GATE_DEFINITIONS,
    "s4": _S4_GATE_DEFINITIONS,
    "s5": _S5_GATE_DEFINITIONS,
}

# Backward-compatible alias — used by step_runner.py
GATE_DEFINITIONS = _S1_GATE_DEFINITIONS

# Step name -> SkillRegistry skill name mapping
STEP_TO_SKILL_NAME: dict[str, str | None] = {
    "scripts": "script-writer-skill",
    "keyframe_images": "keyframe-images",
    "seedance_clips": "seedance-video-generate-skill",
    "assemble_final": None,
    "remix_script": "remix-script-skill",
    "vlog_strategy": "product-strategy-skill",
    "video_prompts": None,
    "thumbnails": None,
}

# Per-scenario step orders — must match step_runner.py _SCENARIO_CONFIGS
SCENARIO_STEP_ORDERS: dict[str, list[str]] = {
    "s1": [
        "strategy", "scripts", "compliance", "storyboards", "keyframe_images",
        "video_prompts", "thumbnail_prompts", "seedance_clips", "tts_audio",
        "thumbnail_images", "assemble_final", "audit",
    ],
    "s2": [
        "strategy", "scripts", "compliance", "storyboards", "keyframe_images",
        "video_prompts", "thumbnail_prompts", "seedance_clips", "tts_audio",
        "thumbnail_images", "assemble_final", "audit",
    ],
    "s3": [
        "video_analysis", "character_identity", "remix_script", "storyboards",
        "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips",
        "tts_audio", "thumbnail_images", "assemble_final", "audit",
    ],
    "s4": ["scripts", "video_prompts", "thumbnails"],
    "s5": [
        "vlog_strategy", "video_prompts", "seedance_clips", "tts_audio",
        "assemble_final", "audit",
    ],
}

# Backward-compatible alias
STEP_ORDER = SCENARIO_STEP_ORDERS["s1"]


def _get_scenario_from_state(state: dict[str, Any]) -> str:
    """Extract scenario from pipeline state, defaulting to s1."""
    return state.get("scenario", "s1")


def _get_gate_defs(scenario: str) -> dict[str, dict[str, Any]]:
    """Return gate definitions for a scenario, falling back to s1."""
    return SCENARIO_GATE_DEFINITIONS.get(scenario, _S1_GATE_DEFINITIONS)


def _get_step_order(scenario: str) -> list[str]:
    """Return step order for a scenario, falling back to s1."""
    return SCENARIO_STEP_ORDERS.get(scenario, SCENARIO_STEP_ORDERS["s1"])


def _get_next_step(step_name: str, scenario: str = "s1") -> str | None:
    """Return the next step name after the given step, or None if last."""
    order = _get_step_order(scenario)
    try:
        idx = order.index(step_name)
        if idx + 1 < len(order):
            return order[idx + 1]
    except ValueError:
        pass
    return None


async def get_gate_state(label: str, gate_id: str) -> dict[str, Any]:
    """Get the current state of a specific gate.

    Args:
        label: Pipeline run label.
        gate_id: One of the GATE_DEFINITIONS keys.

    Returns:
        dict with gate state information, or a 404-like error dict.
    """
    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

    scenario = _get_scenario_from_state(state)
    gate_defs = _get_gate_defs(scenario)
    definition = gate_defs.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id} for scenario {scenario}", "gate_id": gate_id, "scenario": scenario}

    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

    gates_state = state.get("gates", {})
    gate_state = gates_state.get(gate_id, {})

    return {
        "gate_id": gate_id,
        "label": definition["label"],
        "status": gate_state.get("status", "awaiting_candidates"),
        "candidates": gate_state.get("candidates", []),
        "selected_ids": gate_state.get("selected_ids", []),
        "approved": gate_state.get("approved", False),
        "max_selections": definition["max_selections"],
        "after_step": definition["after_step"],
    }


async def generate_candidates(label: str, gate_id: str) -> dict[str, Any]:
    """Generate 3 candidate outputs for a gate's candidate_step.

    For each variant (standard, creative, conservative), calls the
    SkillRegistry to generate a candidate, scores it, and stores the
    results in pipeline state.

    Args:
        label: Pipeline run label.
        gate_id: One of the GATE_DEFINITIONS keys.

    Returns:
        dict with keys:
            candidates: list of candidate dicts with id, variant, data, score, recommended
            gate_id: str
            label: str
    """
    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

    scenario = _get_scenario_from_state(state)
    gate_defs = _get_gate_defs(scenario)
    definition = gate_defs.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id} for scenario {scenario}", "gate_id": gate_id, "scenario": scenario}

    candidate_step = definition.get("candidate_step")

    # ── Gate 4: Final Review — no skill generation, assemble from state ──
    if gate_id == "gate_4_final":
        steps_data = state.get("steps", {})
        assemble_out = steps_data.get("assemble_final", {}).get("output")
        audit_out = steps_data.get("audit", {}).get("output") or {}
        thumbnail_out = steps_data.get("thumbnail_images", {}).get("output") or []
        seedance_out = steps_data.get("seedance_clips", {}).get("output") or {}

        video_path = ""
        if isinstance(assemble_out, (list, tuple)) and len(assemble_out) >= 1:
            video_path = assemble_out[0]
        elif isinstance(assemble_out, dict):
            video_path = assemble_out.get("video_path", "")

        total_duration = 0
        if isinstance(seedance_out, dict):
            total_duration = seedance_out.get("total_duration", 0)
        if not total_duration and isinstance(audit_out, dict):
            total_duration = audit_out.get("duration_seconds", 0)

        candidate = {
            "id": "gate_4_final_c0",
            "variant": "standard",
            "data": {
                "final_video_path": video_path,
                "audit_report": audit_out,
                "thumbnail_image_paths": thumbnail_out if isinstance(thumbnail_out, list) else [],
                "duration": total_duration,
            },
            "score": {
                "overall": 0.9,
                "explanation": "Final assembled video ready for review",
            },
            "recommended": True,
        }

        gates_state = dict(state.get("gates", {}))
        gates_state[gate_id] = {
            "status": "awaiting_approval",
            "candidates": [candidate],
            "selected_ids": [],
            "approved": False,
            "generated_at": datetime.now().isoformat(),
        }
        state["gates"] = gates_state
        await state_manager.save(label, state)

        return {
            "candidates": [candidate],
            "gate_id": gate_id,
            "label": label,
        }

    if candidate_step is None:
        return {"error": f"Gate {gate_id} has no candidate_step", "gate_id": gate_id}

    # Read the existing step output to use as context
    steps_data = state.get("steps", {})
    step_data = steps_data.get(candidate_step, {})
    step_output = step_data.get("output") or {}

    # Read strategy/context for scoring
    strategy_data = steps_data.get("strategy", {}).get("output") or {}
    usps = _extract_usps(strategy_data, state.get("config", {}))

    # Extract params for scoring
    scoring_params = {
        "usps": usps,
        "brand_guidelines": _extract_brand_guidelines(state.get("config", {})),
    }

    # Variant configurations
    variants: list[tuple[str, dict[str, Any]]] = [
        ("standard", {"temperature": 0.7, "variant": "standard"}),
        ("creative", {"temperature": 0.9, "variant": "creative"}),
        ("conservative", {"temperature": 0.5, "variant": "conservative"}),
    ]

    wanted_count = 3
    valid_candidates: list[dict[str, Any]] = []
    CANDIDATE_VARIANTS = [
        {"variant": "standard", "params": {"temperature": 0.7}},
        {"variant": "creative", "params": {"temperature": 0.9}},
        {"variant": "conservative", "params": {"temperature": 0.5}},
    ]

    for attempt in range(wanted_count + 1):  # +1 for retry on failure
        if len(valid_candidates) >= wanted_count:
            break

        variant = CANDIDATE_VARIANTS[len(valid_candidates) % 3]
        variant_name = variant["variant"]

        # Build skill-specific params for each candidate step
        skill_params = _build_skill_params(candidate_step, state, variant_name, variant["params"])

        try:
            skill_name = STEP_TO_SKILL_NAME.get(candidate_step, candidate_step)
            if skill_name is None:
                raise RuntimeError(f"Gate {gate_id} has no skill mapping for step: {candidate_step}")
            skill_result = await SkillRegistry().execute(skill_name, skill_params)
            if skill_result.success and skill_result.data:
                candidate_data = skill_result.data
                # Exclude error-only data
                if isinstance(candidate_data, dict) and "_error" in candidate_data:
                    if attempt < 3:  # retry once
                        continue
                    # After all retries exhausted, fall through to error handling
                    raise RuntimeError(str(candidate_data["_error"]))
            else:
                if attempt < 3:
                    continue
                raise RuntimeError("Skill execution returned no data")
        except Exception as exc:
            logger.warning(
                "gate_manager: candidate generation failed, retrying",
                attempt=attempt,
                gate_id=gate_id,
                variant=variant_name,
                error=str(exc),
            )
            if attempt >= 2:  # After all retries exhausted
                valid_candidates.append({
                    "id": f"{gate_id}_c{len(valid_candidates)}",
                    "variant": variant_name,
                    "data": {"content": f"Generation failed after retries: {str(exc)[:200]}"},
                    "score": {"overall": 0, "error": True},
                    "recommended": False,
                })
            continue

        # Score the candidate
        try:
            score_result = await score_candidate(
                step_name=candidate_step,
                candidate_data=candidate_data,
                params=scoring_params,
            )
        except Exception as exc:
            logger.warning(
                "gate_manager: scoring failed, using default",
                gate_id=gate_id,
                variant=variant_name,
                error=str(exc),
            )
            score_result = {
                "overall": 0.5,
                "breakdown": {},
                "explanation": "Scoring error, defaulted to 0.5",
                "heuristic": True,
            }

        valid_candidates.append({
            "id": f"{gate_id}_c{len(valid_candidates)}",
            "variant": variant_name,
            "data": candidate_data,
            "score": score_result,
            "recommended": False,
        })

    candidates = valid_candidates

    # Determine the recommended (highest-scoring) candidate
    if candidates:
        best = max(candidates, key=lambda c: c["score"].get("overall", 0))
        best["recommended"] = True

    # Store candidates in state under gates.{gate_id}.candidates
    gates_state = dict(state.get("gates", {}))
    gates_state[gate_id] = {
        "status": "awaiting_approval",
        "candidates": candidates,
        "selected_ids": [],
        "approved": False,
        "generated_at": datetime.now().isoformat(),
    }
    state["gates"] = gates_state
    await state_manager.save(label, state)

    best = None
    if candidates:
        best = max(candidates, key=lambda c: c.get("score", 0))

    logger.info(
        "gate_manager: candidates generated",
        gate_id=gate_id,
        label=label,
        candidate_count=len(candidates),
        recommended_id=best["id"] if best else None,
    )

    return {
        "candidates": candidates,
        "gate_id": gate_id,
        "label": label,
    }


async def approve_gate(label: str, gate_id: str, selected_ids: list[str]) -> dict[str, Any]:
    """Record gate approval and continue pipeline execution.

    Validates the selection, records the approved candidate IDs, marks the
    gate as approved, sets the selected candidate's output as the step output
    for downstream consumption, and advances the pipeline's current_step
    past the gate.

    Args:
        label: Pipeline run label.
        gate_id: One of the GATE_DEFINITIONS keys.
        selected_ids: List of candidate IDs the user selected.

    Returns:
        dict with approval result and updated state info.
    """
    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

    scenario = _get_scenario_from_state(state)
    gate_defs = _get_gate_defs(scenario)
    definition = gate_defs.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id} for scenario {scenario}", "gate_id": gate_id, "scenario": scenario}

    gates_state = dict(state.get("gates", {}))
    gate_state = gates_state.get(gate_id, {})

    # Verify gate is awaiting approval
    if gate_state.get("approved", False):
        return {
            "error": f"Gate {gate_id} is already approved",
            "gate_id": gate_id,
            "label": label,
            "approved": True,
        }

    if gate_state.get("status") != "awaiting_approval":
        return {
            "error": f"Gate {gate_id} is not awaiting approval (status={gate_state.get('status', 'unknown')})",
            "gate_id": gate_id,
            "label": label,
            "status": gate_state.get("status", "unknown"),
        }

    candidates = gate_state.get("candidates", [])
    candidate_map = {c["id"]: c for c in candidates}

    # Validate selected IDs
    invalid_ids = [cid for cid in selected_ids if cid not in candidate_map]
    if invalid_ids:
        return {
            "error": f"Invalid candidate IDs: {invalid_ids}",
            "gate_id": gate_id,
            "label": label,
        }

    max_sel = definition["max_selections"]
    if len(selected_ids) > max_sel:
        return {
            "error": f"Maximum {max_sel} selection(s) allowed for gate {gate_id}, got {len(selected_ids)}",
            "gate_id": gate_id,
            "label": label,
        }

    if len(selected_ids) < 1:
        return {
            "error": "At least 1 candidate must be selected",
            "gate_id": gate_id,
            "label": label,
        }

    # Record approval and selected candidates
    selected_candidates = [candidate_map[cid] for cid in selected_ids]
    gate_state["selected_ids"] = selected_ids
    gate_state["approved"] = True
    gate_state["status"] = "approved"
    gate_state["approved_at"] = datetime.now().isoformat()
    gates_state[gate_id] = gate_state
    state["gates"] = gates_state

    # Set the selected candidate's data as the step output for downstream consumption
    # Use the first selected candidate's data as the "edited" output
    step_order = _get_step_order(scenario)
    candidate_step = definition.get("candidate_step")
    if candidate_step and candidate_step in step_order:
        primary_candidate = selected_candidates[0]
        raw_data = primary_candidate.get("data", {})

        # Skills return wrapper dicts or single items, but pipeline _step_* methods
        # extract / wrap into specific formats. Align edited_output to match.
        if candidate_step == "scripts":
            # script-writer-skill returns {"scripts": [...], "count": N}
            # _step_scripts returns res.data.get("scripts", []) → list
            edited_output = raw_data.get("scripts", []) if isinstance(raw_data, dict) else raw_data
        elif candidate_step == "keyframe_images":
            # keyframe-images returns a single storyboard dict
            # _step_keyframe_images appends each result to a list → list[dict]
            edited_output = [raw_data] if isinstance(raw_data, dict) and raw_data else raw_data
        elif candidate_step == "seedance_clips":
            # seedance-video-generate-skill returns a single clip dict
            # _step_seedance_clips returns aggregated dict with clip_paths, clip_details
            if isinstance(raw_data, dict) and raw_data:
                edited_output = {
                    "clip_paths": [raw_data.get("video_path", "")],
                    "clip_details": [raw_data],
                    "total_duration": raw_data.get("duration_seconds", 0),
                    "target_duration": 30,
                }
            else:
                edited_output = raw_data
        else:
            edited_output = raw_data

        steps_data = dict(state.get("steps", {}))
        step_data = dict(steps_data.get(candidate_step, {}))
        step_data["edited"] = True
        step_data["edited_output"] = edited_output
        step_data["gate_selected"] = True
        step_data["selected_variants"] = [c["variant"] for c in selected_candidates]
        steps_data[candidate_step] = step_data
        state["steps"] = steps_data

    # Advance current_step past the gate's after_step
    after_step = definition["after_step"]
    if after_step in step_order:
        next_step = _get_next_step(after_step, scenario)
        if next_step:
            # Only advance if current_step is at or before after_step
            current_step = state.get("current_step")
            if current_step is None or _step_index(current_step, scenario) <= _step_index(after_step, scenario):
                state["current_step"] = next_step
    else:
        # If no after_step defined, just advance the current_step
        pass

    await state_manager.save(label, state)

    logger.info(
        "gate_manager: gate approved",
        gate_id=gate_id,
        label=label,
        selected_ids=selected_ids,
        next_step=state.get("current_step"),
    )

    return {
        "gate_id": gate_id,
        "label": label,
        "approved": True,
        "selected_ids": selected_ids,
        "selected_variants": [c["variant"] for c in selected_candidates],
        "next_step": state.get("current_step"),
    }


async def regenerate_candidate(label: str, gate_id: str, candidate_id: str) -> dict[str, Any]:
    """Regenerate a single candidate for a gate.

    Re-executes the skill for the variant associated with the given
    candidate_id, re-scores it, and updates the candidate in place.

    Args:
        label: Pipeline run label.
        gate_id: One of the GATE_DEFINITIONS keys.
        candidate_id: The candidate ID to regenerate (e.g. "gate_1_script_standard_...").

    Returns:
        dict with the updated candidate data.
    """
    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

    scenario = _get_scenario_from_state(state)
    gate_defs = _get_gate_defs(scenario)
    definition = gate_defs.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id} for scenario {scenario}", "gate_id": gate_id, "scenario": scenario}

    gates_state = dict(state.get("gates", {}))
    gate_state = gates_state.get(gate_id, {})
    candidates = gate_state.get("candidates", [])

    # Find the candidate to regenerate
    target_idx = None
    for idx, c in enumerate(candidates):
        if c["id"] == candidate_id:
            target_idx = idx
            break

    if target_idx is None:
        return {
            "error": f"Candidate {candidate_id} not found in gate {gate_id}",
            "gate_id": gate_id,
            "label": label,
            "candidate_id": candidate_id,
        }

    existing = candidates[target_idx]
    variant_name = existing.get("variant", "standard")

    candidate_step = definition.get("candidate_step")
    if candidate_step is None:
        return {"error": f"Gate {gate_id} has no candidate_step", "gate_id": gate_id}

    steps_data = state.get("steps", {})
    step_data = steps_data.get(candidate_step, {})
    step_output = step_data.get("output") or {}

    # Read strategy/context for scoring
    strategy_data = steps_data.get("strategy", {}).get("output") or {}
    usps = _extract_usps(strategy_data, state.get("config", {}))

    scoring_params = {
        "usps": usps,
        "brand_guidelines": _extract_brand_guidelines(state.get("config", {})),
    }

    # Temperature mapping for variant
    temperature_map = {
        "standard": 0.7,
        "creative": 0.9,
        "conservative": 0.5,
    }
    temperature = temperature_map.get(variant_name, 0.7)

    skill_params = _build_skill_params(
        candidate_step, state, variant_name, {"temperature": temperature}
    )

    new_candidate_id = f"{gate_id}_{variant_name}_{int(time.time())}"

    try:
        skill_name = STEP_TO_SKILL_NAME.get(candidate_step, candidate_step)
        if skill_name is None:
            raise RuntimeError(f"Gate {gate_id} has no skill mapping for step: {candidate_step}")
        skill_result = await SkillRegistry().execute(skill_name, skill_params)
        # P0: Guard against success=True but empty data — treat as failure
        if skill_result.success and skill_result.data:
            candidate_data = skill_result.data
        elif skill_result.success and not skill_result.data:
            logger.warning(
                "gate_manager: regenerate skill returned success but empty data",
                gate_id=gate_id,
                variant=variant_name,
            )
            candidate_data = {"_error": "Skill returned success but no data"}
        else:
            candidate_data = {"_error": skill_result.error or "Skill execution failed"}
    except Exception as exc:
        logger.error(
            "gate_manager: regenerate skill execution failed",
            gate_id=gate_id,
            variant=variant_name,
            error=str(exc),
        )
        candidate_data = {"_error": str(exc)}

    # Score the regenerated candidate
    try:
        score_result = await score_candidate(
            step_name=candidate_step,
            candidate_data=candidate_data,
            params=scoring_params,
        )
    except Exception as exc:
        logger.warning(
            "gate_manager: rescoring failed, using default",
            gate_id=gate_id,
            candidate_id=candidate_id,
            error=str(exc),
        )
        score_result = {
            "overall": 0.5,
            "breakdown": {},
            "explanation": "Scoring error, defaulted to 0.5",
            "heuristic": True,
        }

    # Update candidate in place
    candidates[target_idx] = {
        "id": new_candidate_id,
        "variant": variant_name,
        "data": candidate_data,
        "score": score_result,
        "recommended": False,
    }

    # Recompute recommended (highest scorer)
    if candidates:
        best = max(candidates, key=lambda c: c["score"].get("overall", 0))
        for c in candidates:
            c["recommended"] = c["id"] == best["id"]

    gate_state["candidates"] = candidates
    gates_state[gate_id] = gate_state
    state["gates"] = gates_state
    await state_manager.save(label, state)

    logger.info(
        "gate_manager: candidate regenerated",
        gate_id=gate_id,
        old_id=candidate_id,
        new_id=new_candidate_id,
        label=label,
        variant=variant_name,
    )

    return {
        "candidate": candidates[target_idx],
        "gate_id": gate_id,
        "label": label,
        "old_candidate_id": candidate_id,
    }


# ── Internal helpers ──


def _step_index(step_name: str | None, scenario: str = "s1") -> int:
    """Return the index of a step name in the scenario's step order, or -1 if not found."""
    if step_name is None:
        return -1
    order = _get_step_order(scenario)
    try:
        return order.index(step_name)
    except ValueError:
        return -1


def _extract_step_input(state: dict[str, Any], step_name: str) -> Any:
    """Retrieve input from a previous step's output or edited_output."""
    steps = state.get("steps", {})
    step_data = steps.get(step_name, {})
    if step_data.get("edited") and step_data.get("edited_output") is not None:
        return step_data["edited_output"]
    return step_data.get("output")


def _build_skill_params(candidate_step: str, state: dict[str, Any], variant_name: str, variant_params: dict[str, Any]) -> dict[str, Any]:
    """Build skill-specific parameters for candidate generation.

    Each skill expects a different parameter set. This function maps
    candidate_step names to the correct parameters required by each skill.
    """
    config = state.get("config", {})
    steps_data = state.get("steps", {})
    strategy_output = steps_data.get("strategy", {}).get("output") or {}
    brand_guidelines = config.get("brand_guidelines") or {}
    target_languages = config.get("target_languages", DEFAULT_LANGUAGES)

    if candidate_step == "scripts":
        if isinstance(strategy_output, list):
            briefs = strategy_output
        elif isinstance(strategy_output, dict):
            briefs = strategy_output.get("briefs") or strategy_output.get("strategy_briefs") or []
        else:
            briefs = []
        if not briefs:
            # Fallback: construct a minimal brief from config
            product_catalog = config.get("product_catalog", {})
            briefs = [{
                "id": "fb_1",
                "topic": product_catalog.get("product_name", "Product"),
                "audience": product_catalog.get("target_audience", "general"),
                "platforms": product_catalog.get("platforms", ["shopify"]),
            }]
        return {
            "briefs": briefs,
            "brand_guidelines": brand_guidelines,
            "target_languages": target_languages,
            "variant": variant_name,
            **variant_params,
        }

    if candidate_step == "keyframe_images":
        storyboards = _extract_step_input(state, "storyboards") or []
        scripts = _extract_step_input(state, "scripts") or []
        # keyframe-images skill expects one storyboard at a time
        # For candidate generation, use the first storyboard
        sb = storyboards[0] if storyboards else {"shots": [], "script_id": "default"}
        return {
            "storyboard": sb,
            "scripts": scripts,
            "brand_guidelines": brand_guidelines,
            "size": "1024x1792",
            "quality": "high",
            "variant": variant_name,
            **variant_params,
        }

    if candidate_step == "seedance_clips":
        video_prompts = _extract_step_input(state, "video_prompts") or []
        keyframe_images = _extract_step_input(state, "keyframe_images") or []
        product_catalog = config.get("product_catalog", {})

        # seedance-video-generate-skill expects a single prompt dict, not lists
        first_prompt = ""
        if video_prompts and isinstance(video_prompts, list):
            vp = video_prompts[0]
            if isinstance(vp, dict):
                first_prompt = vp.get("segment_prompt", "") or vp.get("prompt", "")
                if isinstance(first_prompt, dict):
                    first_prompt = first_prompt.get("segment_prompt", "") or first_prompt.get("prompt", "")

        # Extract first keyframe image path for anchoring
        keyframe_path = ""
        if keyframe_images and isinstance(keyframe_images, list):
            kf = keyframe_images[0]
            if isinstance(kf, dict):
                for shot in kf.get("shots", []):
                    path = shot.get("keyframe_image_path", "")
                    if path:
                        keyframe_path = path
                        break

        return {
            "prompt": first_prompt or f"{product_catalog.get('product_name', 'Product')} in natural usage scene",
            "duration": 5,
            "resolution": "720p",
            "output_label": f"{state.get('label', 'default')}_gate3",
            "keyframe_image_path": keyframe_path,
            "variant": variant_name,
            **variant_params,
        }

    if candidate_step == "remix_script":
        video_analysis = _extract_step_input(state, "video_analysis") or {}
        product = config.get("product", config.get("product_catalog", {}))
        return {
            "analysis": video_analysis,
            "product": product,
            "brief_id": config.get("brief_id", ""),
            "influencer_name": config.get("influencer_name", "Influencer"),
            "product_context": {
                "target_platforms": config.get("target_platforms", ["tiktok"]),
                "target_languages": target_languages,
            },
            "variant": variant_name,
            **variant_params,
        }

    if candidate_step == "vlog_strategy":
        product_catalog = config.get("product_catalog", config.get("product_sku", {}))
        return {
            "product_catalog": product_catalog,
            "brand_guidelines": brand_guidelines,
            "content_scenario": "brand_vlog",
            "target_platforms": config.get("target_platforms", ["tiktok", "shopify"]),
            "target_languages": target_languages,
            "variant": variant_name,
            **variant_params,
        }

    if candidate_step == "assemble_final":
        return {
            "input_data": _extract_step_input(state, "assemble_final") or {},
            "variant": variant_name,
            **variant_params,
        }

    # Generic fallback
    return {
        "input_data": _extract_step_input(state, candidate_step),
        "state": state,
        "variant": variant_name,
        **variant_params,
    }


def _extract_usps(strategy_data, config: dict[str, Any]) -> list[str]:
    """Extract USP list from strategy output or config.

    Strategy output can arrive as:
      - dict: {"briefs": [...], "usps": [...]} (legacy / aggregated)
      - list: [Brief, Brief, ...] (current step_runner persists each brief
              with usp_priority list)

    Tries multiple locations where USPs might be stored.
    """
    # Aggregate from list-of-briefs form first
    if isinstance(strategy_data, list):
        out: list[str] = []
        for brief in strategy_data:
            if not isinstance(brief, dict):
                continue
            for key in ("usp_priority", "usps", "unique_selling_points"):
                vals = brief.get(key) or []
                if isinstance(vals, list):
                    out.extend(str(u) for u in vals if u)
                elif isinstance(vals, str) and vals:
                    out.append(vals)
        if out:
            # de-dup preserving order
            seen: set[str] = set()
            return [u for u in out if not (u in seen or seen.add(u))]
        strategy_data = {}

    if isinstance(strategy_data, dict):
        usps = strategy_data.get("usps") or strategy_data.get("unique_selling_points") or []
        if isinstance(usps, list):
            return [str(u) for u in usps if u]

    # From config product_catalog
    product_catalog = config.get("product_catalog", {})
    if isinstance(product_catalog, dict):
        catalog_usps = product_catalog.get("usps") or product_catalog.get("unique_selling_points") or []
        if isinstance(catalog_usps, list):
            return [str(u) for u in catalog_usps if u]
        if isinstance(catalog_usps, str):
            return [catalog_usps]

    # From product info
    product_info = config.get("product_info", {})
    if isinstance(product_info, dict):
        info_usps = product_info.get("usps") or product_info.get("unique_selling_points") or []
        if isinstance(info_usps, list):
            return [str(u) for u in info_usps if u]

    return []


def _extract_brand_guidelines(config: dict[str, Any]) -> str:
    """Extract brand guidelines text from config."""
    guidelines = config.get("brand_guidelines", {})
    if isinstance(guidelines, str):
        return guidelines
    if isinstance(guidelines, dict):
        return json.dumps(guidelines, ensure_ascii=False)
    return ""
