"""S3 must preserve paid-provider and simulation truth across keyframe failures."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.models.provider_cost import ProviderCostContractError
from src.pipeline import s3_remix_pipeline as s3_module
from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline
from src.skills.keyframe_images import KeyframeImagesSkill
from src.skills.registry import SkillRegistry


def _storyboard() -> dict[str, object]:
    return {
        "script_id": "s3-contract",
        "shots": [
            {"visual": "product close-up"},
            {"visual": "lifestyle scene"},
        ],
    }


@pytest.mark.asyncio
async def test_s3_keyframe_provider_cost_error_escapes_without_log_or_fallback() -> None:
    pipeline = S3InfluencerRemixPipeline()
    contract_error = ProviderCostContractError(
        "provider_cost_outcome_ambiguous",
        "private-provider-detail",
    )
    pipeline._registry.execute = AsyncMock(side_effect=contract_error)

    with (
        patch.object(s3_module.logger, "error") as error_log,
        patch.object(s3_module.logger, "warning") as warning_log,
        pytest.raises(ProviderCostContractError) as raised,
    ):
        await pipeline._step_keyframe_images(_storyboard(), {})

    assert raised.value is contract_error
    error_log.assert_not_called()
    warning_log.assert_not_called()


@pytest.mark.asyncio
async def test_s3_keyframe_generic_failure_logs_stable_code_and_marks_fallback_simulated() -> None:
    pipeline = S3InfluencerRemixPipeline()
    pipeline._registry.execute = AsyncMock(
        side_effect=RuntimeError("private-provider-detail"),
    )

    with patch.object(s3_module.logger, "error") as error_log:
        result = await pipeline._step_keyframe_images(_storyboard(), {})

    failure_log = next(
        call
        for call in error_log.call_args_list
        if call.args and call.args[0] == "s3: keyframe-images skill failed"
    )
    assert failure_log.kwargs["code"] == "s3_keyframe_generation_failed"
    assert "error" not in failure_log.kwargs
    assert "private-provider-detail" not in str(failure_log)
    assert result["simulated"] is True
    assert result["keyframes_generated"] == 0
    assert all(shot["keyframe_image_path"] == "" for shot in result["shots"])
    assert all(shot["simulated"] is True for shot in result["shots"])


@pytest.mark.asyncio
async def test_s3_keyframe_cancellation_escapes_full_skill_chain_without_fallback() -> None:
    pipeline = S3InfluencerRemixPipeline()
    cancellation = asyncio.CancelledError("cancelled-provider-job")

    async def execute_with_cancel(
        _registry: SkillRegistry,
        name: str,
        params: dict[str, object],
    ):
        if name == "keyframe-images":
            return await KeyframeImagesSkill().execute(params)
        if name == "gpt-image-generate-skill":
            raise cancellation
        raise AssertionError(f"unexpected skill: {name}")

    with (
        patch.object(SkillRegistry, "execute", new=execute_with_cancel),
        patch.object(s3_module.logger, "error") as error_log,
        patch.object(s3_module.logger, "warning") as warning_log,
        pytest.raises(asyncio.CancelledError) as raised,
    ):
        await pipeline._step_keyframe_images(_storyboard(), {})

    assert raised.value is cancellation
    error_log.assert_not_called()
    warning_log.assert_not_called()
