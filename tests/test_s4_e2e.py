"""S4 Live Shoot E2E integration test.

Verifies the S4 (Live Shoot to Video) scenario end-to-end using StepRunner:
1. script-writer-skill generates scripts from footage + product
2. seedance-video-prompt generates video prompts
3. gpt-image-thumbnail-prompt generates thumbnail prompts

Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import pytest

from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
from src.skills.registry import SkillRegistry

import src.skills.script_writer  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.thumbnail_prompt  # noqa: F401


@pytest.fixture(autouse=True)
def _clear_registry():
    SkillRegistry.clear_global()
    # Re-import to re-register
    import src.skills.script_writer  # noqa: F401
    import src.skills.seedance_prompt  # noqa: F401
    import src.skills.thumbnail_prompt  # noqa: F401
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
    assert result.get("steps_completed") == 3


@pytest.mark.asyncio
async def test_s4_step_runner_init_and_resume():
    """S4 via StepRunner: init_state + resume produces valid state."""
    from src.pipeline.step_runner import StepRunner
    from src.pipeline.state_manager import PipelineStateManager

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
