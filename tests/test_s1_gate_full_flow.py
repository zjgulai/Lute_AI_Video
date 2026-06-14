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
    def test_step_order_has_13_steps(self):
        # 与 step_runner.py 必须保持同步
        assert len(STEP_ORDER) == 13

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
        ("storyboards", "continuity_storyboard_grid"),
        ("continuity_storyboard_grid", "keyframe_images"),
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

class TestGetGateStateErrors:
    @pytest.mark.asyncio
    async def test_unknown_gate_id_returns_error(self, isolated_state_dir):
        # 先创建有效 state,再用无效 gate_id 测试 "Unknown gate" 路径
        sm = PipelineStateManager()
        await sm.save("valid-label", {"label": "valid-label", "steps": {}})
        result = await get_gate_state("valid-label", "gate_99_unknown")
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
            "steps": {
                "audit": {
                    "output": {
                        "continuity_score": 0.8,
                        "asset_ready_audit": {
                            "status": "PASS",
                            "checks": {"director_intent_metadata": True},
                        },
                        "continuity_direction_summary": {
                            "clip_directions": [
                                {
                                    "scene_beat": "context_setup",
                                    "beat_summary": "context_setup -> product_intro",
                                    "transition_intent": "bridge setup into product interaction",
                                }
                            ],
                            "scene_beats": ["context_setup"],
                            "transition_intents": ["bridge setup into product interaction"],
                        },
                    }
                }
            },
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
        assert result["continuity_diagnostics"]["director_intent_metadata"] is True
        assert result["continuity_diagnostics"]["clip_directions"][0]["scene_beat"] == "context_setup"


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
        assert reloaded is not None
        assert "gate_4_final" in reloaded["gates"]
        gate_state = reloaded["gates"]["gate_4_final"]
        assert gate_state["status"] == "awaiting_approval"
        assert len(gate_state["candidates"]) == 1


# ── approve_gate / regenerate_candidate 错误路径 ──

class TestApproveGateErrors:
    @pytest.mark.asyncio
    async def test_unknown_gate_id_returns_error(self, isolated_state_dir):
        # 先创建有效 state,再用无效 gate_id 测试 "Unknown gate" 路径
        sm = PipelineStateManager()
        await sm.save("valid-label-2", {"label": "valid-label-2", "steps": {}})
        result = await approve_gate("valid-label-2", "gate_99_unknown", ["c1"])
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


# ── approve_gate 成功路径 ──

class TestApproveGateSuccess:
    """approve_gate 成功路径：选 candidate → 写入 edited_output → 推进 current_step。"""

    @pytest.mark.asyncio
    async def test_approve_selects_candidate_and_advances(self, isolated_state_dir):
        sm = PipelineStateManager()
        state = {
            "label": "approve-test-1",
            "scenario": "s1",
            "config": {
                "product_catalog": {"product_name": "Test Product", "usps": ["usp1"]},
                "brand_guidelines": {},
            },
            "steps": {
                "strategy": {
                    "output": {
                        "briefs": [{"topic": "test", "usp_priority": ["usp1"]}]
                    },
                    "status": "done",
                },
                "scripts": {
                    "output": [{"text": "original script"}],
                    "status": "done",
                },
            },
            "current_step": "scripts",
            "gates": {
                "gate_1_script": {
                    "status": "awaiting_approval",
                    "candidates": [
                        {
                            "id": "gate_1_c0",
                            "variant": "standard",
                            "data": {"scripts": [{"text": "standard script"}]},
                            "score": {"overall": 0.8},
                        },
                        {
                            "id": "gate_1_c1",
                            "variant": "creative",
                            "data": {"scripts": [{"text": "creative script"}]},
                            "score": {"overall": 0.9},
                        },
                        {
                            "id": "gate_1_c2",
                            "variant": "conservative",
                            "data": {"scripts": [{"text": "conservative script"}]},
                            "score": {"overall": 0.7},
                        },
                    ],
                    "selected_ids": [],
                    "approved": False,
                }
            },
        }
        await sm.save("approve-test-1", state)

        result = await approve_gate("approve-test-1", "gate_1_script", ["gate_1_c1"])

        assert "error" not in result, f"unexpected error: {result.get('error')}"
        assert result["approved"] is True
        assert result["selected_ids"] == ["gate_1_c1"]
        assert result["selected_variants"] == ["creative"]
        # scripts 的 next step 是 compliance
        assert result["next_step"] == "compliance"

        # Reload 验证 state 持久化更新
        reloaded = await sm.load("approve-test-1")
        assert reloaded is not None
        gate_state = reloaded["gates"]["gate_1_script"]
        assert gate_state["approved"] is True
        assert gate_state["status"] == "approved"
        assert gate_state["selected_ids"] == ["gate_1_c1"]
        assert "approved_at" in gate_state

        # 验证 edited_output 被写入 scripts step
        scripts_step = reloaded["steps"]["scripts"]
        assert scripts_step["edited"] is True
        assert scripts_step["gate_selected"] is True
        assert scripts_step["selected_variants"] == ["creative"]
        # edited_output 是 candidate.data.scripts 列表
        assert scripts_step["edited_output"] == [{"text": "creative script"}]

        # 验证 current_step 推进
        assert reloaded["current_step"] == "compliance"

    @pytest.mark.asyncio
    async def test_approve_multi_selection_within_limit(self, isolated_state_dir):
        """gate_1_script 允许 max_selections=2,选 2 个应成功。"""
        sm = PipelineStateManager()
        state = {
            "label": "approve-test-2",
            "scenario": "s1",
            "config": {"product_catalog": {"product_name": "Test"}, "brand_guidelines": {}},
            "steps": {"strategy": {"output": {}, "status": "done"}, "scripts": {"output": [], "status": "done"}},
            "current_step": "scripts",
            "gates": {
                "gate_1_script": {
                    "status": "awaiting_approval",
                    "candidates": [
                        {"id": "c0", "variant": "standard", "data": {"scripts": [{"text": "s"}]}, "score": {"overall": 0.8}},
                        {"id": "c1", "variant": "creative", "data": {"scripts": [{"text": "c"}]}, "score": {"overall": 0.9}},
                    ],
                    "selected_ids": [],
                    "approved": False,
                }
            },
        }
        await sm.save("approve-test-2", state)

        result = await approve_gate("approve-test-2", "gate_1_script", ["c0", "c1"])
        assert "error" not in result
        assert result["approved"] is True
        assert result["selected_ids"] == ["c0", "c1"]
        assert result["selected_variants"] == ["standard", "creative"]

    @pytest.mark.asyncio
    async def test_approve_exceeds_max_selections_returns_error(self, isolated_state_dir):
        """gate_1 max_selections=2,选 3 个应返回错误。"""
        sm = PipelineStateManager()
        state = {
            "label": "approve-test-3",
            "scenario": "s1",
            "config": {"product_catalog": {"product_name": "Test"}, "brand_guidelines": {}},
            "steps": {"strategy": {"output": {}, "status": "done"}, "scripts": {"output": [], "status": "done"}},
            "current_step": "scripts",
            "gates": {
                "gate_1_script": {
                    "status": "awaiting_approval",
                    "candidates": [
                        {"id": "c0", "variant": "standard", "data": {}, "score": {"overall": 0.8}},
                        {"id": "c1", "variant": "creative", "data": {}, "score": {"overall": 0.9}},
                        {"id": "c2", "variant": "conservative", "data": {}, "score": {"overall": 0.7}},
                    ],
                    "selected_ids": [],
                    "approved": False,
                }
            },
        }
        await sm.save("approve-test-3", state)

        result = await approve_gate("approve-test-3", "gate_1_script", ["c0", "c1", "c2"])
        assert "error" in result
        assert "Maximum 2" in result["error"]

    @pytest.mark.asyncio
    async def test_approve_gate_already_approved_same_selection_is_idempotent(self, isolated_state_dir):
        """重复 approve 相同选择应幂等成功。"""
        sm = PipelineStateManager()
        state = {
            "label": "approve-test-4",
            "scenario": "s1",
            "config": {"product_catalog": {"product_name": "Test"}, "brand_guidelines": {}},
            "current_step": "compliance",
            "steps": {},
            "gates": {
                "gate_1_script": {
                    "status": "approved",
                    "candidates": [
                        {"id": "c0", "variant": "standard", "data": {}, "score": {"overall": 0.8}},
                    ],
                    "selected_ids": ["c0"],
                    "approved": True,
                }
            },
        }
        await sm.save("approve-test-4", state)

        result = await approve_gate("approve-test-4", "gate_1_script", ["c0"])
        assert "error" not in result
        assert result["approved"] is True
        assert result["idempotent"] is True
        assert result["selected_ids"] == ["c0"]
        assert result["selected_variants"] == ["standard"]
        assert result["next_step"] == "compliance"

    @pytest.mark.asyncio
    async def test_approve_gate_already_approved_different_selection_returns_error(self, isolated_state_dir):
        """已 approved 的 gate 不允许用不同 candidate 重写选择。"""
        sm = PipelineStateManager()
        state = {
            "label": "approve-test-5",
            "scenario": "s1",
            "config": {"product_catalog": {"product_name": "Test"}, "brand_guidelines": {}},
            "current_step": "compliance",
            "steps": {},
            "gates": {
                "gate_1_script": {
                    "status": "approved",
                    "candidates": [
                        {"id": "c0", "variant": "standard", "data": {}, "score": {"overall": 0.8}},
                        {"id": "c1", "variant": "creative", "data": {}, "score": {"overall": 0.9}},
                    ],
                    "selected_ids": ["c0"],
                    "approved": True,
                }
            },
        }
        await sm.save("approve-test-5", state)

        result = await approve_gate("approve-test-5", "gate_1_script", ["c1"])
        assert "error" in result
        assert "already approved with different selected_ids" in result["error"]


# ── step_runner gate 暂停/恢复 ──

class TestStepRunnerGatePause:
    """StepRunner 在 step_by_step 模式下遇到 gate after_step 时正确暂停。"""

    @pytest.mark.asyncio
    async def test_step_by_step_pauses_at_gate_after_scripts(self, isolated_state_dir):
        """mode=step_by_step 时,scripts step 完成后应触发 gate_1 暂停。"""
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        config = {
            "product_catalog": {"product_name": "Test Product", "usps": ["usp1"]},
            "target_platforms": ["tiktok"],
        }
        step_runner = StepRunner(sm)
        label = await step_runner.init_state(config=config, mode="step_by_step", scenario="s1")

        # Mock pipeline.run_step 让它返回模拟结果(不触发真实 LLM)
        mock_result = {
            "scripts": [
                {"text": "Mock hook", "segment_type": "hook"},
                {"text": "Mock CTA", "segment_type": "cta"},
            ],
            "count": 2,
        }

        with patch("src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            state = await step_runner.run_step(label, "scripts")

        # 验证 step output 被记录
        assert state["steps"]["scripts"]["status"] == "done"
        assert state["steps"]["scripts"]["output"] == mock_result

        # 验证 gate 被触发
        assert "gates" in state
        assert "gate_1_script" in state["gates"]
        gate = state["gates"]["gate_1_script"]
        assert gate["status"] == "awaiting_approval"
        assert gate["candidates"] == []
        assert gate["selections"] == []

        # 验证 current_step 停在 scripts(不推进到下一个)
        assert state["current_step"] == "scripts"
        assert state.get("gate_status") == "awaiting_approval"

    @pytest.mark.asyncio
    async def test_auto_mode_skips_gate_pause(self, isolated_state_dir):
        """mode=auto 时,scripts step 完成后不应触发 gate 暂停。"""
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        config = {
            "product_catalog": {"product_name": "Test Product", "usps": ["usp1"]},
            "target_platforms": ["tiktok"],
        }
        step_runner = StepRunner(sm)
        label = await step_runner.init_state(config=config, mode="auto", scenario="s1")

        mock_result = {"scripts": [{"text": "auto mode script"}]}

        with patch("src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = mock_result
            state = await step_runner.run_step(label, "scripts")

        # auto 模式不触发 gate
        assert "gates" not in state or "gate_1_script" not in state.get("gates", {})
        # current_step 推进到 compliance
        assert state["current_step"] == "compliance"

    @pytest.mark.asyncio
    async def test_resume_pauses_at_pre_step_gate(self, isolated_state_dir):
        """resume 遇到 awaiting_approval 的 gate 时在 pre-step 检查点暂停。"""
        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        step_runner = StepRunner(sm)

        # 构造一个 state:storyboards 已完成,gate_2_keyframe 处于 awaiting_approval
        # current_step = keyframe_images,resume 应该检测到 gate_2 暂停
        state = {
            "label": "resume-gate-test",
            "scenario": "s1",
            "config": {
                "product_catalog": {"product_name": "Test"},
                "target_platforms": ["tiktok"],
                "brand_mode": True,
            },
            "steps": {
                "strategy": {"status": "done", "output": {}},
                "scripts": {"status": "done", "output": {}},
                "compliance": {"status": "done", "output": {}},
                "storyboards": {"status": "done", "output": {}},
            },
            "current_step": "keyframe_images",
            "trace_id": "test-trace",
            "gates": {
                "gate_2_keyframe": {
                    "status": "awaiting_approval",
                    "candidates": [
                        {"id": "c0", "variant": "standard", "data": {}, "score": {"overall": 0.8}},
                    ],
                    "selected_ids": [],
                    "approved": False,
                }
            },
        }
        await sm.save("resume-gate-test", state)

        # resume 应该检测到 gate_2 是 awaiting_approval,在 pre-step 暂停
        # 不需要 mock pipeline.run_step(因为不会执行到)
        final_state = await step_runner.resume("resume-gate-test")

        # 验证 resume 在 keyframe_images 处暂停(没有执行 pipeline.run_step)
        assert final_state["current_step"] == "keyframe_images"
        # gate 状态保持 awaiting_approval
        assert final_state["gates"]["gate_2_keyframe"]["status"] == "awaiting_approval"

    @pytest.mark.asyncio
    async def test_resume_pauses_at_post_step_gate(self, isolated_state_dir):
        """resume 执行完 step 后,如果 step 触发了 gate,在 post-step 检查点暂停。"""
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        step_runner = StepRunner(sm)

        # 用 init_state 创建完整 state(包含所有 steps),再修改需要覆盖的部分
        config = {
            "product_catalog": {"product_name": "Test"},
            "target_platforms": ["tiktok"],
            "brand_mode": True,
        }
        label = await step_runner.init_state(config=config, mode="step_by_step", scenario="s1")

        # 修改 state:strategy/scripts/compliance 已完成,gate_1 已 approved
        state = await sm.load(label)
        state["steps"]["strategy"]["status"] = "done"
        state["steps"]["strategy"]["output"] = {}
        state["steps"]["scripts"]["status"] = "done"
        state["steps"]["scripts"]["output"] = {}
        state["steps"]["scripts"]["edited"] = True
        state["steps"]["scripts"]["edited_output"] = []
        state["steps"]["compliance"]["status"] = "done"
        state["steps"]["compliance"]["output"] = {}
        state["current_step"] = "storyboards"
        state["gates"] = {
            "gate_1_script": {
                "status": "approved",
                "candidates": [],
                "selected_ids": ["c0"],
                "approved": True,
            }
        }
        await sm.save(label, state)

        # 用 step_by_step 模式 resume(从 storyboards 开始)
        # storyboards → continuity_storyboard_grid → keyframe_images(gate_2) → 暂停
        with patch("src.pipeline.s1_product_pipeline.S1ProductDirectPipeline.run_step", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {"storyboards": "mock"}
            final_state = await step_runner.resume(label)

        # 验证 storyboards / continuity_storyboard_grid / keyframe_images 都被执行了
        assert mock_run.call_count == 3
        assert mock_run.call_args_list[0][0][0] == "storyboards"
        assert mock_run.call_args_list[1][0][0] == "continuity_storyboard_grid"
        assert mock_run.call_args_list[2][0][0] == "keyframe_images"

        # 验证在 keyframe_images 处暂停(gate_2 触发)
        assert final_state["current_step"] == "keyframe_images"
        assert "gate_2_keyframe" in final_state.get("gates", {})
        assert final_state["gates"]["gate_2_keyframe"]["status"] == "awaiting_approval"
