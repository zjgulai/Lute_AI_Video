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
