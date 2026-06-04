from __future__ import annotations

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
    assert legacy["pipeline_complete"] is True
    assert _get_state_status(legacy) == "complete"


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
    state["config"].update({
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
    })
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
    serialized = str({
        "current": legacy[CURRENT_STEP_INJECTION_KEY],
        "step": legacy["steps"]["strategy"][STEP_INJECTION_DATA_KEY],
        "map": legacy["step_commercial_injections"],
    })
    assert "must-not-leak" not in serialized
    assert "prompt_payload" not in serialized
