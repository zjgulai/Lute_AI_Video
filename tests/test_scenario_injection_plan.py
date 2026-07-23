from __future__ import annotations

import json

import pytest

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    BrandConstraintBundle,
    LicenseStatus,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.runtime_injection_executor import (
    CURRENT_RUNTIME_INJECTION_KEY,
    STEP_RUNTIME_INJECTION_DATA_KEY,
    with_reviewed_brand_bundles,
)
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.pipeline.scenario_injection_plan import (
    CURRENT_STEP_INJECTION_KEY,
    SCENARIO_INJECTION_CONFIG_KEY,
    SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY,
    SCENARIO_INJECTION_MODE_KEY,
    STEP_INJECTION_DATA_KEY,
    attach_step_injection_visibility,
    build_injection_config_patch,
    get_step_injection_from_state,
    plan_scenario_injection,
    with_injection_config,
    with_optional_injection_config,
)
from tests.generation_policy_test_utils import (
    attach_execution_policy,
    attach_test_provider_execution_authority,
)


def test_scenario_injection_plan_is_read_only_and_excludes_candidate_tokens():
    approved = _token(
        token_id="bat_approved_script",
        status=TokenStatus.APPROVED,
        strength=TokenStrength.HARD,
        step_scope=["scripts"],
        license_status=LicenseStatus.APPROVED,
        review_status="approved",
    )
    candidate = _token(
        token_id="bat_candidate_script",
        status=TokenStatus.CANDIDATE,
        strength=TokenStrength.HARD_FOR_REVIEW_ONLY,
        step_scope=["scripts"],
        license_status=LicenseStatus.UNKNOWN,
    )
    tokens = [approved, candidate]

    def bundle_for_step(step: str) -> BrandConstraintBundle:
        return BrandConstraintBundle.build_approved(
            bundle_id=f"bundle_s1_{step}",
            brand_id="momcozy",
            scenario="s1",
            step=step,
            tokens=tokens,
        )

    plan = plan_scenario_injection(
        scenario="s1",
        brand_id="momcozy",
        tokens_bundle_factory=bundle_for_step,
        platform="tiktok",
    )
    script_step = next(step for step in plan.steps if step.step == "scripts")

    assert plan.read_only is True
    assert script_step.hard_token_ids == ["bat_approved_script"]
    assert "bat_candidate_script" not in script_step.source_token_ids
    assert script_step.notes == ["non-approved or out-of-scope tokens excluded"]


def test_unknown_scenario_returns_empty_read_only_plan():
    plan = plan_scenario_injection(
        scenario="s9",
        brand_id="momcozy",
        tokens_bundle_factory=lambda step: BrandConstraintBundle(
            bundle_id=f"bundle_{step}",
            brand_id="momcozy",
            scenario="s9",
            step=step,
        ),
    )

    assert plan.read_only is True
    assert plan.steps == []


def test_c6_s1_first_pass_blueprint_has_product_truth_and_claim_gate():
    plan = _empty_plan("s1")

    strategy_step = _step(plan, "strategy")
    image_step = _step(plan, "keyframe_images")
    audit_step = _step(plan, "audit")

    assert "ProductTruthBundle" in strategy_step.bundle_refs
    assert "DesignAssetToolbox" in _step(plan, "storyboards").toolbox_refs
    assert "ImageToolbox" in image_step.toolbox_refs
    assert "claim_substantiation_pass" in image_step.gate_checks
    assert "QualityContract" in audit_step.contract_refs


def test_c6_s2_first_pass_blueprint_has_campaign_and_brand_audit():
    plan = _empty_plan("s2")

    strategy_step = _step(plan, "strategy")
    storyboard_step = _step(plan, "storyboards")
    audit_step = _step(plan, "audit")

    assert strategy_step.bundle_refs == ["BrandConstraintBundle", "CampaignAssetPack"]
    assert storyboard_step.toolbox_refs == ["StoryboardToolbox"]
    assert "hard_brand_token_pass" in audit_step.gate_checks
    assert "platform_policy_pass" in audit_step.gate_checks


def test_c6_s5_first_pass_blueprint_has_persona_audio_and_children_gate():
    plan = _empty_plan("s5")

    strategy_step = _step(plan, "vlog_strategy")
    audio_step = _step(plan, "tts_audio")
    audit_step = _step(plan, "audit")

    assert "PersonaSceneBundle" in strategy_step.bundle_refs
    assert "AudioCueLedger" in audio_step.bundle_refs
    assert "children_safety_pass" in audio_step.gate_checks
    assert "children_safety_pass" in audit_step.gate_checks


def test_c7_s3_read_only_blueprint_has_source_fingerprint_transcript_and_remix_boundary():
    s3_plan = _empty_plan("s3")

    analysis_step = _step(s3_plan, "video_analysis")
    remix_step = _step(s3_plan, "remix_script")
    audit_step = _step(s3_plan, "audit")

    assert "SourceFingerprintLedger" in analysis_step.bundle_refs
    assert "TranscriptTimeline" in analysis_step.contract_refs
    assert "source_fingerprint_pass" in analysis_step.gate_checks
    assert "RemixBoundaryBundle" in remix_step.bundle_refs
    assert "remix_boundary_pass" in audit_step.gate_checks


def test_c7_s4_read_only_blueprint_has_footage_cutdown_reframe_and_caption_safe_zone():
    s4_plan = _empty_plan("s4")

    scripts_step = _step(s4_plan, "scripts")
    cutdown_step = _step(s4_plan, "continuity_storyboard_grid")
    reframe_step = _step(s4_plan, "video_prompts")
    audit_step = _step(s4_plan, "audit")

    assert "FootageAssetBundle" in scripts_step.bundle_refs
    assert "CutdownToolbox" in cutdown_step.toolbox_refs
    assert "ReframeJob" in reframe_step.contract_refs
    assert "caption_safe_zone_pass" in reframe_step.gate_checks
    assert "CutdownPlan" in audit_step.contract_refs


def test_c6_blueprint_uses_runtime_step_names():
    for scenario in ("s1", "s2", "s3", "s4", "s5"):
        plan = _empty_plan(scenario)
        plan_steps = {step.step for step in plan.steps}

        assert plan_steps == set(SCENARIO_STEP_ORDERS[scenario])
        assert all(step.step in SCENARIO_STEP_ORDERS[scenario] for step in plan.steps)


def test_c6_injection_config_patch_is_json_safe_and_read_only():
    plan = _empty_plan("s1")

    patch = build_injection_config_patch(plan)

    json.dumps(patch)
    assert patch[SCENARIO_INJECTION_MODE_KEY] == "read_only_blueprint"
    assert patch[SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY] == "L2-fixture-or-dry-run"
    assert patch[SCENARIO_INJECTION_CONFIG_KEY]["read_only"] is True


def test_c6_with_injection_config_does_not_mutate_original_config():
    plan = _empty_plan("s2")
    config = {"product_name": "Momcozy", "enable_media_synthesis": False}

    patched = with_injection_config(config, plan)

    assert SCENARIO_INJECTION_CONFIG_KEY not in config
    assert patched["product_name"] == "Momcozy"
    assert patched[SCENARIO_INJECTION_CONFIG_KEY]["scenario"] == "s2"


def test_c6_step_injection_can_be_read_from_persisted_state_shape():
    plan = _empty_plan("s5")
    state = {
        "scenario": "s5",
        "config": with_injection_config({"brand_id": "momcozy"}, plan),
    }

    step = get_step_injection_from_state(state, "vlog_strategy")

    assert step is not None
    assert step.bundle_refs == ["PersonaSceneBundle"]
    assert "children_safety_pass" in step.gate_checks


def test_c6_step_injection_fails_closed_when_state_scenario_mismatches_plan():
    plan = _empty_plan("s1")
    state = {
        "scenario": "s2",
        "config": with_injection_config({"brand_id": "momcozy"}, plan),
    }

    assert get_step_injection_from_state(state, "strategy") is None


def test_c6_attach_step_injection_visibility_exposes_current_step_metadata():
    state = {
        "scenario": "s1",
        "config": with_injection_config({"brand_id": "momcozy"}, _empty_plan("s1")),
        "steps": {"strategy": {}, "scripts": {}},
    }

    updated = attach_step_injection_visibility(state, "strategy")

    assert updated[CURRENT_STEP_INJECTION_KEY]["step"] == "strategy"
    assert updated["steps"]["strategy"][STEP_INJECTION_DATA_KEY]["bundle_refs"] == ["ProductTruthBundle"]
    assert STEP_INJECTION_DATA_KEY not in updated["steps"]["scripts"]


def test_c11_attach_step_injection_visibility_exposes_runtime_gate_result():
    config = with_reviewed_brand_bundles(
        with_injection_config({"brand_id": "momcozy"}, _empty_plan("s1")),
        [_reviewed_bundle("s1", "strategy")],
    )
    state = {
        "scenario": "s1",
        "config": config,
        "steps": {"strategy": {}, "scripts": {}},
    }

    updated = attach_step_injection_visibility(state, "strategy")
    runtime = updated[CURRENT_RUNTIME_INJECTION_KEY]

    assert runtime["prompt_injection_allowed"] is True
    assert runtime["hard_token_ids"] == ["bat_s1_strategy_runtime"]
    assert "payload" not in json.dumps(runtime)
    assert updated["steps"]["strategy"][STEP_RUNTIME_INJECTION_DATA_KEY] == runtime
    assert STEP_RUNTIME_INJECTION_DATA_KEY not in updated["steps"]["scripts"]


def test_c6_attach_step_injection_visibility_clears_stale_metadata_when_missing():
    state = {
        "scenario": "s2",
        "config": with_injection_config({"brand_id": "momcozy"}, _empty_plan("s1")),
        "steps": {
            "strategy": {STEP_INJECTION_DATA_KEY: {"step": "stale"}},
        },
        CURRENT_STEP_INJECTION_KEY: {"step": "stale"},
        CURRENT_RUNTIME_INJECTION_KEY: {"step": "stale"},
    }

    updated = attach_step_injection_visibility(state, "strategy")

    assert CURRENT_STEP_INJECTION_KEY not in updated
    assert CURRENT_RUNTIME_INJECTION_KEY not in updated
    assert STEP_INJECTION_DATA_KEY not in updated["steps"]["strategy"]


def test_c6_optional_injection_config_fails_closed_on_plan_scenario_mismatch():
    plan = _empty_plan("s1")

    try:
        with_optional_injection_config({"brand_id": "momcozy"}, plan, expected_scenario="s2")
    except ValueError as exc:
        assert "scenario mismatch" in str(exc)
    else:
        raise AssertionError("expected scenario mismatch to fail closed")


@pytest.mark.asyncio
async def test_c6_s1_run_passes_read_only_injection_plan_to_step_runner(monkeypatch):
    from src.pipeline import s1_product_pipeline

    captured: dict[str, object] = {}
    completion_calls: list[dict[str, object]] = []

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(self, config, mode="auto", label=None, scenario="s1"):
            captured["config"] = config
            captured["scenario"] = scenario
            return label or "s1_c6_fixture"

        async def run_step(self, label, step_name):
            return {"scenario": "s1", "steps": {}, "errors": [], "media_synthesis_errors": []}

        async def resume(self, label):
            return {"scenario": "s1", "steps": {}, "errors": [], "media_synthesis_errors": []}

        async def finalize_pipeline_completion(
            self, state: dict[str, object], *, started_at: float
        ) -> bool:
            completion_calls.append(state)
            return True

    monkeypatch.setattr(s1_product_pipeline, "StepRunner", FakeStepRunner)

    await s1_product_pipeline.S1ProductDirectPipeline().run(
        product_catalog={"product_name": "Momcozy Bottle Warmer"},
        enable_media_synthesis=False,
        commercial_injection_plan=_empty_plan("s1").model_dump(mode="json"),
    )

    config = captured["config"]
    assert config[SCENARIO_INJECTION_MODE_KEY] == "read_only_blueprint"
    assert get_step_injection_from_state({"scenario": "s1", "config": config}, "strategy") is not None
    assert len(completion_calls) == 1


@pytest.mark.asyncio
async def test_c6_s2_run_passes_read_only_injection_plan_to_step_runner(monkeypatch):
    from src.pipeline import s2_brand_pipeline_v2

    captured: dict[str, object] = {}
    completion_calls: list[dict[str, object]] = []

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(self, *, config, mode="auto", label=None, scenario="s2"):
            captured["config"] = config
            captured["scenario"] = scenario
            return label or "s2_c6_fixture"

        async def run_step(self, label, step_name):
            return {"scenario": "s2", "steps": {}, "errors": [], "media_synthesis_errors": []}

        async def resume(self, label):
            return {"scenario": "s2", "steps": {}, "errors": [], "media_synthesis_errors": []}

        async def finalize_pipeline_completion(
            self, state: dict[str, object], *, started_at: float
        ) -> bool:
            completion_calls.append(state)
            return True

    monkeypatch.setattr(s2_brand_pipeline_v2, "StepRunner", FakeStepRunner)

    await s2_brand_pipeline_v2.S2BrandCampaignPipeline().run(
        brand_package={"brand_name": "MomCozy"},
        enable_media_synthesis=False,
        commercial_injection_plan=_empty_plan("s2").model_dump(mode="json"),
    )

    config = captured["config"]
    assert captured["scenario"] == "s2"
    assert get_step_injection_from_state({"scenario": "s2", "config": config}, "audit") is not None
    assert len(completion_calls) == 1


@pytest.mark.asyncio
async def test_c6_s5_run_passes_read_only_injection_plan_to_step_runner(monkeypatch):
    from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline

    captured: dict[str, object] = {}
    completion_calls: list[dict[str, object]] = []

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(self, *, config, mode="auto", label=None, scenario="s5"):
            captured["config"] = config
            captured["scenario"] = scenario
            return label or "s5_c6_fixture"

        async def resume(self, label):
            return {
                "steps": {
                    "vlog_strategy": {"output": {"scripts": []}},
                    "video_prompts": {"output": []},
                    "seedance_clips": {"output": {"clip_paths": [], "clip_details": []}},
                    "tts_audio": {"output": []},
                    "assemble_final": {"output": ["", ""]},
                    "audit": {"output": {}},
                },
                "errors": [],
            }

        async def finalize_pipeline_completion(
            self, state: dict[str, object], *, started_at: float
        ) -> bool:
            completion_calls.append(state)
            return True

    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)

    await S5BrandVlogPipeline().run(
        brand_id="momcozy",
        product_sku={"name": "Bottle Warmer"},
        selected_models=[],
        commercial_injection_plan=_empty_plan("s5").model_dump(mode="json"),
    )

    config = captured["config"]
    assert captured["scenario"] == "s5"
    assert get_step_injection_from_state({"scenario": "s5", "config": config}, "vlog_strategy") is not None
    assert len(completion_calls) == 1


@pytest.mark.asyncio
async def test_c6_step_runner_exposes_current_step_injection_before_run_step(
    monkeypatch,
    isolated_provider_cost_db,
):
    del isolated_provider_cost_db
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.pipeline.step_runner import StepRunner

    captured: dict[str, object] = {}
    state = {
        "label": "c6_step_runner_fixture",
        "scenario": "s1",
        "config": with_injection_config({"brand_id": "momcozy"}, _empty_plan("s1")),
        "steps": {
            step: {
                "status": "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
                "started_at": "",
                "completed_at": "",
                "duration_ms": 0,
            }
            for step in SCENARIO_STEP_ORDERS["s1"]
        },
        "current_step": "strategy",
        "mode": "auto",
        "trace_id": "trace_fixture",
        "errors": [],
        "media_synthesis_errors": [],
        "gates": {},
    }
    attach_execution_policy(state, scenario="s1", media=False)
    await attach_test_provider_execution_authority(state)

    class FakeStateManager:
        async def load(self, label):
            return state

        async def save(self, label, saved_state):
            captured["saved_state"] = saved_state

    async def fake_run_step(self, step_name, runtime_state):
        captured["runtime_current_step_injection"] = runtime_state.get(CURRENT_STEP_INJECTION_KEY)
        captured["runtime_step_injection"] = runtime_state["steps"][step_name].get(STEP_INJECTION_DATA_KEY)
        return []

    monkeypatch.setattr(S1ProductDirectPipeline, "run_step", fake_run_step)

    await StepRunner(FakeStateManager()).run_step("c6_step_runner_fixture", "strategy")

    assert captured["runtime_current_step_injection"]["step"] == "strategy"
    assert captured["runtime_step_injection"]["bundle_refs"] == ["ProductTruthBundle"]
    saved_state = captured["saved_state"]
    assert saved_state["steps"]["strategy"][STEP_INJECTION_DATA_KEY]["step"] == "strategy"


@pytest.mark.asyncio
async def test_c11_step_runner_exposes_runtime_injection_before_run_step(
    monkeypatch,
    isolated_provider_cost_db,
):
    del isolated_provider_cost_db
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.pipeline.step_runner import StepRunner

    captured: dict[str, object] = {}
    config = with_reviewed_brand_bundles(
        with_injection_config({"brand_id": "momcozy"}, _empty_plan("s1")),
        [_reviewed_bundle("s1", "strategy")],
    )
    state = {
        "label": "c11_step_runner_fixture",
        "scenario": "s1",
        "config": config,
        "steps": {
            step: {
                "status": "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
                "started_at": "",
                "completed_at": "",
                "duration_ms": 0,
            }
            for step in SCENARIO_STEP_ORDERS["s1"]
        },
        "current_step": "strategy",
        "mode": "auto",
        "trace_id": "trace_fixture",
        "errors": [],
        "media_synthesis_errors": [],
        "gates": {},
    }
    attach_execution_policy(state, scenario="s1", media=False)
    await attach_test_provider_execution_authority(state)

    class FakeStateManager:
        async def load(self, label):
            return state

        async def save(self, label, saved_state):
            captured["saved_state"] = saved_state

    async def fake_run_step(self, step_name, runtime_state):
        captured["current_runtime_injection"] = runtime_state.get(CURRENT_RUNTIME_INJECTION_KEY)
        captured["step_runtime_injection"] = runtime_state["steps"][step_name].get(STEP_RUNTIME_INJECTION_DATA_KEY)
        return []

    monkeypatch.setattr(S1ProductDirectPipeline, "run_step", fake_run_step)

    await StepRunner(FakeStateManager()).run_step("c11_step_runner_fixture", "strategy")

    runtime = captured["current_runtime_injection"]
    assert runtime["prompt_injection_allowed"] is True
    assert runtime["hard_token_ids"] == ["bat_s1_strategy_runtime"]
    assert captured["step_runtime_injection"] == runtime
    saved_state = captured["saved_state"]
    assert saved_state["steps"]["strategy"][STEP_RUNTIME_INJECTION_DATA_KEY] == runtime


def _token(
    *,
    token_id: str,
    status: TokenStatus,
    strength: TokenStrength,
    step_scope: list[str],
    license_status: LicenseStatus,
    review_status: str = "pending",
    rights_ref: str | None = None,
) -> BrandAssetToken:
    return BrandAssetToken(
        token_id=token_id,
        brand_id="momcozy",
        token_type="brand_voice",
        status=status,
        strength=strength,
        scenario_scope=["s1"],
        step_scope=step_scope,
        rights_ref=rights_ref,
        license_status=license_status,
        allowed_uses=[AllowedUse.GENERATION] if license_status == LicenseStatus.APPROVED else [],
        review=TokenReview(review_status=review_status),
    )


def _reviewed_bundle(scenario: str, step: str) -> BrandConstraintBundle:
    return BrandConstraintBundle.build_approved(
        bundle_id=f"bundle_{scenario}_{step}_runtime",
        brand_id="momcozy",
        scenario=scenario,
        step=step,
        tokens=[
            _token(
                token_id=f"bat_{scenario}_{step}_runtime",
                status=TokenStatus.APPROVED,
                strength=TokenStrength.HARD,
                step_scope=[step],
                license_status=LicenseStatus.APPROVED,
                review_status="approved",
                rights_ref="rights_fixture_runtime",
            ),
        ],
    )


def _empty_plan(scenario: str):
    return plan_scenario_injection(
        scenario=scenario,
        brand_id="momcozy",
        tokens_bundle_factory=lambda step: BrandConstraintBundle(
            bundle_id=f"bundle_{scenario}_{step}",
            brand_id="momcozy",
            scenario=scenario,
            step=step,
        ),
        platform="tiktok",
    )


def _step(plan, step_name: str):
    return next(step for step in plan.steps if step.step == step_name)
