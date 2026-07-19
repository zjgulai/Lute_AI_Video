from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.runtime_injection_executor import (
    CURRENT_RUNTIME_INJECTION_KEY,
    STEP_RUNTIME_INJECTION_DATA_KEY,
)
from src.pipeline.scenario_injection_plan import (
    CURRENT_STEP_INJECTION_KEY,
    SCENARIO_INJECTION_CONFIG_KEY,
    SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY,
    SCENARIO_INJECTION_MODE_KEY,
    STEP_INJECTION_DATA_KEY,
)
from src.routers.pipeline import (
    LEGACY_PROXY_REQUIRED_STATE_FIELDS,
    _get_state_status,
    _steprunner_state_to_legacy,
)


def _sample_steprunner_state() -> dict:
    return {
        "scenario": "s1",
        "config": {
            "product_catalog": {"name": "Bottle Warmer"},
            "brand_guidelines": {"brand_name": "Momcozy"},
            "target_platforms": ["tiktok"],
            "target_languages": ["en"],
            "week": "2026-W22",
            "content_scenario": "product_direct",
        },
        "current_step": "assemble_final",
        "errors": [],
        "steps": {
            "strategy": {"status": "done", "output": [{"brief_id": "B1"}]},
            "scripts": {"status": "done", "output": [{"script_id": "S1"}]},
            "compliance": {"status": "done", "output": {"status": "pass"}},
            "storyboards": {"status": "done", "output": [{"shot": 1}]},
            "keyframe_images": {"status": "done", "output": ["kf.png"]},
            "video_prompts": {"status": "done", "output": [{"prompt": "demo"}]},
            "thumbnail_prompts": {"status": "done", "output": [{"prompt": "thumb"}]},
            "seedance_clips": {"status": "done", "output": {"clips": ["clip.mp4"]}},
            "tts_audio": {"status": "done", "output": ["audio.wav"]},
            "thumbnail_images": {"status": "done", "output": ["thumb.png"]},
            "assemble_final": {
                "status": "done",
                "output": {
                    "final_video_path": "final.mp4",
                    "distribution_plans": [{"platform": "tiktok"}],
                },
            },
            "audit": {"status": "done", "output": {"score": 0.91}},
        },
    }


def test_steprunner_state_to_legacy_pins_required_fields() -> None:
    legacy = _steprunner_state_to_legacy("run_1", _sample_steprunner_state())

    missing = [field for field in LEGACY_PROXY_REQUIRED_STATE_FIELDS if field not in legacy]
    assert missing == []
    assert legacy["product_catalog"] == {"name": "Bottle Warmer"}
    assert legacy["brand_guidelines"] == {"brand_name": "Momcozy"}
    assert legacy["target_platforms"] == ["tiktok"]
    assert legacy["target_languages"] == ["en"]
    assert legacy["content_calendar_week"] == "2026-W22"
    assert legacy["content_scenario"] == "product_direct"
    assert legacy["briefs"] == [{"brief_id": "B1"}]
    assert legacy["scripts"] == [{"script_id": "S1"}]
    assert legacy["seedance_output"] == {"clips": ["clip.mp4"]}
    assert legacy["final_video_path"] == {
        "final_video_path": "final.mp4",
        "distribution_plans": [{"platform": "tiktok"}],
    }
    assert legacy["distribution_plans"] == [{"platform": "tiktok"}]
    assert legacy["analytics_reports"] == {"score": 0.91}
    assert legacy["human_reviews"] == {}
    # Step completion alone is not proof of final assembly, publication, or
    # delivery acceptance. Legacy projection must not synthesize full success.
    assert legacy["pipeline_complete"] is False
    assert _get_state_status(legacy) == "interrupted"
    assert legacy["request_succeeded"] is False
    assert legacy["success"] is False
    assert legacy["full_media_success"] is False
    assert legacy["publish_allowed"] is False
    assert legacy["delivery_accepted"] is False


def test_steprunner_state_to_legacy_preserves_completed_bounded_truth() -> None:
    state = _sample_steprunner_state()
    state.update(
        {
            "status": "completed_bounded",
            "lifecycle_status": "completed_bounded",
            "completion_kind": "bounded_media",
            "request_succeeded": True,
            "success": False,
            "full_media_success": False,
            "pipeline_complete": False,
            "publish_allowed": False,
            "delivery_accepted": False,
            "current_step": None,
        }
    )

    legacy = _steprunner_state_to_legacy("run-bounded", state)

    assert _get_state_status(legacy) == "completed_bounded"
    assert legacy["lifecycle_status"] == "completed_bounded"
    assert legacy["completion_kind"] == "bounded_media"
    assert legacy["request_succeeded"] is True
    assert legacy["success"] is False
    assert legacy["full_media_success"] is False
    assert legacy["pipeline_complete"] is False
    assert legacy["publish_allowed"] is False
    assert legacy["delivery_accepted"] is False


@pytest.mark.asyncio
async def test_legacy_bounded_state_has_no_fake_review_and_keeps_output_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.routers import pipeline as pipeline_router

    thread_id = "bounded-thread"
    label = "bounded-label"
    state = _sample_steprunner_state()
    state.update(
        {
            "status": "completed_bounded",
            "lifecycle_status": "completed_bounded",
            "completion_kind": "no_media",
            "request_succeeded": True,
            "success": False,
            "full_media_success": False,
            "pipeline_complete": False,
            "publish_allowed": False,
            "delivery_accepted": False,
            "current_step": None,
        }
    )
    cleanup_calls = 0

    async def fake_load(run_label: str) -> dict:
        assert run_label == label
        return state

    def counted_cleanup(run_thread_id: str) -> None:
        nonlocal cleanup_calls
        assert run_thread_id == thread_id
        cleanup_calls += 1

    pipeline_router._thread_label_map[thread_id] = label
    monkeypatch.setattr(pipeline_router, "_load_steprunner_state", fake_load)
    monkeypatch.setattr(pipeline_router, "_cleanup_thread_cache", counted_cleanup)

    result = await pipeline_router.get_pipeline_state(thread_id)
    output = await pipeline_router.get_pipeline_output(thread_id)

    assert result["status"] == "completed_bounded"
    assert result["current_review"] is None
    assert cleanup_calls == 0
    assert pipeline_router._thread_label_map[thread_id] == label
    assert output["lifecycle_status"] == "completed_bounded"


@pytest.mark.asyncio
async def test_legacy_background_failure_is_persisted_and_projected_as_error(
    isolated_state_dir,
    isolated_provider_cost_db,
    auth_headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner
    from src.tools import translate

    async def identity_translation(value: dict) -> dict:
        return value

    async def fail_resume(self, label):
        del self, label
        raise RuntimeError("legacy fixture background failure")

    monkeypatch.setattr(translate, "translate_catalog_to_english", identity_translation)
    monkeypatch.setattr(StepRunner, "resume", fail_resume)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start_response = await client.post(
            "/pipeline/start",
            headers=auth_headers,
            json={"product_catalog": {"name": "Fixture"}},
        )
        assert start_response.status_code == 200, start_response.text
        started = start_response.json()

        state = None
        for _ in range(20):
            await asyncio.sleep(0)
            state = await PipelineStateManager().load(started["label"])
            if state and state.get("pipeline_degraded"):
                break

        status_response = await client.get(
            f"/pipeline/{started['thread_id']}/state",
            headers=auth_headers,
        )

    assert state is not None
    assert state["pipeline_degraded"] is True
    assert state["degraded_reason"] == "legacy_background_run_failed"
    assert state["current_step"] is None
    assert "legacy_background_run_failed: RuntimeError" in state["errors"]
    assert status_response.status_code == 200, status_response.text
    payload = status_response.json()
    assert payload["status"] == "error"
    assert payload["current_review"] is None
    assert payload["state"]["request_succeeded"] is False
    assert payload["state"]["success"] is False
    assert payload["state"]["full_media_success"] is False
    assert payload["state"]["pipeline_complete"] is False
    assert payload["state"]["publish_allowed"] is False
    assert payload["state"]["delivery_accepted"] is False


def test_steprunner_state_to_legacy_keeps_contract_for_partial_state() -> None:
    state = _sample_steprunner_state()
    state["steps"]["assemble_final"] = {"status": "running", "output": None}

    legacy = _steprunner_state_to_legacy("run_2", state)

    missing = [field for field in LEGACY_PROXY_REQUIRED_STATE_FIELDS if field not in legacy]
    assert missing == []
    assert legacy["distribution_plans"] == []
    assert legacy["pipeline_complete"] is False
    assert _get_state_status(legacy) == "interrupted"


def test_steprunner_state_to_legacy_not_found_shape() -> None:
    legacy = _steprunner_state_to_legacy("missing", None)

    assert legacy == {"label": "missing", "status": "not_found"}
    assert _get_state_status(legacy) == "not_found"


def test_steprunner_state_to_legacy_projects_commercial_injection_without_payload() -> None:
    state = _sample_steprunner_state()
    state["current_step"] = "strategy"
    state["config"].update(
        {
            SCENARIO_INJECTION_CONFIG_KEY: {
                "scenario": "s1",
                "brand_id": "momcozy",
                "platform": "tiktok",
                "read_only": True,
                "evidence_level": "L2-fixture-or-dry-run",
                "steps": [
                    {
                        "scenario": "s1",
                        "step": "strategy",
                        "hard_token_ids": ["bat_hard_fixture"],
                        "soft_token_ids": [],
                        "source_token_ids": ["bat_hard_fixture"],
                        "bundle_refs": ["BrandConstraintBundle"],
                        "toolbox_refs": ["ImageToolbox"],
                        "contract_refs": ["QualityContract"],
                        "gate_checks": ["rights_pass"],
                        "notes": [],
                    }
                ],
            },
            SCENARIO_INJECTION_MODE_KEY: "read_only_blueprint",
            SCENARIO_INJECTION_EVIDENCE_LEVEL_KEY: "L2-fixture-or-dry-run",
        }
    )
    state["steps"]["strategy"][STEP_INJECTION_DATA_KEY] = {
        "scenario": "s1",
        "step": "strategy",
        "prompt_payload": "must-not-leak",
    }
    state[CURRENT_STEP_INJECTION_KEY] = {
        "scenario": "s1",
        "step": "strategy",
        "prompt_payload": "must-not-leak",
    }

    legacy = _steprunner_state_to_legacy("run_3", state)

    assert legacy[CURRENT_STEP_INJECTION_KEY]["source_token_ids"] == ["bat_hard_fixture"]
    assert legacy["steps"]["strategy"][STEP_INJECTION_DATA_KEY]["gate_checks"] == ["rights_pass"]
    assert legacy["step_commercial_injections"]["strategy"]["bundle_refs"] == ["BrandConstraintBundle"]
    assert legacy[CURRENT_RUNTIME_INJECTION_KEY]["prompt_injection_allowed"] is False
    assert legacy["steps"]["strategy"][STEP_RUNTIME_INJECTION_DATA_KEY]["blocked_reasons"] == [
        "reviewed brand bundle missing"
    ]
    assert legacy["step_runtime_injections"]["strategy"]["contract_refs"] == ["QualityContract"]
    serialized = str(
        {
            "current": legacy[CURRENT_STEP_INJECTION_KEY],
            "step": legacy["steps"]["strategy"][STEP_INJECTION_DATA_KEY],
            "map": legacy["step_commercial_injections"],
            "runtime_current": legacy[CURRENT_RUNTIME_INJECTION_KEY],
            "runtime_step": legacy["steps"]["strategy"][STEP_RUNTIME_INJECTION_DATA_KEY],
            "runtime_map": legacy["step_runtime_injections"],
        }
    )
    assert "must-not-leak" not in serialized
    assert "prompt_payload" not in serialized
