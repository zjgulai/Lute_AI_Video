"""Step runner for executing individual pipeline steps with state management.

The StepRunner loads pipeline state, executes a single step using the
S1ProductDirectPipeline methods, and persists the updated state back to disk.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

import structlog

from src.pipeline.gate_manager import SCENARIO_GATE_DEFINITIONS
from src.pipeline.state_manager import PipelineStateManager
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
    elif isinstance(result, list) and result and isinstance(result[0], dict) and result[0].get("_soft_degraded") is True:
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
        "step_order": STEP_ORDER,
        "pipeline_class": "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline",
    },
    "s2": {
        # S2 Brand Campaign is an S1 wrapper (brand_mode=True) — same steps, same class
        "step_order": STEP_ORDER,
        "pipeline_class": "src.pipeline.s1_product_pipeline.S1ProductDirectPipeline",
    },
    "s4": {
        "step_order": [
            "scripts",
            "video_prompts",
            "thumbnails",
            "seedance_clips",
            "tts_audio",
            "assemble_final",
            "audit",
        ],
        "pipeline_class": "src.pipeline.s4_live_shoot_pipeline.S4LiveShootPipeline",
    },
    "s3": {
        "step_order": [
            "video_analysis",
            "character_identity",
            "remix_script",
            "storyboards",
            "keyframe_images",
            "video_prompts",
            "thumbnail_prompts",
            "seedance_clips",
            "tts_audio",
            "thumbnail_images",
            "assemble_final",
            "audit",
        ],
        "pipeline_class": "src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline",
    },
    "s5": {
        "step_order": [
            "vlog_strategy",
            "video_prompts",
            "seedance_clips",
            "tts_audio",
            "assemble_final",
            "audit",
        ],
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
        config = _with_continuity_defaults(config, scenario)

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
        state = {
            "schema_version": STATE_SCHEMA_VERSION,
            "label": label,
            "scenario": scenario,
            "tenant_id": auth_ctx.tenant_id if auth_ctx else config.get("tenant_id", "default"),
            "config": config,
            "steps": steps,
            "current_step": step_order[0],
            "mode": mode,
            "trace_id": trace_id,
            "errors": [],
            "media_synthesis_errors": [],
        }

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

    async def regenerate_step(self, label: str, step_name: str) -> dict[str, Any]:
        """Force re-execution of a step even if it is already done."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        scenario_cfg = _get_scenario_config(state.get("scenario", "s1"))
        if step_name not in scenario_cfg["step_order"]:
            raise ValueError(f"Unknown step name: {step_name}")

        return await self._execute_step(state, step_name, force=True)

    async def resume(self, label: str) -> dict[str, Any]:
        """Run from current_step until completion, returning the final state."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        current = state.get("current_step")
        if current is None:
            logger.info("step_runner: no current_step, pipeline already complete", label=label)
            return state

        # Find the index of current_step
        scenario_cfg = _get_scenario_config(state.get("scenario", "s1"))
        step_order = scenario_cfg["step_order"]
        try:
            start_idx = step_order.index(current)
        except ValueError:
            raise ValueError(f"Invalid current_step in state: {current}")

        pipeline_start = time.perf_counter()
        total_errors = len(state.get("errors", []))
        success = True

        for step_name in step_order[start_idx:]:
            # P0: Degraded guard — if any previous step set pipeline_degraded, stop
            if state.get("pipeline_degraded"):
                logger.error("step_runner: pipeline degraded, halting", step=step_name, reason=state.get("degraded_reason"))
                success = False
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
            total_errors = len(state.get("errors", []))

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

        pipeline_duration_ms = (time.perf_counter() - pipeline_start) * 1000
        scenario = state.get("scenario", "unknown")
        trace_id = state.get("trace_id", "unknown")

        pipeline_metrics.record_pipeline(
            label=label,
            scenario=scenario,
            total_duration_ms=pipeline_duration_ms,
            success=success,
            error_count=total_errors,
        )
        logger.info(
            "step_runner: pipeline complete",
            label=label,
            trace_id=trace_id,
            scenario=scenario,
            total_duration_ms=round(pipeline_duration_ms, 2),
            success=success,
            error_count=total_errors,
        )
        return state

    async def _execute_step(self, state: dict[str, Any], step_name: str, force: bool = False) -> dict[str, Any]:
        """Execute a single step and update state."""
        steps = state.get("steps", {})
        if step_name not in steps:
            raise ValueError(f"Step '{step_name}' not found in state steps")
        step_data = steps[step_name]

        # Resolve scenario-specific step order for next-step navigation
        scenario_cfg = _get_scenario_config(state.get("scenario", "s1"))
        step_order = scenario_cfg["step_order"]

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
            step_data["output"] = None
            step_data["completed_at"] = datetime.now().isoformat()
            next_step = _get_next_step(step_name, step_order)
            state["current_step"] = next_step
            await self.state_manager.save(state["label"], state)
            return state

        # Mark step as started
        step_data["status"] = "pending"
        step_data["started_at"] = datetime.now().isoformat()
        await self.state_manager.save(state["label"], state)

        # Instantiate pipeline and run the step (lazy import to avoid circular dep)
        pipeline_module, pipeline_class_name = scenario_cfg["pipeline_class"].rsplit(".", 1)
        pipeline_module = __import__(pipeline_module, fromlist=[pipeline_class_name])
        pipeline_class = getattr(pipeline_module, pipeline_class_name)
        pipeline = pipeline_class()
        step_start = time.perf_counter()
        trace_id = state.get("trace_id", "unknown")
        try:
            # Sprint 3 P3-4 (Phase 0 fix): hard budget enforcement for Expert
            # mode. Inside try: so BudgetExceededError flows through the
            # existing degraded handler — sets pipeline_degraded=True,
            # degraded_reason, structured_errors. Without this, the prior
            # placement (outside try) caused HTTP 500 / stuck pending state.
            from src.tools.cost_tracker import check_budget
            check_budget(state.get("label"), state.get("mode", "auto"))
            result = await pipeline.run_step(step_name, state)
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
            state.setdefault("soft_degraded_reasons", []).append({
                "ts": datetime.now().isoformat(),
                "step": step_name,
                "reason": soft_signal["reason"],
                "detail": soft_signal["detail"],
                "trace_id": trace_id,
            })
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

        await self.state_manager.save(state["label"], state)
        logger.info("step_runner: step complete", step=step_name, label=state["label"], trace_id=trace_id, duration_ms=round(step_duration_ms, 2))
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
        upstream_step = _SCENARIO_REGENERATE_STEP_MAP.get(upstream_skill, upstream_skill)
        steps = state.get("steps", {})
        if upstream_step not in steps:
            logger.warning(
                "step_runner: regenerate signal points at unknown upstream step",
                upstream_skill=upstream_skill,
                upstream_step=upstream_step,
                consumer=step_name,
                trace_id=trace_id,
            )
            step_data["status"] = "done"
            step_data["completed_at"] = datetime.now().isoformat()
            step_data["duration_ms"] = round(step_duration_ms)
            await self.state_manager.save(state["label"], state)
            return state

        chain: list[dict[str, Any]] = state.setdefault("regenerate_chain", [])
        attempt = int(signal.get("attempt", 0)) + 1
        chain.append({
            "ts": datetime.now().isoformat(),
            "consumer": signal.get("consumer", step_name),
            "upstream_skill": upstream_skill,
            "upstream_step": upstream_step,
            "score": signal.get("score"),
            "reason": signal.get("reason", ""),
            "attempt": attempt,
            "trace_id": trace_id,
        })

        upstream_step_data = steps[upstream_step]
        upstream_step_data["status"] = "pending"
        upstream_step_data["_quality_attempt"] = attempt
        upstream_step_data.pop("completed_at", None)
        step_data["status"] = "pending"
        step_data.pop("completed_at", None)
        state["current_step"] = upstream_step
        logger.info(
            "step_runner: feedback_gate regenerate dispatched",
            consumer=step_name,
            upstream_step=upstream_step,
            attempt=attempt,
            score=signal.get("score"),
            trace_id=trace_id,
        )
        await self.state_manager.save(state["label"], state)
        return state
