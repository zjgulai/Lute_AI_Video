from __future__ import annotations

from typing import Any

import pytest

from src.pipeline import step_runner
from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline


def test_all_clips_are_stubs_returns_false_when_no_clips():
    assert S5BrandVlogPipeline._all_clips_are_stubs([], []) is True


def test_all_clips_are_stubs_with_explicit_metadata_all_true():
    paths = ["/p1.mp4", "/p2.mp4"]
    details = [{"is_stub": True}, {"is_stub": True}]
    assert S5BrandVlogPipeline._all_clips_are_stubs(paths, details) is True


def test_all_clips_are_stubs_with_explicit_metadata_mixed():
    paths = ["/p1.mp4", "/p2.mp4"]
    details = [{"is_stub": True}, {"is_stub": False}]
    assert S5BrandVlogPipeline._all_clips_are_stubs(paths, details) is False


def test_all_clips_are_stubs_with_explicit_metadata_all_real():
    paths = ["/p1.mp4", "/p2.mp4"]
    details = [{"is_stub": False}, {"is_stub": False}]
    assert S5BrandVlogPipeline._all_clips_are_stubs(paths, details) is False


def test_all_clips_are_stubs_falls_back_to_filename_check_when_no_details():
    paths = ["/tmp/stub_seg_0.mp4", "/tmp/stub_seg_1.mp4"]
    assert S5BrandVlogPipeline._all_clips_are_stubs(paths, None) is True

    real_paths = ["/tmp/seedance_0.mp4", "/tmp/seedance_1.mp4"]
    assert S5BrandVlogPipeline._all_clips_are_stubs(real_paths, None) is False


def test_result_indicates_all_stubs_with_explicit_marker():
    result = {"_all_stubs": True, "clip_paths": ["/p.mp4"], "clip_details": []}
    assert step_runner._result_indicates_all_stubs(result) is True


def test_result_indicates_all_stubs_inferred_from_details():
    result = {
        "clip_paths": ["/p1.mp4", "/p2.mp4"],
        "clip_details": [{"is_stub": True}, {"is_stub": True}],
    }
    assert step_runner._result_indicates_all_stubs(result) is True


def test_result_indicates_all_stubs_false_with_mixed_clips():
    result = {
        "clip_paths": ["/p1.mp4", "/p2.mp4"],
        "clip_details": [{"is_stub": True}, {"is_stub": False}],
    }
    assert step_runner._result_indicates_all_stubs(result) is False


def test_result_indicates_all_stubs_false_for_unrelated_result():
    assert step_runner._result_indicates_all_stubs(None) is False
    assert step_runner._result_indicates_all_stubs([]) is False
    assert step_runner._result_indicates_all_stubs({"clip_paths": []}) is False
    assert step_runner._result_indicates_all_stubs({"_all_stubs": False}) is False
    assert step_runner._result_indicates_all_stubs("string-result") is False


@pytest.mark.asyncio
async def test_step_runner_marks_pipeline_degraded_on_seedance_all_stubs(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)

    state = {
        "label": "test_d10_s5",
        "scenario": "s5",
        "trace_id": "trace-d10",
        "errors": [],
        "steps": {
            "seedance_clips": {"status": "pending"},
            "assemble_final": {"status": "pending"},
        },
        "current_step": "seedance_clips",
        "config": {},
        "mode": "auto",
    }

    monkeypatch.setattr(step_runner, "_get_scenario_config", lambda scenario: {
        "step_order": ["seedance_clips", "assemble_final"],
        "pipeline_class": "src.pipeline.s5_brand_vlog_pipeline.S5BrandVlogPipeline",
    })

    async def _fake_run_step(self, step_name: str, st: dict[str, Any]) -> Any:
        return {
            "clip_paths": ["/tmp/stub_a.mp4", "/tmp/stub_b.mp4"],
            "clip_details": [{"is_stub": True}, {"is_stub": True}],
            "_all_stubs": True,
        }

    monkeypatch.setattr(S5BrandVlogPipeline, "run_step", _fake_run_step, raising=True)

    out = await runner._execute_step(state, "seedance_clips", force=False)
    assert out["pipeline_degraded"] is True
    assert out["degraded_reason"] == "all_seedance_clips_are_stubs"
    assert any("stub clips" in e for e in out["errors"])
    assert out["steps"]["seedance_clips"]["status"] == "done"


@pytest.mark.asyncio
async def test_step_runner_does_not_flag_degraded_for_real_clips(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)

    state = {
        "label": "test_d10_real",
        "scenario": "s5",
        "trace_id": "trace-d10-r",
        "errors": [],
        "steps": {
            "seedance_clips": {"status": "pending"},
            "assemble_final": {"status": "pending"},
        },
        "current_step": "seedance_clips",
        "config": {},
        "mode": "auto",
    }

    monkeypatch.setattr(step_runner, "_get_scenario_config", lambda scenario: {
        "step_order": ["seedance_clips", "assemble_final"],
        "pipeline_class": "src.pipeline.s5_brand_vlog_pipeline.S5BrandVlogPipeline",
    })

    async def _fake_run_step(self, step_name: str, st: dict[str, Any]) -> Any:
        return {
            "clip_paths": ["/tmp/real_a.mp4", "/tmp/real_b.mp4"],
            "clip_details": [{"is_stub": False}, {"is_stub": False}],
            "_all_stubs": False,
        }

    monkeypatch.setattr(S5BrandVlogPipeline, "run_step", _fake_run_step, raising=True)

    out = await runner._execute_step(state, "seedance_clips", force=False)
    assert out.get("pipeline_degraded") is not True
    assert out.get("degraded_reason") != "all_seedance_clips_are_stubs"
    assert out["steps"]["seedance_clips"]["status"] == "done"
