from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.pipeline import step_runner
from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
from src.skills.base import SkillResult


def test_validate_footage_assets_returns_two_lists():
    valid, invalid = S4LiveShootPipeline._validate_footage_assets([])
    assert valid == []
    assert invalid == []


def test_validate_footage_assets_keeps_filename():
    valid, invalid = S4LiveShootPipeline._validate_footage_assets([
        {"filename": "kitchen.mp4", "file_size": 1024},
    ])
    assert len(valid) == 1
    assert len(invalid) == 0
    assert valid[0]["filename"] == "kitchen.mp4"


def test_validate_footage_assets_keeps_url_or_path_or_asset_id():
    valid, _ = S4LiveShootPipeline._validate_footage_assets([
        {"path": "/tmp/a.mp4", "file_size": 100},
        {"url": "https://x/b.mp4", "file_size": 200},
        {"asset_id": "asset-c", "file_size": 300},
    ])
    assert len(valid) == 3


def test_validate_footage_assets_drops_corrupted():
    valid, invalid = S4LiveShootPipeline._validate_footage_assets([
        {"filename": "good.mp4"},
        {"filename": "bad.mp4", "is_corrupted": True},
    ])
    assert len(valid) == 1
    assert len(invalid) == 1
    assert invalid[0]["reason"] == "is_corrupted"


def test_validate_footage_assets_drops_zero_size():
    valid, invalid = S4LiveShootPipeline._validate_footage_assets([
        {"filename": "zero.mp4", "file_size": 0},
    ])
    assert len(valid) == 0
    assert invalid[0]["reason"] == "zero_size"


def test_validate_footage_assets_drops_no_reference():
    valid, invalid = S4LiveShootPipeline._validate_footage_assets([
        {"file_size": 100},
        {"description": "no path or filename"},
    ])
    assert len(valid) == 0
    assert all(i["reason"] == "no_reference" for i in invalid)


def test_validate_footage_assets_drops_non_dict():
    valid, invalid = S4LiveShootPipeline._validate_footage_assets([
        "not_a_dict",  # type: ignore[list-item]
        42,  # type: ignore[list-item]
    ])
    assert valid == []
    assert len(invalid) == 2
    assert all(i["reason"] == "not_a_dict" for i in invalid)


def test_extract_stock_footage_urls_default_empty():
    assert S4LiveShootPipeline._extract_stock_footage_urls({}) == []
    assert S4LiveShootPipeline._extract_stock_footage_urls({"other_key": []}) == []


def test_extract_stock_footage_urls_returns_strings():
    out = S4LiveShootPipeline._extract_stock_footage_urls({
        "stock_footage_urls": ["https://stock/a.mp4", "https://stock/b.mp4"],
    })
    assert out == ["https://stock/a.mp4", "https://stock/b.mp4"]


def test_extract_stock_footage_urls_filters_non_strings():
    out = S4LiveShootPipeline._extract_stock_footage_urls({
        "stock_footage_urls": ["https://stock/a.mp4", "", None, 42, "https://stock/b.mp4"],
    })
    assert out == ["https://stock/a.mp4", "https://stock/b.mp4"]


def test_extract_stock_footage_urls_handles_non_dict():
    assert S4LiveShootPipeline._extract_stock_footage_urls(None) == []  # type: ignore[arg-type]
    assert S4LiveShootPipeline._extract_stock_footage_urls("string") == []  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_s4_scripts_uses_stock_fallback_when_all_footage_invalid():
    pipeline = S4LiveShootPipeline()
    reg = AsyncMock()
    reg.execute = AsyncMock(return_value=SkillResult(
        success=True,
        data={"scripts": [{"id": "SCR-1", "segments": [{"visual_description": "x"}]}]},
    ))

    config = {
        "footage_assets": [
            {"filename": "bad1.mp4", "is_corrupted": True},
            {"filename": "bad2.mp4", "file_size": 0},
        ],
        "product_info": {"name": "Pump"},
        "brand_guidelines": {"stock_footage_urls": ["https://stock/kitchen.mp4"]},
        "target_platforms": ["tiktok"],
    }

    out = await pipeline._step_scripts(reg, config, {}, [])

    assert isinstance(out, list)
    assert out[0].get("_soft_degraded") is True
    assert out[0]["_degraded_reason"] == "footage_invalid_using_stock_fallback"
    assert "stock asset" in out[0]["_degraded_detail"]
    assert config["footage_assets"][0]["is_stock"] is True
    assert config["footage_assets"][0]["url"] == "https://stock/kitchen.mp4"


@pytest.mark.asyncio
async def test_s4_scripts_emits_no_stock_fallback_sentinel_when_no_stock():
    pipeline = S4LiveShootPipeline()
    reg = AsyncMock()
    reg.execute = AsyncMock(return_value=SkillResult(
        success=True,
        data={"scripts": [{"id": "SCR-1", "segments": []}]},
    ))

    config = {
        "footage_assets": [{"filename": "bad.mp4", "is_corrupted": True}],
        "product_info": {"name": "Pump"},
        "brand_guidelines": {},
        "target_platforms": ["tiktok"],
    }

    out = await pipeline._step_scripts(reg, config, {}, [])

    assert out[0].get("_soft_degraded") is True
    assert out[0]["_degraded_reason"] == "footage_invalid_no_stock_fallback"
    assert config["footage_assets"] == []


@pytest.mark.asyncio
async def test_s4_scripts_filters_invalid_keeps_valid_no_sentinel():
    pipeline = S4LiveShootPipeline()
    reg = AsyncMock()
    reg.execute = AsyncMock(return_value=SkillResult(
        success=True,
        data={"scripts": [{"id": "SCR-1", "segments": []}]},
    ))

    config = {
        "footage_assets": [
            {"filename": "good.mp4", "file_size": 100},
            {"filename": "bad.mp4", "is_corrupted": True},
        ],
        "product_info": {"name": "Pump"},
        "brand_guidelines": {},
        "target_platforms": ["tiktok"],
    }

    out = await pipeline._step_scripts(reg, config, {}, [])

    assert out[0].get("_soft_degraded") is None or "_soft_degraded" not in out[0]
    assert len(config["footage_assets"]) == 1
    assert config["footage_assets"][0]["filename"] == "good.mp4"


@pytest.mark.asyncio
async def test_s4_scripts_no_filtering_when_all_valid():
    pipeline = S4LiveShootPipeline()
    reg = AsyncMock()
    reg.execute = AsyncMock(return_value=SkillResult(
        success=True,
        data={"scripts": [{"id": "SCR-1", "segments": []}]},
    ))

    raw = [
        {"filename": "a.mp4", "file_size": 100},
        {"filename": "b.mp4", "file_size": 200},
    ]
    config = {
        "footage_assets": raw,
        "product_info": {"name": "Pump"},
        "brand_guidelines": {},
        "target_platforms": ["tiktok"],
    }

    out = await pipeline._step_scripts(reg, config, {}, [])

    assert out[0].get("_soft_degraded") is None or "_soft_degraded" not in out[0]
    assert config["footage_assets"] == raw


@pytest.mark.asyncio
async def test_s4_scripts_empty_footage_no_sentinel():
    pipeline = S4LiveShootPipeline()
    reg = AsyncMock()
    reg.execute = AsyncMock(return_value=SkillResult(
        success=True,
        data={"scripts": [{"id": "SCR-1"}]},
    ))

    config = {
        "footage_assets": [],
        "product_info": {"name": "Pump"},
        "brand_guidelines": {},
        "target_platforms": ["tiktok"],
    }

    out = await pipeline._step_scripts(reg, config, {}, [])
    assert "_soft_degraded" not in out[0]


def test_step_runner_detect_signal_first_in_list_with_soft_degraded():
    sentinel = {
        "_soft_degraded": True,
        "_degraded_reason": "footage_invalid_using_stock_fallback",
        "_degraded_detail": "all 3 invalid",
    }
    detected = step_runner._result_indicates_soft_degraded([sentinel, {"id": "SCR-2"}])
    assert detected is not None
    assert detected["reason"] == "footage_invalid_using_stock_fallback"


def test_step_runner_detect_signal_returns_none_for_normal_list():
    detected = step_runner._result_indicates_soft_degraded([{"id": "SCR-1"}])
    assert detected is None


@pytest.mark.asyncio
async def test_step_runner_appends_soft_degraded_for_s4_list_sentinel(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_FILE_DIR", str(tmp_path))

    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_mgr = PipelineStateManager()

    async def _save_noop(label: str, st: dict[str, Any]) -> None:
        pass

    monkeypatch.setattr(state_mgr, "save", _save_noop, raising=True)
    runner = StepRunner(state_mgr)

    state: dict[str, Any] = {
        "label": "test_s4_d10pr3",
        "scenario": "s4",
        "trace_id": "trace-d10pr3",
        "errors": [],
        "steps": {
            "scripts": {"status": "pending"},
            "video_prompts": {"status": "pending"},
        },
        "current_step": "scripts",
        "config": {},
        "mode": "auto",
    }

    monkeypatch.setattr(step_runner, "_get_scenario_config", lambda scenario: {
        "step_order": ["scripts", "video_prompts"],
        "pipeline_class": "src.pipeline.s4_live_shoot_pipeline.S4LiveShootPipeline",
    })

    async def _fake_run_step(self, step_name: str, st: dict[str, Any]) -> Any:
        return [
            {
                "_soft_degraded": True,
                "_degraded_reason": "footage_invalid_using_stock_fallback",
                "_degraded_detail": "all 2 invalid; using 1 stock",
                "id": "SCR-1",
                "segments": [],
            },
            {"id": "SCR-2", "segments": []},
        ]

    monkeypatch.setattr(S4LiveShootPipeline, "run_step", _fake_run_step, raising=True)

    out = await runner._execute_step(state, "scripts", force=False)

    assert "soft_degraded_reasons" in out
    assert len(out["soft_degraded_reasons"]) == 1
    entry = out["soft_degraded_reasons"][0]
    assert entry["step"] == "scripts"
    assert entry["reason"] == "footage_invalid_using_stock_fallback"
    assert "stock" in entry["detail"]
    assert out.get("pipeline_degraded") is not True
