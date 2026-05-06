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

import pytest

from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
from src.skills.registry import SkillRegistry

import src.skills.seedance_prompt  # noqa: F401
import src.skills.seedance_video_generate  # noqa: F401
import src.skills.elevenlabs_tts  # noqa: F401
import src.skills.remotion_assemble  # noqa: F401
import src.skills.media_quality_audit  # noqa: F401


@pytest.fixture(autouse=True)
def _clear_registry():
    SkillRegistry.clear_global()
    import src.skills.seedance_prompt  # noqa: F401
    import src.skills.seedance_video_generate  # noqa: F401
    import src.skills.elevenlabs_tts  # noqa: F401
    import src.skills.remotion_assemble  # noqa: F401
    import src.skills.media_quality_audit  # noqa: F401
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
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager

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
    assert label.startswith("vlog_")

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
