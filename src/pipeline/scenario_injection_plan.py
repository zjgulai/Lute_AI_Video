"""Read-only scenario injection planning for BrandConstraintBundle."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from src.models.commercial_contracts import BrandConstraintBundle
from src.pipeline.runtime_injection_executor import (
    CURRENT_RUNTIME_INJECTION_KEY,
    STEP_RUNTIME_INJECTION_DATA_KEY,
    RuntimeInjectionResult,
    build_runtime_injection_result,
    find_reviewed_brand_bundle,
)
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS

SCENARIO_INJECTION_CONFIG_KEY = "commercial_injection_plan"
SCENARIO_INJECTION_MODE_KEY = "commercial_injection_mode"
SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY = "commercial_injection_evidence_level"
CURRENT_STEP_INJECTION_KEY = "current_step_injection"
STEP_INJECTION_DATA_KEY = "commercial_injection"
SCENARIO_INJECTION_MODE = "read_only_blueprint"
SCENARIO_INJECTION_EVIDENCE_LEVEL = "L2-fixture-or-dry-run"


class StepInjectionBlueprint(BaseModel):
    bundle_refs: list[str] = Field(default_factory=list)
    toolbox_refs: list[str] = Field(default_factory=list)
    contract_refs: list[str] = Field(default_factory=list)
    gate_checks: list[str] = Field(default_factory=list)


C6_FIRST_PASS_BLUEPRINTS: dict[str, dict[str, StepInjectionBlueprint]] = {
    "s1": {
        "strategy": StepInjectionBlueprint(
            bundle_refs=["ProductTruthBundle"],
            contract_refs=["StrategyBrief"],
        ),
        "storyboards": StepInjectionBlueprint(
            toolbox_refs=["DesignAssetToolbox"],
            contract_refs=["StoryboardShotSchema"],
        ),
        "keyframe_images": StepInjectionBlueprint(
            toolbox_refs=["ImageToolbox"],
            gate_checks=["claim_substantiation_pass", "hard_brand_token_pass"],
        ),
        "video_prompts": StepInjectionBlueprint(
            gate_checks=["claim_substantiation_pass", "rights_pass"],
        ),
        "audit": StepInjectionBlueprint(
            contract_refs=["QualityContract", "AuditEvidenceBundle"],
            gate_checks=["claim_substantiation_pass", "rights_pass"],
        ),
    },
    "s2": {
        "strategy": StepInjectionBlueprint(
            bundle_refs=["BrandConstraintBundle", "CampaignAssetPack"],
            contract_refs=["StrategyBrief"],
        ),
        "storyboards": StepInjectionBlueprint(
            toolbox_refs=["StoryboardToolbox"],
            contract_refs=["StoryboardShotSchema"],
        ),
        "video_prompts": StepInjectionBlueprint(
            gate_checks=["hard_brand_token_pass", "platform_policy_pass"],
        ),
        "audit": StepInjectionBlueprint(
            contract_refs=["QualityContract", "AuditEvidenceBundle"],
            gate_checks=["hard_brand_token_pass", "platform_policy_pass"],
        ),
    },
    "s3": {
        "video_analysis": StepInjectionBlueprint(
            bundle_refs=["SourceFingerprintLedger"],
            contract_refs=["TranscriptTimeline"],
            gate_checks=["source_rights_pass", "source_fingerprint_pass"],
        ),
        "character_identity": StepInjectionBlueprint(
            toolbox_refs=["IdentityAbstractionToolbox"],
            gate_checks=["visible_likeness_pass", "source_rights_pass"],
        ),
        "remix_script": StepInjectionBlueprint(
            bundle_refs=["RemixBoundaryBundle"],
            contract_refs=["TranscriptTimeline"],
            gate_checks=["source_fingerprint_pass", "rights_pass"],
        ),
        "storyboards": StepInjectionBlueprint(
            toolbox_refs=["StoryboardToolbox"],
            contract_refs=["SceneLedger", "ShotLedger"],
            gate_checks=["remix_boundary_pass"],
        ),
        "continuity_storyboard_grid": StepInjectionBlueprint(
            toolbox_refs=["ContinuityToolbox"],
            contract_refs=["TimelineManifest"],
        ),
        "video_prompts": StepInjectionBlueprint(
            gate_checks=["source_fingerprint_pass", "hard_brand_token_pass"],
        ),
        "audit": StepInjectionBlueprint(
            contract_refs=["QualityContract", "AuditEvidenceBundle", "EditDecisionList"],
            gate_checks=["source_fingerprint_pass", "rights_pass", "remix_boundary_pass"],
        ),
    },
    "s4": {
        "scripts": StepInjectionBlueprint(
            bundle_refs=["FootageAssetBundle"],
            contract_refs=["SceneLedger"],
            gate_checks=["rights_pass"],
        ),
        "continuity_storyboard_grid": StepInjectionBlueprint(
            toolbox_refs=["CutdownToolbox"],
            contract_refs=["ShotLedger", "TimelineManifest"],
        ),
        "video_prompts": StepInjectionBlueprint(
            contract_refs=["ReframeJob"],
            gate_checks=["caption_safe_zone_pass", "rights_pass"],
        ),
        "thumbnails": StepInjectionBlueprint(
            toolbox_refs=["ThumbnailToolbox"],
            gate_checks=["platform_policy_pass"],
        ),
        "seedance_clips": StepInjectionBlueprint(
            contract_refs=["CutdownPlan", "ReframeJob"],
            gate_checks=["footage_rights_pass"],
        ),
        "assemble_final": StepInjectionBlueprint(
            contract_refs=["EditDecisionList", "TimelineManifest"],
            gate_checks=["caption_safe_zone_pass"],
        ),
        "audit": StepInjectionBlueprint(
            contract_refs=["QualityContract", "AuditEvidenceBundle", "CutdownPlan", "ReframeJob"],
            gate_checks=["rights_pass", "caption_safe_zone_pass", "source_fingerprint_pass"],
        ),
    },
    "s5": {
        "vlog_strategy": StepInjectionBlueprint(
            bundle_refs=["PersonaSceneBundle"],
            contract_refs=["StrategyBrief"],
            gate_checks=["children_safety_pass"],
        ),
        "video_prompts": StepInjectionBlueprint(
            gate_checks=["children_safety_pass", "rights_pass"],
        ),
        "tts_audio": StepInjectionBlueprint(
            bundle_refs=["AudioCueLedger"],
            gate_checks=["children_safety_pass"],
        ),
        "audit": StepInjectionBlueprint(
            contract_refs=["QualityContract", "AuditEvidenceBundle"],
            gate_checks=["children_safety_pass", "rights_pass"],
        ),
    },
}


class ScenarioStepInjection(BaseModel):
    scenario: str
    step: str
    hard_token_ids: list[str] = Field(default_factory=list)
    soft_token_ids: list[str] = Field(default_factory=list)
    source_token_ids: list[str] = Field(default_factory=list)
    bundle_refs: list[str] = Field(default_factory=list)
    toolbox_refs: list[str] = Field(default_factory=list)
    contract_refs: list[str] = Field(default_factory=list)
    gate_checks: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ScenarioInjectionPlan(BaseModel):
    scenario: str
    brand_id: str
    platform: str | None = None
    steps: list[ScenarioStepInjection] = Field(default_factory=list)
    read_only: bool = True
    evidence_level: str = SCENARIO_INJECTION_EVIDENCE_LEVEL


def plan_scenario_injection(
    *,
    scenario: str,
    brand_id: str,
    tokens_bundle_factory: Callable[[str], BrandConstraintBundle],
    platform: str | None = None,
) -> ScenarioInjectionPlan:
    """Compute which approved bundle tokens would be injected into each step.

    ``tokens_bundle_factory`` is a callable so this planner stays read-only and
    does not know how tokens are stored. It must return a BrandConstraintBundle
    for each step.
    """
    steps: list[ScenarioStepInjection] = []
    for step in SCENARIO_STEP_ORDERS.get(scenario, []):
        bundle: BrandConstraintBundle = tokens_bundle_factory(step)
        blueprint = C6_FIRST_PASS_BLUEPRINTS.get(scenario, {}).get(step, StepInjectionBlueprint())
        notes: list[str] = []
        if bundle.rejected_token_ids:
            notes.append("non-approved or out-of-scope tokens excluded")
        steps.append(ScenarioStepInjection(
            scenario=scenario,
            step=step,
            hard_token_ids=[token.token_id for token in bundle.hard_tokens],
            soft_token_ids=[token.token_id for token in bundle.soft_tokens],
            source_token_ids=bundle.source_token_ids,
            bundle_refs=blueprint.bundle_refs,
            toolbox_refs=blueprint.toolbox_refs,
            contract_refs=blueprint.contract_refs,
            gate_checks=blueprint.gate_checks,
            notes=notes,
        ))

    return ScenarioInjectionPlan(
        scenario=scenario,
        brand_id=brand_id,
        platform=platform,
        steps=steps,
    )


def build_injection_config_patch(plan: ScenarioInjectionPlan) -> dict[str, Any]:
    """Build a JSON-safe config patch that StepRunner can persist unchanged."""
    return {
        SCENARIO_INJECTION_CONFIG_KEY: plan.model_dump(mode="json"),
        SCENARIO_INJECTION_MODE_KEY: SCENARIO_INJECTION_MODE,
        SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY: plan.evidence_level,
    }


def with_injection_config(config: dict[str, Any], plan: ScenarioInjectionPlan) -> dict[str, Any]:
    """Return a copy of config with the read-only injection plan attached."""
    return {
        **config,
        **build_injection_config_patch(plan),
    }


def with_optional_injection_config(
    config: dict[str, Any],
    plan_payload: ScenarioInjectionPlan | dict[str, Any] | None,
    *,
    expected_scenario: str,
) -> dict[str, Any]:
    """Attach a read-only injection plan when provided, failing closed on scenario drift."""
    if plan_payload is None:
        return dict(config)

    plan = (
        plan_payload
        if isinstance(plan_payload, ScenarioInjectionPlan)
        else ScenarioInjectionPlan.model_validate(plan_payload)
    )
    if plan.scenario != expected_scenario:
        raise ValueError(
            f"injection plan scenario mismatch: expected {expected_scenario}, got {plan.scenario}"
        )
    return with_injection_config(config, plan)


def get_step_injection_from_state(state: dict[str, Any], step_name: str) -> ScenarioStepInjection | None:
    """Read one step's C6 injection blueprint from a persisted pipeline state."""
    config = state.get("config", {})
    plan_payload = config.get(SCENARIO_INJECTION_CONFIG_KEY)
    if plan_payload is None:
        plan_payload = state.get(SCENARIO_INJECTION_CONFIG_KEY)
    if plan_payload is None:
        return None

    plan = plan_payload if isinstance(plan_payload, ScenarioInjectionPlan) else ScenarioInjectionPlan.model_validate(plan_payload)
    if plan.scenario != state.get("scenario"):
        return None
    for step in plan.steps:
        if step.step == step_name:
            return step
    return None


def attach_step_injection_visibility(state: dict[str, Any], step_name: str) -> dict[str, Any]:
    """Expose one step's read-only injection metadata without executing it."""
    state.pop(CURRENT_STEP_INJECTION_KEY, None)
    state.pop(CURRENT_RUNTIME_INJECTION_KEY, None)
    steps = state.get("steps", {})
    step_data = steps.get(step_name)
    if isinstance(step_data, dict):
        step_data.pop(STEP_INJECTION_DATA_KEY, None)
        step_data.pop(STEP_RUNTIME_INJECTION_DATA_KEY, None)

    injection = get_step_injection_from_state(state, step_name)
    if injection is None:
        return state

    payload = injection.model_dump(mode="json")
    runtime_payload = _build_runtime_injection_visibility(state, payload)
    state[CURRENT_STEP_INJECTION_KEY] = payload
    state[CURRENT_RUNTIME_INJECTION_KEY] = runtime_payload
    if isinstance(step_data, dict):
        step_data[STEP_INJECTION_DATA_KEY] = payload
        step_data[STEP_RUNTIME_INJECTION_DATA_KEY] = runtime_payload
    return state


def project_step_injection_visibility(state: dict[str, Any], step_name: str) -> dict[str, Any] | None:
    """Return one step's sanitized read-only injection projection."""
    injection = get_step_injection_from_state(state, step_name)
    if injection is not None:
        return injection.model_dump(mode="json")

    step_data = state.get("steps", {}).get(step_name)
    if not isinstance(step_data, dict):
        return None
    existing = step_data.get(STEP_INJECTION_DATA_KEY)
    if existing is None:
        return None
    try:
        return ScenarioStepInjection.model_validate(existing).model_dump(mode="json")
    except ValueError:
        return None


def project_current_step_injection_visibility(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return sanitized current-step injection metadata when available."""
    current_step = state.get("current_step")
    if isinstance(current_step, str) and current_step:
        projected = project_step_injection_visibility(state, current_step)
        if projected is not None:
            return projected

    existing = state.get(CURRENT_STEP_INJECTION_KEY)
    if existing is None:
        return None
    try:
        return ScenarioStepInjection.model_validate(existing).model_dump(mode="json")
    except ValueError:
        return None


def project_step_runtime_injection_visibility(state: dict[str, Any], step_name: str) -> dict[str, Any] | None:
    """Return one step's sanitized runtime injection projection."""
    injection = get_step_injection_from_state(state, step_name)
    if injection is not None:
        return _build_runtime_injection_visibility(state, injection.model_dump(mode="json"))

    step_data = state.get("steps", {}).get(step_name)
    if not isinstance(step_data, dict):
        return None
    existing = step_data.get(STEP_RUNTIME_INJECTION_DATA_KEY)
    if existing is None:
        return None
    try:
        return RuntimeInjectionResult.model_validate(existing).model_dump(mode="json")
    except ValueError:
        return None


def project_current_runtime_injection_visibility(state: dict[str, Any]) -> dict[str, Any] | None:
    """Return sanitized current-step runtime injection metadata when available."""
    current_step = state.get("current_step")
    if isinstance(current_step, str) and current_step:
        projected = project_step_runtime_injection_visibility(state, current_step)
        if projected is not None:
            return projected

    existing = state.get(CURRENT_RUNTIME_INJECTION_KEY)
    if existing is None:
        return None
    try:
        return RuntimeInjectionResult.model_validate(existing).model_dump(mode="json")
    except ValueError:
        return None


def project_state_injection_visibility(state: dict[str, Any]) -> dict[str, Any]:
    """Copy state with sanitized injection metadata added to top-level and steps."""
    projected_state = dict(state)
    projected_steps: dict[str, Any] = {}
    steps = state.get("steps", {})

    if isinstance(steps, dict):
        for step_name, step_data in steps.items():
            if not isinstance(step_data, dict):
                projected_steps[step_name] = step_data
                continue
            projected_step = dict(step_data)
            projected_step.pop(STEP_INJECTION_DATA_KEY, None)
            projected_step.pop(STEP_RUNTIME_INJECTION_DATA_KEY, None)
            injection = project_step_injection_visibility(state, step_name)
            if injection is not None:
                projected_step[STEP_INJECTION_DATA_KEY] = injection
            runtime_injection = project_step_runtime_injection_visibility(state, step_name)
            if runtime_injection is not None:
                projected_step[STEP_RUNTIME_INJECTION_DATA_KEY] = runtime_injection
            projected_steps[step_name] = projected_step
        projected_state["steps"] = projected_steps

    current_injection = project_current_step_injection_visibility(state)
    if current_injection is None:
        projected_state.pop(CURRENT_STEP_INJECTION_KEY, None)
    else:
        projected_state[CURRENT_STEP_INJECTION_KEY] = current_injection

    current_runtime_injection = project_current_runtime_injection_visibility(state)
    if current_runtime_injection is None:
        projected_state.pop(CURRENT_RUNTIME_INJECTION_KEY, None)
    else:
        projected_state[CURRENT_RUNTIME_INJECTION_KEY] = current_runtime_injection
    return projected_state


def _build_runtime_injection_visibility(
    state: dict[str, Any],
    planned_injection: dict[str, Any],
) -> dict[str, Any]:
    config = state.get("config", {})
    if not isinstance(config, dict):
        config = {}
    lookup = find_reviewed_brand_bundle(
        config=config,
        scenario=planned_injection["scenario"],
        step=planned_injection["step"],
    )
    return build_runtime_injection_result(
        planned_injection=planned_injection,
        bundle_lookup=lookup,
    ).model_dump(mode="json")
