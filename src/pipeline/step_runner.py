"""Step runner for executing individual pipeline steps with state management.

The StepRunner loads pipeline state, executes a single step using the
S1ProductDirectPipeline methods, and persists the updated state back to disk.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import datetime
from typing import Any

import structlog

from src.models.pipeline_completion import derive_pipeline_completion_facts
from src.pipeline.gate_manager import SCENARIO_GATE_DEFINITIONS
from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.scenario_injection_plan import attach_step_injection_visibility
from src.pipeline.state_manager import PipelineStateManager, claim_pipeline_completion
from src.telemetry import error_collector, generate_trace_id, pipeline_metrics


def _get_gate_after_steps(scenario: str = "s1") -> set[str]:
    """Return the set of step names that trigger a gate pause for a scenario."""
    gate_defs = SCENARIO_GATE_DEFINITIONS.get(scenario, SCENARIO_GATE_DEFINITIONS["s1"])
    return {g["after_step"] for g in gate_defs.values()}


def _get_gate_id_for_step(step_name: str, scenario: str = "s1") -> str:
    """Return the gate_id whose after_step matches the given step_name, or ''."""
    gate_defs = SCENARIO_GATE_DEFINITIONS.get(scenario, SCENARIO_GATE_DEFINITIONS["s1"])
    for gate_id, gate_def in gate_defs.items():
        if gate_def["after_step"] == step_name:
            return gate_id
    return ""


_SCENARIO_REGENERATE_STEP_MAP: dict[str, str] = {
    "storyboard": "storyboards",
    "storyboards": "storyboards",
    "seedance_prompt": "video_prompts",
    "video_prompts": "video_prompts",
    "script_writer": "scripts",
    "scripts": "scripts",
}


def _detect_regenerate_signal(result: Any) -> dict[str, Any] | None:
    """Inspect a step result for the TODO-D11 regenerate sentinel.

    Contract: a step that hit feedback_gate may embed a marker dict
    `{"_regenerate_upstream": "<upstream_skill>", "score": ..., "reason": ...,
       "consumer": ..., "attempt": ...}` either as the first element of a
    list result or as a top-level dict. Returns the marker if found, else None.
    """
    if isinstance(result, dict) and result.get("_regenerate_upstream"):
        return result
    if isinstance(result, list) and result and isinstance(result[0], dict) and result[0].get("_regenerate_upstream"):
        return result[0]
    return None


_QUALITY_REWIND_MAX_ATTEMPTS = 2
_PIPELINE_COMPLETION_CLAIM_KEY = "pipeline_completion_metric_v1"


def _validate_pipeline_completion_claim(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if (
        type(raw) is not dict
        or set(raw)
        != {
            "version",
            "outcome",
            "claimed_at",
            "duration_ms",
            "error_count",
            "scenario",
        }
        or raw.get("version") != "pipeline-completion-metric.v1"
        or raw.get("outcome") not in {"success", "failure"}
        or type(raw.get("claimed_at")) is not str
        or not raw["claimed_at"]
        or type(raw.get("duration_ms")) not in {int, float}
        or raw["duration_ms"] < 0
        or type(raw.get("error_count")) is not int
        or raw["error_count"] < 0
        or type(raw.get("scenario")) is not str
        or not raw["scenario"]
    ):
        raise ValueError("pipeline_completion_metric_invalid")
    return raw


def _quality_rewind_envelope(state: dict[str, Any]) -> dict[str, Any] | None:
    from fastapi import HTTPException

    config = state.get("config")
    if not isinstance(config, dict) or "quality_rewind" not in config:
        return None
    rewind = config["quality_rewind"]
    if (
        type(rewind) is not dict
        or set(rewind)
        != {"upstream_step", "consumer_step", "attempt", "status"}
        or type(rewind.get("upstream_step")) is not str
        or not rewind["upstream_step"]
        or type(rewind.get("consumer_step")) is not str
        or not rewind["consumer_step"]
        or type(rewind.get("attempt")) is not int
        or not 1 <= rewind["attempt"] <= _QUALITY_REWIND_MAX_ATTEMPTS
        or rewind.get("status") not in {"awaiting_upstream", "upstream_completed"}
    ):
        raise HTTPException(status_code=422, detail="Invalid quality rewind state")
    return rewind


def _assert_quality_rewind_step_allowed(state: dict[str, Any], step_name: str) -> None:
    from fastapi import HTTPException

    rewind = _quality_rewind_envelope(state)
    if (
        rewind is not None
        and rewind["status"] == "awaiting_upstream"
        and step_name == rewind["consumer_step"]
    ):
        raise HTTPException(
            status_code=409,
            detail="Quality rewind requires upstream completion before consumer execution",
        )


def _record_quality_rewind_step_completion(
    state: dict[str, Any],
    step_name: str,
) -> None:
    rewind = _quality_rewind_envelope(state)
    if rewind is None:
        return
    if rewind["status"] == "awaiting_upstream" and step_name == rewind["upstream_step"]:
        rewind["status"] = "upstream_completed"
    elif rewind["status"] == "upstream_completed" and step_name == rewind["consumer_step"]:
        config = state.get("config")
        assert isinstance(config, dict)
        config.pop("quality_rewind", None)


def _mark_quality_rewind_invalid(
    state: dict[str, Any],
    step_data: dict[str, Any],
    error_code: str,
) -> None:
    step_data["status"] = "error"
    state["pipeline_degraded"] = True
    state["degraded_reason"] = error_code
    errors = state.setdefault("errors", [])
    if error_code not in errors:
        errors.append(error_code)


def _result_indicates_all_stubs(result: Any) -> bool:
    """TODO-D10: detect the S5 all-stubs sentinel from _step_seedance_clips.

    Contract: when every seedance clip is a stub (POYO failure / content-mod
    rejection), the step returns a dict with `_all_stubs=True`. step_runner
    sets pipeline_degraded so partial_artifacts.summarize correctly flags
    the run as degraded and downstream steps short-circuit.
    """
    if not isinstance(result, dict):
        return False
    if result.get("_all_stubs") is True:
        return True
    details = result.get("clip_details")
    if isinstance(details, list) and details and all(d.get("is_stub", False) for d in details):
        return True
    return False


def _result_indicates_soft_degraded(result: Any) -> dict[str, Any] | None:
    """TODO-D10 PR2/PR3: detect a soft-degraded sentinel from any step.

    Contract: a step that hit a recoverable failure but produced fallback
    output (instead of halting the pipeline) embeds:
      `{"_soft_degraded": True, "_degraded_reason": "...", "_degraded_detail": "..."}`
    plus the normal output fields. The marker may live at the top level
    (dict result) OR as the first element of a list result (when the
    step's normal contract is list[dict]). step_runner appends to
    state.soft_degraded_reasons (list, audit-only) and lets the pipeline
    continue. Distinct from the hard pipeline_degraded flag which halts.
    """
    candidate: Any = None
    if isinstance(result, dict) and result.get("_soft_degraded") is True:
        candidate = result
    elif (
        isinstance(result, list) and result and isinstance(result[0], dict) and result[0].get("_soft_degraded") is True
    ):
        candidate = result[0]
    if candidate is None:
        return None
    return {
        "reason": candidate.get("_degraded_reason", "unknown"),
        "detail": candidate.get("_degraded_detail", ""),
    }


logger = structlog.get_logger()

# Ordered list of all pipeline step names
STEP_ORDER = [
    "strategy",
    "scripts",
    "compliance",
    "storyboards",
    "continuity_storyboard_grid",
    "keyframe_images",
    "video_prompts",
    "thumbnail_prompts",
    "seedance_clips",
    "tts_audio",
    "thumbnail_images",
    "assemble_final",
    "audit",
]

# Mapping of step names to the S1ProductDirectPipeline method names
STEP_METHOD_MAP = {
    "strategy": "_step_strategy",
    "scripts": "_step_scripts",
    "compliance": "_step_compliance",
    "storyboards": "_step_storyboards",
    "continuity_storyboard_grid": "_step_continuity_storyboard_grid",
    "keyframe_images": "_step_keyframe_images",
    "video_prompts": "_step_video_prompts",
    "thumbnail_prompts": "_step_thumbnail_prompts",
    "seedance_clips": "_step_seedance_clips",
    "tts_audio": "_step_tts_audio",
    "thumbnail_images": "_step_thumbnail_images",
    "assemble_final": "_step_assemble_final",
    "audit": "_step_audit",
}

# ── Scenario configurations ──
_SCENARIO_CONFIGS: dict[str, dict[str, Any]] = {
    "s1": {
        "step_order": get_scenario_step_order("s1"),
        "pipeline_class": "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline",
    },
    "s2": {
        # S2 Brand Campaign is an S1 wrapper (brand_mode=True) — same steps, same class
        "step_order": get_scenario_step_order("s2"),
        "pipeline_class": "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline",
    },
    "s4": {
        "step_order": get_scenario_step_order("s4"),
        "pipeline_class": "src.pipeline.s4_live_shoot_pipeline.S4LiveShootPipeline",
    },
    "s3": {
        "step_order": get_scenario_step_order("s3"),
        "pipeline_class": "src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline",
    },
    "s5": {
        "step_order": get_scenario_step_order("s5"),
        "pipeline_class": "src.pipeline.s5_brand_vlog_pipeline.S5BrandVlogPipeline",
    },
}


def _get_scenario_config(scenario: str) -> dict[str, Any]:
    """Return scenario config, falling back to s1 for unknown scenarios."""
    if scenario not in _SCENARIO_CONFIGS:
        logger.warning("step_runner: unknown scenario, falling back to s1", scenario=scenario)
        return _SCENARIO_CONFIGS["s1"]
    return _SCENARIO_CONFIGS[scenario]


def _get_next_step(step_name: str, step_order: list[str] | None = None) -> str | None:
    """Return the next step name after the given step, or None if last."""
    order = step_order or STEP_ORDER
    try:
        idx = order.index(step_name)
        if idx + 1 < len(order):
            return order[idx + 1]
    except ValueError:
        pass
    return None


def _get_step_input(state: dict[str, Any], step_name: str, input_key: str) -> Any:
    """Retrieve input from a previous step's output or edited_output."""
    steps = state.get("steps", {})
    step_data = steps.get(input_key, {})
    if step_data.get("edited") and step_data.get("edited_output") is not None:
        return step_data["edited_output"]
    return step_data.get("output")


def _with_continuity_defaults(config: dict[str, Any], scenario: str) -> dict[str, Any]:
    """Attach S1/S2 continuity defaults without changing caller-owned config."""
    if scenario not in {"s1", "s2"}:
        return config

    normalized = dict(config)
    normalized.setdefault("continuity_mode", True)
    normalized.setdefault("storyboard_grid", 12)
    normalized.setdefault("clip_group_size", 3)
    return normalized


def _mirror_continuity_output(state: dict[str, Any], result: Any) -> None:
    """Expose continuity output at top level for consumers that do not read steps."""
    if not isinstance(result, dict):
        return

    state["continuity_storyboard_grid"] = result.get("continuity_storyboard_grid", result)
    state["continuity_micro_shots"] = result.get("continuity_micro_shots", result.get("micro_shots", []))
    state["clip_groups"] = result.get("clip_groups", [])
    state["transition_plan"] = result.get("transition_plan", [])
    if result.get("metadata"):
        state["continuity_storyboard_metadata"] = result["metadata"]


def _record_step_transparency(
    state: dict[str, Any],
    *,
    step_name: str,
    output: Any,
    skipped: bool = False,
) -> Any:
    from src.config import OUTPUT_DIR
    from src.services.transparency_provenance import record_step_provenance

    updated_output, transparency = record_step_provenance(
        state=state,
        step_name=step_name,
        output=output,
        output_dir=OUTPUT_DIR,
        origin_kind="simulated" if skipped else "local",
    )
    state["transparency"] = transparency
    return updated_output


def _mark_execution_terminal(
    state: dict[str, Any],
    *,
    profile: Any,
) -> dict[str, Any]:
    """Derive and persist one truthful terminal lifecycle envelope."""

    from src.pipeline import completion_truth

    state["current_step"] = None
    lifecycle = completion_truth.derive_scenario_completion(
        state,
        expected_completion_kind=profile.completion_kind,
    )
    config = state.setdefault("config", {})
    if lifecycle["status"] == "error":
        for field in (
            "status",
            "lifecycle_status",
            "completion_kind",
            "request_succeeded",
            "success",
            "full_media_success",
            "pipeline_complete",
            "publish_allowed",
            "delivery_accepted",
        ):
            state.pop(field, None)
        config.pop("execution_lifecycle", None)
        state["pipeline_degraded"] = True
        state["degraded_reason"] = "completion_truth_failed"
        errors = state.setdefault("errors", [])
        if "completion_truth_failed" not in errors:
            errors.append("completion_truth_failed")
        return state

    state.update(lifecycle)
    state["execution_profile_id"] = profile.profile_id
    state["provider_job_caps"] = dict(profile.provider_job_caps)
    config["execution_lifecycle"] = {
        key: state[key]
        for key in (
            "status",
            "lifecycle_status",
            "completion_kind",
            "request_succeeded",
            "success",
            "full_media_success",
            "pipeline_complete",
            "publish_allowed",
            "delivery_accepted",
            "execution_profile_id",
            "provider_job_caps",
        )
    }
    return state


def _mark_policy_blocked(state: dict[str, Any]) -> dict[str, Any]:
    """Stop a legacy state with no durable authority without claiming success."""

    state.update(
        {
            "status": "policy_blocked",
            "lifecycle_status": "policy_blocked",
            "completion_kind": "legacy_no_policy_blocked",
            "request_succeeded": False,
            "success": False,
            "full_media_success": False,
            "pipeline_complete": False,
            "publish_allowed": False,
            "delivery_accepted": False,
            "current_step": None,
        }
    )
    state.setdefault("config", {})["execution_lifecycle"] = {
        key: state[key]
        for key in (
            "status",
            "lifecycle_status",
            "completion_kind",
            "request_succeeded",
            "success",
            "full_media_success",
            "pipeline_complete",
            "publish_allowed",
            "delivery_accepted",
        )
    }
    return state


class StepRunner:
    """Runs individual steps of the S1 pipeline using state persistence."""

    def __init__(self, state_manager: PipelineStateManager) -> None:
        self.state_manager = state_manager

    async def init_state(
        self,
        config: dict[str, Any],
        mode: str = "auto",
        label: str | None = None,
        scenario: str = "s1",
    ) -> str:
        """Create initial empty pipeline state, save it, and return the label."""
        if label is None:
            # uuid suffix prevents same-second concurrent collision (Task H)
            label = f"{scenario}_{int(time.time())}_{uuid.uuid4().hex[:8]}"

        scenario_cfg = _get_scenario_config(scenario)
        step_order = scenario_cfg["step_order"]
        config = dict(_with_continuity_defaults(config, scenario))
        if _PIPELINE_COMPLETION_CLAIM_KEY in config:
            raise ValueError("pipeline completion metric claim is server-owned")

        # Request-time generation authority is server-owned.  Blocking
        # scenario wrappers build their own config before reaching StepRunner,
        # so project the bound policy here as the final persistence boundary.
        # Runtime enforcement remains in the dedicated execution-policy guard.
        from src.pipeline.generation_policy import get_effective_generation_policy
        from src.services.provider_execution import (
            PROVIDER_EXECUTION_CONFIG_KEY,
            get_provider_execution_context,
            project_provider_execution_context,
        )

        effective_policy = get_effective_generation_policy()
        execution_context = get_provider_execution_context()
        if effective_policy is not None:
            if execution_context is None:
                from src.models.provider_cost import ProviderCostContractError

                raise ProviderCostContractError(
                    "provider_execution_context_missing",
                    "provider execution context must be initialized before state",
                )
            if effective_policy.scenario != scenario:
                raise ValueError(
                    "Effective generation policy scenario mismatch: "
                    f"policy={effective_policy.scenario} state={scenario}"
                )
            if (
                execution_context.tenant_id != effective_policy.tenant_id
                or execution_context.scenario_or_resource_type != scenario
                or execution_context.generation_policy_version != effective_policy.version
            ):
                from src.models.provider_cost import ProviderCostContractError

                raise ProviderCostContractError(
                    "provider_execution_context_missing",
                    "provider execution context conflicts with generation policy",
                )
            execution_projection = project_provider_execution_context(execution_context)
            supplied_projection = config.get(PROVIDER_EXECUTION_CONFIG_KEY)
            if supplied_projection is not None and supplied_projection != execution_projection:
                from src.models.provider_cost import ProviderCostContractError

                raise ProviderCostContractError(
                    "provider_execution_context_missing",
                    "provider execution projection cannot be supplied by a caller",
                )
            config.update(
                {
                    "enable_media_synthesis": effective_policy.enable_media_synthesis,
                    "artifact_disposition": effective_policy.artifact_disposition,
                    "provider_max_retries": effective_policy.provider_max_retries,
                    "c2pa_signing_mode": effective_policy.c2pa_signing_mode,
                    "effective_generation_policy": effective_policy.model_dump(mode="json"),
                    PROVIDER_EXECUTION_CONFIG_KEY: execution_projection,
                }
            )
        elif PROVIDER_EXECUTION_CONFIG_KEY in config:
            from src.models.provider_cost import ProviderCostContractError

            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "provider execution projection requires bound server authority",
            )

        # Build empty step statuses
        steps = {}
        for step_name in step_order:
            steps[step_name] = {
                "status": "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
                "started_at": "",
                "completed_at": "",
                "duration_ms": 0,
            }

        trace_id = generate_trace_id()
        from src.models.state import STATE_SCHEMA_VERSION
        from src.routers._deps import get_auth_context

        auth_ctx = get_auth_context()
        state_tenant_id = (
            auth_ctx.tenant_id
            if auth_ctx
            else execution_context.tenant_id
            if execution_context is not None
            else config.get("tenant_id", "default")
        )
        if execution_context is not None and state_tenant_id != execution_context.tenant_id:
            from src.models.provider_cost import ProviderCostContractError

            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "provider execution tenant conflicts with state owner",
            )
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "label": label,
            "scenario": scenario,
            "tenant_id": state_tenant_id,
            "config": config,
            "steps": steps,
            "current_step": step_order[0],
            "mode": mode,
            "trace_id": trace_id,
            "errors": [],
            "media_synthesis_errors": [],
            "gates": {},
            "pipeline_degraded": False,
            "degraded_reason": None,
            "structured_errors": [],
            "regenerate_chain": [],
            "soft_degraded_reasons": [],
        }

        if effective_policy is not None:
            from src.pipeline.generation_policy import resolve_generation_execution_profile

            profile = resolve_generation_execution_profile(
                state,
                require_persisted_profile=False,
            )
            config["effective_generation_execution_profile"] = profile.model_dump()
            config["provider_job_caps"] = dict(profile.provider_job_caps)

        await self.state_manager.save(label, state)
        logger.info("step_runner: state initialized", label=label, mode=mode, trace_id=trace_id)
        return label

    async def run_step(self, label: str, step_name: str) -> dict[str, Any]:
        """Load state, execute the specified step, save state back, and return state."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        scenario_cfg = _get_scenario_config(state.get("scenario", "s1"))
        if step_name not in scenario_cfg["step_order"]:
            raise ValueError(f"Unknown step name: {step_name}")

        return await self._execute_step(state, step_name, force=False)

    async def finalize_pipeline_completion(
        self,
        state: dict[str, Any],
        *,
        started_at: float,
    ) -> bool:
        """Atomically persist one terminal claim before emitting completion."""
        config = state.get("config")
        if type(config) is not dict:
            raise ValueError("pipeline_completion_metric_invalid")
        existing = _validate_pipeline_completion_claim(
            config.get(_PIPELINE_COMPLETION_CLAIM_KEY)
        )
        if existing is not None:
            return False

        proposed_facts = derive_pipeline_completion_facts(state)
        if proposed_facts is None:
            return False

        duration_ms = max((time.perf_counter() - started_at) * 1000, 0.0)
        claim = {
            "version": "pipeline-completion-metric.v1",
            "outcome": proposed_facts["outcome"],
            "claimed_at": datetime.now().astimezone().isoformat(),
            "duration_ms": duration_ms,
            "error_count": proposed_facts["error_count"],
            "scenario": proposed_facts["scenario"],
        }
        winning_claim = await claim_pipeline_completion(
            self.state_manager,
            label=state["label"],
            state=state,
            claim=claim,
        )
        if winning_claim is None:
            return False
        success = winning_claim["outcome"] == "success"
        pipeline_metrics.record_pipeline(
            label=state["label"],
            scenario=winning_claim["scenario"],
            total_duration_ms=winning_claim["duration_ms"],
            success=success,
            error_count=winning_claim["error_count"],
        )
        logger.info(
            "step_runner: pipeline completion claimed",
            label=state["label"],
            trace_id=state.get("trace_id", "unknown"),
            scenario=winning_claim["scenario"],
            total_duration_ms=round(winning_claim["duration_ms"], 2),
            success=success,
            error_count=winning_claim["error_count"],
        )
        return True

    async def regenerate_step(self, label: str, step_name: str) -> dict[str, Any]:
        """Force re-execution of a step even if it is already done."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        scenario_cfg = _get_scenario_config(state.get("scenario", "s1"))
        if step_name not in scenario_cfg["step_order"]:
            raise ValueError(f"Unknown step name: {step_name}")

        _assert_quality_rewind_step_allowed(state, step_name)

        from src.pipeline.generation_policy import assert_generation_step_allowed
        from src.services.provider_execution import (
            persist_trusted_regeneration_epoch,
        )

        assert_generation_step_allowed(state, step_name, force=True)
        await persist_trusted_regeneration_epoch(
            state,
            state_writer=self.state_manager,
            operation_key=f"step.regenerate.{step_name}",
        )

        return await self._execute_step(state, step_name, force=True)

    async def resume(self, label: str) -> dict[str, Any]:
        """Run from current_step until completion, returning the final state."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")
        pipeline_start = time.perf_counter()

        from fastapi import HTTPException

        from src.pipeline.generation_policy import resolve_generation_execution_profile

        config = state.get("config")
        if not isinstance(config, dict) or "effective_generation_policy" not in config:
            _mark_policy_blocked(state)
            await self.state_manager.save(label, state)
            await self.finalize_pipeline_completion(state, started_at=pipeline_start)
            return state

        profile = resolve_generation_execution_profile(state)
        step_order = list(profile.allowed_steps)
        current = state.get("current_step")
        if current is None:
            incomplete = [step for step in step_order if state.get("steps", {}).get(step, {}).get("status") != "done"]
            if incomplete or state.get("pipeline_degraded"):
                await self.finalize_pipeline_completion(
                    state,
                    started_at=pipeline_start,
                )
                raise HTTPException(
                    status_code=422,
                    detail="Empty execution cursor has incomplete or failed profile steps",
                )
            if state.get("status") != "completed_bounded":
                _mark_execution_terminal(state, profile=profile)
                await self.state_manager.save(label, state)
            await self.finalize_pipeline_completion(state, started_at=pipeline_start)
            return state

        if current not in step_order:
            canonical_order = _get_scenario_config(state.get("scenario", "s1"))["step_order"]
            completed_allowed = all(state.get("steps", {}).get(step, {}).get("status") == "done" for step in step_order)
            if current in canonical_order and completed_allowed and not state.get("pipeline_degraded"):
                _mark_execution_terminal(state, profile=profile)
                await self.state_manager.save(label, state)
                await self.finalize_pipeline_completion(
                    state,
                    started_at=pipeline_start,
                )
                return state
            raise HTTPException(
                status_code=422,
                detail=f"Invalid current_step for execution profile: {current}",
            )

        try:
            start_idx = step_order.index(current)
        except ValueError:
            raise ValueError(f"Invalid current_step in state: {current}")

        for step_name in step_order[start_idx:]:
            # P0: Degraded guard — if any previous step set pipeline_degraded, stop
            if state.get("pipeline_degraded"):
                logger.error(
                    "step_runner: pipeline degraded, halting", step=step_name, reason=state.get("degraded_reason")
                )
                break
            # Gate check: if this step has a gate awaiting approval, pause and return
            gate_id = _get_gate_id_for_step(step_name, state.get("scenario", "s1"))
            if gate_id:
                gate_state = state.get("gates", {}).get(gate_id, {})
                if gate_state.get("status") == "awaiting_approval":
                    logger.info("step_runner: gate awaiting approval, pausing", gate=gate_id)
                    state["current_step"] = step_name
                    await self.state_manager.save(state["label"], state)
                    return state
            state = await self._execute_step(state, step_name, force=False)
            rewind = _quality_rewind_envelope(state)
            if (
                rewind is not None
                and rewind["status"] == "awaiting_upstream"
                and state.get("current_step") == rewind["upstream_step"]
            ):
                return state

            # Post-step gate check: if the step we just ran registered a gate
            # (e.g. keyframe_images → gate_2_keyframe), the gate is now
            # awaiting approval and the loop must pause here. Without this
            # check, the loop would proceed to the next step (video_prompts)
            # whose pre-check only inspects ITS own gate (none), missing the
            # newly-registered gate_2_keyframe.
            post_gate_id = _get_gate_id_for_step(step_name, state.get("scenario", "s1"))
            if post_gate_id:
                post_gate = state.get("gates", {}).get(post_gate_id, {})
                if post_gate.get("status") == "awaiting_approval":
                    logger.info(
                        "step_runner: gate registered after step, pausing resume",
                        step=step_name,
                        gate=post_gate_id,
                    )
                    return state

        if not state.get("pipeline_degraded") and state.get("current_step") is None:
            _mark_execution_terminal(state, profile=profile)
            await self.state_manager.save(label, state)

        await self.finalize_pipeline_completion(state, started_at=pipeline_start)
        return state

    async def _execute_step(self, state: dict[str, Any], step_name: str, force: bool = False) -> dict[str, Any]:
        """Execute a single step and update state."""
        from src.pipeline.generation_policy import assert_generation_step_allowed

        profile = assert_generation_step_allowed(state, step_name, force=force)
        _assert_quality_rewind_step_allowed(state, step_name)
        steps = state.get("steps", {})
        if step_name not in steps:
            raise ValueError(f"Step '{step_name}' not found in state steps")
        step_data = steps[step_name]

        # Resolve scenario-specific step order for next-step navigation
        scenario_cfg = _get_scenario_config(state.get("scenario", "s1"))
        step_order = list(profile.allowed_steps)

        # Skip if already done and not forcing
        if step_data["status"] == "done" and not force:
            logger.info("step_runner: step already done, skipping", step=step_name)
            next_step = _get_next_step(step_name, step_order)
            state["current_step"] = next_step
            await self.state_manager.save(state["label"], state)
            return state

        # Skip compliance if not in brand_mode
        config = state["config"]
        if step_name == "compliance" and not config.get("brand_mode"):
            logger.info("step_runner: skipping compliance (brand_mode=False)")
            step_data["status"] = "done"
            step_data["output"] = _record_step_transparency(
                state,
                step_name=step_name,
                output=None,
                skipped=True,
            )
            step_data["completed_at"] = datetime.now().isoformat()
            next_step = _get_next_step(step_name, step_order)
            state["current_step"] = next_step
            await self.state_manager.save(state["label"], state)
            return state

        # P1-2: In auto mode, thumbnail generation is a sidecar artifact.
        # Skip it when SKIP_THUMBNAIL_IN_AUTO env is set to reduce pipeline latency.
        # Thumbnails can be regenerated later without affecting the video.
        _skip_thumbnail = (
            step_name == "thumbnail_images"
            and state.get("mode") == "auto"
            and os.environ.get("SKIP_THUMBNAIL_IN_AUTO", "").lower() in ("1", "true", "yes")
        )
        if _skip_thumbnail:
            logger.info("step_runner: skipping thumbnail_images in auto mode (SKIP_THUMBNAIL_IN_AUTO)")
            step_data["status"] = "done"
            step_data["output"] = _record_step_transparency(
                state,
                step_name=step_name,
                output=[],
                skipped=True,
            )
            step_data["completed_at"] = datetime.now().isoformat()
            next_step = _get_next_step(step_name, step_order)
            state["current_step"] = next_step
            await self.state_manager.save(state["label"], state)
            return state

        state = attach_step_injection_visibility(state, step_name)
        step_data = state["steps"][step_name]

        # Mark step as started
        step_data["status"] = "pending"
        step_data["started_at"] = datetime.now().isoformat()
        # P1-1: In auto mode, skip intermediate save to reduce I/O.
        # The final save on step completion is sufficient for recovery.
        # step_by_step mode still saves so human review sees the latest state.
        from src.pipeline.generation_policy import ATTEMPT_GUARDED_STEPS

        if state.get("mode") != "auto" or step_name in ATTEMPT_GUARDED_STEPS:
            await self.state_manager.save(state["label"], state)

        step_start = time.perf_counter()
        trace_id = state.get("trace_id", "unknown")
        try:
            from src.pipeline.generation_policy import persisted_generation_policy_scope
            from src.services.provider_execution import (
                persisted_provider_execution_scope,
                provider_operation_scope,
                resolve_provider_operation_scope,
            )

            async with persisted_provider_execution_scope(state):
                with persisted_generation_policy_scope(state):
                    async with provider_operation_scope(
                        resolve_provider_operation_scope(state.get("scenario", "s1"), step_name)
                    ):
                        # Instantiate only after all immutable execution guards passed.
                        pipeline_module, pipeline_class_name = scenario_cfg["pipeline_class"].rsplit(".", 1)
                        pipeline_module = __import__(pipeline_module, fromlist=[pipeline_class_name])
                        pipeline_class = getattr(pipeline_module, pipeline_class_name)
                        pipeline = pipeline_class()
                        result = await pipeline.run_step(step_name, state)
                        result = _record_step_transparency(
                            state,
                            step_name=step_name,
                            output=result,
                        )
        except Exception as exc:
            step_duration_ms = (time.perf_counter() - step_start) * 1000
            logger.error("step_runner: step failed", step=step_name, error=str(exc), trace_id=trace_id)
            step_data["status"] = "error"
            state["errors"].append(f"{step_name}_failed: {exc}")
            state["pipeline_degraded"] = True
            state["degraded_reason"] = step_name
            from src.tools.error_classifier import classify_error

            structured = classify_error(exc, context=step_name, node=step_name)
            state.setdefault("structured_errors", [])
            state["structured_errors"].append(structured.model_dump())
            error_collector.collect(
                label=state["label"],
                trace_id=trace_id,
                step=step_name,
                error=str(exc),
                context={"label": state["label"], "step": step_name, "trace_id": trace_id},
            )
            pipeline_metrics.record_step(
                label=state["label"],
                step_name=step_name,
                duration_ms=step_duration_ms,
                success=False,
            )
            await self.state_manager.save(state["label"], state)
            return state

        step_duration_ms = (time.perf_counter() - step_start) * 1000
        pipeline_metrics.record_step(
            label=state["label"],
            step_name=step_name,
            duration_ms=step_duration_ms,
            success=True,
        )

        regen_signal = _detect_regenerate_signal(result)
        if regen_signal is not None:
            return await self._handle_regenerate_signal(
                state=state,
                step_name=step_name,
                step_data=step_data,
                step_duration_ms=step_duration_ms,
                signal=regen_signal,
                trace_id=trace_id,
            )

        step_data["output"] = result
        step_data["status"] = "done"
        step_data["completed_at"] = datetime.now().isoformat()
        step_data["duration_ms"] = round(step_duration_ms)
        _record_quality_rewind_step_completion(state, step_name)

        if step_name == "continuity_storyboard_grid":
            _mirror_continuity_output(state, result)

        if step_name == "seedance_clips" and _result_indicates_all_stubs(result):
            state["pipeline_degraded"] = True
            state["degraded_reason"] = "all_seedance_clips_are_stubs"
            state.setdefault("errors", []).append(
                "seedance API returned all stub clips; check POYO_API_KEY + content moderation"
            )
            logger.warning(
                "step_runner: all seedance clips are stubs, pipeline degraded",
                label=state["label"],
                trace_id=trace_id,
            )

        soft_signal = _result_indicates_soft_degraded(result)
        if soft_signal is not None:
            state.setdefault("soft_degraded_reasons", []).append(
                {
                    "ts": datetime.now().isoformat(),
                    "step": step_name,
                    "reason": soft_signal["reason"],
                    "detail": soft_signal["detail"],
                    "trace_id": trace_id,
                }
            )
            logger.warning(
                "step_runner: soft degraded, continuing with fallback",
                step=step_name,
                reason=soft_signal["reason"],
                trace_id=trace_id,
            )

        # Gate pause: if this step is a gate trigger and NOT auto mode, pause here
        scenario = state.get("scenario", "s1")
        if step_name in _get_gate_after_steps(scenario) and state.get("mode") != "auto":
            gate_id = _get_gate_id_for_step(step_name, scenario)
            state.setdefault("gates", {})
            state["gates"][gate_id] = {
                "status": "awaiting_approval",
                "candidates": [],
                "selections": [],
            }
            # Don't advance current_step -- stay at this step until approved
            state["current_step"] = step_name
            state["gate_status"] = "awaiting_approval"
            await self.state_manager.save(state["label"], state)
            logger.info("step_runner: gate pause", step=step_name, gate=gate_id)
            return state

        next_step = _get_next_step(step_name, step_order)
        state["current_step"] = next_step
        if next_step is None and not state.get("pipeline_degraded"):
            _mark_execution_terminal(state, profile=profile)

        await self.state_manager.save(state["label"], state)
        logger.info(
            "step_runner: step complete",
            step=step_name,
            label=state["label"],
            trace_id=trace_id,
            duration_ms=round(step_duration_ms, 2),
        )
        return state

    async def _handle_regenerate_signal(
        self,
        state: dict[str, Any],
        step_name: str,
        step_data: dict[str, Any],
        step_duration_ms: float,
        signal: dict[str, Any],
        trace_id: str,
    ) -> dict[str, Any]:
        """TODO-D11: handle a feedback_gate regenerate-upstream signal.

        Records one entry to state.regenerate_chain (audit trail), bumps
        the upstream step's _quality_attempt counter, then re-queues the
        upstream step by setting current_step + status='pending'. The
        downstream step that emitted the signal stays unchanged so the
        next loop will re-run it after upstream regenerates.
        """
        upstream_skill = signal.get("_regenerate_upstream") or signal.get("regenerate_upstream") or ""
        upstream_step = (
            _SCENARIO_REGENERATE_STEP_MAP.get(upstream_skill, upstream_skill)
            if type(upstream_skill) is str
            else ""
        )
        steps = state.get("steps", {})
        if (
            type(upstream_skill) is not str
            or not upstream_skill
            or type(upstream_step) is not str
            or upstream_step not in steps
        ):
            logger.warning(
                "step_runner: regenerate signal points at unknown upstream step",
                upstream_skill=upstream_skill,
                upstream_step=upstream_step,
                consumer=step_name,
                trace_id=trace_id,
            )
            _mark_quality_rewind_invalid(
                state,
                step_data,
                "quality_rewind_upstream_invalid",
            )
            await self.state_manager.save(state["label"], state)
            return state

        upstream_step_data = steps[upstream_step]
        raw_attempt = signal.get("attempt")
        durable_attempt = upstream_step_data.get("_quality_attempt", 0)
        if (
            type(raw_attempt) is not int
            or type(durable_attempt) is not int
            or raw_attempt != durable_attempt
            or not 0 <= durable_attempt < _QUALITY_REWIND_MAX_ATTEMPTS
        ):
            _mark_quality_rewind_invalid(
                state,
                step_data,
                "quality_rewind_attempt_invalid",
            )
            await self.state_manager.save(state["label"], state)
            return state

        from src.pipeline.generation_policy import assert_generation_step_allowed
        from src.services.provider_execution import (
            persist_trusted_regeneration_epoch,
        )

        chain: list[dict[str, Any]] = state.setdefault("regenerate_chain", [])
        attempt = durable_attempt + 1
        chain.append(
            {
                "ts": datetime.now().isoformat(),
                "consumer": step_name,
                "upstream_skill": upstream_skill,
                "upstream_step": upstream_step,
                "score": signal.get("score"),
                "reason": signal.get("reason", ""),
                "attempt": attempt,
                "trace_id": trace_id,
            }
        )

        upstream_step_data["status"] = "pending"
        upstream_step_data["_quality_attempt"] = attempt
        upstream_step_data.pop("completed_at", None)
        step_data["status"] = "pending"
        step_data.pop("completed_at", None)
        config = state.setdefault("config", {})
        config["quality_rewind"] = {
            "upstream_step": upstream_step,
            "consumer_step": step_name,
            "attempt": attempt,
            "status": "awaiting_upstream",
        }
        state["current_step"] = upstream_step

        assert_generation_step_allowed(state, upstream_step, force=True)
        await persist_trusted_regeneration_epoch(
            state,
            state_writer=self.state_manager,
            operation_key=f"feedback.regenerate.{upstream_step}",
        )

        logger.info(
            "step_runner: feedback_gate regenerate dispatched",
            consumer=step_name,
            upstream_step=upstream_step,
            attempt=attempt,
            score=signal.get("score"),
            trace_id=trace_id,
        )
        return state
