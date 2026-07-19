"""S3/S4/S5 gate 配置端到端验证。

验证 gate_manager 的 per-scenario 配置和 step_runner 的 gate 触发
逻辑在非 S1 场景下正确工作。
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.pipeline.gate_manager import (
    SCENARIO_GATE_DEFINITIONS,
    SCENARIO_STEP_ORDERS,
    STEP_TO_SKILL_NAME,
    _build_skill_params,
    approve_gate,
    generate_candidates,
)
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import _get_gate_after_steps, _get_gate_id_for_step
from tests.generation_policy_test_utils import (
    attach_execution_policy,
    bound_generation_policy,
)

# ── 静态配置验证 ──


class TestScenarioGateDefinitions:
    """验证 SCENARIO_GATE_DEFINITIONS 各场景 gate 定义完整且一致。"""

    @pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
    def test_scenario_has_gate_definitions(self, scenario: str):
        assert scenario in SCENARIO_GATE_DEFINITIONS, f"{scenario} 不在 SCENARIO_GATE_DEFINITIONS 中"
        defs = SCENARIO_GATE_DEFINITIONS[scenario]
        assert len(defs) > 0, f"{scenario} 没有 gate 定义"

    @pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
    def test_each_gate_has_required_fields(self, scenario: str):
        defs = SCENARIO_GATE_DEFINITIONS[scenario]
        for gate_id, definition in defs.items():
            assert "after_step" in definition, f"{scenario}.{gate_id} 缺 after_step"
            assert "label" in definition, f"{scenario}.{gate_id} 缺 label"
            assert "max_selections" in definition, f"{scenario}.{gate_id} 缺 max_selections"
            assert definition["max_selections"] >= 1
            assert "candidate_step" in definition

    @pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
    def test_after_step_in_scenario_step_order(self, scenario: str):
        """每个 gate 的 after_step 必须在该场景的 step_order 中。"""
        defs = SCENARIO_GATE_DEFINITIONS[scenario]
        step_order = SCENARIO_STEP_ORDERS.get(scenario, [])
        for gate_id, definition in defs.items():
            after = definition["after_step"]
            assert after in step_order, f"{scenario}.{gate_id}.after_step={after} 不在 {scenario} 的 step_order 中"

    @pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
    def test_candidate_step_has_skill_mapping(self, scenario: str):
        """有 candidate_step 的 gate 必须有对应的 skill 映射(允许 None 表示非 skill 生成)。"""
        defs = SCENARIO_GATE_DEFINITIONS[scenario]
        for gate_id, definition in defs.items():
            cs = definition.get("candidate_step")
            if cs is not None:
                assert cs in STEP_TO_SKILL_NAME, f"{scenario}.{gate_id}.candidate_step={cs} 不在 STEP_TO_SKILL_NAME"
                # NOTE: video_prompts / thumbnails 映射为 None 是已知设计
                # (S4 gate_2_prompts / gate_3_thumbnails 从 state 组装而非 skill 生成)


class TestS3SpecificGates:
    """S3: Influencer Remix 的 gate 定义验证。"""

    def test_s3_has_three_gates(self):
        defs = SCENARIO_GATE_DEFINITIONS["s3"]
        assert set(defs.keys()) == {
            "gate_1_script",
            "gate_2_keyframe",
            "gate_3_clips",
            "gate_4_final",
        }

    def test_s3_gate_1_uses_remix_script(self):
        defs = SCENARIO_GATE_DEFINITIONS["s3"]
        assert defs["gate_1_script"]["candidate_step"] == "remix_script"
        assert defs["gate_1_script"]["after_step"] == "remix_script"

    def test_s3_step_order_matches(self):
        s3_order = SCENARIO_STEP_ORDERS["s3"]
        assert s3_order[0] == "video_analysis"
        assert "remix_script" in s3_order
        assert "character_identity" in s3_order


class TestS4SpecificGates:
    """S4: Live Shoot 的 gate 定义验证。"""

    def test_s4_has_three_gates(self):
        defs = SCENARIO_GATE_DEFINITIONS["s4"]
        assert set(defs.keys()) == {
            "gate_1_script",
            "gate_2_prompts",
            "gate_3_thumbnails",
        }

    def test_s4_gate_1_after_scripts(self):
        defs = SCENARIO_GATE_DEFINITIONS["s4"]
        assert defs["gate_1_script"]["after_step"] == "scripts"
        assert defs["gate_1_script"]["candidate_step"] == "scripts"

    def test_s4_gate_2_after_video_prompts(self):
        defs = SCENARIO_GATE_DEFINITIONS["s4"]
        assert defs["gate_2_prompts"]["after_step"] == "video_prompts"
        assert defs["gate_2_prompts"]["candidate_step"] == "video_prompts"

    def test_s4_gate_3_no_candidate_step(self):
        defs = SCENARIO_GATE_DEFINITIONS["s4"]
        assert defs["gate_3_thumbnails"]["candidate_step"] is None
        assert defs["gate_3_thumbnails"]["after_step"] == "thumbnails"

    def test_s4_step_order_matches(self):
        s4_order = SCENARIO_STEP_ORDERS["s4"]
        assert s4_order == [
            "scripts",
            "continuity_storyboard_grid",
            "video_prompts",
            "thumbnails",
            "seedance_clips",
            "tts_audio",
            "assemble_final",
            "audit",
        ]


class TestS5SpecificGates:
    """S5: Brand VLOG 的 gate 定义验证。"""

    def test_s5_has_three_gates(self):
        defs = SCENARIO_GATE_DEFINITIONS["s5"]
        assert set(defs.keys()) == {
            "gate_1_strategy",
            "gate_2_clips",
            "gate_3_final",
        }

    def test_s5_gate_1_uses_vlog_strategy(self):
        defs = SCENARIO_GATE_DEFINITIONS["s5"]
        assert defs["gate_1_strategy"]["candidate_step"] == "vlog_strategy"
        assert defs["gate_1_strategy"]["after_step"] == "vlog_strategy"

    def test_s5_gate_2_after_seedance_clips(self):
        defs = SCENARIO_GATE_DEFINITIONS["s5"]
        assert defs["gate_2_clips"]["after_step"] == "seedance_clips"
        assert defs["gate_2_clips"]["candidate_step"] == "seedance_clips"

    def test_s5_step_order_matches(self):
        s5_order = SCENARIO_STEP_ORDERS["s5"]
        assert s5_order[0] == "vlog_strategy"
        assert "continuity_storyboard_grid" in s5_order
        assert "seedance_clips" in s5_order
        assert "assemble_final" in s5_order


# ── 动态查询函数验证 ──


class TestGetGateAfterSteps:
    """验证 _get_gate_after_steps 返回正确的 after_step 集合。"""

    def test_s1_returns_scripts_keyframe_seedance_assemble(self):
        after_steps = _get_gate_after_steps("s1")
        assert after_steps == {"scripts", "keyframe_images", "seedance_clips", "assemble_final"}

    def test_s3_returns_remix_keyframe_seedance_assemble(self):
        after_steps = _get_gate_after_steps("s3")
        assert after_steps == {"remix_script", "keyframe_images", "seedance_clips", "assemble_final"}

    def test_s4_returns_scripts_prompts_thumbnails(self):
        after_steps = _get_gate_after_steps("s4")
        assert after_steps == {"scripts", "video_prompts", "thumbnails"}

    def test_s5_returns_strategy_seedance_assemble(self):
        after_steps = _get_gate_after_steps("s5")
        assert after_steps == {"vlog_strategy", "seedance_clips", "assemble_final"}

    def test_unknown_scenario_falls_back_to_s1(self):
        after_steps = _get_gate_after_steps("s99_unknown")
        assert after_steps == _get_gate_after_steps("s1")


class TestGetGateIdForStep:
    """验证 _get_gate_id_for_step 正确映射 step → gate_id。"""

    def test_s1_scripts_maps_to_gate_1(self):
        assert _get_gate_id_for_step("scripts", "s1") == "gate_1_script"

    def test_s1_keyframe_maps_to_gate_2(self):
        assert _get_gate_id_for_step("keyframe_images", "s1") == "gate_2_keyframe"

    def test_s3_remix_script_maps_to_gate_1(self):
        assert _get_gate_id_for_step("remix_script", "s3") == "gate_1_script"

    def test_s4_video_prompts_maps_to_gate_2(self):
        assert _get_gate_id_for_step("video_prompts", "s4") == "gate_2_prompts"

    def test_s5_vlog_strategy_maps_to_gate_1(self):
        assert _get_gate_id_for_step("vlog_strategy", "s5") == "gate_1_strategy"

    def test_non_gate_step_returns_empty(self):
        assert _get_gate_id_for_step("strategy", "s1") == ""
        assert _get_gate_id_for_step("compliance", "s1") == ""


class TestScenarioGateLifecycle:
    @pytest.mark.asyncio
    async def test_s4_gate_1_approval_advances_to_continuity_step(self, isolated_state_dir):
        state = {
            "label": "s4-gate-advance",
            "scenario": "s4",
            "current_step": "scripts",
            "config": {"product_catalog": {"name": "X1"}},
            "steps": {
                "scripts": {"output": [], "edited": False},
            },
            "gates": {
                "gate_1_script": {
                    "status": "awaiting_approval",
                    "approved": False,
                    "selected_ids": [],
                    "candidates": [
                        {"id": "s4_c0", "variant": "standard", "data": {"scripts": []}, "score": {"overall": 0.9}},
                    ],
                },
            },
        }
        attach_execution_policy(state, scenario="s4", media=False)
        await PipelineStateManager().save("s4-gate-advance", state)

        result = await approve_gate("s4-gate-advance", "gate_1_script", ["s4_c0"])
        assert result["next_step"] == "continuity_storyboard_grid"

    @pytest.mark.asyncio
    async def test_s5_gate_1_approval_advances_to_continuity_step(self, isolated_state_dir):
        state = {
            "label": "s5-gate-advance",
            "scenario": "s5",
            "current_step": "vlog_strategy",
            "config": {"product_sku": {"name": "X1"}},
            "steps": {
                "vlog_strategy": {"output": {"shots": [], "scripts": []}, "edited": False},
            },
            "gates": {
                "gate_1_strategy": {
                    "status": "awaiting_approval",
                    "approved": False,
                    "selected_ids": [],
                    "candidates": [
                        {
                            "id": "s5_c0",
                            "variant": "standard",
                            "data": {"product_catalog": {"name": "X1"}},
                            "score": {"overall": 0.9},
                        },
                    ],
                },
            },
        }
        attach_execution_policy(state, scenario="s5", media=False)
        await PipelineStateManager().save("s5-gate-advance", state)

        result = await approve_gate("s5-gate-advance", "gate_1_strategy", ["s5_c0"])
        assert result["next_step"] == "continuity_storyboard_grid"

    @pytest.mark.asyncio
    async def test_s4_thumbnail_gate_is_blocked_outside_exact_profile(self, isolated_state_dir):
        state = {
            "label": "s4-final-gate",
            "scenario": "s4",
            "config": {},
            "steps": {
                "thumbnails": {"output": [{"script_id": "s1", "variants": [{"prompt": "thumb"}]}]},
                "scripts": {"output": [{"id": "s1"}]},
            },
        }
        attach_execution_policy(state, scenario="s4", media=True)
        await PipelineStateManager().save("s4-final-gate", state)

        with pytest.raises(HTTPException) as exc:
            await generate_candidates("s4-final-gate", "gate_3_thumbnails")
        assert exc.value.status_code == 422
        assert "outside execution profile" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_s5_final_gate_is_blocked_outside_exact_profile(self, isolated_state_dir):
        state = {
            "label": "s5-final-gate",
            "scenario": "s5",
            "config": {},
            "steps": {
                "assemble_final": {"output": ["/tmp/final.mp4", "/tmp/render.json"]},
                "audit": {"output": {"duration_seconds": 15}},
                "seedance_clips": {"output": {"total_duration": 15}},
            },
        }
        attach_execution_policy(state, scenario="s5", media=True)
        await PipelineStateManager().save("s5-final-gate", state)

        with pytest.raises(HTTPException) as exc:
            await generate_candidates("s5-final-gate", "gate_3_final")
        assert exc.value.status_code == 422
        assert "outside execution profile" in str(exc.value.detail)


# ── _build_skill_params 验证 ──


class TestBuildSkillParamsForScenarios:
    """验证 _build_skill_params 为各场景的 candidate_step 正确构建参数。"""

    def test_scripts_step_params(self):
        state = {
            "config": {
                "product_catalog": {"product_name": "Test", "usps": ["usp1"]},
                "brand_guidelines": {"tone": "warm"},
                "target_languages": ["en"],
            },
            "steps": {
                "strategy": {"output": {"briefs": [{"topic": "t"}]}},
            },
        }
        params = _build_skill_params("scripts", state, "standard", {"temperature": 0.7})
        assert "briefs" in params
        assert params["variant"] == "standard"
        assert params["temperature"] == 0.7

    def test_remix_script_params(self):
        """S3 remix_script 参数构建:analysis + product + brief_id + influencer_name。"""
        state = {
            "config": {
                "product": {"name": "Test Product", "usps": ["usp1"]},
                "brief_id": "BRIEF-123",
                "influencer_name": "TestInfluencer",
                "target_platforms": ["tiktok"],
                "target_languages": ["en"],
            },
            "steps": {
                "video_analysis": {"output": {"hook_type": "question", "speech_style": "casual"}},
            },
        }
        params = _build_skill_params("remix_script", state, "creative", {"temperature": 0.9})
        assert "analysis" in params
        assert params["analysis"]["hook_type"] == "question"
        assert params["product"]["name"] == "Test Product"
        assert params["brief_id"] == "BRIEF-123"
        assert params["influencer_name"] == "TestInfluencer"
        assert params["variant"] == "creative"
        assert params["temperature"] == 0.9

    def test_vlog_strategy_params(self):
        """S5 vlog_strategy 参数构建:product_catalog + brand_guidelines + content_scenario。"""
        state = {
            "config": {
                "product_sku": {"name": "Test SKU", "usps": ["usp1"]},
                "brand_guidelines": {"tone": "warm"},
                "target_platforms": ["tiktok"],
                "target_languages": ["en"],
            },
            "steps": {},
        }
        params = _build_skill_params("vlog_strategy", state, "standard", {"temperature": 0.7})
        assert "product_catalog" in params
        assert params["product_catalog"]["name"] == "Test SKU"
        assert params["content_scenario"] == "brand_vlog"
        assert params["variant"] == "standard"
        assert params["temperature"] == 0.7

    def test_keyframe_images_params(self):
        state = {
            "config": {"brand_guidelines": {}},
            "steps": {
                "storyboards": {"output": [{"shots": []}]},
                "scripts": {"output": []},
            },
        }
        params = _build_skill_params("keyframe_images", state, "standard", {})
        assert "storyboard" in params
        assert params["size"] == "1024x1792"

    def test_seedance_clips_params(self):
        state = {
            "config": {"product_catalog": {"product_name": "Test"}},
            "label": "test-label",
            "steps": {
                "video_prompts": {"output": [{"segment_prompt": "prompt1"}]},
                "keyframe_images": {"output": []},
            },
        }
        params = _build_skill_params("seedance_clips", state, "standard", {})
        assert "prompt" in params
        assert params["duration"] == 5
        assert params["resolution"] == "720p"


# ── step_runner gate 触发验证(S3/S4/S5) ──


class TestStepRunnerGatePauseForScenarios:
    """验证 StepRunner 在非 S1 场景下正确触发 gate 暂停。"""

    @pytest.mark.asyncio
    async def test_s3_step_by_step_pauses_at_remix_script_gate(
        self,
        isolated_state_dir,
        isolated_provider_cost_db,
    ):
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        step_runner = StepRunner(sm)
        config = {
            "video_url": "https://example.com/video.mp4",
            "product": {"name": "Test Product"},
            "influencer_name": "TestInfluencer",
        }
        async with bound_generation_policy("s3", media=False):
            label = await step_runner.init_state(
                config=config,
                mode="step_by_step",
                scenario="s3",
            )

        # 预跑 video_analysis 和 character_identity(没有 gate)
        with patch(
            "src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline.run_step", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = {"mock": "data"}
            await step_runner.run_step(label, "video_analysis")
            await step_runner.run_step(label, "character_identity")

            # remix_script 是 S3 gate_1 的 after_step
            mock_run.return_value = {"scripts": [{"text": "mock remix"}]}
            state = await step_runner.run_step(label, "remix_script")

        # 验证 gate_1_script 被触发
        assert "gates" in state
        assert "gate_1_script" in state["gates"]
        assert state["gates"]["gate_1_script"]["status"] == "awaiting_approval"
        assert state["current_step"] == "remix_script"

    @pytest.mark.asyncio
    async def test_s4_step_by_step_pauses_at_scripts_gate(
        self,
        isolated_state_dir,
        isolated_provider_cost_db,
    ):
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        step_runner = StepRunner(sm)
        config = {
            "footage_assets": [],
            "product_info": {"name": "Test"},
            "topic": "test topic",
        }
        async with bound_generation_policy("s4", media=False):
            label = await step_runner.init_state(
                config=config,
                mode="step_by_step",
                scenario="s4",
            )

        with patch(
            "src.pipeline.s4_live_shoot_pipeline.S4LiveShootPipeline.run_step", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = {"scripts": [{"text": "mock"}]}
            state = await step_runner.run_step(label, "scripts")

        assert "gates" in state
        assert "gate_1_script" in state["gates"]
        assert state["gates"]["gate_1_script"]["status"] == "awaiting_approval"
        assert state["current_step"] == "scripts"

    @pytest.mark.asyncio
    async def test_s5_step_by_step_pauses_at_vlog_strategy_gate(
        self,
        isolated_state_dir,
        isolated_provider_cost_db,
    ):
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        step_runner = StepRunner(sm)
        config = {
            "brand_id": "momcozy",
            "product_sku": {"name": "Test SKU"},
            "scene_id": "living-room",
        }
        async with bound_generation_policy("s5", media=False):
            label = await step_runner.init_state(
                config=config,
                mode="step_by_step",
                scenario="s5",
            )

        with patch(
            "src.pipeline.s5_brand_vlog_pipeline.S5BrandVlogPipeline.run_step", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = {"strategy": "mock vlog strategy"}
            state = await step_runner.run_step(label, "vlog_strategy")

        assert "gates" in state
        assert "gate_1_strategy" in state["gates"]
        assert state["gates"]["gate_1_strategy"]["status"] == "awaiting_approval"
        assert state["current_step"] == "vlog_strategy"

    @pytest.mark.asyncio
    async def test_s3_auto_mode_skips_gate(
        self,
        isolated_state_dir,
        isolated_provider_cost_db,
    ):
        from unittest.mock import AsyncMock, patch

        from src.pipeline.step_runner import StepRunner

        sm = PipelineStateManager()
        step_runner = StepRunner(sm)
        async with bound_generation_policy("s3", media=False):
            label = await step_runner.init_state(
                config={"video_url": "", "product": {"name": "Test"}},
                mode="auto",
                scenario="s3",
            )

        with patch(
            "src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline.run_step", new_callable=AsyncMock
        ) as mock_run:
            mock_run.return_value = {"scripts": [{"text": "mock"}]}
            state = await step_runner.run_step(label, "remix_script")

        # auto 模式不触发 gate
        assert "gate_1_script" not in state.get("gates", {})
