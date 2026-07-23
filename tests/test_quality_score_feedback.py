from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.pipeline import step_runner
from src.pipeline.state_manager import PipelineStateManager
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

        return SkillResult(
            success=True,
            data={
                "image_path": f"/tmp/{params['image_id']}.png",
                "simulated": False,
            },
        )

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


def test_quality_rewind_blocks_consumer_until_upstream_completed() -> None:
    from fastapi import HTTPException

    state = {
        "config": {
            "quality_rewind": {
                "upstream_step": "storyboards",
                "consumer_step": "keyframe_images",
                "attempt": 1,
                "status": "awaiting_upstream",
            }
        }
    }

    with pytest.raises(HTTPException, match="upstream completion") as exc_info:
        step_runner._assert_quality_rewind_step_allowed(state, "keyframe_images")

    assert exc_info.value.status_code == 409
    step_runner._assert_quality_rewind_step_allowed(state, "storyboards")
    step_runner._record_quality_rewind_step_completion(state, "storyboards")
    assert state["config"]["quality_rewind"]["status"] == "upstream_completed"
    step_runner._assert_quality_rewind_step_allowed(state, "keyframe_images")
    step_runner._record_quality_rewind_step_completion(state, "keyframe_images")
    assert "quality_rewind" not in state["config"]


@pytest.mark.asyncio
async def test_run_step_blocks_quality_rewind_consumer_before_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    state = {
        "label": "quality-rewind-direct-consumer",
        "scenario": "s1",
        "config": {
            "quality_rewind": {
                "upstream_step": "storyboards",
                "consumer_step": "keyframe_images",
                "attempt": 1,
                "status": "awaiting_upstream",
            }
        },
        "steps": {"keyframe_images": {"status": "pending"}},
    }

    class _StateManager:
        async def load(self, _label: str) -> dict[str, Any]:
            return state

    runner = step_runner.StepRunner(cast(PipelineStateManager, _StateManager()))
    monkeypatch.setattr(
        "src.pipeline.generation_policy.assert_generation_step_allowed",
        lambda *_args, **_kwargs: SimpleNamespace(allowed_steps=("keyframe_images",)),
    )

    with pytest.raises(HTTPException, match="upstream completion") as exc_info:
        await runner.run_step(state["label"], "keyframe_images")

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_regenerate_step_blocks_consumer_before_epoch_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    state = {
        "label": "quality-rewind-regenerate-consumer",
        "scenario": "s1",
        "config": {
            "quality_rewind": {
                "upstream_step": "storyboards",
                "consumer_step": "keyframe_images",
                "attempt": 1,
                "status": "awaiting_upstream",
            }
        },
        "steps": {"keyframe_images": {"status": "pending"}},
    }

    class _StateManager:
        async def load(self, _label: str) -> dict[str, Any]:
            return state

    epoch_calls: list[str] = []

    async def record_epoch(
        _state: dict[str, Any],
        *,
        state_writer: Any,
        operation_key: str,
    ) -> None:
        del state_writer
        epoch_calls.append(operation_key)

    runner = step_runner.StepRunner(cast(PipelineStateManager, _StateManager()))
    monkeypatch.setattr(
        "src.pipeline.generation_policy.assert_generation_step_allowed",
        lambda *_args, **_kwargs: SimpleNamespace(allowed_steps=("keyframe_images",)),
    )
    monkeypatch.setattr(
        "src.services.provider_execution.persist_trusted_regeneration_epoch",
        record_epoch,
    )

    with pytest.raises(HTTPException, match="upstream completion") as exc_info:
        await runner.regenerate_step(state["label"], "keyframe_images")

    assert exc_info.value.status_code == 409
    assert epoch_calls == []


@pytest.mark.asyncio
async def test_resume_stops_immediately_when_consumer_dispatches_quality_rewind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "label": "quality-rewind-resume",
        "scenario": "s1",
        "config": {"effective_generation_policy": {}},
        "steps": {
            "storyboards": {"status": "done"},
            "keyframe_images": {"status": "pending"},
            "video_prompts": {"status": "pending"},
        },
        "current_step": "keyframe_images",
        "errors": [],
    }

    class _StateManager:
        async def load(self, _label: str) -> dict[str, Any]:
            return state

        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    runner = step_runner.StepRunner(cast(PipelineStateManager, _StateManager()))
    calls: list[str] = []

    async def fake_execute(
        current_state: dict[str, Any],
        step_name: str,
        force: bool = False,
    ) -> dict[str, Any]:
        del force
        calls.append(step_name)
        current_state["config"]["quality_rewind"] = {
            "upstream_step": "storyboards",
            "consumer_step": "keyframe_images",
            "attempt": 1,
            "status": "awaiting_upstream",
        }
        current_state["current_step"] = "storyboards"
        return current_state

    monkeypatch.setattr(runner, "_execute_step", fake_execute)
    monkeypatch.setattr(
        "src.pipeline.generation_policy.resolve_generation_execution_profile",
        lambda _state: SimpleNamespace(
            allowed_steps=("storyboards", "keyframe_images", "video_prompts")
        ),
    )

    result = await runner.resume(state["label"])

    assert calls == ["keyframe_images"]
    assert result["current_step"] == "storyboards"


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
            "c2pa_signing_mode": effective_policy.c2pa_signing_mode,
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
async def test_handle_regenerate_signal_rejects_exhausted_attempt_before_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "label": "quality-rewind-attempt-exhausted",
        "scenario": "s1",
        "trace_id": "trace-quality-rewind-exhausted",
        "steps": {
            "storyboards": {"status": "done", "_quality_attempt": 2},
            "keyframe_images": {"status": "pending"},
        },
        "current_step": "keyframe_images",
        "errors": [],
    }

    class _StateManager:
        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    async def unexpected_epoch(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("exhausted attempt must not create a regeneration epoch")

    monkeypatch.setattr(
        "src.services.provider_execution.persist_trusted_regeneration_epoch",
        unexpected_epoch,
    )
    runner = step_runner.StepRunner(cast(PipelineStateManager, _StateManager()))

    result = await runner._handle_regenerate_signal(
        state=state,
        step_name="keyframe_images",
        step_data=state["steps"]["keyframe_images"],
        step_duration_ms=1.0,
        signal={
            "_regenerate_upstream": "storyboard",
            "consumer": "keyframe_images",
            "attempt": 2,
        },
        trace_id=state["trace_id"],
    )

    assert result["pipeline_degraded"] is True
    assert result["degraded_reason"] == "quality_rewind_attempt_invalid"
    assert result["errors"] == ["quality_rewind_attempt_invalid"]
    assert result["steps"]["storyboards"]["status"] == "done"
    assert "regenerate_chain" not in result


@pytest.mark.asyncio
async def test_handle_regenerate_signal_rejects_stale_attempt_before_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_chain = [
        {"consumer": "keyframe_images", "upstream_step": "storyboards", "attempt": 1}
    ]
    state = {
        "label": "quality-rewind-stale-attempt",
        "scenario": "s1",
        "trace_id": "trace-quality-rewind-stale",
        "steps": {
            "storyboards": {"status": "done", "_quality_attempt": 1},
            "keyframe_images": {"status": "pending"},
        },
        "current_step": "keyframe_images",
        "errors": [],
        "regenerate_chain": copy.deepcopy(existing_chain),
    }

    class _StateManager:
        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    async def unexpected_epoch(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("stale attempt must not create a regeneration epoch")

    monkeypatch.setattr(
        "src.services.provider_execution.persist_trusted_regeneration_epoch",
        unexpected_epoch,
    )
    runner = step_runner.StepRunner(cast(PipelineStateManager, _StateManager()))

    result = await runner._handle_regenerate_signal(
        state=state,
        step_name="keyframe_images",
        step_data=state["steps"]["keyframe_images"],
        step_duration_ms=1.0,
        signal={"_regenerate_upstream": "storyboard", "attempt": 0},
        trace_id=state["trace_id"],
    )

    assert result["degraded_reason"] == "quality_rewind_attempt_invalid"
    assert result["regenerate_chain"] == existing_chain
    assert result["steps"]["storyboards"]["_quality_attempt"] == 1


@pytest.mark.asyncio
async def test_handle_regenerate_signal_first_write_is_crash_complete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "label": "quality-rewind-crash-complete",
        "scenario": "s1",
        "trace_id": "trace-quality-rewind-crash",
        "config": {},
        "steps": {
            "storyboards": {"status": "done", "completed_at": "before"},
            "keyframe_images": {"status": "pending"},
        },
        "current_step": "keyframe_images",
        "errors": [],
    }
    captured: list[dict[str, Any]] = []

    class _StateManager:
        async def save(self, _label: str, persisted: dict[str, Any]) -> None:
            captured.append(copy.deepcopy(persisted))
            raise RuntimeError("simulated crash after first durable write")

    async def persist_epoch(
        current: dict[str, Any],
        *,
        state_writer: Any,
        operation_key: str,
    ) -> None:
        current["config"]["provider_execution_context"] = {
            "regeneration_epoch_ref": f"epoch:{operation_key}"
        }
        await state_writer.save(current["label"], current)

    monkeypatch.setattr(
        "src.pipeline.generation_policy.assert_generation_step_allowed",
        lambda *_args, **_kwargs: SimpleNamespace(allowed_steps=("storyboards",)),
    )
    monkeypatch.setattr(
        "src.services.provider_execution.persist_trusted_regeneration_epoch",
        persist_epoch,
    )
    runner = step_runner.StepRunner(cast(PipelineStateManager, _StateManager()))

    with pytest.raises(RuntimeError, match="simulated crash"):
        await runner._handle_regenerate_signal(
            state=state,
            step_name="keyframe_images",
            step_data=state["steps"]["keyframe_images"],
            step_duration_ms=1.0,
            signal={"_regenerate_upstream": "storyboard", "attempt": 0},
            trace_id=state["trace_id"],
        )

    assert len(captured) == 1
    persisted = captured[0]
    assert persisted["current_step"] == "storyboards"
    assert persisted["steps"]["storyboards"]["status"] == "pending"
    assert persisted["steps"]["storyboards"]["_quality_attempt"] == 1
    assert persisted["steps"]["keyframe_images"]["status"] == "pending"
    assert persisted["regenerate_chain"][0]["attempt"] == 1
    assert persisted["config"]["quality_rewind"] == {
        "upstream_step": "storyboards",
        "consumer_step": "keyframe_images",
        "attempt": 1,
        "status": "awaiting_upstream",
    }
    assert "regeneration_epoch_ref" in persisted["config"]["provider_execution_context"]


@pytest.mark.asyncio
@pytest.mark.parametrize("upstream", ["no_such_skill", "", 7, ["storyboard"]])
async def test_handle_regenerate_signal_unknown_upstream_fails_closed(
    tmp_path,
    monkeypatch,
    upstream: object,
):
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
        signal={"_regenerate_upstream": upstream},
        trace_id="trace-d11-u",
    )

    assert out["steps"]["keyframe_images"]["status"] == "error"
    assert out["pipeline_degraded"] is True
    assert out["degraded_reason"] == "quality_rewind_upstream_invalid"
    assert out["errors"] == ["quality_rewind_upstream_invalid"]
    assert out["current_step"] == "keyframe_images"
    assert "regenerate_chain" not in out
