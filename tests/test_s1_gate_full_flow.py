"""Test-AB(B): S1 step-by-step + Gate 候选生成全链路回归测试。

覆盖内容(对应 CLAUDE.md B 任务):
- GATE_DEFINITIONS 4 个 gate 配置完整性
- _get_next_step / STEP_ORDER 不变量
- get_gate_state 错误路径(unknown gate_id / 不存在 label)
- gate_4_final 候选组装(不依赖外部 LLM/POYO,纯 state 拼装)
- approve_gate / regenerate_candidate 错误路径

不在本测试范围:
- gate_1_script / gate_2_keyframe / gate_3_clips 候选生成依赖真实 LLM/POYO
  端到端跑通,需要真实 API key + 长时执行,放到 integration suite。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.gate_manager import (
    GATE_DEFINITIONS,
    STEP_ORDER,
    STEP_TO_SKILL_NAME,
    _get_next_step,
    approve_gate,
    generate_candidates,
    get_gate_state,
    regenerate_candidate,
)
from src.pipeline.state_manager import PipelineStateManager


# ── GATE_DEFINITIONS 静态契约 ──

class TestGateDefinitionsContract:
    """4 个 gate 必须有 after_step / label / max_selections / candidate_step 字段。"""

    def test_four_gates_defined(self):
        assert set(GATE_DEFINITIONS.keys()) == {
            "gate_1_script",
            "gate_2_keyframe",
            "gate_3_clips",
            "gate_4_final",
        }

    def test_each_gate_has_required_fields(self):
        for gate_id, definition in GATE_DEFINITIONS.items():
            assert "after_step" in definition, f"{gate_id} 缺 after_step"
            assert "label" in definition, f"{gate_id} 缺 label"
            assert "max_selections" in definition, f"{gate_id} 缺 max_selections"
            assert definition["max_selections"] >= 1
            # candidate_step 可以是 None(gate_4_final 这种)
            assert "candidate_step" in definition

    def test_after_step_in_step_order(self):
        for gate_id, definition in GATE_DEFINITIONS.items():
            assert definition["after_step"] in STEP_ORDER, (
                f"{gate_id}.after_step={definition['after_step']} 不在 STEP_ORDER 里"
            )

    def test_skill_mapping_complete(self):
        # 有 candidate_step 的 gate 必须在 STEP_TO_SKILL_NAME 里
        for gate_id, definition in GATE_DEFINITIONS.items():
            cs = definition["candidate_step"]
            if cs is not None:
                assert cs in STEP_TO_SKILL_NAME, f"{gate_id}.candidate_step={cs} 不在 STEP_TO_SKILL_NAME"


# ── STEP_ORDER 不变量 ──

class TestStepOrderInvariants:
    def test_step_order_has_12_steps(self):
        # 与 step_runner.py 必须保持同步
        assert len(STEP_ORDER) == 12

    def test_strategy_is_first(self):
        assert STEP_ORDER[0] == "strategy"

    def test_audit_is_last(self):
        assert STEP_ORDER[-1] == "audit"

    def test_no_duplicates(self):
        assert len(STEP_ORDER) == len(set(STEP_ORDER))

    @pytest.mark.parametrize("step,expected_next", [
        ("strategy", "scripts"),
        ("scripts", "compliance"),
        ("compliance", "storyboards"),
        ("storyboards", "keyframe_images"),
        ("keyframe_images", "video_prompts"),
        ("video_prompts", "thumbnail_prompts"),
        ("thumbnail_prompts", "seedance_clips"),
        ("seedance_clips", "tts_audio"),
        ("tts_audio", "thumbnail_images"),
        ("thumbnail_images", "assemble_final"),
        ("assemble_final", "audit"),
        ("audit", None),
        ("nonexistent", None),
    ])
    def test_get_next_step(self, step, expected_next):
        assert _get_next_step(step) == expected_next


# ── get_gate_state 错误路径 ──

@pytest.fixture
def isolated_state_dir(tmp_path, monkeypatch):
    """每个 test 给 PipelineStateManager 一个独立 tmp 目录,避免污染 output/。"""
    monkeypatch.setattr(PipelineStateManager, "OUTPUT_DIR", tmp_path)
    # 同时强制不走 PG(测试隔离)
    monkeypatch.setattr(PipelineStateManager, "__init__", lambda self, use_pg=False: None)
    monkeypatch.setattr(PipelineStateManager, "use_pg", False, raising=False)
    yield tmp_path


class TestGetGateStateErrors:
    @pytest.mark.asyncio
    async def test_unknown_gate_id_returns_error(self, isolated_state_dir):
        result = await get_gate_state("any-label", "gate_99_unknown")
        assert "error" in result
        assert "Unknown gate" in result["error"]
        assert result["gate_id"] == "gate_99_unknown"

    @pytest.mark.asyncio
    async def test_missing_label_returns_error(self, isolated_state_dir):
        # label 没对应 state 文件 → 返回 error 不抛异常
        result = await get_gate_state("nonexistent-label-xyz", "gate_1_script")
        assert "error" in result
        assert "State not found" in result["error"]


class TestGateStateLifecycle:
    """有 state 文件时的 gate state 生命周期。"""

    @pytest.mark.asyncio
    async def test_default_status_when_gate_not_yet_initialized(
        self, isolated_state_dir
    ):
        # 创建 state 文件,但里面没 gates 字段
        sm = PipelineStateManager()
        await sm.save("test-label-1", {"label": "test-label-1", "steps": {}})
        result = await get_gate_state("test-label-1", "gate_1_script")
        assert result["gate_id"] == "gate_1_script"
        assert result["status"] == "awaiting_candidates"
        assert result["candidates"] == []
        assert result["selected_ids"] == []
        assert result["approved"] is False

    @pytest.mark.asyncio
    async def test_returns_persisted_gate_state(self, isolated_state_dir):
        sm = PipelineStateManager()
        await sm.save("test-label-2", {
            "label": "test-label-2",
            "steps": {},
            "gates": {
                "gate_1_script": {
                    "status": "awaiting_approval",
                    "candidates": [{"id": "c1", "variant": "standard"}],
                    "selected_ids": ["c1"],
                    "approved": False,
                }
            },
        })
        result = await get_gate_state("test-label-2", "gate_1_script")
        assert result["status"] == "awaiting_approval"
        assert result["candidates"] == [{"id": "c1", "variant": "standard"}]
        assert result["selected_ids"] == ["c1"]


# ── gate_4_final 候选组装(不依赖 LLM,验证拼装逻辑) ──

class TestGate4FinalAssembly:
    """gate_4_final 不调 SkillRegistry,直接从 state.steps 里拼装 final candidate。
    这个 gate 的代码路径是端到端关键最后一步。"""

    @pytest.mark.asyncio
    async def test_assembles_from_steps_state(self, isolated_state_dir):
        sm = PipelineStateManager()
        # 模拟一个完整的 pipeline state,包含 assemble_final/audit/thumbnail/seedance
        # assemble_final.output 实际是 (video_path, metadata) tuple — 看 gate_manager.py:166
        state = {
            "label": "final-test-1",
            "steps": {
                "assemble_final": {"output": ["/tmp/test-video.mp4", {"meta": "info"}]},
                "audit": {"output": {"duration_seconds": 30, "score": 0.92}},
                "thumbnail_images": {"output": ["/tmp/thumb1.png", "/tmp/thumb2.png"]},
                "seedance_clips": {"output": {"total_duration": 30, "clips": []}},
            },
        }
        await sm.save("final-test-1", state)

        result = await generate_candidates("final-test-1", "gate_4_final")

        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert result["gate_id"] == "gate_4_final"
        assert len(result["candidates"]) == 1, "gate_4_final 应该只有 1 个候选"

        candidate = result["candidates"][0]
        assert candidate["id"] == "gate_4_final_c0"
        assert candidate["variant"] == "standard"
        assert candidate["recommended"] is True
        # data 字段填了 video / audit / thumbnail / duration
        data = candidate["data"]
        assert data["final_video_path"] == "/tmp/test-video.mp4"
        assert data["audit_report"]["score"] == 0.92
        assert data["thumbnail_image_paths"] == ["/tmp/thumb1.png", "/tmp/thumb2.png"]
        assert data["duration"] == 30

    @pytest.mark.asyncio
    async def test_assemble_handles_dict_video_path(self, isolated_state_dir):
        """assemble_final 可能返回 dict(video_path 字段)而不是直接的 str。"""
        sm = PipelineStateManager()
        state = {
            "label": "final-test-2",
            "steps": {
                "assemble_final": {"output": {"video_path": "/tmp/dict-video.mp4"}},
                "audit": {"output": {"duration_seconds": 45}},
                "thumbnail_images": {"output": []},
                "seedance_clips": {"output": {}},
            },
        }
        await sm.save("final-test-2", state)
        result = await generate_candidates("final-test-2", "gate_4_final")
        assert result["candidates"][0]["data"]["final_video_path"] == "/tmp/dict-video.mp4"

    @pytest.mark.asyncio
    async def test_persists_gate_state_after_assembly(self, isolated_state_dir):
        """gate_4_final 组装后必须把 candidate 写回 state.gates。"""
        sm = PipelineStateManager()
        state = {
            "label": "final-test-3",
            "steps": {
                "assemble_final": {"output": ["/tmp/v.mp4", {}]},
                "audit": {"output": {}},
                "thumbnail_images": {"output": []},
                "seedance_clips": {"output": {}},
            },
        }
        await sm.save("final-test-3", state)
        await generate_candidates("final-test-3", "gate_4_final")

        # Reload 看 gates 字段是否被写入
        reloaded = await sm.load("final-test-3")
        assert "gate_4_final" in reloaded["gates"]
        gate_state = reloaded["gates"]["gate_4_final"]
        assert gate_state["status"] == "awaiting_approval"
        assert len(gate_state["candidates"]) == 1


# ── approve_gate / regenerate_candidate 错误路径 ──

class TestApproveGateErrors:
    @pytest.mark.asyncio
    async def test_unknown_gate_id_returns_error(self, isolated_state_dir):
        result = await approve_gate("any-label", "gate_99_unknown", ["c1"])
        assert "error" in result
        assert "Unknown gate" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_label_returns_error(self, isolated_state_dir):
        result = await approve_gate("missing-label", "gate_1_script", ["c1"])
        assert "error" in result


class TestRegenerateCandidateErrors:
    @pytest.mark.asyncio
    async def test_unknown_gate_id_returns_error(self, isolated_state_dir):
        result = await regenerate_candidate("any-label", "gate_99_unknown", "c1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_label_returns_error(self, isolated_state_dir):
        result = await regenerate_candidate("missing-label", "gate_1_script", "c1")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_candidate_id_returns_error(self, isolated_state_dir):
        sm = PipelineStateManager()
        await sm.save("regen-test-1", {
            "label": "regen-test-1",
            "steps": {},
            "gates": {
                "gate_1_script": {
                    "status": "awaiting_approval",
                    "candidates": [{"id": "real-candidate", "variant": "standard"}],
                }
            },
        })
        result = await regenerate_candidate("regen-test-1", "gate_1_script", "fake-candidate-id")
        assert "error" in result
