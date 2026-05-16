from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.pipeline import step_runner
from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline as S3RemixPipeline
from src.skills.base import SkillResult


def test_detect_soft_degraded_signal_returns_payload():
    sentinel = {
        "_soft_degraded": True,
        "_degraded_reason": "video_analysis_failed_using_fallback",
        "_degraded_detail": "DeepSeek timeout after 60s",
        "viral_segments": [],
        "fallback_prompt": "Generic remix",
    }
    detected = step_runner._result_indicates_soft_degraded(sentinel)
    assert detected is not None
    assert detected["reason"] == "video_analysis_failed_using_fallback"
    assert detected["detail"] == "DeepSeek timeout after 60s"


def test_detect_soft_degraded_returns_none_for_normal_result():
    assert step_runner._result_indicates_soft_degraded(None) is None
    assert step_runner._result_indicates_soft_degraded([]) is None
    assert step_runner._result_indicates_soft_degraded({}) is None
    assert step_runner._result_indicates_soft_degraded({"_soft_degraded": False}) is None
    assert step_runner._result_indicates_soft_degraded({"foo": "bar"}) is None


def test_detect_soft_degraded_handles_missing_optional_fields():
    detected = step_runner._result_indicates_soft_degraded({"_soft_degraded": True})
    assert detected is not None
    assert detected["reason"] == "unknown"
    assert detected["detail"] == ""


@pytest.mark.asyncio
async def test_s3_video_analysis_failure_returns_soft_degraded_sentinel():
    pipeline = S3RemixPipeline()
    pipeline._registry = AsyncMock()
    pipeline._registry.execute = AsyncMock(return_value=SkillResult(
        success=False,
        error="DeepSeek timeout after 60s",
    ))

    state: dict[str, Any] = {
        "label": "s3_test",
        "scenario": "s3",
        "config": {"video_url": "https://example.com/kol.mp4", "product": {}},
        "steps": {
            "video_analysis": {"status": "pending"},
            "remix_script": {"status": "pending"},
        },
        "errors": [],
    }

    out = await pipeline.run_step("video_analysis", state)

    assert isinstance(out, dict)
    assert out["_soft_degraded"] is True
    assert out["_degraded_reason"] == "video_analysis_failed_using_fallback"
    assert "DeepSeek timeout" in out["_degraded_detail"]
    assert out["fallback_prompt"]
    assert "Generic product remix" in out["fallback_prompt"]
    assert out["viral_segments"] == []
    assert any("video_analysis_failed" in e for e in state["errors"])


@pytest.mark.asyncio
async def test_s3_video_analysis_success_returns_payload_unchanged():
    pipeline = S3RemixPipeline()
    pipeline._registry = AsyncMock()
    pipeline._registry.execute = AsyncMock(return_value=SkillResult(
        success=True,
        data={"hook_type": "pain_point", "segments": [{"start": 0, "end": 3}]},
    ))

    state: dict[str, Any] = {
        "label": "s3_test_ok",
        "scenario": "s3",
        "config": {"video_url": "https://example.com/kol.mp4", "product": {}},
        "steps": {"video_analysis": {"status": "pending"}},
        "errors": [],
    }

    out = await pipeline.run_step("video_analysis", state)
    assert "_soft_degraded" not in out
    assert out["hook_type"] == "pain_point"
    assert state["errors"] == []


@pytest.mark.asyncio
async def test_s3_remix_script_threads_fallback_prompt_when_upstream_degraded():
    pipeline = S3RemixPipeline()
    pipeline._registry = AsyncMock()

    captured_params: dict[str, Any] = {}

    async def _capture(skill_name: str, params: dict[str, Any]) -> SkillResult:
        captured_params.update(params)
        return SkillResult(success=True, data={"segments": [{"id": 1}]})

    pipeline._registry.execute = _capture

    degraded_analysis = {
        "_soft_degraded": True,
        "_degraded_reason": "video_analysis_failed_using_fallback",
        "fallback_prompt": "Generic product remix from original creator's segment.",
        "viral_segments": [],
    }
    state: dict[str, Any] = {
        "label": "s3_test_remix",
        "scenario": "s3",
        "config": {
            "video_url": "https://example.com/x.mp4",
            "product": {"name": "Pump", "pain_points": ["bulky"], "target_audience": "moms"},
            "influencer_name": "Jane",
            "brief_id": "RMX-001",
        },
        "steps": {
            "video_analysis": {"status": "done", "output": degraded_analysis},
            "remix_script": {"status": "pending"},
        },
        "errors": [],
    }

    out = await pipeline.run_step("remix_script", state)

    assert "fallback_prompt" in captured_params
    assert captured_params["fallback_prompt"] == degraded_analysis["fallback_prompt"]
    assert captured_params["upstream_degraded"] is True
    assert out["segments"] == [{"id": 1}]


@pytest.mark.asyncio
async def test_s3_remix_script_no_fallback_prompt_when_upstream_clean():
    pipeline = S3RemixPipeline()
    pipeline._registry = AsyncMock()

    captured_params: dict[str, Any] = {}

    async def _capture(skill_name: str, params: dict[str, Any]) -> SkillResult:
        captured_params.update(params)
        return SkillResult(success=True, data={"segments": []})

    pipeline._registry.execute = _capture

    clean_analysis = {"hook_type": "pain_point", "segments": [{"start": 0}]}
    state: dict[str, Any] = {
        "label": "s3_test_remix_ok",
        "scenario": "s3",
        "config": {
            "video_url": "https://example.com/x.mp4",
            "product": {"name": "Pump"},
            "influencer_name": "Jane",
            "brief_id": "RMX-002",
        },
        "steps": {
            "video_analysis": {"status": "done", "output": clean_analysis},
            "remix_script": {"status": "pending"},
        },
        "errors": [],
    }

    await pipeline.run_step("remix_script", state)
    assert "fallback_prompt" not in captured_params
    assert "upstream_degraded" not in captured_params


@pytest.mark.asyncio
async def test_step_runner_appends_to_soft_degraded_reasons(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)

    state: dict[str, Any] = {
        "label": "test_soft_degraded",
        "scenario": "s3",
        "trace_id": "trace-d10pr2",
        "errors": [],
        "steps": {
            "video_analysis": {"status": "pending"},
            "remix_script": {"status": "pending"},
        },
        "current_step": "video_analysis",
        "config": {},
        "mode": "auto",
    }

    monkeypatch.setattr(step_runner, "_get_scenario_config", lambda scenario: {
        "step_order": ["video_analysis", "remix_script"],
        "pipeline_class": "src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline",
    })

    async def _fake_run_step(self, step_name: str, st: dict[str, Any]) -> Any:
        return {
            "_soft_degraded": True,
            "_degraded_reason": "video_analysis_failed_using_fallback",
            "_degraded_detail": "test detail",
            "fallback_prompt": "fb",
            "viral_segments": [],
        }

    monkeypatch.setattr(S3RemixPipeline, "run_step", _fake_run_step, raising=True)

    out = await runner._execute_step(state, "video_analysis", force=False)

    assert "soft_degraded_reasons" in out
    assert len(out["soft_degraded_reasons"]) == 1
    entry = out["soft_degraded_reasons"][0]
    assert entry["step"] == "video_analysis"
    assert entry["reason"] == "video_analysis_failed_using_fallback"
    assert entry["detail"] == "test detail"
    assert entry["trace_id"] == "trace-d10pr2"
    assert "ts" in entry
    assert out.get("pipeline_degraded") is not True


@pytest.mark.asyncio
async def test_step_runner_soft_degraded_does_not_halt_pipeline_at_next_step(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)

    state: dict[str, Any] = {
        "label": "test_soft_continues",
        "scenario": "s3",
        "soft_degraded_reasons": [
            {"ts": "2026-05-16", "step": "video_analysis", "reason": "x", "detail": "y", "trace_id": "z"},
        ],
        "errors": [],
        "steps": {
            "remix_script": {"status": "pending"},
        },
        "current_step": "remix_script",
        "config": {},
        "mode": "auto",
    }

    assert state.get("pipeline_degraded") is not True