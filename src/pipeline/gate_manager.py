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

logger = structlog.get_logger()

# ── Gate Definitions ──

VariantType = Literal["standard", "creative", "conservative"]

GATE_DEFINITIONS: dict[str, dict[str, Any]] = {
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

# STEP_ORDER constant — must match step_runner.py
STEP_ORDER = [
    "strategy",
    "scripts",
    "compliance",
    "storyboards",
    "keyframe_images",
    "video_prompts",
    "thumbnail_prompts",
    "seedance_clips",
    "tts_audio",
    "thumbnail_images",
    "assemble_final",
    "audit",
]


def _get_next_step(step_name: str) -> str | None:
    """Return the next step name after the given step, or None if last."""
    try:
        idx = STEP_ORDER.index(step_name)
        if idx + 1 < len(STEP_ORDER):
            return STEP_ORDER[idx + 1]
    except ValueError:
        pass
    return None


async def get_gate_state(label: str, gate_id: str) -> dict:
    """Get the current state of a specific gate.

    Args:
        label: Pipeline run label.
        gate_id: One of the GATE_DEFINITIONS keys.

    Returns:
        dict with gate state information, or a 404-like error dict.
    """
    definition = GATE_DEFINITIONS.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id}", "gate_id": gate_id}

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


async def generate_candidates(label: str, gate_id: str) -> dict:
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
    definition = GATE_DEFINITIONS.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id}", "gate_id": gate_id}

    candidate_step = definition.get("candidate_step")
    if candidate_step is None:
        return {"error": f"Gate {gate_id} has no candidate_step", "gate_id": gate_id}

    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

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
    variants: list[tuple[str, dict]] = [
        ("standard", {"temperature": 0.7, "variant": "standard"}),
        ("creative", {"temperature": 0.9, "variant": "creative"}),
        ("conservative", {"temperature": 0.5, "variant": "conservative"}),
    ]

    wanted_count = 3
    valid_candidates: list[dict] = []
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

        skill_params = {
            "step_output": step_output,
            "state": state,
            "variant": variant_name,
            **variant["params"],
        }
        # Gate 4 has no candidate_step; use the assemble_final output directly
        if candidate_step == "assemble_final":
            skill_params["input_data"] = step_output
        else:
            skill_params["input_data"] = _extract_step_input(state, candidate_step)

        try:
            skill_result = await SkillRegistry.execute(candidate_step, skill_params)
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

    logger.info(
        "gate_manager: candidates generated",
        gate_id=gate_id,
        label=label,
        candidate_count=len(candidates),
        recommended_id=best["id"] if candidates else None,
    )

    return {
        "candidates": candidates,
        "gate_id": gate_id,
        "label": label,
    }


async def approve_gate(label: str, gate_id: str, selected_ids: list[str]) -> dict:
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
    definition = GATE_DEFINITIONS.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id}", "gate_id": gate_id}

    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

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
    candidate_step = definition.get("candidate_step")
    if candidate_step and candidate_step in STEP_ORDER:
        primary_candidate = selected_candidates[0]
        steps_data = dict(state.get("steps", {}))
        step_data = dict(steps_data.get(candidate_step, {}))
        step_data["edited"] = True
        step_data["edited_output"] = primary_candidate.get("data", {})
        step_data["gate_selected"] = True
        step_data["selected_variants"] = [c["variant"] for c in selected_candidates]
        steps_data[candidate_step] = step_data
        state["steps"] = steps_data

    # Advance current_step past the gate's after_step
    after_step = definition["after_step"]
    if after_step in STEP_ORDER:
        next_step = _get_next_step(after_step)
        if next_step:
            # Only advance if current_step is at or before after_step
            current_step = state.get("current_step")
            if current_step is None or _step_index(current_step) <= _step_index(after_step):
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


async def regenerate_candidate(label: str, gate_id: str, candidate_id: str) -> dict:
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
    definition = GATE_DEFINITIONS.get(gate_id)
    if definition is None:
        return {"error": f"Unknown gate: {gate_id}", "gate_id": gate_id}

    state_manager = PipelineStateManager()
    state = await state_manager.load(label)
    if state is None:
        return {"error": f"State not found for label: {label}", "gate_id": gate_id, "label": label}

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

    skill_params = {
        "step_output": step_output,
        "state": state,
        "variant": variant_name,
        "temperature": temperature,
        "input_data": _extract_step_input(state, candidate_step),
    }

    new_candidate_id = f"{gate_id}_{variant_name}_{int(time.time())}"

    try:
        skill_result = await SkillRegistry.execute(candidate_step, skill_params)
        candidate_data = skill_result.data if skill_result.success else {}
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


def _step_index(step_name: str | None) -> int:
    """Return the index of a step name in STEP_ORDER, or -1 if not found."""
    if step_name is None:
        return -1
    try:
        return STEP_ORDER.index(step_name)
    except ValueError:
        return -1


def _extract_step_input(state: dict, step_name: str) -> Any:
    """Retrieve input from a previous step's output or edited_output."""
    steps = state.get("steps", {})
    step_data = steps.get(step_name, {})
    if step_data.get("edited") and step_data.get("edited_output") is not None:
        return step_data["edited_output"]
    return step_data.get("output")


def _extract_usps(strategy_data: dict, config: dict) -> list[str]:
    """Extract USP list from strategy output or config.

    Tries multiple locations where USPs might be stored.
    """
    # From strategy output
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


def _extract_brand_guidelines(config: dict) -> str:
    """Extract brand guidelines text from config."""
    guidelines = config.get("brand_guidelines", {})
    if isinstance(guidelines, str):
        return guidelines
    if isinstance(guidelines, dict):
        return json.dumps(guidelines, ensure_ascii=False)
    return ""
