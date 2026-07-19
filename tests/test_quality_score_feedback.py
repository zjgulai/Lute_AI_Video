from __future__ import annotations

from typing import Any

import pytest

from src.pipeline import step_runner
from src.skills.keyframe_images import KeyframeImagesSkill
from tests.generation_policy_test_utils import attach_test_provider_execution_authority


def _storyboard(score: float | None) -> dict[str, Any]:
    sb: dict[str, Any] = {
        "script_id": "test_sb",
        "shots": [
            {"visual": "warm bedroom", "camera": "static", "shot_type": "MS"},
            {"visual": "product close-up", "camera": "slow push-in", "shot_type": "ECU"},
        ],
    }
    if score is not None:
        sb["quality_score"] = score
    return sb


class _StubGptImageSkill:
    name = "gpt-image-generate-skill"

    async def execute(self, params: dict[str, Any]) -> Any:
        from src.skills.base import SkillResult

        return SkillResult(success=True, data={"image_path": f"/tmp/{params['image_id']}.png"})

    async def safe_execute(self, params: dict[str, Any]) -> Any:
        return await self.execute(params)


@pytest.fixture(autouse=True)
def _patch_gpt_image(monkeypatch: pytest.MonkeyPatch):
    from src.skills.registry import SkillRegistry

    stub = _StubGptImageSkill()

    async def _fake_execute(self: SkillRegistry, name: str, params: dict[str, Any]) -> Any:
        if name == "gpt-image-generate-skill":
            return await stub.execute(params)
        skill = self._skills.get(name) if hasattr(self, "_skills") else None
        if skill is None:
            from src.skills.base import SkillResult

            return SkillResult(success=False, error=f"unknown skill: {name}")
        return await skill.safe_execute(params)

    monkeypatch.setattr(SkillRegistry, "execute", _fake_execute, raising=True)


@pytest.mark.asyncio
async def test_keyframe_proceeds_when_score_high():
    skill = KeyframeImagesSkill()
    res = await skill.execute({"storyboard": _storyboard(0.85)})
    assert res.success is True
    assert res.data["keyframes_generated"] == 2
    assert "_quality_warning" not in res.data


@pytest.mark.asyncio
async def test_keyframe_warns_when_score_in_warn_band():
    skill = KeyframeImagesSkill()
    res = await skill.execute({"storyboard": _storyboard(0.65)})
    assert res.success is True
    assert "_quality_warning" in res.data
    assert "0.65" in res.data["_quality_warning"]


@pytest.mark.asyncio
async def test_keyframe_regenerates_when_score_below_threshold():
    skill = KeyframeImagesSkill()
    res = await skill.execute({"storyboard": _storyboard(0.40)})
    assert res.success is False
    assert res.data["regenerate_upstream"] == "storyboard"
    assert res.data["consumer"] == "keyframe_images"
    assert res.data["score"] == 0.40
    assert res.data["attempt"] == 0
    assert res.metadata["regenerate_upstream"] == "storyboard"


@pytest.mark.asyncio
async def test_keyframe_force_proceeds_when_attempts_exhausted():
    skill = KeyframeImagesSkill()
    res = await skill.execute({"storyboard": _storyboard(0.40), "_quality_attempt": 2})
    assert res.success is True
    assert "_quality_warning" in res.data
    assert "exhausted" in res.data["_quality_warning"]


@pytest.mark.asyncio
async def test_keyframe_proceeds_when_no_score_present():
    skill = KeyframeImagesSkill()
    res = await skill.execute({"storyboard": _storyboard(None)})
    assert res.success is True
    assert "_quality_warning" not in res.data


def test_step_runner_detect_signal_dict():
    sentinel = {"_regenerate_upstream": "storyboard", "score": 0.4}
    detected = step_runner._detect_regenerate_signal(sentinel)
    assert detected is sentinel


def test_step_runner_detect_signal_first_in_list():
    sentinel = {"_regenerate_upstream": "storyboard", "score": 0.4}
    other = {"shots": []}
    detected = step_runner._detect_regenerate_signal([sentinel, other])
    assert detected is sentinel


def test_step_runner_detect_signal_returns_none_for_normal_result():
    assert step_runner._detect_regenerate_signal([{"shots": [], "keyframes_generated": 2}]) is None
    assert step_runner._detect_regenerate_signal({"shots": []}) is None
    assert step_runner._detect_regenerate_signal(None) is None
    assert step_runner._detect_regenerate_signal([]) is None


def test_scenario_step_map_routes_storyboard_to_storyboards():
    assert step_runner._SCENARIO_REGENERATE_STEP_MAP["storyboard"] == "storyboards"
    assert step_runner._SCENARIO_REGENERATE_STEP_MAP["seedance_prompt"] == "video_prompts"


@pytest.mark.asyncio
async def test_handle_regenerate_signal_appends_chain_and_requeues_upstream(
    tmp_path,
    monkeypatch,
    isolated_provider_cost_db,
):
    del isolated_provider_cost_db
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.generation_policy import (
        EffectiveGenerationPolicy,
        resolve_generation_execution_profile,
    )
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)
    effective_policy = EffectiveGenerationPolicy(
        tenant_id="tenant-test",
        scenario="s1",
        enable_media_synthesis=False,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )
    state = {
        "label": "test_d11_chain",
        "tenant_id": "tenant-test",
        "scenario": "s1",
        "trace_id": "trace-d11",
        "config": {
            "enable_media_synthesis": False,
            "artifact_disposition": "pending_review",
            "provider_max_retries": 0,
            "effective_generation_policy": effective_policy.model_dump(mode="json"),
        },
        "steps": {
            "storyboards": {"status": "done", "completed_at": "2026-05-16T10:00:00"},
            "keyframe_images": {"status": "pending"},
        },
        "current_step": "keyframe_images",
    }
    execution_profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    state["config"]["effective_generation_execution_profile"] = execution_profile.model_dump()
    state["config"]["provider_job_caps"] = dict(execution_profile.provider_job_caps)
    await attach_test_provider_execution_authority(state)

    async def _save_noop2(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(runner.state_manager, "save", _save_noop2, raising=True)

    out = await runner._handle_regenerate_signal(
        state=state,
        step_name="keyframe_images",
        step_data=state["steps"]["keyframe_images"],
        step_duration_ms=12.5,
        signal={
            "_regenerate_upstream": "storyboard",
            "consumer": "keyframe_images",
            "score": 0.42,
            "reason": "test",
            "attempt": 0,
        },
        trace_id="trace-d11",
    )

    chain = out["regenerate_chain"]
    assert len(chain) == 1
    entry = chain[0]
    assert entry["consumer"] == "keyframe_images"
    assert entry["upstream_skill"] == "storyboard"
    assert entry["upstream_step"] == "storyboards"
    assert entry["score"] == 0.42
    assert entry["attempt"] == 1
    assert out["current_step"] == "storyboards"
    assert out["steps"]["storyboards"]["status"] == "pending"
    assert out["steps"]["storyboards"]["_quality_attempt"] == 1
    assert "completed_at" not in out["steps"]["storyboards"]
    assert out["steps"]["keyframe_images"]["status"] == "pending"


@pytest.mark.asyncio
async def test_handle_regenerate_signal_unknown_upstream_step_marks_done(tmp_path, monkeypatch):
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)
    state = {
        "label": "test_d11_unknown",
        "scenario": "s1",
        "trace_id": "trace-d11-u",
        "steps": {"keyframe_images": {"status": "pending"}},
        "current_step": "keyframe_images",
    }

    out = await runner._handle_regenerate_signal(
        state=state,
        step_name="keyframe_images",
        step_data=state["steps"]["keyframe_images"],
        step_duration_ms=5.0,
        signal={"_regenerate_upstream": "no_such_skill"},
        trace_id="trace-d11-u",
    )

    assert out["steps"]["keyframe_images"]["status"] == "done"
    assert "regenerate_chain" not in out
