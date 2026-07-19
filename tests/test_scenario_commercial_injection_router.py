from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import HTTPException

from src.pipeline.scenario_injection_plan import (
    CURRENT_STEP_INJECTION_KEY,
    SCENARIO_INJECTION_CONFIG_KEY,
    SCENARIO_INJECTION_MODE_KEY,
    get_step_injection_from_state,
)
from src.routers._deps import ApiKeyType, AuthContext
from src.routers._state import S1StartRequest, S2BrandCampaignRequest, S5BrandVlogRequest


@pytest.fixture(autouse=True)
def _authorized_generation_context(monkeypatch: pytest.MonkeyPatch, isolated_provider_cost_db) -> None:
    del isolated_provider_cost_db
    auth = AuthContext(
        tenant_id="tenant-a",
        permissions=frozenset({"provider:submit"}),
        key_type=ApiKeyType.TENANT,
        key_id="commercial-injection-test",
    )
    monkeypatch.setattr("src.routers.scenario.get_auth_context", lambda: auth)


def _plan_payload(scenario: str, step: str = "strategy") -> dict[str, Any]:
    return {
        "scenario": scenario,
        "brand_id": "momcozy",
        "platform": "tiktok",
        "read_only": True,
        "evidence_level": "L2-fixture-or-dry-run",
        "steps": [
            {
                "scenario": scenario,
                "step": step,
                "hard_token_ids": [],
                "soft_token_ids": [],
                "source_token_ids": ["bat_fixture"],
                "bundle_refs": ["BrandConstraintBundle"],
                "toolbox_refs": ["ImageToolbox"],
                "contract_refs": ["QualityContract"],
                "gate_checks": ["rights_pass"],
                "notes": [],
            }
        ],
    }


@pytest.mark.asyncio
async def test_s1_start_accepts_commercial_injection_plan_in_step_runner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import step_runner
    from src.routers import scenario

    captured: dict[str, Any] = {}

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(self, config: dict[str, Any], mode: str = "auto", label=None, scenario: str = "s1") -> str:
            captured["config"] = config
            captured["mode"] = mode
            captured["scenario"] = scenario
            return "s1_injection_start"

        async def resume(self, label: str) -> dict[str, Any]:
            return {
                "label": label,
                "scenario": "s1",
                CURRENT_STEP_INJECTION_KEY: captured["config"][SCENARIO_INJECTION_CONFIG_KEY]["steps"][0],
            }

    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)

    result = await scenario.start_s1_pipeline(
        S1StartRequest(
            product_catalog={"product_name": "Momcozy Bottle Warmer"},
            mode="step_by_step",
            commercial_injection_plan=_plan_payload("s1"),
        )
    )

    config = captured["config"]
    assert result["label"] == "s1_injection_start"
    assert captured["mode"] == "step_by_step"
    assert config[SCENARIO_INJECTION_MODE_KEY] == "read_only_blueprint"
    assert get_step_injection_from_state({"scenario": "s1", "config": config}, "strategy") is not None


@pytest.mark.asyncio
async def test_s1_start_mismatched_commercial_injection_plan_returns_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import step_runner
    from src.routers import scenario

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)

    with pytest.raises(HTTPException) as exc:
        await scenario.start_s1_pipeline(
            S1StartRequest(
                product_catalog={"product_name": "Momcozy Bottle Warmer"},
                commercial_injection_plan=_plan_payload("s2"),
            )
        )

    assert exc.value.status_code == 422
    assert "scenario mismatch" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_s2_run_passes_commercial_injection_plan_to_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline
    from src.routers import scenario

    captured: dict[str, Any] = {}

    async def fake_run(self: S2BrandCampaignPipeline, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"success": True, "_execution_completed": True, "scenario": "s2"}

    monkeypatch.setattr(S2BrandCampaignPipeline, "run", fake_run)

    result = await scenario.run_s2_brand_campaign(
        S2BrandCampaignRequest(
            brand_package={"brand_name": "Momcozy"},
            commercial_injection_plan=_plan_payload("s2"),
        )
    )

    assert result["status"] == "completed_bounded"
    assert result["completion_kind"] == "no_media"
    assert result["request_succeeded"] is True
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert captured["commercial_injection_plan"]["scenario"] == "s2"
    assert captured["commercial_injection_plan"]["steps"][0]["gate_checks"] == ["rights_pass"]


@pytest.mark.asyncio
async def test_s5_run_passes_commercial_injection_plan_to_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
    from src.routers import scenario

    captured: dict[str, Any] = {}

    async def fake_run(self: S5BrandVlogPipeline, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"success": True, "_execution_completed": True, "scenario": "s5"}

    monkeypatch.setattr(S5BrandVlogPipeline, "run", fake_run)

    result = await scenario.run_s5_brand_vlog(
        S5BrandVlogRequest(
            brand_id="momcozy",
            product_sku={"name": "Bottle Warmer"},
            commercial_injection_plan=_plan_payload("s5", step="vlog_strategy"),
        )
    )

    assert result["status"] == "completed_bounded"
    assert result["completion_kind"] == "no_media"
    assert result["request_succeeded"] is True
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert captured["commercial_injection_plan"]["scenario"] == "s5"
    assert captured["commercial_injection_plan"]["steps"][0]["step"] == "vlog_strategy"


@pytest.mark.asyncio
@pytest.mark.parametrize(("scenario_id", "step_name"), [("s2", "strategy"), ("s5", "vlog_strategy")])
async def test_unified_submit_attaches_commercial_injection_to_step_runner_config(
    monkeypatch: pytest.MonkeyPatch,
    scenario_id: str,
    step_name: str,
) -> None:
    from src.pipeline import step_runner
    from src.routers import scenario
    from src.services import submission_idempotency
    from src.services.submission_idempotency import SubmissionClaim

    captured: dict[str, Any] = {}

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(
            self,
            config: dict[str, Any],
            mode: str = "auto",
            label=None,
            scenario: str = "s1",
        ) -> str:
            captured["config"] = config
            captured["mode"] = mode
            captured["scenario"] = scenario
            captured["label"] = label
            return label or f"{scenario}_injection_submit"

        async def resume(self, label: str) -> dict[str, Any]:
            return {"label": label}

    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)
    monkeypatch.setattr(scenario, "_register_background_task", lambda task, label: None)

    class FakeSubmissionIdempotency:
        async def claim_submission(self, **_kwargs: Any) -> SubmissionClaim:
            return SubmissionClaim(outcome="owner", record={"id": "submission-fixture"})

        async def transition(self, **kwargs: Any) -> dict[str, Any]:
            return {"id": kwargs["record_id"], "record_status": kwargs["new_status"]}

        def start_heartbeat(self, **_kwargs: Any) -> None:
            return None

        async def mark_terminal(self, **kwargs: Any) -> dict[str, Any]:
            return {"id": kwargs["record_id"], "record_status": kwargs["status"]}

        async def stop_heartbeat(self, **_kwargs: Any) -> None:
            return None

    monkeypatch.setattr(
        submission_idempotency,
        "get_submission_idempotency_service",
        lambda: FakeSubmissionIdempotency(),
    )

    body: dict[str, Any] = {"commercial_injection_plan": _plan_payload(scenario_id, step=step_name)}
    if scenario_id == "s2":
        body["brand_package"] = {"brand_name": "Momcozy"}
    if scenario_id == "s5":
        body["product_sku"] = {"name": "Bottle Warmer"}

    result = await scenario._submit_scenario_validated(
        scenario_id,
        body,
        f"commercial-{scenario_id}-submit-0001",
    )
    await asyncio.sleep(0)

    config = captured["config"]
    assert result["label"] == captured["label"]
    assert captured["scenario"] == scenario_id
    assert config[SCENARIO_INJECTION_MODE_KEY] == "read_only_blueprint"
    assert get_step_injection_from_state({"scenario": scenario_id, "config": config}, step_name) is not None
