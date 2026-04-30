"""Step runner for executing individual pipeline steps with state management.

The StepRunner loads pipeline state, executes a single step using the
S1ProductDirectPipeline methods, and persists the updated state back to disk.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import structlog

from src.pipeline.gate_manager import GATE_DEFINITIONS
from src.pipeline.state_manager import PipelineStateManager
from src.skills.registry import SkillRegistry
from src.telemetry import generate_trace_id, pipeline_metrics, error_collector

# After these steps complete, pause for gate approval in expert mode
GATE_AFTER_STEPS = {g["after_step"] for g in GATE_DEFINITIONS.values()}

logger = structlog.get_logger()

# Ordered list of all pipeline step names
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

# Mapping of step names to the S1ProductDirectPipeline method names
STEP_METHOD_MAP = {
    "strategy": "_step_strategy",
    "scripts": "_step_scripts",
    "compliance": "_step_compliance",
    "storyboards": "_step_storyboards",
    "keyframe_images": "_step_keyframe_images",
    "video_prompts": "_step_video_prompts",
    "thumbnail_prompts": "_step_thumbnail_prompts",
    "seedance_clips": "_step_seedance_clips",
    "tts_audio": "_step_tts_audio",
    "thumbnail_images": "_step_thumbnail_images",
    "assemble_final": "_step_assemble_final",
    "audit": "_step_audit",
}


def _get_next_step(step_name: str) -> str | None:
    """Return the next step name after the given step, or None if last."""
    try:
        idx = STEP_ORDER.index(step_name)
        if idx + 1 < len(STEP_ORDER):
            return STEP_ORDER[idx + 1]
    except ValueError:
        pass
    return None


def _get_step_input(state: dict, step_name: str, input_key: str) -> Any:
    """Retrieve input from a previous step's output or edited_output."""
    steps = state.get("steps", {})
    step_data = steps.get(input_key, {})
    if step_data.get("edited") and step_data.get("edited_output") is not None:
        return step_data["edited_output"]
    return step_data.get("output")


def _get_gate_id_for_step(step_name: str) -> str:
    """Return the gate_id whose after_step matches the given step_name, or ''."""
    for gate_id, gate_def in GATE_DEFINITIONS.items():
        if gate_def["after_step"] == step_name:
            return gate_id
    return ""


class StepRunner:
    """Runs individual steps of the S1 pipeline using state persistence."""

    def __init__(self, state_manager: PipelineStateManager) -> None:
        self.state_manager = state_manager

    async def init_state(
        self,
        config: dict,
        mode: str = "auto",
        label: str | None = None,
    ) -> str:
        """Create initial empty pipeline state, save it, and return the label."""
        if label is None:
            label = f"s1_{int(time.time())}"

        scenario = "brand_campaign" if config.get("brand_mode") else "product_direct"

        # Build empty step statuses
        steps = {}
        for step_name in STEP_ORDER:
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
        state = {
            "label": label,
            "scenario": scenario,
            "config": config,
            "steps": steps,
            "current_step": STEP_ORDER[0],
            "mode": mode,
            "trace_id": trace_id,
            "errors": [],
            "media_synthesis_errors": [],
        }

        await self.state_manager.save(label, state)
        logger.info("step_runner: state initialized", label=label, mode=mode, trace_id=trace_id)
        return label

    async def run_step(self, label: str, step_name: str) -> dict:
        """Load state, execute the specified step, save state back, and return state."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        if step_name not in STEP_ORDER:
            raise ValueError(f"Unknown step name: {step_name}")

        return await self._execute_step(state, step_name, force=False)

    async def regenerate_step(self, label: str, step_name: str) -> dict:
        """Force re-execution of a step even if it is already done."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        if step_name not in STEP_ORDER:
            raise ValueError(f"Unknown step name: {step_name}")

        return await self._execute_step(state, step_name, force=True)

    async def resume(self, label: str) -> dict:
        """Run from current_step until completion, returning the final state."""
        state = await self.state_manager.load(label)
        if state is None:
            raise ValueError(f"State not found for label: {label}")

        current = state.get("current_step")
        if current is None:
            logger.info("step_runner: no current_step, pipeline already complete", label=label)
            return state

        # Find the index of current_step
        try:
            start_idx = STEP_ORDER.index(current)
        except ValueError:
            raise ValueError(f"Invalid current_step in state: {current}")

        pipeline_start = time.perf_counter()
        total_errors = len(state.get("errors", []))
        success = True

        for step_name in STEP_ORDER[start_idx:]:
            # Gate check: if this step has a gate awaiting approval, pause and return
            gate_id = _get_gate_id_for_step(step_name)
            if gate_id:
                gate_state = state.get("gates", {}).get(gate_id, {})
                if gate_state.get("status") == "awaiting_approval":
                    logger.info("step_runner: gate awaiting approval, pausing", gate=gate_id)
                    state["current_step"] = step_name
                    await self.state_manager.save(state["label"], state)
                    return state
            try:
                state = await self._execute_step(state, step_name, force=False)
            except Exception:
                success = False
                raise
            finally:
                total_errors = len(state.get("errors", []))

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

    async def _execute_step(self, state: dict, step_name: str, force: bool = False) -> dict:
        """Execute a single step and update state."""
        steps = state.get("steps", {})
        if step_name not in steps:
            raise ValueError(f"Step '{step_name}' not found in state steps")
        step_data = steps[step_name]

        # Skip if already done and not forcing
        if step_data["status"] == "done" and not force:
            logger.info("step_runner: step already done, skipping", step=step_name)
            next_step = _get_next_step(step_name)
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
            next_step = _get_next_step(step_name)
            state["current_step"] = next_step
            await self.state_manager.save(state["label"], state)
            return state

        # Mark step as started
        step_data["status"] = "pending"
        step_data["started_at"] = datetime.now().isoformat()
        await self.state_manager.save(state["label"], state)

        # Instantiate pipeline and run the step (lazy import to avoid circular dep)
        from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
        pipeline = S1ProductDirectPipeline()
        step_start = time.perf_counter()
        trace_id = state.get("trace_id", "unknown")
        try:
            result = await pipeline.run_step(step_name, state)
        except Exception as exc:
            step_duration_ms = (time.perf_counter() - step_start) * 1000
            logger.error("step_runner: step failed", step=step_name, error=str(exc), trace_id=trace_id)
            step_data["status"] = "error"
            state["errors"].append(f"{step_name}_failed: {exc}")
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
            raise

        step_duration_ms = (time.perf_counter() - step_start) * 1000
        pipeline_metrics.record_step(
            label=state["label"],
            step_name=step_name,
            duration_ms=step_duration_ms,
            success=True,
        )

        # Update state with result and actual duration
        step_data["output"] = result
        step_data["status"] = "done"
        step_data["completed_at"] = datetime.now().isoformat()
        step_data["duration_ms"] = round(step_duration_ms)

        # Gate pause: if this step is a gate trigger and NOT auto mode, pause here
        if step_name in GATE_AFTER_STEPS and state.get("mode") != "auto":
            gate_id = _get_gate_id_for_step(step_name)
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

        next_step = _get_next_step(step_name)
        state["current_step"] = next_step

        await self.state_manager.save(state["label"], state)
        logger.info("step_runner: step complete", step=step_name, label=state["label"], trace_id=trace_id, duration_ms=round(step_duration_ms, 2))
        return state
