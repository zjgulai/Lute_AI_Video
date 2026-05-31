"""S4 Live Shoot E2E integration test.

Verifies the S4 (Live Shoot to Video) scenario end-to-end using StepRunner:
1. script-writer-skill generates scripts from footage + product
2. seedance-video-prompt generates video prompts
3. gpt-image-thumbnail-prompt generates thumbnail prompts

Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

import src.skills.continuity_storyboard_grid as continuity_storyboard_grid_skill
import src.skills.script_writer as script_writer_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.thumbnail_prompt as thumbnail_prompt_skill
from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    original_global_skills = dict(SkillRegistry._global_skills)
    SkillRegistry.clear_global()
    for module in (
        continuity_storyboard_grid_skill,
        script_writer_skill,
        seedance_prompt_skill,
        thumbnail_prompt_skill,
    ):
        importlib.reload(module)
    yield
    SkillRegistry._global_skills = original_global_skills


FOOTAGE_FIXTURE = [
    {"filename": "scene1.mp4", "duration": 15, "description": "Close-up of product"},
    {"filename": "scene2.mp4", "duration": 20, "description": "Lifestyle usage shot"},
]

PRODUCT_INFO_FIXTURE = {
    "name": "LactFit Wearable Breast Pump X1",
    "brand_name": "LactFit",
    "usps": ["Ultra-silent", "Hands-free", "2-hour battery"],
}


@pytest.mark.asyncio
async def test_s4_full_pipeline_mock():
    """S4 full run() returns expected output shape in mock mode."""
    pipeline = S4LiveShootPipeline()
    result = await pipeline.run(
        footage_assets=FOOTAGE_FIXTURE,
        product_info=PRODUCT_INFO_FIXTURE,
        topic="Working mom daily routine",
        target_platforms=["tiktok", "shopify"],
    )

    assert result.get("success") is True
    assert result.get("scenario") == "s4_live_shoot"
    assert isinstance(result.get("scripts"), list)
    assert isinstance(result.get("video_prompts"), list)
    assert isinstance(result.get("thumbnail_sets"), list)
    assert result.get("steps_completed") == 7


@pytest.mark.asyncio
@pytest.mark.hermetic_slow
async def test_s4_step_runner_init_and_resume():
    """S4 via StepRunner: init_state + resume produces valid state."""
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    config = {
        "footage_assets": FOOTAGE_FIXTURE,
        "product_info": PRODUCT_INFO_FIXTURE,
        "topic": "Test topic",
        "target_platforms": ["tiktok"],
        "product_name": "Test Product",
        "brand_name": "TestBrand",
    }

    runner = StepRunner(PipelineStateManager())
    label = await runner.init_state(config=config, mode="auto", scenario="s4")
    assert label.startswith("s4_")

    final_state = await runner.resume(label)
    assert final_state.get("scenario") == "s4"
    steps = final_state.get("steps", {})
    assert "scripts" in steps
    assert "video_prompts" in steps
    assert "thumbnails" in steps

    # All steps should be done (mock mode is fast)
    for step_name in ["scripts", "video_prompts", "thumbnails"]:
        assert steps[step_name]["status"] == "done", f"Step {step_name} not done"


@pytest.mark.asyncio
async def test_s4_scripts_forwards_configured_video_duration():
    """S4 script generation must honor the caller's target duration."""
    captured: dict[str, int] = {}

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "script-writer-skill"
            captured["video_duration"] = params["video_duration"]
            return SkillResult(
                success=True,
                data={"scripts": [{"id": "s4-script", "segments": []}]},
            )

    result = await S4LiveShootPipeline()._step_scripts(
        reg=FakeRegistry(),
        config={
            "footage_assets": FOOTAGE_FIXTURE,
            "product_info": PRODUCT_INFO_FIXTURE,
            "product_name": PRODUCT_INFO_FIXTURE["name"],
            "video_duration": 15,
        },
        steps={},
        errors=[],
    )

    assert captured["video_duration"] == 15
    assert result[0]["id"] == "s4-script"


@pytest.mark.asyncio
async def test_s4_audit_reads_persisted_assemble_list_path(monkeypatch):
    pipeline = S4LiveShootPipeline()
    captured: dict[str, str] = {}

    async def _fake_audit(**kwargs):
        captured["video_path"] = kwargs["video_path"]
        return {"overall_status": "pass"}

    monkeypatch.setattr(pipeline, "_step_audit", _fake_audit)

    result = await pipeline.run_step(
        "audit",
        {
            "config": {
                "product_name": "X1 Pump",
                "target_language": "en",
                "video_duration": 15,
            },
            "steps": {
                "assemble_final": {"output": ["/tmp/s4-final.mp4", "/tmp/s4-render.json"]},
                "tts_audio": {"output": {"audio_paths": ["/tmp/s4.mp3"]}},
                "thumbnails": {"output": []},
                "scripts": {"output": []},
                "seedance_clips": {"output": {"clip_paths": ["/tmp/s4-clip.mp4"]}},
            },
            "errors": [],
        },
    )

    assert captured["video_path"] == "/tmp/s4-final.mp4"
    assert result == {"overall_status": "pass"}


@pytest.mark.asyncio
async def test_s4_seedance_clips_use_prompt_durations():
    captured_durations: list[int] = []

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-generate-skill"
            captured_durations.append(params["duration"])
            index = len(captured_durations)
            return SkillResult(
                success=True,
                data={
                    "video_path": f"/tmp/s4-clip-{index}.mp4",
                    "duration_seconds": params["duration"],
                    "verification": {"all_ok": True},
                },
            )

    result = await S4LiveShootPipeline()._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {
                "prompt": "first scene",
                "duration_seconds": 4,
                "scene_beat": "setup_context",
                "beat_summary": "establish live-shoot scene",
                "transition_intent": "lead into the hands-on usage",
            },
            {
                "prompt": "second scene",
                "duration_seconds": 7,
                "scene_beat": "usage_demo",
                "beat_summary": "capture product use in motion",
                "transition_intent": "carry action into proof detail",
            },
            {
                "prompt": "third scene",
                "duration_seconds": 9,
                "scene_beat": "proof_detail",
                "beat_summary": "close with tactile result shot",
                "transition_intent": "resolve into a grounded finish",
            },
        ],
        product_name="X1 Pump",
        label="s4-duration-test",
        errors=[],
    )

    assert captured_durations == [4, 7, 9]
    assert result["total_duration"] == 20
    assert result["clip_details"][0]["scene_beat"] == "setup_context"
    assert result["clip_details"][1]["beat_summary"] == "capture product use in motion"
    assert result["clip_details"][2]["transition_intent"] == "resolve into a grounded finish"


@pytest.mark.asyncio
async def test_s4_seedance_clips_concurrent_generation():
    """P0-2: S4 clips are generated concurrently with no continuity chain."""
    call_log: list[dict[str, Any]] = []

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-generate-skill"
            call_log.append({"name": name, "params": params})
            return SkillResult(
                success=True,
                data={
                    "video_path": f"/tmp/s4-concurrent-{params['output_label']}.mp4",
                    "duration_seconds": params["duration"],
                    "verification": {"all_ok": True},
                },
            )

    pipeline = S4LiveShootPipeline()
    result = await pipeline._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {"prompt": "first scene", "duration_seconds": 4},
            {"prompt": "second scene", "duration_seconds": 7},
            {"prompt": "third scene", "duration_seconds": 9},
        ],
        product_name="X1 Pump",
        label="s4-concurrent-test",
        errors=[],
    )

    # All 3 clips generated (concurrent, no continuity_frame_path)
    assert len(call_log) == 3
    for call in call_log:
        assert "continuity_frame_path" not in call["params"]

    # clip_details populated correctly with continuity_frame_used=None
    assert len(result["clip_paths"]) == 3
    assert len(result["clip_details"]) == 3
    assert result["clip_details"][0]["continuity_frame_used"] is None
    assert result["total_duration"] == 20


@pytest.mark.asyncio
async def test_s4_continuity_skill_fallback_marks_soft_degraded():
    pipeline = S4LiveShootPipeline()

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "continuity-storyboard-grid"
            return SkillResult(
                success=True,
                data={"clip_groups": [{"clip_index": 1}]},
                metadata={"is_fallback": True, "fallback_reason": "mock_fallback"},
            )

    result = await pipeline._step_continuity_storyboard_grid(
        reg=FakeRegistry(),
        scripts=[{"segments": [{"start_time": 0, "end_time": 5, "visual_description": "demo"}]}],
        product_name="X1 Pump",
        topic="demo topic",
        product_info={},
        brand_guidelines={},
        errors=[],
    )

    assert result["_soft_degraded"] is True
    assert result["_degraded_reason"] == "continuity_skill_fallback"
    assert result["degraded"] is True


@pytest.mark.asyncio
async def test_s4_continuity_threads_topic_brand_and_stock_context():
    pipeline = S4LiveShootPipeline()
    captured: dict[str, Any] = {}

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "continuity-storyboard-grid"
            captured["params"] = params
            return SkillResult(
                success=True,
                data={
                    "grid_type": "12-grid",
                    "product_name": "X1 Pump",
                    "visual_identity": {},
                    "micro_shots": [],
                    "clip_groups": [{"clip_index": 1, "shot_indices": [1, 2, 3], "duration": 5}],
                },
            )

    await pipeline._step_continuity_storyboard_grid(
        reg=FakeRegistry(),
        scripts=[{
            "segments": [
                {"start_time": 0, "end_time": 5, "visual_description": "Mother uses the pump at her desk."},
            ]
        }],
        product_name="X1 Pump",
        topic="Working mom desk routine",
        product_info={"brand_name": "LactFit", "usps": ["hands-free", "quiet"]},
        brand_guidelines={
            "voice_guidelines": "warm, supportive",
            "values": ["comfort", "confidence"],
            "visual_constraints": "natural window light; authentic work setting",
            "stock_footage_urls": ["https://example.com/stock-a.mp4", "https://example.com/stock-b.mp4"],
        },
        errors=[],
    )

    product_catalog = captured["params"]["product_catalog"]
    assert product_catalog["brand_name"] == "LactFit"
    assert product_catalog["usage_scenario"] == "Working mom desk routine"
    assert product_catalog["usps"] == ["hands-free", "quiet"]
    assert product_catalog["values"] == ["comfort", "confidence"]
    assert product_catalog["voice_guidelines"] == "warm, supportive"
    assert "natural window light" in product_catalog["visual_constraints"]
    assert any("2 approved stock footage" in item for item in product_catalog["visual_constraints"])


def test_s4_fallback_clip_groups_include_topic_and_stock_context():
    groups = S4LiveShootPipeline._s4_fallback_clip_groups(
        shots=[{
            "start_time": 0,
            "end_time": 4,
            "visual": "Close-up of product on desk",
            "text_overlay": "Desk demo",
        }],
        product_name="X1 Pump",
        topic="Working mom desk routine",
        stock_footage_count=2,
    )

    prompt = groups[0]["seedance_prompt"]
    assert "Working mom desk routine" in prompt
    assert "2 approved stock/live reference asset" in prompt
