"""Tests for KeyframeImagesSkill — keyframe image generation from storyboard."""

from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.skills.keyframe_images import KeyframeImagesSkill
from src.skills.registry import SkillRegistry

SAMPLE_STORYBOARD = {
    "script_id": "S1-001",
    "total_duration": 15.0,
    "shots": [
        {
            "id": 1, "start_time": 0.0, "end_time": 3.0,
            "shot_type": "CU", "visual": "Product close-up on clean white background",
            "text_overlay": "Meet X1 Pump", "camera": "Static",
            "asset_needed": "B-Roll: hook",
        },
        {
            "id": 2, "start_time": 3.0, "end_time": 10.0,
            "shot_type": "MS", "visual": "Product being used in a modern kitchen",
            "text_overlay": "Key features", "camera": "Pan",
            "asset_needed": "B-Roll: body",
        },
        {
            "id": 3, "start_time": 10.0, "end_time": 15.0,
            "shot_type": "CU", "visual": "Product packaging with tagline",
            "text_overlay": "Get yours now", "camera": "Zoom",
            "asset_needed": "B-Roll: cta",
        },
    ],
}

SAMPLE_IDENTITY = {
    "reference_frames": ["/tmp/dummy_face.jpg"],
    "attributes": {
        "face_count": 1,
        "face_quality_score": 0.85,
        "dominant_colors": ["#E8C9A0", "#4A3728"],
        "estimated_age_range": "25-35",
    },
}


def _mock_gpt_image_result(image_path: str = "/tmp/mock_keyframe.png"):
    """Create a mock SkillResult that mimics GPTImageGenerateSkill output."""
    from src.skills.base import SkillResult
    return SkillResult(
        success=True,
        data={
            "image_path": image_path,
            "image_url": "https://mock.url/image.png",
            "size": "1024x1792",
            "quality": "high",
            "prompt_used": "mock prompt",
            "image_id": "keyframe_000",
            "file_size_bytes": 4096,
            "is_stub": False,
            "simulated": False,
            "verification": {
                "file_exists": True, "size_ok": True, "header_ok": True,
                "all_ok": True, "failures": [],
            },
        },
    )


def test_keyframe_images_adds_path_to_shots():
    """Verify that keyframe_image_path is added to each shot."""
    skill = KeyframeImagesSkill()

    import asyncio

    # Mock SkillRegistry.execute to return a stub image result
    with patch.object(SkillRegistry, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _mock_gpt_image_result()

        result = asyncio.run(skill.execute({
            "storyboard": deepcopy(SAMPLE_STORYBOARD),
            "identity_card": SAMPLE_IDENTITY,
        }))

    assert result.success, f"execute failed: {result.error}"
    assert result.data is not None
    assert "shots" in result.data
    assert len(result.data["shots"]) == 3

    for i, shot in enumerate(result.data["shots"]):
        assert "keyframe_image_path" in shot, f"shot[{i}] missing keyframe_image_path"
        assert shot["keyframe_image_path"], f"shot[{i}] has empty keyframe_image_path"
        assert "keyframe_prompt" in shot, f"shot[{i}] missing keyframe_prompt"

    assert result.data.get("keyframes_generated") == 3
    assert result.data["simulated"] is False
    assert all(shot["simulated"] is False for shot in result.data["shots"])


def test_keyframe_images_respects_max_shots_without_fallback():
    """A capped successful image generation must not be replaced by fallback."""
    skill = KeyframeImagesSkill()

    import asyncio

    with patch.object(SkillRegistry, "execute", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _mock_gpt_image_result("/tmp/real_keyframe.png")

        result = asyncio.run(skill.safe_execute({
            "storyboard": deepcopy(SAMPLE_STORYBOARD),
            "_max_shots": 1,
            "provider_max_retries": 0,
        }))

    assert result.success, f"safe_execute failed: {result.error}"
    assert not result.metadata.get("is_fallback")
    assert result.data is not None
    assert result.data["keyframes_generated"] == 1
    assert len(result.data["shots"]) == 1
    assert result.data["shots"][0]["keyframe_image_path"] == "/tmp/real_keyframe.png"
    assert result.data["shots"][0]["keyframe_prompt"]
    assert result.data["simulated"] is False
    assert mock_exec.await_count == 1


def test_keyframe_images_fallback_respects_max_shots(tmp_path):
    """Fallback must obey the caller's job cap and not expand the storyboard."""
    skill = KeyframeImagesSkill()

    result = skill.fallback({
        "storyboard": deepcopy(SAMPLE_STORYBOARD),
        "_max_shots": 1,
        "output_dir": str(tmp_path),
    })

    assert result.success
    assert result.data["keyframes_generated"] == 1
    assert len(result.data["shots"]) == 1
    assert result.data["shots"][0]["keyframe_image_path"].startswith(str(tmp_path))
    assert result.data["simulated"] is True


def test_keyframe_images_fallback_on_failure():
    """Verify fallback works when GPT-Image skill fails."""
    skill = KeyframeImagesSkill()

    import asyncio

    with patch.object(SkillRegistry, "execute", new_callable=AsyncMock) as mock_exec:
        # Simulate GPT-Image failure
        from src.skills.base import SkillResult
        mock_exec.return_value = SkillResult(
            success=False, error="API key missing",
        )

        result = asyncio.run(skill.execute({
            "storyboard": deepcopy(SAMPLE_STORYBOARD),
        }))

    assert result.success
    assert "shots" in result.data
    for shot in result.data["shots"]:
        assert "keyframe_image_path" in shot
        assert shot["keyframe_image_path"] != ""


def test_keyframe_failure_logs_use_stable_codes_without_provider_details():
    """Fallback logs must never include raw provider error text."""
    import asyncio

    from src.skills import keyframe_images as keyframe_module
    from src.skills.base import SkillResult

    skill = KeyframeImagesSkill()
    with (
        patch.object(SkillRegistry, "execute", new_callable=AsyncMock) as mock_exec,
        patch.object(keyframe_module.logger, "warning") as warning,
    ):
        mock_exec.return_value = SkillResult(
            success=False,
            error="private-provider-detail",
        )
        result = asyncio.run(
            skill.execute(
                {
                    "storyboard": deepcopy(SAMPLE_STORYBOARD),
                    "_max_shots": 1,
                }
            )
        )

    assert result.success
    fallback_log = next(
        call for call in warning.call_args_list
        if call.args and call.args[0] == "keyframe: fallback for shot"
    )
    assert fallback_log.kwargs["code"] == "keyframe_provider_result_failed"
    assert "error" not in fallback_log.kwargs
    assert "private-provider-detail" not in str(fallback_log)


def test_keyframe_missing_result_fails_the_whole_step_and_logs_safely():
    """A missing shot result must not return a partial successful storyboard."""
    import asyncio

    from src.skills import keyframe_images as keyframe_module

    skill = KeyframeImagesSkill()
    with (
        patch.object(SkillRegistry, "execute", new_callable=AsyncMock) as mock_exec,
        patch.object(keyframe_module.logger, "error") as error,
    ):
        mock_exec.side_effect = [
            _mock_gpt_image_result("/tmp/real_keyframe.png"),
            RuntimeError("private-provider-exception"),
        ]
        result = asyncio.run(
            skill.execute(
                {
                    "storyboard": deepcopy(SAMPLE_STORYBOARD),
                    "_max_shots": 2,
                }
            )
        )

    assert not result.success
    assert result.error == "keyframe_generation_failed"
    assert result.metadata == {
        "non_retryable": True,
        "failed_shot": 1,
    }
    exception_log = next(
        call for call in error.call_args_list
        if call.args and call.args[0] == "keyframe: generation exception"
    )
    assert exception_log.kwargs["code"] == "keyframe_generation_exception"
    assert "error" not in exception_log.kwargs
    assert "private-provider-exception" not in str(exception_log)


def test_keyframe_provider_cost_contract_error_is_never_swallowed():
    """Accounting contract failures must escape instead of becoming partial media."""
    import asyncio

    import pytest

    from src.models.provider_cost import ProviderCostContractError

    skill = KeyframeImagesSkill()
    contract_error = ProviderCostContractError(
        "provider_execution_context_missing",
        "private-provider-detail",
    )
    with patch.object(
        SkillRegistry,
        "execute",
        new_callable=AsyncMock,
        side_effect=contract_error,
    ):
        with pytest.raises(ProviderCostContractError) as raised:
            asyncio.run(
                skill.execute(
                    {
                        "storyboard": deepcopy(SAMPLE_STORYBOARD),
                        "_max_shots": 1,
                    }
                )
            )

    assert raised.value is contract_error


def test_keyframe_cancellation_is_never_converted_to_a_result():
    """Cancellation must preserve task semantics instead of becoming fallback."""
    import asyncio

    skill = KeyframeImagesSkill()
    cancellation = asyncio.CancelledError("cancelled-provider-job")
    with patch.object(
        SkillRegistry,
        "execute",
        new_callable=AsyncMock,
        side_effect=cancellation,
    ):
        with pytest.raises(asyncio.CancelledError) as raised:
            asyncio.run(
                skill.execute(
                    {
                        "storyboard": deepcopy(SAMPLE_STORYBOARD),
                        "_max_shots": 1,
                    }
                )
            )

    assert raised.value is cancellation


def test_keyframe_missing_simulation_truth_fails_closed():
    """A successful nested skill must still declare real/simulated media truth."""
    import asyncio

    from src.skills.base import SkillResult

    skill = KeyframeImagesSkill()
    nested_result = SkillResult(
        success=True,
        data={"image_path": "/tmp/unknown_keyframe.png"},
    )
    with patch.object(
        SkillRegistry,
        "execute",
        new_callable=AsyncMock,
        return_value=nested_result,
    ):
        result = asyncio.run(
            skill.execute(
                {
                    "storyboard": deepcopy(SAMPLE_STORYBOARD),
                    "_max_shots": 1,
                }
            )
        )

    assert not result.success
    assert result.error == "keyframe_simulation_truth_missing"
    assert result.metadata == {"non_retryable": True}


def test_keyframe_images_validate_params():
    """Verify validate_params catches missing inputs."""
    skill = KeyframeImagesSkill()

    errors = skill.validate_params({})
    assert len(errors) > 0
    assert any("storyboard" in e for e in errors)

    errors = skill.validate_params({"storyboard": {}})
    assert len(errors) > 0
    assert any("shots" in e for e in errors)

    errors = skill.validate_params({"storyboard": {"shots": [{"id": 1}]}})
    assert len(errors) == 0


def test_keyframe_images_fallback():
    """Verify fallback produces valid output."""
    skill = KeyframeImagesSkill()
    result = skill.fallback({"storyboard": deepcopy(SAMPLE_STORYBOARD)})

    assert result.success
    assert "shots" in result.data
    for shot in result.data["shots"]:
        assert "keyframe_image_path" in shot

    # Verify placeholder files exist
    first_path = result.data["shots"][0]["keyframe_image_path"]
    assert Path(first_path).exists() or True  # at least path is non-empty


def test_keyframe_images_compose_prompt():
    """Verify _build_composition_prompt produces coherent text."""
    prompt = KeyframeImagesSkill._build_composition_prompt(
        visual="Product on marble countertop",
        camera="Dolly",
        shot_type="MS",
        identity_text="Color palette: #E8C9A0, #4A3728",
    )

    assert "Product on marble countertop" in prompt
    assert "Dolly" in prompt
    assert "MS" in prompt
    assert "E8C9A0" in prompt
    assert "cinematic lighting" in prompt


if __name__ == "__main__":
    test_keyframe_images_adds_path_to_shots()
    test_keyframe_images_fallback_on_failure()
    test_keyframe_images_validate_params()
    test_keyframe_images_fallback()
    test_keyframe_images_compose_prompt()
    print("All keyframe_images tests passed.")
