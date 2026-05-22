"""S4 Live Shoot E2E integration test.

Verifies the S4 (Live Shoot to Video) scenario end-to-end using StepRunner:
1. script-writer-skill generates scripts from footage + product
2. seedance-video-prompt generates video prompts
3. gpt-image-thumbnail-prompt generates thumbnail prompts

Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import importlib

import pytest

import src.skills.script_writer as script_writer_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.thumbnail_prompt as thumbnail_prompt_skill
from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    SkillRegistry.clear_global()
    for module in (script_writer_skill, seedance_prompt_skill, thumbnail_prompt_skill):
        importlib.reload(module)
    yield
    SkillRegistry.clear_global()


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
            {"prompt": "first scene", "duration_seconds": 4},
            {"prompt": "second scene", "duration_seconds": 7},
            {"prompt": "third scene", "duration_seconds": 9},
        ],
        product_name="X1 Pump",
        label="s4-duration-test",
        errors=[],
    )

    assert captured_durations == [4, 7, 9]
    assert result["total_duration"] == 20


@pytest.mark.asyncio
async def test_s4_seedance_clips_chain_last_frame_continuity(monkeypatch):
    captured_continuity_frames: list[str | None] = []
    extracted_from: list[str] = []

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-generate-skill"
            captured_continuity_frames.append(params.get("continuity_frame_path"))
            index = len(captured_continuity_frames)
            return SkillResult(
                success=True,
                data={
                    "video_path": f"/tmp/s4-continuity-clip-{index}.mp4",
                    "duration_seconds": params["duration"],
                    "verification": {"all_ok": True},
                },
            )

    def _fake_extract(video_path: str, output_dir: str) -> str:
        extracted_from.append(video_path)
        return f"/tmp/last-frame-{len(extracted_from)}.jpg"

    pipeline = S4LiveShootPipeline()
    import src.pipeline.s4_live_shoot_pipeline as s4_module
    monkeypatch.setattr(s4_module, "extract_clip_last_frame", _fake_extract)

    result = await pipeline._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {"prompt": "first scene", "duration_seconds": 4},
            {"prompt": "second scene", "duration_seconds": 7},
            {"prompt": "third scene", "duration_seconds": 9},
        ],
        product_name="X1 Pump",
        label="s4-continuity-test",
        errors=[],
    )

    assert captured_continuity_frames == [
        None,
        "/tmp/last-frame-1.jpg",
        "/tmp/last-frame-2.jpg",
    ]
    assert extracted_from == [
        "/tmp/s4-continuity-clip-1.mp4",
        "/tmp/s4-continuity-clip-2.mp4",
        "/tmp/s4-continuity-clip-3.mp4",
    ]
    assert result["clip_details"][1]["continuity_frame_used"] == "/tmp/last-frame-1.jpg"
