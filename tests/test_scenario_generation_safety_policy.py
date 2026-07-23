"""Generation-safety request contract tests.

All HTTP submit tests replace runners/services at the provider boundary.  They
exercise FastAPI's real request parsing without starting a provider-capable
pipeline or making external HTTP requests.
"""

from __future__ import annotations

import asyncio
import importlib
import uuid
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.routers import _deps
from src.routers._state import (
    FastModeRequest,
    PipelineStartRequest,
    S1StartRequest,
    S2BrandCampaignRequest,
    S3InfluencerRemixRequest,
    S4LiveShootRequest,
    S5BrandVlogRequest,
)

POLICY_VERSION = "generation-safety.v2"
SAFE_MEDIA_INTENT = {
    "enable_media_synthesis": True,
    "artifact_disposition": "pending_review",
    "provider_max_retries": 0,
}


def _policy_module():
    try:
        return importlib.import_module("src.pipeline.generation_policy")
    except ModuleNotFoundError:
        pytest.fail("canonical src.pipeline.generation_policy module is missing")


def _policy_projection() -> dict[str, Any] | None:
    try:
        module = importlib.import_module("src.pipeline.generation_policy")
    except ModuleNotFoundError:
        return None
    policy = module.get_effective_generation_policy()
    return policy.model_dump(mode="json") if policy is not None else None


def _auth(
    permissions: frozenset[str] = frozenset({"all"}),
) -> _deps.AuthContext:
    return _deps.AuthContext(
        tenant_id="tenant-a",
        permissions=permissions,
        key_type=_deps.ApiKeyType.TENANT,
        key_id="key-a",
    )


def _expected_policy(scenario: str, *, media: bool = True) -> dict[str, Any]:
    return {
        "version": POLICY_VERSION,
        "tenant_id": "tenant-a",
        "scenario": scenario,
        "provider_submit_allowed": True,
        "enable_media_synthesis": media,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
        "c2pa_signing_mode": "local_draft",
    }


def test_generation_safety_intent_defaults_are_fail_closed():
    policy = _policy_module()

    intent = policy.GenerationSafetyIntent()

    assert intent.model_dump() == {
        "enable_media_synthesis": False,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }


def test_s2_result_builder_never_upgrades_degraded_bounded_state() -> None:
    from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline

    result = S2BrandCampaignPipeline()._build_result(
        final_state={
            "lifecycle_status": "completed_bounded",
            "pipeline_degraded": True,
            "steps": {},
            "errors": ["fixture degraded"],
            "media_synthesis_errors": [],
        },
        brand_name="Fixture",
        brand_package={"brand_name": "Fixture"},
        video_duration=30,
        enable_media_synthesis=False,
        artifact_disposition="pending_review",
        provider_max_retries=0,
        provider_job_caps={},
        bounded_media_pilot=False,
        model_id="fixture-model",
        label="s2-degraded-result",
    )

    assert result["_execution_completed"] is False
    assert result["success"] is False
    assert result["pipeline_degraded"] is True


@pytest.mark.parametrize("invalid", ["false", 0])
def test_generation_safety_intent_accepts_only_strict_booleans(invalid: Any):
    policy = _policy_module()

    with pytest.raises(ValidationError):
        policy.GenerationSafetyIntent(enable_media_synthesis=invalid)


@pytest.mark.parametrize("disposition", ["default", "approved", "public"])
def test_generation_safety_intent_rejects_uncontrolled_dispositions(disposition: str):
    policy = _policy_module()

    with pytest.raises(ValidationError):
        policy.GenerationSafetyIntent(artifact_disposition=disposition)


@pytest.mark.parametrize("retry", [False, 1, 2, -1])
def test_generation_safety_intent_allows_only_zero_mutation_retry(retry: Any):
    policy = _policy_module()

    with pytest.raises(ValidationError):
        policy.GenerationSafetyIntent(provider_max_retries=retry)


def test_resolver_defaults_do_not_grant_provider_authority():
    policy = _policy_module()

    with pytest.raises(HTTPException) as exc:
        policy.resolve_generation_policy({}, auth=_auth(frozenset()), scenario="s1")

    assert exc.value.status_code == 403


def test_resolver_uses_authenticated_tenant_and_explicit_provider_permission():
    policy = _policy_module()

    effective = policy.resolve_generation_policy(
        {},
        auth=_auth(frozenset({"provider:submit"})),
        scenario="s1",
    )

    assert effective.model_dump(mode="json") == _expected_policy("s1", media=False)


def test_resolver_projects_server_owned_required_signing_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy_module()
    monkeypatch.setenv("AI_VIDEO_C2PA_SIGNING_MODE", "required")

    effective = policy.resolve_generation_policy(
        {},
        auth=_auth(frozenset({"provider:submit"})),
        scenario="s1",
    )

    assert effective.c2pa_signing_mode == "required"


def test_resolver_rejects_invalid_server_signing_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _policy_module()
    monkeypatch.setenv("AI_VIDEO_C2PA_SIGNING_MODE", "disabled")

    with pytest.raises(HTTPException) as exc:
        policy.resolve_generation_policy(
            {},
            auth=_auth(frozenset({"provider:submit"})),
            scenario="s1",
        )

    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "forbidden_key",
    [
        "tenant_id",
        "idempotency_key",
        "budget_limit",
        "budget_limit_usd",
        "approved_budget_limit_usd",
        "per_spec_budget",
        "per_spec_budget_usd",
        "cost_budget",
        "client_spend",
        "transparency_policy",
        "transparency_sidecar",
        "c2pa_signing_mode",
        "human_approved",
        "approval_id",
        "approval_record_ref",
        "publish_allowed",
        "publish_policy",
        "delivery_accepted",
        "delivery_acceptance",
        "accepted_for_delivery",
        "artifact_policy",
        "effective_generation_policy",
        "effective_policy_version",
        "generation_safety_policy",
        "generation_policy_version",
    ],
)
def test_resolver_rejects_client_authority_assertions(forbidden_key: str):
    policy = _policy_module()

    assert forbidden_key in policy.DEFERRED_GENERATION_CONTROL_KEYS
    with pytest.raises(HTTPException) as exc:
        policy.resolve_generation_policy(
            {forbidden_key: True},
            auth=_auth(),
            scenario="s1",
        )

    assert exc.value.status_code == 422


@pytest.mark.parametrize(
    "raw_permissions",
    [None, "", "not-json", {}, 0, True, [], ["unknown:permission"]],
)
def test_db_permission_payloads_fail_closed(raw_permissions: Any):
    assert _deps._normalize_permissions(raw_permissions) == frozenset()


def test_db_permission_payload_accepts_explicit_recognized_values():
    assert _deps._normalize_permissions(["provider:submit", "provider:submit"]) == frozenset({"provider:submit"})


def test_db_permission_payload_accepts_deduplicated_artifact_accept():
    assert _deps._normalize_permissions(["artifact:accept", "artifact:accept"]) == frozenset({"artifact:accept"})


def test_db_permission_payload_with_any_unknown_value_fails_closed():
    assert _deps._normalize_permissions(["provider:submit", "unknown:permission"]) == frozenset()
    assert _deps._normalize_permissions(["artifact:accept", "unknown:permission"]) == frozenset()


@pytest.mark.parametrize(
    "raw",
    [
        ["artifact:publish", "unknown:permission"],
        ["artifact:publish", ""],
        ["provider:submit", "artifact:publish", "unknown:permission"],
    ],
)
def test_publish_permission_mixed_with_invalid_input_fails_closed(
    raw: object,
) -> None:
    assert _deps._normalize_permissions(raw) == frozenset()


@pytest.mark.parametrize(
    "raw_permissions",
    [["all", ""], ["provider:submit", " "], ["\t", "all"]],
)
def test_db_permission_payload_with_blank_elements_fails_closed(
    raw_permissions: list[str],
):
    assert _deps._normalize_permissions(raw_permissions) == frozenset()


@pytest.mark.parametrize(
    ("model", "required"),
    [
        (FastModeRequest, {"user_prompt": "safe fake request"}),
        (PipelineStartRequest, {}),
        (S1StartRequest, {"product_catalog": {"name": "Fixture"}}),
        (S2BrandCampaignRequest, {}),
        (S3InfluencerRemixRequest, {}),
        (S4LiveShootRequest, {}),
        (S5BrandVlogRequest, {}),
    ],
)
def test_all_submit_models_default_to_no_media_pending_review_zero_retry(
    model: type[Any],
    required: dict[str, Any],
):
    request = model(**required)

    assert request.enable_media_synthesis is False
    assert request.artifact_disposition == "pending_review"
    assert request.provider_max_retries == 0


def test_legacy_pipeline_request_defaults_to_its_s1_compatible_contract():
    request = PipelineStartRequest()

    assert request.content_scenario == "product_direct"


@dataclass(frozen=True)
class SubmitCase:
    name: str
    path: str
    scenario: str
    payload: dict[str, Any]


S1_BROWSER_WIRE_PAYLOAD = {
    "product_catalog": {"name": "Fixture"},
    "target_platforms": ["tiktok"],
    "target_languages": ["en"],
    "week": "2026-W28",
    "video_duration": 30,
    "continuity_mode": True,
    "continuity_generation_mode": "standard",
    "storyboard_grid": 12,
    "clip_group_size": 3,
    "transition_style": "match_cut",
}
S2_BROWSER_WIRE_PAYLOAD = {
    "brand_package": {"brand_name": "Fixture"},
    "target_platforms": ["tiktok"],
    "target_languages": ["en"],
    "week": "2026-W28",
    "video_duration": 60,
}
S3_BROWSER_WIRE_PAYLOAD = {
    "video_url": "",
    "product": {"name": "Fixture"},
    "influencer_name": "Influencer",
    "brief_id": "",
    "target_platforms": ["tiktok"],
    "target_languages": ["en"],
    "video_duration": 30,
}
S4_BROWSER_WIRE_PAYLOAD = {
    "footage_assets": [],
    "product_info": {"name": "Fixture"},
    "topic": "",
    "target_platforms": ["tiktok"],
    "brand_guidelines": {},
    "video_duration": 30,
}
S5_BROWSER_WIRE_PAYLOAD = {
    "brand_id": "momcozy",
    "product_sku": {"name": "Fixture"},
    "scene_id": "living-room",
    "selected_models": [],
    "story_description": "",
    "video_duration": 30,
}


SUBMIT_CASES = [
    SubmitCase(
        "fast-generate",
        "/fast/generate",
        "fast",
        {"user_prompt": "fake fast request", "duration": 10, "enable_tts": False},
    ),
    SubmitCase(
        "fast-submit",
        "/fast/submit",
        "fast",
        {"user_prompt": "fake async fast request", "duration": 10, "enable_tts": False},
    ),
    SubmitCase("s1-blocking", "/scenario/s1", "s1", S1_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s2-blocking", "/scenario/s2", "s2", S2_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s3-blocking", "/scenario/s3", "s3", S3_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s4-blocking", "/scenario/s4", "s4", S4_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s5-blocking", "/scenario/s5", "s5", S5_BROWSER_WIRE_PAYLOAD),
    SubmitCase(
        "s1-step-start",
        "/scenario/s1/start",
        "s1",
        S1_BROWSER_WIRE_PAYLOAD | {"mode": "step_by_step"},
    ),
    SubmitCase("s1-unified", "/scenario/s1/submit", "s1", S1_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s2-unified", "/scenario/s2/submit", "s2", S2_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s3-unified", "/scenario/s3/submit", "s3", S3_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s4-unified", "/scenario/s4/submit", "s4", S4_BROWSER_WIRE_PAYLOAD),
    SubmitCase("s5-unified", "/scenario/s5/submit", "s5", S5_BROWSER_WIRE_PAYLOAD),
    SubmitCase(
        "legacy-pipeline-start",
        "/pipeline/start",
        "s1",
        {"product_catalog": {"name": "Fixture"}, "content_scenario": "s1"},
    ),
]


@pytest.fixture
def fake_submit_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
):
    """Replace provider-capable execution while retaining real HTTP validation."""
    captures: list[dict[str, Any]] = []

    class FakeStateManager:
        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager
            self.config: dict[str, Any] = {}
            self.scenario = "s1"

        async def init_state(
            self,
            *,
            config: dict[str, Any],
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            self.config = deepcopy(config)
            self.scenario = scenario
            captures.append(
                {
                    "boundary": "step_runner",
                    "scenario": scenario,
                    "config": deepcopy(config),
                    "policy": _policy_projection(),
                }
            )
            return label or f"fake_{scenario}_label"

        async def resume(self, _label: str) -> dict[str, Any]:
            return {
                "scenario": self.scenario,
                "config": deepcopy(self.config),
                "steps": {},
                "errors": [],
                "media_synthesis_errors": [],
                "lifecycle_status": "completed_bounded",
                "pipeline_degraded": False,
            }

        async def run_step(self, _label: str, step_name: str) -> dict[str, Any]:
            return {
                "scenario": self.scenario,
                "config": deepcopy(self.config),
                "steps": {step_name: {"output": {}}},
                "errors": [],
                "media_synthesis_errors": [],
                "lifecycle_status": "completed_bounded",
                "pipeline_degraded": False,
            }
        async def finalize_pipeline_completion(self, state: dict[str, Any], *, started_at: float) -> bool: return True
    class FakeFastService:
        async def generate(self, **kwargs: Any) -> dict[str, Any]:
            captures.append(
                {
                    "boundary": "fast_service",
                    "scenario": "fast",
                    "config": deepcopy(kwargs),
                    "policy": _policy_projection(),
                }
            )
            return {"success": True, "is_stub": True}

    class FakeS3Result:
        def to_dict(self) -> dict[str, Any]:
            return {
                "success": True,
                "scenario": "s3",
                "_execution_completed": True,
            }

    def fake_pipeline(scenario: str):
        class FakePipeline:
            async def run(self, **kwargs: Any) -> Any:
                captures.append(
                    {
                        "boundary": "scenario_pipeline",
                        "scenario": scenario,
                        "config": deepcopy(kwargs),
                        "policy": _policy_projection(),
                    }
                )
                if scenario == "s3":
                    return FakeS3Result()
                return {
                    "success": True,
                    "scenario": scenario,
                    "_execution_completed": True,
                }

        return FakePipeline

    async def identity_translation(value: dict[str, Any]) -> dict[str, Any]:
        return value

    async def fake_auth_dependency() -> _deps.AuthContext:
        ctx = _auth()
        _deps._bind_auth_context(ctx)
        return ctx

    from src.api import app
    from src.pipeline import (
        s2_brand_pipeline_v2,
        s3_remix_pipeline,
        s4_live_shoot_pipeline,
        s5_brand_vlog_pipeline,
        state_manager,
        step_runner,
    )
    from src.services import fast_mode
    from src.tasks import fast_task_registry
    from src.tools import translate

    app.dependency_overrides[_deps.verify_api_key] = fake_auth_dependency
    monkeypatch.setattr(state_manager, "PipelineStateManager", FakeStateManager)
    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)
    monkeypatch.setattr(translate, "translate_catalog_to_english", identity_translation)
    monkeypatch.setattr(fast_mode, "get_fast_mode_service", lambda: FakeFastService())
    monkeypatch.setattr(
        s2_brand_pipeline_v2,
        "S2BrandCampaignPipeline",
        fake_pipeline("s2"),
    )
    monkeypatch.setattr(
        s3_remix_pipeline,
        "S3InfluencerRemixPipeline",
        fake_pipeline("s3"),
    )
    monkeypatch.setattr(
        s4_live_shoot_pipeline,
        "S4LiveShootPipeline",
        fake_pipeline("s4"),
    )
    monkeypatch.setattr(
        s5_brand_vlog_pipeline,
        "S5BrandVlogPipeline",
        fake_pipeline("s5"),
    )
    monkeypatch.setattr(
        fast_task_registry,
        "register_fast_task",
        lambda _task, **_kwargs: "fake-task",
    )

    yield captures

    app.dependency_overrides.pop(_deps.verify_api_key, None)


async def _post(case: SubmitCase, payload: dict[str, Any]):
    from src.api import app

    headers = {
        "X-API-Key": "ignored-by-override",
        "X-Forwarded-For": f"test-{uuid.uuid4().hex}",
    }
    if case.path == "/fast/submit" or (case.path.startswith("/scenario/") and case.path.endswith("/submit")):
        headers["Idempotency-Key"] = f"contract-{uuid.uuid4()}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            case.path,
            json=payload,
            headers=headers,
        )


async def _wait_for_submit_boundary(
    captures: list[dict[str, Any]],
    *,
    description: str,
) -> None:
    try:
        async with asyncio.timeout(2.0):
            while not captures:
                await asyncio.sleep(0.01)
    except TimeoutError:
        raise AssertionError(f"{description} did not reach its fake execution boundary") from None


@pytest.mark.asyncio
@pytest.mark.parametrize("case", SUBMIT_CASES, ids=lambda case: case.name)
async def test_every_submit_surface_builds_the_same_effective_policy(
    case: SubmitCase,
    fake_submit_boundaries: list[dict[str, Any]],
):
    response = await _post(case, case.payload | SAFE_MEDIA_INTENT)
    await _wait_for_submit_boundary(fake_submit_boundaries, description=case.name)

    assert response.status_code == 200, response.text
    captured = fake_submit_boundaries[-1]
    assert captured["policy"] == _expected_policy(case.scenario)
    assert captured["config"]["artifact_disposition"] == "pending_review"
    assert captured["config"]["provider_max_retries"] == 0
    assert captured["config"]["enable_media_synthesis"] is True
    if captured["boundary"] == "fast_service":
        assert captured["config"]["effective_generation_policy"] == _expected_policy(case.scenario)
    if captured["boundary"] == "step_runner":
        assert captured["config"]["effective_generation_policy"] == _expected_policy(case.scenario)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_config"),
    [
        pytest.param(
            next(case for case in SUBMIT_CASES if case.name == "s2-unified"),
            {"video_duration": 60},
            id="s2-preserves-duration",
        ),
        pytest.param(
            next(case for case in SUBMIT_CASES if case.name == "s4-unified"),
            {
                "video_duration": 30,
                "brand_guidelines": {"stock_footage_urls": ["https://stock.example/clip.mp4"]},
            },
            id="s4-preserves-duration-and-brand-guidelines",
        ),
    ],
)
async def test_unified_submit_preserves_blocking_route_scenario_fields(
    case: SubmitCase,
    expected_config: dict[str, Any],
    fake_submit_boundaries: list[dict[str, Any]],
):
    payload = case.payload | SAFE_MEDIA_INTENT
    payload.update(expected_config)

    response = await _post(case, payload)
    await _wait_for_submit_boundary(fake_submit_boundaries, description=case.name)

    assert response.status_code == 200, response.text
    captured = next(
        item
        for item in reversed(fake_submit_boundaries)
        if item["boundary"] == "step_runner" and item["scenario"] == case.scenario
    )
    for key, expected in expected_config.items():
        assert captured["config"][key] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    SUBMIT_CASES[2:7],
    ids=lambda case: f"{case.name}-bounded-truth",
)
@pytest.mark.parametrize(
    ("intent", "completion_kind"),
    [
        pytest.param({}, "no_media", id="no-media"),
        pytest.param(SAFE_MEDIA_INTENT, "bounded_media", id="bounded-media"),
    ],
)
async def test_blocking_s1_to_s5_never_claim_full_success_for_bounded_runs(
    case: SubmitCase,
    intent: dict[str, Any],
    completion_kind: str,
    fake_submit_boundaries: list[dict[str, Any]],
):
    response = await _post(case, case.payload | intent)

    assert response.status_code == 200, response.text
    assert fake_submit_boundaries
    payload = response.json()
    assert payload["status"] == "completed_bounded"
    assert payload["lifecycle_status"] == "completed_bounded"
    assert payload["completion_kind"] == completion_kind
    assert payload["request_succeeded"] is True
    assert payload["success"] is False
    assert payload["full_media_success"] is False
    assert payload["pipeline_complete"] is False
    assert payload["publish_allowed"] is False
    assert payload["delivery_accepted"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    SUBMIT_CASES[2:7],
    ids=lambda case: f"{case.name}-failure-truth",
)
async def test_blocking_s1_to_s5_never_upgrade_failed_execution_to_bounded_success(
    case: SubmitCase,
    fake_submit_boundaries: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
):
    del fake_submit_boundaries
    from src.pipeline import (
        s2_brand_pipeline_v2,
        s3_remix_pipeline,
        s4_live_shoot_pipeline,
        s5_brand_vlog_pipeline,
        step_runner,
    )

    failed_result = {
        "success": False,
        "pipeline_degraded": True,
        "errors": ["fixture execution failure"],
    }

    if case.scenario == "s1":

        async def failed_run_step(self: Any, label: str, step_name: str) -> dict[str, Any]:
            del self, label, step_name
            return {
                **failed_result,
                "lifecycle_status": "error",
                "scenario": "s1",
                "steps": {},
                "media_synthesis_errors": [],
            }

        monkeypatch.setattr(step_runner.StepRunner, "run_step", failed_run_step)
    else:

        class FailurePipeline:
            async def run(self, **kwargs: Any) -> Any:
                del kwargs
                if case.scenario == "s3":

                    class FailureResult:
                        def to_dict(self) -> dict[str, Any]:
                            return dict(failed_result)

                    return FailureResult()
                return dict(failed_result)

        module_by_scenario = {
            "s2": (s2_brand_pipeline_v2, "S2BrandCampaignPipeline"),
            "s3": (s3_remix_pipeline, "S3InfluencerRemixPipeline"),
            "s4": (s4_live_shoot_pipeline, "S4LiveShootPipeline"),
            "s5": (s5_brand_vlog_pipeline, "S5BrandVlogPipeline"),
        }
        module, class_name = module_by_scenario[case.scenario]
        monkeypatch.setattr(module, class_name, FailurePipeline)

    response = await _post(case, case.payload)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["lifecycle_status"] == "error"
    assert payload["completion_kind"] == "execution_failed"
    assert payload["request_succeeded"] is False
    assert payload["success"] is False
    assert payload["full_media_success"] is False
    assert payload["pipeline_complete"] is False
    assert payload["publish_allowed"] is False
    assert payload["delivery_accepted"] is False


@pytest.mark.asyncio
async def test_s1_type_error_after_first_attempt_never_replays_legacy_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
):
    from src.api import app
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.pipeline.step_runner import StepRunner
    from src.tools import translate

    provider_attempts = 0
    legacy_replays = 0

    async def fake_auth_dependency() -> _deps.AuthContext:
        ctx = _auth()
        _deps._bind_auth_context(ctx)
        return ctx

    async def identity_translation(value: dict[str, Any]) -> dict[str, Any]:
        return value

    async def fake_init_state(self: StepRunner, **kwargs: Any) -> str:
        del self, kwargs
        return "s1-no-replay"

    async def fail_after_attempt(
        self: StepRunner,
        label: str,
        step_name: str,
    ) -> dict[str, Any]:
        nonlocal provider_attempts
        del self, label
        assert step_name == "strategy"
        provider_attempts += 1
        raise TypeError("provider response normalization failed after submit")

    async def forbidden_legacy_run(self: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal legacy_replays
        del self, kwargs
        legacy_replays += 1
        return {"success": True}

    app.dependency_overrides[_deps.verify_api_key] = fake_auth_dependency
    monkeypatch.setattr(translate, "translate_catalog_to_english", identity_translation)
    monkeypatch.setattr(StepRunner, "init_state", fake_init_state)
    monkeypatch.setattr(StepRunner, "run_step", fail_after_attempt)
    monkeypatch.setattr(S1ProductDirectPipeline, "run", forbidden_legacy_run)
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                SUBMIT_CASES[2].path,
                json=SUBMIT_CASES[2].payload,
                headers={"X-API-Key": "ignored-by-override"},
            )
    finally:
        app.dependency_overrides.pop(_deps.verify_api_key, None)

    assert response.status_code == 500, response.text
    assert provider_attempts == 1
    assert legacy_replays == 0


@pytest.mark.asyncio
async def test_legacy_pipeline_default_builds_an_s1_policy_and_state(
    fake_submit_boundaries: list[dict[str, Any]],
):
    case = SubmitCase(
        "legacy-default",
        "/pipeline/start",
        "s1",
        {"product_catalog": {"name": "Fixture"}},
    )

    response = await _post(case, case.payload | SAFE_MEDIA_INTENT)
    await _wait_for_submit_boundary(fake_submit_boundaries, description=case.name)

    assert response.status_code == 200, response.text
    captured = fake_submit_boundaries[-1]
    assert captured["scenario"] == "s1"
    assert captured["policy"] == _expected_policy("s1")
    assert captured["config"]["effective_generation_policy"] == _expected_policy("s1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsupported_scenario",
    ["brand_campaign", "influencer_remix", "live_shoot", "brand_vlog", "s2", "s3", "s4", "s5"],
)
async def test_legacy_pipeline_rejects_scenarios_its_s1_shaped_config_cannot_run(
    unsupported_scenario: str,
    fake_submit_boundaries: list[dict[str, Any]],
):
    case = SubmitCase(
        f"legacy-{unsupported_scenario}",
        "/pipeline/start",
        "s1",
        {
            "product_catalog": {"name": "Fixture"},
            "content_scenario": unsupported_scenario,
        },
    )

    response = await _post(case, case.payload | SAFE_MEDIA_INTENT)

    assert response.status_code == 422, response.text
    assert fake_submit_boundaries == []


INVALID_RAW_SAFETY_FIELDS = [
    pytest.param({"enable_media_synthesis": "false"}, id="string-bool"),
    pytest.param({"provider_max_retries": False}, id="bool-as-int"),
    pytest.param({"tenant_id": "attacker-tenant"}, id="body-tenant"),
    pytest.param({"generation_policy_version": "unknown-v99"}, id="unknown-version"),
    pytest.param({"budget_limit_usd": 1}, id="deferred-budget-alias"),
    pytest.param({"approval_record_ref": "client-ref"}, id="deferred-approval-alias"),
    pytest.param({"transparency_sidecar": True}, id="deferred-transparency-alias"),
    pytest.param({"unknown_generation_authority": True}, id="unknown-extra-field"),
    pytest.param({"artifact_disposition": "approved"}, id="approved-disposition"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("case", SUBMIT_CASES, ids=lambda case: case.name)
@pytest.mark.parametrize("invalid_fields", INVALID_RAW_SAFETY_FIELDS)
async def test_every_submit_surface_rejects_invalid_raw_safety_fields(
    case: SubmitCase,
    invalid_fields: dict[str, Any],
    fake_submit_boundaries: list[dict[str, Any]],
):
    payload = case.payload | SAFE_MEDIA_INTENT | invalid_fields

    response = await _post(case, payload)

    assert response.status_code == 422, response.text
    assert fake_submit_boundaries == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "label"),
    [
        (SUBMIT_CASES[3], "s2_policy_persistence"),
        (SUBMIT_CASES[4], "s3_policy_persistence"),
        (SUBMIT_CASES[5], "s4_policy_persistence"),
        (SUBMIT_CASES[6], "s5_policy_persistence"),
    ],
    ids=["s2-blocking", "s3-blocking", "s4-blocking", "s5-blocking"],
)
async def test_blocking_s2_to_s5_persist_server_owned_effective_policy(
    case: SubmitCase,
    label: str,
    isolated_state_dir: Path,
    isolated_provider_cost_db: Any,
    monkeypatch: pytest.MonkeyPatch,
):
    """Exercise the real blocking pipeline/config builder and real init_state.

    ``run_step`` is replaced before any provider-capable step method is called,
    while each real blocking orchestrator, ``StepRunner.init_state`` and state
    persistence remain in the path. This catches policy that exists only in a
    router contextvar/kwargs.
    """

    del isolated_state_dir
    from src.api import app
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner
    from src.tools import translate

    async def fake_auth_dependency() -> _deps.AuthContext:
        ctx = _auth()
        _deps._bind_auth_context(ctx)
        return ctx

    async def identity_translation(value: dict[str, Any]) -> dict[str, Any]:
        return value

    async def provider_free_run_step(
        self: StepRunner,
        run_label: str,
        step_name: str,
    ) -> dict[str, Any]:
        state = await self.state_manager.load(run_label)
        assert state is not None
        step = state["steps"][step_name]
        step["status"] = "done"
        step["output"] = {}
        state["current_step"] = None
        await self.state_manager.save(run_label, state)
        return state

    app.dependency_overrides[_deps.verify_api_key] = fake_auth_dependency
    monkeypatch.setattr(translate, "translate_catalog_to_english", identity_translation)
    monkeypatch.setattr(StepRunner, "run_step", provider_free_run_step)

    try:
        payload = case.payload | SAFE_MEDIA_INTENT | {"output_label": label}
        response = await _post(case, payload)
        assert response.status_code == 200, response.text

        state = await PipelineStateManager().load(label)
        assert state is not None
        assert state["config"]["effective_generation_policy"] == _expected_policy(case.scenario)
        assert state["config"]["enable_media_synthesis"] is True
        assert state["config"]["provider_max_retries"] == 0
    finally:
        app.dependency_overrides.pop(_deps.verify_api_key, None)


def test_fresh_schema_defaults_tenant_key_permissions_to_empty_array():
    sql = Path("src/storage/migrations/001_init.sql").read_text()

    assert "permissions JSONB DEFAULT '[]'" in sql
    assert "permissions JSONB DEFAULT '[\"all\"]'" not in sql


def test_fail_closed_permission_migration_exists_without_being_executed():
    migration = Path("migrations/alembic/versions/7c4b8e2f1a09_fail_closed_api_key_permissions.py")

    assert migration.exists()
    source = migration.read_text()
    assert 'revision: str = "7c4b8e2f1a09"' in source
    assert "ALTER COLUMN permissions SET DEFAULT '[]'::jsonb" in source
