from __future__ import annotations

from src.routers.pipeline import (
    LEGACY_PROXY_REQUIRED_STATE_FIELDS,
    _get_state_status,
    _steprunner_state_to_legacy,
)


def _sample_steprunner_state() -> dict:
    return {
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
