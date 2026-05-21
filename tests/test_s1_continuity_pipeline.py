from __future__ import annotations

import pytest


def test_s1_step_order_includes_continuity_before_keyframes() -> None:
    from src.pipeline.step_runner import STEP_ORDER
    from src.routers._state import _SCENARIO_STEP_ORDER

    assert "continuity_storyboard_grid" in STEP_ORDER
    assert STEP_ORDER.index("storyboards") < STEP_ORDER.index("continuity_storyboard_grid")
    assert STEP_ORDER.index("continuity_storyboard_grid") < STEP_ORDER.index("keyframe_images")

    s1_order = _SCENARIO_STEP_ORDER["s1"]
    assert "continuity_storyboard_grid" in s1_order
    assert s1_order.index("storyboards") < s1_order.index("continuity_storyboard_grid")
    assert s1_order.index("continuity_storyboard_grid") < s1_order.index("keyframe_images")


def test_s1_config_defaults_for_continuity() -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.pipeline.step_runner import _with_continuity_defaults
    from src.routers._state import S1StartRequest

    config = S1ProductDirectPipeline._normalize_continuity_config({})
    request = S1StartRequest(product_catalog={"product_name": "Test"})
    runner_config = _with_continuity_defaults({"product_catalog": {}}, "s1")

    assert config["continuity_mode"] is True
    assert config["storyboard_grid"] == 12
    assert config["clip_group_size"] == 3
    assert request.continuity_mode is True
    assert request.storyboard_grid == 12
    assert request.clip_group_size == 3
    assert runner_config["continuity_mode"] is True
    assert runner_config["storyboard_grid"] == 12
    assert runner_config["clip_group_size"] == 3


def test_remotion_payload_contains_transitions() -> None:
    from src.skills.remotion_assemble import RemotionAssembleSkill

    skill = RemotionAssembleSkill()
    payload = skill._build_render_payload(
        shots=[
            {"id": 1, "start_time": 0, "end_time": 4, "visual": "a"},
            {"id": 2, "start_time": 4, "end_time": 10, "visual": "b"},
        ],
        captions=[],
        audio_paths=[],
        lyrics_text="",
        brand_guidelines={},
        total_duration=10,
        label="test",
        clip_paths=["/tmp/a.mp4", "/tmp/b.mp4"],
        transitions=[
            {
                "from_clip": 1,
                "to_clip": 2,
                "type": "match_cut",
                "duration_frames": 8,
            }
        ],
    )

    assert payload["transitions"] == [
        {
            "from_clip": 1,
            "to_clip": 2,
            "type": "match_cut",
            "duration_frames": 8,
        }
    ]


def _sample_continuity_grid() -> dict:
    return {
        "product_name": "Momcozy Nutri Bottle Warmer",
        "visual_identity": {
            "location": "warm night kitchen and nursery doorway",
            "lighting": "soft warm low-light",
            "product_anchor": "same bottle warmer on the same countertop",
        },
        "clip_groups": [
            {
                "clip_index": 1,
                "shot_indices": [1, 2, 3],
                "duration": 4,
                "purpose": "pain setup",
                "seedance_prompt": "Clock, cold bottle, parent approaches warmer.",
                "transition_to_next": (
                    "match cut from cold bottle movement to bottle placement"
                ),
                "transition_type": "match_cut",
            },
            {
                "clip_index": 2,
                "shot_indices": [4, 5, 6],
                "duration": 6,
                "purpose": "product action",
                "seedance_prompt": (
                    "Bottle placed into warmer, button press, indicator light."
                ),
                "transition_to_next": "action cut from indicator to bottle removal",
                "transition_type": "action_cut",
            },
        ],
    }


@pytest.mark.asyncio
async def test_seedance_prompt_uses_continuity_clip_groups() -> None:
    import src.skills.seedance_prompt  # noqa: F401
    from src.skills.registry import SkillRegistry

    result = await SkillRegistry().execute(
        "seedance-video-prompt",
        {
            "continuity_storyboard_grid": _sample_continuity_grid(),
            "product_name": "Momcozy Nutri Bottle Warmer",
        },
    )

    assert result.success is True
    assert result.metadata["source"] == "continuity_storyboard_grid"
    prompts = result.data
    assert len(prompts) == 2
    assert prompts[0]["segment_type"] == "clip_group"
    assert prompts[0]["clip_index"] == 1
    assert prompts[0]["duration_seconds"] == 4
    assert prompts[0]["transition_to_next"] == (
        "match cut from cold bottle movement to bottle placement"
    )
    assert prompts[0]["transition_type"] == "match_cut"
    assert prompts[1]["clip_index"] == 2
    assert prompts[1]["duration_seconds"] == 6
    assert prompts[1]["transition_to_next"] == (
        "action cut from indicator to bottle removal"
    )
    assert "same bottle warmer on the same countertop" in prompts[0]["segment_prompt"]
    assert all(prompt["has_forbidden_words"] is False for prompt in prompts)
    assert all(prompt["forbidden_hits"] == [] for prompt in prompts)


@pytest.mark.asyncio
async def test_seedance_prompt_rejects_invalid_continuity_clip_groups() -> None:
    import src.skills.seedance_prompt  # noqa: F401
    from src.skills.registry import SkillRegistry

    non_dict_group_grid = _sample_continuity_grid()
    non_dict_group_grid["clip_groups"] = ["bad group"]

    non_dict_result = await SkillRegistry().execute(
        "seedance-video-prompt",
        {
            "continuity_storyboard_grid": non_dict_group_grid,
            "product_name": "Momcozy Nutri Bottle Warmer",
        },
    )

    assert non_dict_result.success is False
    assert "clip_groups[0] must be a dict" in (non_dict_result.error or "")

    invalid_number_grid = _sample_continuity_grid()
    invalid_number_grid["clip_groups"][0]["duration"] = "not-a-number"
    invalid_number_grid["clip_groups"][0]["clip_index"] = "not-a-number"

    invalid_number_result = await SkillRegistry().execute(
        "seedance-video-prompt",
        {
            "continuity_storyboard_grid": invalid_number_grid,
            "product_name": "Momcozy Nutri Bottle Warmer",
        },
    )

    assert invalid_number_result.success is False
    assert "clip_groups[0].duration must be numeric" in (
        invalid_number_result.error or ""
    )
    assert "clip_groups[0].clip_index must be numeric" in (
        invalid_number_result.error or ""
    )


@pytest.mark.asyncio
async def test_video_prompts_empty_continuity_prompt_falls_back_to_script_segments() -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.registry import SkillRegistry

    continuity_grid = _sample_continuity_grid()
    continuity_grid["clip_groups"][0]["seedance_prompt"] = "   "

    errors: list[str] = []
    result = await S1ProductDirectPipeline()._step_video_prompts(
        reg=SkillRegistry(),
        scripts=[
            {
                "id": "script-1",
                "product_name": "Momcozy Nutri Bottle Warmer",
                "segments": [
                    {
                        "segment_type": "hook",
                        "visual_description": "parent reaches for bottle warmer",
                        "voiceover": "Warm the bottle quickly.",
                        "start_time": 0,
                        "end_time": 5,
                    }
                ],
            }
        ],
        product_name="Momcozy Nutri Bottle Warmer",
        errors=errors,
        continuity_storyboard_grid=continuity_grid,
    )

    assert len(result) == 1
    assert result[0]["segment_type"] == "hook"
    assert result[0]["script_id"] == "script-1"
    assert result[0]["product_name"] == "Momcozy Nutri Bottle Warmer"
    assert result[0]["segment_prompt"] != "fallback prompt"
    assert len(errors) == 1
    assert errors[0].startswith("video_prompts_continuity_failed: ")
    assert "seedance_prompt" in errors[0]


@pytest.mark.asyncio
async def test_video_prompts_step_prefers_continuity_clip_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    captured: dict[str, object] = {}
    expected_prompts = [
        {
            "segment_prompt": "clip one",
            "segment_type": "clip_group",
            "clip_index": 1,
            "duration_seconds": 4,
        },
        {
            "segment_prompt": "clip two",
            "segment_type": "clip_group",
            "clip_index": 2,
            "duration_seconds": 6,
        },
    ]

    async def fake_execute(self: SkillRegistry, skill_name: str, params: dict) -> SkillResult:
        captured["skill_name"] = skill_name
        captured["params"] = params
        return SkillResult(success=True, data=expected_prompts)

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    pipeline = S1ProductDirectPipeline()
    result = await pipeline.run_step(
        "video_prompts",
        {
            "config": {
                "product_name": "Momcozy Nutri Bottle Warmer",
                "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            },
            "errors": [],
            "media_synthesis_errors": [],
            "steps": {
                "scripts": {
                    "output": [
                        {
                            "id": "script-1",
                            "segments": [
                                {
                                    "segment_type": "hook",
                                    "visual_description": "old script segment",
                                }
                            ],
                        }
                    ],
                    "edited": False,
                    "edited_output": None,
                },
                "continuity_storyboard_grid": {
                    "output": _sample_continuity_grid(),
                    "edited": False,
                    "edited_output": None,
                },
            },
        },
    )

    assert result == expected_prompts
    assert captured["skill_name"] == "seedance-video-prompt"
    assert captured["params"]["product_name"] == "Momcozy Nutri Bottle Warmer"
    assert "continuity_storyboard_grid" in captured["params"]
    assert "script_segments" not in captured["params"]


@pytest.mark.asyncio
async def test_video_prompts_continuity_fallback_uses_script_segments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    calls: list[dict[str, object]] = []
    segment_prompts = [
        {
            "segment_prompt": "segment prompt",
            "segment_type": "hook",
            "duration_seconds": 5,
        }
    ]

    async def fake_execute(self: SkillRegistry, skill_name: str, params: dict) -> SkillResult:
        calls.append({"skill_name": skill_name, "params": params})
        if "continuity_storyboard_grid" in params:
            return SkillResult(
                success=True,
                data=[
                    {
                        "segment_prompt": "fallback prompt",
                        "segment_type": "body",
                        "_fallback": True,
                    }
                ],
                metadata={
                    "is_fallback": True,
                    "fallback_reason": "continuity builder failed",
                },
            )
        return SkillResult(success=True, data=segment_prompts)

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    errors: list[str] = []
    result = await S1ProductDirectPipeline()._step_video_prompts(
        reg=SkillRegistry(),
        scripts=[
            {
                "id": "script-1",
                "product_name": "Momcozy Nutri Bottle Warmer",
                "segments": [
                    {
                        "segment_type": "hook",
                        "visual_description": "parent reaches for bottle warmer",
                        "voiceover": "Warm the bottle quickly.",
                        "start_time": 0,
                        "end_time": 5,
                    }
                ],
            }
        ],
        product_name="Momcozy Nutri Bottle Warmer",
        errors=errors,
        continuity_storyboard_grid=_sample_continuity_grid(),
    )

    assert result == [
        {
            **segment_prompts[0],
            "script_id": "script-1",
            "product_name": "Momcozy Nutri Bottle Warmer",
        }
    ]
    assert len(calls) == 2
    assert "continuity_storyboard_grid" in calls[0]["params"]
    assert "script_segments" in calls[1]["params"]
    assert errors == [
        "video_prompts_continuity_failed: continuity builder failed"
    ]


@pytest.mark.asyncio
async def test_run_step_continuity_storyboard_grid_calls_skill(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    captured: dict[str, object] = {}

    async def fake_execute(self: SkillRegistry, skill_name: str, params: dict) -> SkillResult:
        captured["skill_name"] = skill_name
        captured["params"] = params
        return SkillResult(
            success=True,
            data={
                "grid_type": "12-grid",
                "product_name": "Momcozy Nutri Bottle Warmer",
                "visual_identity": {},
                "micro_shots": [
                    {"index": index, "continuity_in": "in", "continuity_out": "out"}
                    for index in range(1, 13)
                ],
                "clip_groups": [
                    {
                        "clip_index": 1,
                        "shot_indices": [1, 2, 3],
                        "transition_to_next": "match cut",
                        "transition_type": "match_cut",
                    },
                    {"clip_index": 2, "shot_indices": [4, 5, 6]},
                    {"clip_index": 3, "shot_indices": [7, 8, 9]},
                    {"clip_index": 4, "shot_indices": [10, 11, 12]},
                ],
            },
            metadata={"grid_size": 12},
        )

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    pipeline = S1ProductDirectPipeline()
    state = {
        "config": {
            "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            "storyboard_grid": 12,
            "clip_group_size": 3,
            "continuity_mode": True,
            "transition_style": "match_cut",
        },
        "errors": [],
        "media_synthesis_errors": [],
        "steps": {
            "scripts": {"output": [{"id": "script-1"}], "edited": False, "edited_output": None},
            "storyboards": {
                "output": [{"script_id": "script-1", "shots": []}],
                "edited": False,
                "edited_output": None,
            },
        },
    }

    result = await pipeline.run_step("continuity_storyboard_grid", state)

    assert captured["skill_name"] == "continuity-storyboard-grid"
    assert captured["params"]["product_catalog"]["product_name"] == "Momcozy Nutri Bottle Warmer"
    assert captured["params"]["storyboard_grid"] == 12
    assert result["continuity_storyboard_grid"]["grid_type"] == "12-grid"
    assert result["continuity_micro_shots"]
    assert result["clip_groups"]
    assert result["transition_plan"] == [
        {
            "from_clip": 1,
            "to_clip": 2,
            "transition": "match cut",
            "transition_type": "match_cut",
        }
    ]
    assert result["metadata"]["grid_size"] == 12


@pytest.mark.asyncio
async def test_step_runner_persists_continuity_state_fields() -> None:
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    state_manager = PipelineStateManager(use_pg=False)
    runner = StepRunner(state_manager)
    label = await runner.init_state(
        config={"product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"}},
        mode="auto",
        label="s1_continuity_test",
        scenario="s1",
    )
    state = await state_manager.load(label)
    assert state is not None
    state["steps"]["storyboards"]["output"] = [{"script_id": "script-1", "shots": []}]
    state["steps"]["storyboards"]["status"] = "done"
    await state_manager.save(label, state)

    result_state = await runner.run_step(label, "continuity_storyboard_grid")

    assert result_state["steps"]["continuity_storyboard_grid"]["status"] == "done"
    assert result_state["continuity_storyboard_grid"]["grid_type"] == "12-grid"
    assert result_state["config"]["storyboard_grid"] == 12
    assert "storyboard_grid" not in result_state
    assert result_state["continuity_micro_shots"]
    assert result_state["clip_groups"]
    assert result_state["transition_plan"]


@pytest.mark.asyncio
async def test_continuity_mode_false_skips_without_missing_state_fields() -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    storyboards = [{"script_id": "script-1", "shots": [{"id": 1, "visual": "Existing shot"}]}]
    pipeline = S1ProductDirectPipeline()
    state = {
        "config": {
            "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            "continuity_mode": False,
        },
        "errors": [],
        "media_synthesis_errors": [],
        "steps": {
            "scripts": {"output": [{"id": "script-1"}], "edited": False, "edited_output": None},
            "storyboards": {
                "output": storyboards,
                "edited": False,
                "edited_output": None,
            },
        },
    }

    result = await pipeline.run_step("continuity_storyboard_grid", state)

    assert result["continuity_storyboard_grid"]["skipped"] is True
    assert result["continuity_storyboard_grid"]["status"] == "skipped"
    assert result["continuity_storyboard_grid"]["metadata"]["skipped"] is True
    assert result["continuity_micro_shots"] == []
    assert result["clip_groups"] == []
    assert result["transition_plan"] == []
    assert result["metadata"]["skipped"] is True
    assert state["errors"] == []


@pytest.mark.asyncio
async def test_direct_run_preserves_explicit_continuity_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline import s1_product_pipeline

    captured: dict[str, object] = {}

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(
            self,
            config: dict,
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            captured["config"] = config
            captured["mode"] = mode
            captured["scenario"] = scenario
            return label or "s1_direct_run_test"

        async def resume(self, label: str) -> dict:
            return {
                "label": label,
                "scenario": "s1",
                "steps": {},
                "errors": [],
                "media_synthesis_errors": [],
            }

    monkeypatch.setattr(s1_product_pipeline, "StepRunner", FakeStepRunner)

    await s1_product_pipeline.S1ProductDirectPipeline().run(
        product_catalog={"product_name": "Momcozy Nutri Bottle Warmer"},
        enable_media_synthesis=False,
        output_label="s1_direct_run_test",
        continuity_mode=False,
        storyboard_grid="24",
        clip_group_size=4,
    )

    config = captured["config"]
    assert config["continuity_mode"] is False
    assert config["storyboard_grid"] == "24"
    assert config["clip_group_size"] == 4


@pytest.mark.asyncio
async def test_scenario_s1_dict_entry_preserves_explicit_continuity_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.routers import scenario
    from src.tools import translate

    captured: dict[str, object] = {}

    async def fake_translate_catalog(product_catalog: dict) -> dict:
        return product_catalog

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(
            self,
            config: dict,
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            captured["config"] = config
            captured["mode"] = mode
            captured["scenario"] = scenario
            return "s1_dict_entry_test"

        async def resume(self, label: str) -> dict:
            return {
                "label": label,
                "scenario": "s1",
                "config": captured["config"],
                "steps": {},
                "errors": [],
                "media_synthesis_errors": [],
            }

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate_catalog)
    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)
    monkeypatch.setattr("src.tools.cost_tracker.set_thread_id", lambda label: None)

    await scenario.run_s1_product_direct(
        {
            "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            "continuity_mode": False,
            "storyboard_grid": 12,
            "clip_group_size": 3,
        }
    )

    config = captured["config"]
    assert config["continuity_mode"] is False
    assert config["storyboard_grid"] == 12
    assert config["clip_group_size"] == 3


@pytest.mark.asyncio
async def test_scenario_s1_typeerror_fallback_preserves_explicit_continuity_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.routers import scenario
    from src.tools import translate

    captured: dict[str, object] = {}

    async def fake_translate_catalog(product_catalog: dict) -> dict:
        return product_catalog

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(
            self,
            config: dict,
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            return "s1_fallback_test"

        async def resume(self, label: str) -> dict:
            raise TypeError("structlog fallback")

    async def fake_run(
        self: S1ProductDirectPipeline,
        product_catalog: dict,
        **kwargs: object,
    ) -> dict:
        captured["product_catalog"] = product_catalog
        captured["kwargs"] = kwargs
        return {"success": True}

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate_catalog)
    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)
    monkeypatch.setattr("src.tools.cost_tracker.set_thread_id", lambda label: None)
    monkeypatch.setattr(S1ProductDirectPipeline, "run", fake_run)

    result = await scenario.run_s1_product_direct(
        {
            "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            "continuity_mode": False,
            "storyboard_grid": "24",
            "clip_group_size": 4,
        }
    )

    kwargs = captured["kwargs"]
    assert result == {"success": True}
    assert kwargs["continuity_mode"] is False
    assert kwargs["storyboard_grid"] == "24"
    assert kwargs["clip_group_size"] == 4


@pytest.mark.asyncio
async def test_scenario_s1_start_preserves_explicit_continuity_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.routers import scenario
    from src.routers._state import S1StartRequest

    captured: dict[str, object] = {}

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(
            self,
            config: dict,
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            captured["config"] = config
            captured["mode"] = mode
            captured["scenario"] = scenario
            return "s1_start_entry_test"

        async def resume(self, label: str) -> dict:
            return {"label": label, "steps": {}}

    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)

    result = await scenario.start_s1_pipeline(
        S1StartRequest(
            product_catalog={"product_name": "Momcozy Nutri Bottle Warmer"},
            mode="step_by_step",
            continuity_mode=False,
            storyboard_grid=24,
            clip_group_size=4,
        )
    )

    config = captured["config"]
    assert result["label"] == "s1_start_entry_test"
    assert captured["mode"] == "step_by_step"
    assert config["continuity_mode"] is False
    assert config["storyboard_grid"] == 24
    assert config["clip_group_size"] == 4


@pytest.mark.asyncio
async def test_unified_scenario_s1_entry_preserves_explicit_continuity_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.routers import scenario
    from src.tools import translate

    captured: dict[str, object] = {}

    async def fake_translate_catalog(product_catalog: dict) -> dict:
        return product_catalog

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = state_manager

        async def init_state(
            self,
            config: dict,
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            captured["config"] = config
            captured["mode"] = mode
            captured["scenario"] = scenario
            return "s1_unified_entry_test"

        async def resume(self, label: str) -> dict:
            return {"label": label, "steps": {}}

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate_catalog)
    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)
    monkeypatch.setattr("src.tools.cost_tracker.set_thread_id", lambda label: None)
    monkeypatch.setattr(scenario, "_register_background_task", lambda task, label: None)

    result = await scenario.submit_scenario(
        "s1",
        {
            "product_catalog": {"product_name": "Momcozy Nutri Bottle Warmer"},
            "continuity_mode": False,
            "storyboard_grid": 12,
            "clip_group_size": 3,
        },
    )

    config = captured["config"]
    assert result["label"] == "s1_unified_entry_test"
    assert captured["scenario"] == "s1"
    assert config["continuity_mode"] is False
    assert config["storyboard_grid"] == 12
    assert config["clip_group_size"] == 3


@pytest.mark.asyncio
async def test_seedance_grouped_prompts_keep_transition_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    calls: list[dict[str, object]] = []

    async def fake_execute(
        self: SkillRegistry,
        skill_name: str,
        params: dict,
    ) -> SkillResult:
        calls.append({"skill_name": skill_name, "params": params})
        if skill_name == "media-quality-audit-skill":
            return SkillResult(success=True, data={"overall_status": "PASS"})
        return SkillResult(
            success=True,
            data={
                "video_path": f"/tmp/{params['output_label']}.mp4",
                "duration_seconds": params["duration"],
                "file_size_bytes": 2048,
                "is_stub": False,
                "verification": {"all_ok": True},
                "prompt_used": params["prompt"],
            },
        )

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    result = await S1ProductDirectPipeline()._step_seedance_clips(
        reg=SkillRegistry(),
        video_prompts=[
            {
                "segment_prompt": "clip one",
                "segment_type": "clip_group",
                "shot_type": "wide_to_medium",
                "duration_seconds": 4,
                "clip_index": 1,
                "transition_to_next": "match cut",
                "transition_type": "match_cut",
            },
            {
                "segment_prompt": "clip two",
                "segment_type": "clip_group",
                "shot_type": "medium_to_detail",
                "duration_seconds": 6,
                "clip_index": 2,
                "transition_type": "action_cut",
            },
        ],
        product_name="Momcozy Nutri Bottle Warmer",
        label="test_label",
        errors=[],
        video_duration=10,
        keyframe_images=[],
        continuity_mode="standard",
    )

    seedance_calls = [
        call for call in calls if call["skill_name"] == "seedance-video-generate-skill"
    ]
    assert len(result["clip_paths"]) == 2
    assert result["clip_details"][0]["clip_index"] == 1
    assert result["clip_details"][0]["transition_to_next"] == "match cut"
    assert result["clip_details"][0]["transition_type"] == "match_cut"
    assert result["clip_details"][0]["segment_type"] == "clip_group"
    assert result["clip_details"][0]["shot_type"] == "wide_to_medium"
    assert result["clip_details"][0]["continuity_frame"] is False
    assert result["clip_details"][1]["clip_index"] == 2
    assert result["clip_details"][1]["transition_to_next"] == ""
    assert result["clip_details"][1]["transition_type"] == "action_cut"
    assert seedance_calls[0]["params"]["duration"] == 4
    assert seedance_calls[1]["params"]["duration"] == 6


@pytest.mark.asyncio
async def test_assemble_final_passes_clip_transitions_to_remotion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    captured: dict[str, object] = {}

    async def fake_execute(
        self: SkillRegistry,
        skill_name: str,
        params: dict,
    ) -> SkillResult:
        captured["skill_name"] = skill_name
        captured["params"] = params
        return SkillResult(
            success=True,
            data={
                "video_path": "/tmp/final.mp4",
                "render_json_path": "/tmp/final_input.json",
            },
        )

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)

    result = await S1ProductDirectPipeline()._step_assemble_final(
        reg=SkillRegistry(),
        storyboards=[
            {
                "shots": [
                    {"id": 1, "start_time": 0, "end_time": 4, "visual": "a"},
                    {"id": 2, "start_time": 4, "end_time": 8, "visual": "b"},
                    {"id": 3, "start_time": 8, "end_time": 12, "visual": "c"},
                ],
            }
        ],
        scripts=[],
        audio_paths=[],
        lyrics_paths=[],
        clip_paths=["/tmp/a.mp4", "/tmp/b.mp4", "/tmp/c.mp4"],
        clip_details=[
            {
                "transition_to_next": "soft crossfade to product closeup",
                "transition_type": "soft_crossfade",
            },
            {
                "transition_to_next": "action cut to final hero",
                "transition_type": "action_cut",
            },
            {
                "transition_to_next": "ignored because last clip",
                "transition_type": "match_cut",
            },
        ],
        brand_guidelines={},
        label="test_label",
        errors=[],
    )

    assert result == ("/tmp/final.mp4", "/tmp/final_input.json")
    assert captured["skill_name"] == "remotion-assemble-skill"
    assert captured["params"]["transitions"] == [
        {
            "from_clip": 1,
            "to_clip": 2,
            "type": "soft_crossfade",
            "duration_frames": 12,
            "description": "soft crossfade to product closeup",
        },
        {
            "from_clip": 2,
            "to_clip": 3,
            "type": "action_cut",
            "duration_frames": 8,
            "description": "action cut to final hero",
        },
    ]


@pytest.mark.asyncio
async def test_seedance_high_quality_passes_continuity_frame_to_next_clip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
    from src.skills.base import SkillResult
    from src.skills.registry import SkillRegistry

    calls: list[dict[str, object]] = []

    async def fake_execute(
        self: SkillRegistry,
        skill_name: str,
        params: dict,
    ) -> SkillResult:
        calls.append({"skill_name": skill_name, "params": params})
        if skill_name == "media-quality-audit-skill":
            return SkillResult(success=True, data={"overall_status": "PASS"})
        return SkillResult(
            success=True,
            data={
                "video_path": f"/tmp/{params['output_label']}.mp4",
                "duration_seconds": params["duration"],
                "file_size_bytes": 2048,
                "is_stub": False,
                "verification": {"all_ok": True},
                "prompt_used": params["prompt"],
            },
        )

    def fake_extract(video_path: str, output_dir: str) -> str | None:
        return f"/tmp/frame_for_{video_path.rsplit('/', maxsplit=1)[-1]}.jpg"

    monkeypatch.setattr(SkillRegistry, "execute", fake_execute)
    monkeypatch.setattr(
        S1ProductDirectPipeline,
        "_extract_clip_last_frame",
        staticmethod(fake_extract),
    )

    result = await S1ProductDirectPipeline()._step_seedance_clips(
        reg=SkillRegistry(),
        video_prompts=[
            {
                "segment_prompt": "clip one",
                "duration_seconds": 4,
                "clip_index": 1,
            },
            {
                "segment_prompt": "clip two",
                "duration_seconds": 4,
                "clip_index": 2,
            },
        ],
        product_name="Momcozy Nutri Bottle Warmer",
        label="test_hq",
        errors=[],
        video_duration=8,
        keyframe_images=[],
        continuity_mode="high_quality",
    )

    seedance_calls = [
        call for call in calls if call["skill_name"] == "seedance-video-generate-skill"
    ]
    assert "continuity_frame_path" not in seedance_calls[0]["params"]
    assert seedance_calls[1]["params"]["continuity_frame_path"] == (
        "/tmp/frame_for_test_hq_seg_0.mp4.jpg"
    )
    assert result["clip_details"][0]["continuity_frame"] is False
    assert result["clip_details"][1]["continuity_frame"] is True


def test_continuity_generation_mode_preserves_false_skip_contract() -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    disabled = S1ProductDirectPipeline._normalize_continuity_config(
        {"continuity_mode": False}
    )
    disabled_string = S1ProductDirectPipeline._normalize_continuity_config(
        {"continuity_mode": "off", "continuity_generation_mode": "high_quality"}
    )
    high_quality = S1ProductDirectPipeline._normalize_continuity_config(
        {"continuity_mode": "high_quality"}
    )
    explicit_generation = S1ProductDirectPipeline._normalize_continuity_config(
        {"continuity_mode": True, "continuity_generation_mode": "high_quality"}
    )

    assert disabled["continuity_mode"] is False
    assert disabled["continuity_generation_mode"] == "standard"
    assert disabled_string["continuity_mode"] is False
    assert disabled_string["continuity_generation_mode"] == "standard"
    assert high_quality["continuity_mode"] is True
    assert high_quality["continuity_generation_mode"] == "high_quality"
    assert explicit_generation["continuity_mode"] is True
    assert explicit_generation["continuity_generation_mode"] == "high_quality"
