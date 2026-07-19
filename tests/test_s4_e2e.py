"""S4 Live Shoot E2E integration test.

Verifies the S4 (Live Shoot to Video) scenario end-to-end using StepRunner:
1. script-writer-skill generates scripts from footage + product
2. seedance-video-prompt generates video prompts
3. gpt-image-thumbnail-prompt generates thumbnail prompts

Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

import src.pipeline.s4_live_shoot_pipeline as s4_live_shoot_pipeline
import src.skills.continuity_storyboard_grid as continuity_storyboard_grid_skill
import src.skills.script_writer as script_writer_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.thumbnail_prompt as thumbnail_prompt_skill
from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry
from tests.generation_policy_test_utils import bound_generation_policy


@pytest.fixture(autouse=True)
def _clear_registry():
    original_global_skills = dict(SkillRegistry._global_skills)
    SkillRegistry.clear_global()
    for module in (
        continuity_storyboard_grid_skill,
        script_writer_skill,
        seedance_prompt_skill,
        thumbnail_prompt_skill,
    ):
        importlib.reload(module)
    yield
    SkillRegistry._global_skills = original_global_skills


FOOTAGE_FIXTURE = [
    {"filename": "scene1.mp4", "duration": 15, "description": "Close-up of product"},
    {"filename": "scene2.mp4", "duration": 20, "description": "Lifestyle usage shot"},
]

PRODUCT_INFO_FIXTURE = {
    "name": "LactFit Wearable Breast Pump X1",
    "brand_name": "LactFit",
    "usps": ["Ultra-silent", "Hands-free", "2-hour battery"],
}


@pytest.mark.asyncio
async def test_s4_direct_run_without_effective_policy_fails_closed():
    """A direct run cannot silently grant itself provider authority."""
    pipeline = S4LiveShootPipeline()
    result = await pipeline.run(
        footage_assets=FOOTAGE_FIXTURE,
        product_info=PRODUCT_INFO_FIXTURE,
        topic="Working mom daily routine",
        target_platforms=["tiktok", "shopify"],
    )

    assert result.get("success") is False
    assert result.get("scenario") == "s4_live_shoot"
    assert isinstance(result.get("scripts"), list)
    assert isinstance(result.get("video_prompts"), list)
    assert isinstance(result.get("thumbnail_sets"), list)
    assert result.get("_execution_completed") is False
    assert result.get("final_video_path") == ""
    assert "Script generation failed" in result.get("errors", [])


def test_s4_import_does_not_register_media_prompt_or_generation_skills():
    forbidden_media_skill_names = {
        "seedance-video-prompt",
        "gpt-image-thumbnail-prompt",
        "seedance-video-generate-skill",
        "elevenlabs-tts-skill",
        "remotion-assemble-skill",
        "media-quality-audit-skill",
    }

    SkillRegistry.clear_global()
    importlib.reload(s4_live_shoot_pipeline)

    assert forbidden_media_skill_names.isdisjoint(SkillRegistry._global_skills)


def test_s4_media_prompt_skills_register_lazily_for_media_steps():
    SkillRegistry.clear_global()
    importlib.reload(s4_live_shoot_pipeline)

    assert "seedance-video-prompt" not in SkillRegistry._global_skills

    s4_live_shoot_pipeline._ensure_step_skills_registered("video_prompts")

    assert "seedance-video-prompt" in SkillRegistry._global_skills


@pytest.mark.asyncio
async def test_s4_no_media_stops_before_provider_backed_steps(monkeypatch: pytest.MonkeyPatch):
    executed_steps: list[str] = []
    saved_states: list[dict[str, Any]] = []
    captured: dict[str, Any] = {}

    class FakeStateManager:
        async def save(self, label: str, state: dict[str, Any]) -> None:
            saved_states.append({"label": label, "current_step": state.get("current_step")})

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = FakeStateManager()

        async def init_state(self, *, config, mode="auto", label=None, scenario="s4"):
            captured["config"] = config
            captured["scenario"] = scenario
            return label or "s4_no_media_fixture"

        async def resume(self, label):
            raise AssertionError("no-media S4 must not resume the full media pipeline")

        async def run_step(self, label, step_name):
            executed_steps.append(step_name)
            steps: dict[str, dict[str, Any]] = {}
            if "scripts" in executed_steps:
                steps["scripts"] = {"output": [{"id": "s4-script", "segments": []}]}
            if "continuity_storyboard_grid" in executed_steps:
                steps["continuity_storyboard_grid"] = {"output": {"clip_groups": []}}
            return {
                "label": label,
                "scenario": "s4",
                "steps": steps,
                "errors": [],
                "media_synthesis_errors": [],
                "pipeline_degraded": False,
                "lifecycle_status": (
                    "completed_bounded"
                    if step_name == "continuity_storyboard_grid"
                    else None
                ),
            }

    monkeypatch.setattr(s4_live_shoot_pipeline, "StepRunner", FakeStepRunner)

    result = await s4_live_shoot_pipeline.S4LiveShootPipeline().run(
        footage_assets=FOOTAGE_FIXTURE,
        product_info=PRODUCT_INFO_FIXTURE,
        topic="Working mom daily routine",
        target_platforms=["tiktok"],
        video_duration=15,
        enable_media_synthesis=False,
    )

    assert captured["scenario"] == "s4"
    assert captured["config"]["enable_media_synthesis"] is False
    assert captured["config"]["video_duration"] == 15
    assert executed_steps == ["scripts", "continuity_storyboard_grid"]
    assert "video_prompts" not in executed_steps
    assert result["success"] is True
    assert result["video_prompts"] == []
    assert result["thumbnail_sets"] == []
    assert result["seedance_clips"] == []
    assert result["clip_paths"] == []
    assert result["audio_paths"] == []
    assert result["final_video_path"] == ""
    assert result["steps_completed"] == 2
    assert saved_states[-1]["current_step"] is None


@pytest.mark.asyncio
async def test_scenario_s4_route_passes_bounded_media_controls(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    del isolated_provider_cost_db
    from src.routers import _deps, scenario
    from src.routers._state import S4LiveShootRequest

    captured: dict[str, object] = {}

    class FakeS4Pipeline:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {
                "success": True,
                "_execution_completed": True,
                "scenario": "s4_live_shoot",
            }

    monkeypatch.setattr(
        "src.pipeline.s4_live_shoot_pipeline.S4LiveShootPipeline",
        FakeS4Pipeline,
    )
    monkeypatch.setattr(
        scenario,
        "get_auth_context",
        lambda: _deps.AuthContext(
            tenant_id="tenant-a",
            permissions=frozenset({"provider:submit"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id="s4-bounded-route-test",
        ),
    )

    response = await scenario.run_s4_live_shoot(
        S4LiveShootRequest(
            footage_assets=FOOTAGE_FIXTURE,
            product_info=PRODUCT_INFO_FIXTURE,
            topic="Working mom daily routine",
            target_platforms=["tiktok"],
            video_duration=15,
            output_label="s4_bounded_contract",
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=0,
        )
    )

    assert response["status"] == "completed_bounded"
    assert response["completion_kind"] == "bounded_media"
    assert response["request_succeeded"] is True
    assert response["success"] is False
    assert response["full_media_success"] is False
    assert response["publish_allowed"] is False
    assert response["delivery_accepted"] is False
    assert captured["output_label"] == "s4_bounded_contract"
    assert captured["artifact_disposition"] == "pending_review"
    assert captured["provider_max_retries"] == 0


@pytest.mark.asyncio
async def test_s4_bounded_media_stops_after_seedance_and_clears_publishable_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed_steps: list[str] = []
    saved_states: list[dict[str, object]] = []
    captured_config: dict[str, object] = {}

    class FakeStateManager:
        async def save(self, label: str, state: dict[str, object]) -> None:
            saved_states.append(
                {
                    "label": label,
                    "current_step": state.get("current_step"),
                    "bounded_media_stop_step": state.get("bounded_media_stop_step"),
                }
            )

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            self.state_manager = FakeStateManager()

        async def init_state(self, *, config, mode="auto", label=None, scenario="s4"):
            captured_config.update(config)
            return label or "s4_bounded_fixture"

        async def resume(self, label):
            raise AssertionError("bounded S4 must not resume the full media pipeline")

        async def run_step(self, label, step_name):
            executed_steps.append(step_name)
            steps: dict[str, dict[str, object]] = {
                step: {"status": "done", "output": {}} for step in executed_steps
            }
            steps["scripts"] = {
                "status": "done",
                "output": [{"id": "s4-script", "segments": []}],
            }
            steps["video_prompts"] = {
                "status": "done",
                "output": [{"prompt": "authentic live shoot", "duration_seconds": 6}],
            }
            steps["seedance_clips"] = {
                "status": "done",
                "output": {
                    "clip_paths": [
                        (
                            "/output/tenants/momcozy-marketing/pending_review/"
                            "s4_bounded_fixture/clips/clip_0.mp4"
                        )
                    ],
                    "clip_details": [{"duration": 6}],
                    "total_duration": 6,
                },
            }
            for pending_step in (
                "thumbnails",
                "tts_audio",
                "assemble_final",
                "audit",
            ):
                steps.setdefault(pending_step, {"status": "pending", "output": None})
            return {
                "label": label,
                "scenario": "s4",
                "tenant_id": "momcozy-marketing",
                "config": captured_config,
                "steps": steps,
                "errors": [],
                "media_synthesis_errors": [],
                "pipeline_degraded": False,
                "lifecycle_status": (
                    "completed_bounded"
                    if step_name == "seedance_clips"
                    else None
                ),
            }

    monkeypatch.setattr(s4_live_shoot_pipeline, "StepRunner", FakeStepRunner)

    result = await S4LiveShootPipeline().run(
        footage_assets=FOOTAGE_FIXTURE,
        product_info=PRODUCT_INFO_FIXTURE,
        topic="Working mom daily routine",
        target_platforms=["tiktok"],
        video_duration=15,
        output_label="s4_bounded_fixture",
        enable_media_synthesis=True,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )

    assert executed_steps == s4_live_shoot_pipeline.S4_BOUNDED_MEDIA_STEP_ORDER
    assert captured_config["provider_max_retries"] == 0
    assert captured_config["provider_job_caps"] == {"image": 1, "video": 1}
    assert captured_config["seedance_quality_gate_enabled"] is False
    assert result["success"] is True
    assert result["label"] == "s4_bounded_fixture"
    assert result["bounded_media_pilot"] is True
    assert result["bounded_media_stop_step"] == "seedance_clips"
    assert result["provider_max_retries"] == 0
    assert result["provider_job_caps"] == {"image": 1, "video": 1}
    assert result["clip_paths"] == [
        "/output/tenants/momcozy-marketing/pending_review/s4_bounded_fixture/clips/clip_0.mp4"
    ]
    assert result["audio_paths"] == []
    assert result["thumbnail_sets"] == []
    assert result["thumbnail_image_paths"] == []
    assert result["final_video_path"] == ""
    assert result["render_json_path"] == ""
    assert result["audit_report"] == {}
    assert result["delivery_accepted"] is False
    assert result["publish_allowed"] is False
    assert result["approved_brand_token_write"] is False
    assert saved_states[-1]["current_step"] is None


@pytest.mark.asyncio
@pytest.mark.hermetic_slow
async def test_s4_step_runner_init_and_resume(isolated_provider_cost_db: Any):
    """S4 via StepRunner: init_state + resume produces valid state."""
    del isolated_provider_cost_db
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    config = {
        "footage_assets": FOOTAGE_FIXTURE,
        "product_info": PRODUCT_INFO_FIXTURE,
        "topic": "Test topic",
        "target_platforms": ["tiktok"],
        "product_name": "Test Product",
        "brand_name": "TestBrand",
    }

    async with bound_generation_policy("s4", media=False, tenant_id="momcozy-marketing"):
        runner = StepRunner(PipelineStateManager())
        label = await runner.init_state(config=config, mode="auto", scenario="s4")
        assert label.startswith("s4_")

        final_state = await runner.resume(label)
    assert final_state.get("scenario") == "s4"
    steps = final_state.get("steps", {})
    assert "scripts" in steps
    assert "video_prompts" in steps
    assert "thumbnails" in steps

    assert final_state.get("lifecycle_status") == "completed_bounded"
    assert final_state.get("completion_kind") == "no_media"
    assert final_state.get("request_succeeded") is True

    # Only the no-media profile's pre-media steps may run.
    for step_name in ["scripts", "continuity_storyboard_grid"]:
        assert steps[step_name]["status"] == "done", f"Step {step_name} not done"
    assert steps["video_prompts"]["status"] == "pending"
    assert steps["thumbnails"]["status"] == "pending"


@pytest.mark.asyncio
async def test_s4_scripts_forwards_configured_video_duration():
    """S4 script generation must honor the caller's target duration."""
    captured: dict[str, int] = {}

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "script-writer-skill"
            captured["video_duration"] = params["video_duration"]
            return SkillResult(
                success=True,
                data={"scripts": [{"id": "s4-script", "segments": []}]},
            )

    result = await S4LiveShootPipeline()._step_scripts(
        reg=FakeRegistry(),
        config={
            "footage_assets": FOOTAGE_FIXTURE,
            "product_info": PRODUCT_INFO_FIXTURE,
            "product_name": PRODUCT_INFO_FIXTURE["name"],
            "video_duration": 15,
        },
        steps={},
        errors=[],
    )

    assert captured["video_duration"] == 15
    assert result[0]["id"] == "s4-script"


@pytest.mark.asyncio
async def test_s4_video_prompts_preserve_path_only_upload_reference():
    """Frontend uploads provide `path`; S4 must keep that identity in prompts."""
    captured: dict[str, Any] = {}

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-prompt"
            captured.update(params)
            return SkillResult(success=True, data=[{"prompt": "fixture prompt"}])

    result = await S4LiveShootPipeline()._step_video_prompts(
        reg=FakeRegistry(),
        config={
            "footage_assets": [
                {
                    "path": "/api/media/uploads/momcozy-live-demo.mp4",
                    "source": "guided_form",
                },
            ],
        },
        steps={
            "scripts": {
                "output": [
                    {
                        "id": "s4-upload-trace",
                        "product_name": "KleanPal Pro",
                        "segments": [
                            {
                                "segment_type": "hook",
                                "visual_description": "show the sterilizer in use",
                                "start_time": 0,
                                "end_time": 4,
                            },
                        ],
                    },
                ],
            },
        },
        errors=[],
    )

    description = captured["script_segments"][0]["description"]
    assert "@material '/api/media/uploads/momcozy-live-demo.mp4'" in description
    assert "@material 'footage'" not in description
    assert result[0]["script_id"] == "s4-upload-trace"


@pytest.mark.asyncio
async def test_s4_audit_reads_persisted_assemble_list_path(monkeypatch):
    pipeline = S4LiveShootPipeline()
    captured: dict[str, str] = {}

    async def _fake_audit(**kwargs):
        captured["video_path"] = kwargs["video_path"]
        return {"overall_status": "pass"}

    monkeypatch.setattr(pipeline, "_step_audit", _fake_audit)

    result = await pipeline.run_step(
        "audit",
        {
            "config": {
                "product_name": "X1 Pump",
                "target_language": "en",
                "video_duration": 15,
            },
            "steps": {
                "assemble_final": {"output": ["/tmp/s4-final.mp4", "/tmp/s4-render.json"]},
                "tts_audio": {"output": {"audio_paths": ["/tmp/s4.mp3"]}},
                "thumbnails": {"output": []},
                "scripts": {"output": []},
                "seedance_clips": {"output": {"clip_paths": ["/tmp/s4-clip.mp4"]}},
            },
            "errors": [],
        },
    )

    assert captured["video_path"] == "/tmp/s4-final.mp4"
    assert result == {"overall_status": "pass"}


@pytest.mark.asyncio
async def test_s4_seedance_clips_use_prompt_durations():
    captured_durations: list[int] = []

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-generate-skill"
            captured_durations.append(params["duration"])
            index = len(captured_durations)
            return SkillResult(
                success=True,
                data={
                    "video_path": f"/tmp/s4-clip-{index}.mp4",
                    "duration_seconds": params["duration"],
                    "verification": {"all_ok": True},
                },
            )

    result = await S4LiveShootPipeline()._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {
                "prompt": "first scene",
                "duration_seconds": 4,
                "scene_beat": "setup_context",
                "beat_summary": "establish live-shoot scene",
                "transition_intent": "lead into the hands-on usage",
            },
            {
                "prompt": "second scene",
                "duration_seconds": 7,
                "scene_beat": "usage_demo",
                "beat_summary": "capture product use in motion",
                "transition_intent": "carry action into proof detail",
            },
            {
                "prompt": "third scene",
                "duration_seconds": 9,
                "scene_beat": "proof_detail",
                "beat_summary": "close with tactile result shot",
                "transition_intent": "resolve into a grounded finish",
            },
        ],
        product_name="X1 Pump",
        label="s4-duration-test",
        errors=[],
    )

    assert captured_durations == [4, 7, 9]
    assert result["total_duration"] == 20
    assert result["clip_details"][0]["scene_beat"] == "setup_context"
    assert result["clip_details"][1]["beat_summary"] == "capture product use in motion"
    assert result["clip_details"][2]["transition_intent"] == "resolve into a grounded finish"


@pytest.mark.asyncio
async def test_s4_seedance_clips_honor_video_cap_output_dir_and_retries():
    call_log: list[dict[str, Any]] = []

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-generate-skill"
            call_log.append(params)
            return SkillResult(
                success=True,
                data={
                    "video_path": f"/tmp/s4-capped-{params['output_label']}.mp4",
                    "duration_seconds": params["duration"],
                    "verification": {"all_ok": True},
                },
            )

    result = await S4LiveShootPipeline()._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {"prompt": "first scene", "duration_seconds": 4},
            {"prompt": "second scene", "duration_seconds": 7},
        ],
        product_name="X1 Pump",
        label="s4-capped-test",
        errors=[],
        artifact_output_dir="/tmp/s4-pending-review/clips",
        provider_max_retries=0,
        video_job_cap=1,
    )

    assert len(call_log) == 1
    assert call_log[0]["output_dir"] == "/tmp/s4-pending-review/clips"
    assert call_log[0]["provider_max_retries"] == 0
    assert len(result["clip_paths"]) == 1
    assert result["total_duration"] == 4


@pytest.mark.asyncio
async def test_s4_seedance_clips_concurrent_generation():
    """P0-2: S4 clips are generated concurrently with no continuity chain."""
    call_log: list[dict[str, Any]] = []

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "seedance-video-generate-skill"
            call_log.append({"name": name, "params": params})
            return SkillResult(
                success=True,
                data={
                    "video_path": f"/tmp/s4-concurrent-{params['output_label']}.mp4",
                    "duration_seconds": params["duration"],
                    "verification": {"all_ok": True},
                },
            )

    pipeline = S4LiveShootPipeline()
    result = await pipeline._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {"prompt": "first scene", "duration_seconds": 4},
            {"prompt": "second scene", "duration_seconds": 7},
            {"prompt": "third scene", "duration_seconds": 9},
        ],
        product_name="X1 Pump",
        label="s4-concurrent-test",
        errors=[],
    )

    # All 3 clips generated (concurrent, no continuity_frame_path)
    assert len(call_log) == 3
    for call in call_log:
        assert "continuity_frame_path" not in call["params"]

    # clip_details populated correctly with continuity_frame_used=None
    assert len(result["clip_paths"]) == 3
    assert len(result["clip_details"]) == 3
    assert result["clip_details"][0]["continuity_frame_used"] is None
    assert result["total_duration"] == 20


@pytest.mark.asyncio
async def test_s4_continuity_skill_fallback_marks_soft_degraded():
    pipeline = S4LiveShootPipeline()

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "continuity-storyboard-grid"
            return SkillResult(
                success=True,
                data={"clip_groups": [{"clip_index": 1}]},
                metadata={"is_fallback": True, "fallback_reason": "mock_fallback"},
            )

    result = await pipeline._step_continuity_storyboard_grid(
        reg=FakeRegistry(),
        scripts=[{"segments": [{"start_time": 0, "end_time": 5, "visual_description": "demo"}]}],
        product_name="X1 Pump",
        topic="demo topic",
        product_info={},
        brand_guidelines={},
        errors=[],
    )

    assert result["_soft_degraded"] is True
    assert result["_degraded_reason"] == "continuity_skill_fallback"
    assert result["degraded"] is True


@pytest.mark.asyncio
async def test_s4_continuity_threads_topic_brand_and_stock_context():
    pipeline = S4LiveShootPipeline()
    captured: dict[str, Any] = {}

    class FakeRegistry:
        async def execute(self, name, params):
            assert name == "continuity-storyboard-grid"
            captured["params"] = params
            return SkillResult(
                success=True,
                data={
                    "grid_type": "12-grid",
                    "product_name": "X1 Pump",
                    "visual_identity": {},
                    "micro_shots": [],
                    "clip_groups": [{"clip_index": 1, "shot_indices": [1, 2, 3], "duration": 5}],
                },
            )

    await pipeline._step_continuity_storyboard_grid(
        reg=FakeRegistry(),
        scripts=[{
            "segments": [
                {"start_time": 0, "end_time": 5, "visual_description": "Mother uses the pump at her desk."},
            ]
        }],
        product_name="X1 Pump",
        topic="Working mom desk routine",
        product_info={"brand_name": "LactFit", "usps": ["hands-free", "quiet"]},
        brand_guidelines={
            "voice_guidelines": "warm, supportive",
            "values": ["comfort", "confidence"],
            "visual_constraints": "natural window light; authentic work setting",
            "stock_footage_urls": ["https://example.com/stock-a.mp4", "https://example.com/stock-b.mp4"],
        },
        errors=[],
    )

    product_catalog = captured["params"]["product_catalog"]
    assert product_catalog["brand_name"] == "LactFit"
    assert product_catalog["usage_scenario"] == "Working mom desk routine"
    assert product_catalog["usps"] == ["hands-free", "quiet"]
    assert product_catalog["values"] == ["comfort", "confidence"]
    assert product_catalog["voice_guidelines"] == "warm, supportive"
    assert "natural window light" in product_catalog["visual_constraints"]
    assert any("2 approved stock footage" in item for item in product_catalog["visual_constraints"])


def test_s4_fallback_clip_groups_include_topic_and_stock_context():
    groups = S4LiveShootPipeline._s4_fallback_clip_groups(
        shots=[{
            "start_time": 0,
            "end_time": 4,
            "visual": "Close-up of product on desk",
            "text_overlay": "Desk demo",
        }],
        product_name="X1 Pump",
        topic="Working mom desk routine",
        stock_footage_count=2,
    )

    prompt = groups[0]["seedance_prompt"]
    assert "Working mom desk routine" in prompt
    assert "2 approved stock/live reference asset" in prompt


@pytest.mark.asyncio
async def test_scenario_s4_route_passes_enable_media_synthesis_false(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    del isolated_provider_cost_db
    from src.routers import _deps, scenario
    from src.routers._state import S4LiveShootRequest

    captured: dict[str, Any] = {}

    class FakeS4Pipeline:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return {
                "success": True,
                "_execution_completed": True,
                "scenario": "s4_live_shoot",
            }

    monkeypatch.setattr(
        "src.pipeline.s4_live_shoot_pipeline.S4LiveShootPipeline",
        FakeS4Pipeline,
    )
    monkeypatch.setattr(
        scenario,
        "get_auth_context",
        lambda: _deps.AuthContext(
            tenant_id="tenant-a",
            permissions=frozenset({"provider:submit"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id="s4-route-test",
        ),
    )

    response = await scenario.run_s4_live_shoot(
        S4LiveShootRequest(
            footage_assets=[],
            product_info={"name": "Momcozy UV Sterilizer", "brand_name": "Momcozy"},
            topic="kitchen hygiene",
            target_platforms=["tiktok"],
            video_duration=15,
            enable_media_synthesis=False,
        )
    )

    assert response["status"] == "completed_bounded"
    assert response["completion_kind"] == "no_media"
    assert response["request_succeeded"] is True
    assert response["success"] is False
    assert response["full_media_success"] is False
    assert response["publish_allowed"] is False
    assert response["delivery_accepted"] is False
    assert captured["enable_media_synthesis"] is False
    assert captured["video_duration"] == 15
