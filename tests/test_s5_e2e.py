"""S5 Brand VLOG E2E integration test.

Verifies the S5 (Brand VLOG) scenario end-to-end using StepRunner:
1. vlog_strategy generates shot list via LLM
2. seedance-video-prompt generates video prompts
3. seedance-video-generate produces clips
4. tts_audio generates voiceover
5. remotion-assemble produces final video
6. audit runs quality check

Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import importlib

import pytest

import src.skills.elevenlabs_tts as elevenlabs_tts_skill
import src.skills.media_quality_audit as media_quality_audit_skill
import src.skills.remotion_assemble as remotion_assemble_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.seedance_video_generate as seedance_video_generate_skill
from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    SkillRegistry.clear_global()
    for module in (
        elevenlabs_tts_skill,
        media_quality_audit_skill,
        remotion_assemble_skill,
        seedance_prompt_skill,
        seedance_video_generate_skill,
    ):
        importlib.reload(module)
    yield
    SkillRegistry.clear_global()


PRODUCT_SKU_FIXTURE = {
    "name": "LactFit Wearable Breast Pump X1",
    "shortName": "X1 Pump",
    "views": [
        {"label": "主视图", "title": "Front View", "usage_note": "Hero shot"},
        {"label": "45度视图", "title": "Angle View", "usage_note": "Detail shot"},
        {"label": "侧视图", "title": "Side View", "usage_note": "Profile"},
        {"label": "底视图", "title": "Bottom View", "usage_note": "Base detail"},
        {"label": "佩戴图", "title": "Worn View", "usage_note": "In-use shot"},
        {"label": "包装图", "title": "Package View", "usage_note": "Box shot"},
    ],
}

SELECTED_MODELS_FIXTURE = [
    {"name": "Sarah", "role": "new mom", "description": "28yo, first-time mother"},
]


@pytest.mark.asyncio
async def test_s5_full_pipeline_mock():
    """S5 full run() returns expected output shape in mock mode."""
    pipeline = S5BrandVlogPipeline()
    result = await pipeline.run(
        brand_id="lactfit",
        product_sku=PRODUCT_SKU_FIXTURE,
        scene_id="living-room",
        selected_models=SELECTED_MODELS_FIXTURE,
        story_description="A day in the life of a working mom",
        video_duration=30,
    )

    # In mock mode clips may be stubs — check structure, not media existence
    assert result.get("success") is not None
    assert result.get("scenario") == "brand_vlog"
    assert isinstance(result.get("scripts"), list)
    assert isinstance(result.get("video_prompts"), list)
    assert isinstance(result.get("clip_paths"), list)
    assert isinstance(result.get("audio_paths"), list)


@pytest.mark.asyncio
async def test_s5_step_runner_init_and_resume():
    """S5 via StepRunner: init_state + resume produces valid state."""
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    config = {
        "brand_id": "lactfit",
        "product_sku": PRODUCT_SKU_FIXTURE,
        "scene_id": "living-room",
        "selected_models": SELECTED_MODELS_FIXTURE,
        "story_description": "Test story",
        "video_duration": 15,
        "product_name": "X1 Pump",
        "output_label": "vlog_test",
    }

    runner = StepRunner(PipelineStateManager())
    label = await runner.init_state(config=config, mode="auto", scenario="s5")
    assert label.startswith("s5_")

    final_state = await runner.resume(label)
    assert final_state.get("scenario") == "s5"
    steps = final_state.get("steps", {})
    assert "vlog_strategy" in steps
    assert "video_prompts" in steps
    assert "seedance_clips" in steps
    assert "tts_audio" in steps

    # In mock mode all steps should complete quickly
    for step_name in ["vlog_strategy", "video_prompts", "seedance_clips", "tts_audio", "assemble_final", "audit"]:
        step_data = steps.get(step_name, {})
        assert step_data.get("status") in ("done", "pending"), f"Step {step_name} unexpected status"


@pytest.mark.asyncio
async def test_s5_audit_reads_persisted_assemble_list_path(monkeypatch):
    pipeline = S5BrandVlogPipeline()
    captured: dict[str, str] = {}

    async def _fake_audit(reg, video_path, audio_paths, thumbnail_paths, clip_paths, errors):
        captured["video_path"] = video_path
        return {"overall_status": "pass"}

    monkeypatch.setattr(pipeline, "_step_audit", _fake_audit)

    result = await pipeline.run_step(
        "audit",
        {
            "config": {
                "product_name": "X1 Pump",
                "video_duration": 15,
            },
            "steps": {
                "assemble_final": {"output": ["/tmp/s5-final.mp4", "/tmp/s5-render.json"]},
                "tts_audio": {"output": ["/tmp/s5.mp3"]},
                "seedance_clips": {
                    "output": {
                        "clip_paths": ["/tmp/s5-clip.mp4"],
                        "clip_details": [{"is_stub": False}],
                    },
                },
            },
            "errors": [],
        },
    )

    assert captured["video_path"] == "/tmp/s5-final.mp4"
    assert result == {"overall_status": "pass"}


@pytest.mark.asyncio
async def test_s5_run_preserves_persisted_assemble_list_paths(monkeypatch):
    class FakeRunner:
        def __init__(self, state_manager):
            pass

        async def init_state(self, *, config, mode, label, scenario):
            return label

        async def resume(self, label):
            return {
                "steps": {
                    "vlog_strategy": {"output": {"scripts": []}},
                    "video_prompts": {"output": []},
                    "seedance_clips": {
                        "output": {
                            "clip_paths": ["/tmp/s5-clip.mp4"],
                            "clip_details": [{"is_stub": False}],
                        },
                    },
                    "tts_audio": {"output": ["/tmp/s5.mp3"]},
                    "assemble_final": {"output": ["/tmp/s5-final.mp4", "/tmp/s5-render.json"]},
                    "audit": {"output": {}},
                },
                "errors": [],
            }

    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeRunner)

    result = await S5BrandVlogPipeline().run(
        brand_id="lactfit",
        product_sku=PRODUCT_SKU_FIXTURE,
        scene_id="living-room",
        selected_models=SELECTED_MODELS_FIXTURE,
        story_description="Test story",
        video_duration=15,
    )

    assert result["final_video_path"] == "/tmp/s5-final.mp4"
    assert result["render_json_path"] == "/tmp/s5-render.json"
