"""S5 Brand VLOG E2E integration test.

Verifies the S5 (Brand VLOG) scenario end-to-end using StepRunner:
1. vlog_strategy generates shot list via LLM
2. seedance-video-prompt generates video prompts
3. seedance-video-generate produces clips
4. tts_audio generates voiceover
5. remotion-assemble produces final video
6. audit runs quality check

Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import src.skills.elevenlabs_tts as elevenlabs_tts_skill
import src.skills.media_quality_audit as media_quality_audit_skill
import src.skills.remotion_assemble as remotion_assemble_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.seedance_video_generate as seedance_video_generate_skill
from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
from src.skills.base import SkillResult
from src.skills.elevenlabs_tts import ElevenLabsTTSSkill
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    original_global_skills = dict(SkillRegistry._global_skills)
    SkillRegistry.clear_global()
    for module in (
        elevenlabs_tts_skill,
        media_quality_audit_skill,
        remotion_assemble_skill,
        seedance_prompt_skill,
        seedance_video_generate_skill,
    ):
        importlib.reload(module)
    yield
    SkillRegistry._global_skills = original_global_skills


def _write_fake_mp4(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x14ftypisom" + (b"\x00" * 4096))


def _write_stub_mp3(path: Path) -> None:
    ElevenLabsTTSSkill._build_stub_mp3(path)


@pytest.fixture(autouse=True)
def _patch_s5_external_dependencies(monkeypatch, tmp_path):
    media_dir = tmp_path / "s5-hermetic"

    async def _fake_invoke_json(self, system_prompt: str, user_prompt: str):
        return [
            {
                "shot_type": "close-up",
                "duration_seconds": 3,
                "visual_description": "Front view close-up in soft daylight",
                "voiceover": "轻松开启一天的节奏。",
                "product_angle": "主视图",
                "model_in_shot": "",
            },
            {
                "shot_type": "mid-shot",
                "duration_seconds": 6,
                "visual_description": "Hands using the product in a calm home scene",
                "voiceover": "忙碌时也能保持从容。",
                "product_angle": "佩戴图",
                "model_in_shot": "Sarah",
            },
            {
                "shot_type": "static beauty",
                "duration_seconds": 6,
                "visual_description": "Clean package beauty shot with soft shadows",
                "voiceover": "为真实生活准备的舒适选择。",
                "product_angle": "包装图",
                "model_in_shot": "",
            },
        ]

    async def _fake_text_to_video(
        self,
        prompt: str,
        image_refs=None,
        duration: int = 10,
        resolution: str = "720p",
        model=None,
    ):
        clip_path = media_dir / f"clip_{abs(hash((prompt, duration))) & 0xFFFF:04x}.mp4"
        _write_fake_mp4(clip_path)
        return {
            "video_url": "https://example.invalid/mock.mp4",
            "local_path": str(clip_path),
            "duration": duration,
        }

    async def _fake_image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        duration: int = 10,
        style_preserve: bool = True,
        model=None,
    ):
        return await _fake_text_to_video(self, prompt=prompt or image_url, duration=duration, model=model)

    async def _fake_synthesize(self, text: str, **kwargs):
        audio_path = media_dir / f"audio_{abs(hash(text)) & 0xFFFF:04x}.mp3"
        _write_stub_mp3(audio_path)
        return audio_path

    async def _fake_remotion_execute(self, params):
        output_path = Path("output/renders") / f"{params.get('output_label', 's5-test')}.mp4"
        render_json_path = Path("output/renders") / f"{params.get('output_label', 's5-test')}_input.json"
        _write_fake_mp4(output_path)
        render_json_path.parent.mkdir(parents=True, exist_ok=True)
        render_json_path.write_text("{}", encoding="utf-8")
        return SkillResult(
            success=True,
            data={
                "video_path": str(output_path),
                "render_json_path": str(render_json_path),
                "duration_seconds": float(params.get("total_duration", 15)),
                "file_size_bytes": output_path.stat().st_size,
                "resolution": "1080x1920",
                "fps": 30,
                "shot_count": len(params.get("shots") or []),
                "is_stub": False,
                "verification": {"all_ok": True},
            },
        )

    def _fake_validate_environment(self):
        return {"available": True, "issues": []}

    def _fake_render(self, input_json, output_filename, blocking=True, composition_id=None):
        output_path = Path(input_json).parent / output_filename
        _write_fake_mp4(output_path)
        return output_path

    async def _fake_audit_execute(self, params):
        return SkillResult(
            success=True,
            data={
                "overall_status": "PASS",
                "overall_score": 1.0,
                "criteria": [],
                "summary": "mock pass",
            },
        )

    def _fake_seedance_verify(self, local_path, is_stub):
        return {
            "file_exists": True,
            "size_ok": True,
            "header_ok": True,
            "duration_ok": True,
            "resolution_ok": True,
            "variance_ok": True,
            "variance_details": None,
            "dimensions": (720, 1280),
            "all_ok": True,
            "failures": [],
            "mode": "real" if not is_stub else "stub_relaxed",
        }

    monkeypatch.setattr("src.tools.llm_client.LLMClient.invoke_json", _fake_invoke_json)
    monkeypatch.setattr("src.tools.seedance_client.SeedanceClient.text_to_video", _fake_text_to_video)
    monkeypatch.setattr("src.tools.seedance_client.SeedanceClient.image_to_video", _fake_image_to_video)
    monkeypatch.setattr("src.tools.cosyvoice_client.CosyVoiceClient.synthesize", _fake_synthesize)
    monkeypatch.setattr("src.tools.elevenlabs_client.ElevenLabsClient.synthesize", _fake_synthesize)
    monkeypatch.setattr("src.tools.remotion_renderer.RemotionRenderer.validate_environment", _fake_validate_environment)
    monkeypatch.setattr("src.tools.remotion_renderer.RemotionRenderer.render", _fake_render)
    monkeypatch.setattr("src.skills.media_quality_audit.MediaQualityAuditSkill.execute", _fake_audit_execute)
    monkeypatch.setattr("src.skills.seedance_video_generate.SeedanceVideoGenerateSkill._self_verify", _fake_seedance_verify)
    remotion_skill = SkillRegistry._global_skills.get("remotion-assemble-skill")
    if remotion_skill is not None:
        monkeypatch.setattr(remotion_skill, "execute", _fake_remotion_execute.__get__(remotion_skill, type(remotion_skill)))
    audit_skill = SkillRegistry._global_skills.get("media-quality-audit-skill")
    if audit_skill is not None:
        monkeypatch.setattr(audit_skill, "execute", _fake_audit_execute.__get__(audit_skill, type(audit_skill)))


PRODUCT_SKU_FIXTURE = {
    "name": "LactFit Wearable Breast Pump X1",
    "shortName": "X1 Pump",
    "views": [
        {"label": "主视图", "title": "Front View", "usage_note": "Hero shot"},
        {"label": "45度视图", "title": "Angle View", "usage_note": "Detail shot"},
        {"label": "侧视图", "title": "Side View", "usage_note": "Profile"},
        {"label": "底视图", "title": "Bottom View", "usage_note": "Base detail"},
        {"label": "佩戴图", "title": "Worn View", "usage_note": "In-use shot"},
        {"label": "包装图", "title": "Package View", "usage_note": "Box shot"},
    ],
}

SELECTED_MODELS_FIXTURE = [
    {"name": "Sarah", "role": "new mom", "description": "28yo, first-time mother"},
]


@pytest.mark.asyncio
async def test_s5_full_pipeline_mock():
    """S5 full run() returns expected output shape in mock mode."""
    pipeline = S5BrandVlogPipeline()
    result = await pipeline.run(
        brand_id="lactfit",
        product_sku=PRODUCT_SKU_FIXTURE,
        scene_id="living-room",
        selected_models=SELECTED_MODELS_FIXTURE,
        story_description="A day in the life of a working mom",
        video_duration=30,
    )

    # In mock mode clips may be stubs — check structure, not media existence
    assert result.get("success") is not None
    assert result.get("scenario") == "brand_vlog"
    assert isinstance(result.get("scripts"), list)
    assert isinstance(result.get("video_prompts"), list)
    assert isinstance(result.get("clip_paths"), list)
    assert isinstance(result.get("audio_paths"), list)
    assert result.get("errors") == []


@pytest.mark.asyncio
@pytest.mark.hermetic_slow
async def test_s5_step_runner_init_and_resume():
    """S5 via StepRunner: init_state + resume produces valid state."""
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner

    config = {
        "brand_id": "lactfit",
        "product_sku": PRODUCT_SKU_FIXTURE,
        "scene_id": "living-room",
        "selected_models": SELECTED_MODELS_FIXTURE,
        "story_description": "Test story",
        "video_duration": 15,
        "product_name": "X1 Pump",
        "output_label": "vlog_test",
    }

    runner = StepRunner(PipelineStateManager())
    label = await runner.init_state(config=config, mode="auto", scenario="s5")
    assert label.startswith("s5_")

    final_state = await runner.resume(label)
    assert final_state.get("scenario") == "s5"
    steps = final_state.get("steps", {})
    assert "vlog_strategy" in steps
    assert "video_prompts" in steps
    assert "seedance_clips" in steps
    assert "tts_audio" in steps

    # In mock mode all steps should complete quickly
    for step_name in ["vlog_strategy", "video_prompts", "seedance_clips", "tts_audio", "assemble_final", "audit"]:
        step_data = steps.get(step_name, {})
        assert step_data.get("status") in ("done", "pending"), f"Step {step_name} unexpected status"
    assert final_state.get("errors") == []


@pytest.mark.asyncio
async def test_s5_audit_reads_persisted_assemble_list_path(monkeypatch):
    pipeline = S5BrandVlogPipeline()
    captured: dict[str, str] = {}

    async def _fake_audit(reg, video_path, audio_paths, thumbnail_paths, clip_paths, clip_details, errors, continuity_grid=None):
        captured["video_path"] = video_path
        return {"overall_status": "pass"}

    monkeypatch.setattr(pipeline, "_step_audit", _fake_audit)

    result = await pipeline.run_step(
        "audit",
        {
            "config": {
                "product_name": "X1 Pump",
                "video_duration": 15,
            },
            "steps": {
                "assemble_final": {"output": ["/tmp/s5-final.mp4", "/tmp/s5-render.json"]},
                "tts_audio": {"output": ["/tmp/s5.mp3"]},
                "seedance_clips": {
                    "output": {
                        "clip_paths": ["/tmp/s5-clip.mp4"],
                        "clip_details": [{"is_stub": False}],
                    },
                },
            },
            "errors": [],
        },
    )

    assert captured["video_path"] == "/tmp/s5-final.mp4"
    assert result == {"overall_status": "pass"}


@pytest.mark.asyncio
async def test_s5_run_preserves_persisted_assemble_list_paths(monkeypatch):
    class FakeRunner:
        def __init__(self, state_manager):
            pass

        async def init_state(self, *, config, mode, label, scenario):
            return label

        async def resume(self, label):
            return {
                "steps": {
                    "vlog_strategy": {"output": {"scripts": []}},
                    "video_prompts": {"output": []},
                    "seedance_clips": {
                        "output": {
                            "clip_paths": ["/tmp/s5-clip.mp4"],
                            "clip_details": [{"is_stub": False}],
                        },
                    },
                    "tts_audio": {"output": ["/tmp/s5.mp3"]},
                    "assemble_final": {"output": ["/tmp/s5-final.mp4", "/tmp/s5-render.json"]},
                    "audit": {"output": {}},
                },
                "errors": [],
            }

    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeRunner)

    result = await S5BrandVlogPipeline().run(
        brand_id="lactfit",
        product_sku=PRODUCT_SKU_FIXTURE,
        scene_id="living-room",
        selected_models=SELECTED_MODELS_FIXTURE,
        story_description="Test story",
        video_duration=15,
    )

    assert result["final_video_path"] == "/tmp/s5-final.mp4"
    assert result["render_json_path"] == "/tmp/s5-render.json"


@pytest.mark.asyncio
async def test_s5_seedance_clips_preserve_director_intent_metadata():
    pipeline = S5BrandVlogPipeline()

    class FakeRegistry:
        async def execute(self, name, params):
            if name == "seedance-video-generate-skill":
                return SkillResult(
                    success=True,
                    data={
                        "video_path": f"/tmp/{params['output_label']}.mp4",
                        "duration_seconds": params["duration"],
                        "file_size_bytes": 2048,
                        "verification": {"all_ok": True},
                        "is_stub": False,
                    },
                )
            assert name == "video-continuity-manager-skill"
            return SkillResult(success=True, data={"continuity_frame_path": None})

    result = await pipeline._step_seedance_clips(
        reg=FakeRegistry(),
        video_prompts=[
            {
                "segment_prompt": "opening scene",
                "duration_seconds": 4,
                "scene_beat": "vlog_intro",
                "beat_summary": "hero open in the living room",
                "transition_intent": "ease into the day-in-the-life setup",
                "product_angle": "主视图",
                "shot_type": "close-up",
            },
            {
                "segment_prompt": "usage scene",
                "duration_seconds": 6,
                "scene_beat": "lived_in_demo",
                "beat_summary": "hands-on usage with Sarah",
                "transition_intent": "carry the story toward practical proof",
                "product_angle": "佩戴图",
                "shot_type": "mid-shot",
                "model_in_shot": "Sarah",
            },
        ],
        product_name="X1 Pump",
        label="s5-director-intent",
        errors=[],
        video_duration=10,
    )

    assert result["clip_details"][0]["scene_beat"] == "vlog_intro"
    assert result["clip_details"][0]["beat_summary"] == "hero open in the living room"
    assert result["clip_details"][0]["transition_intent"] == "ease into the day-in-the-life setup"
    assert result["clip_details"][1]["scene_beat"] == "lived_in_demo"
    assert result["clip_details"][1]["beat_summary"] == "hands-on usage with Sarah"
    assert result["clip_details"][1]["transition_intent"] == "carry the story toward practical proof"


def test_s5_clip_groups_preserve_angle_model_and_shot_type():
    result = S5BrandVlogPipeline._vlog_shots_to_clip_groups(
        [
            {
                "shot_type": "close-up",
                "duration_seconds": 3,
                "visual": "Front view close-up in soft daylight",
                "product_angle": "主视图",
                "model_in_shot": "Sarah",
            },
            {
                "shot_type": "mid-shot",
                "duration_seconds": 5,
                "visual": "Hands using the product in a calm home scene",
                "product_angle": "佩戴图",
                "model_in_shot": "",
            },
        ],
        "LactFit Wearable Breast Pump X1",
        scene_name="客厅",
        scene_desc="轻松陪伴和家庭氛围",
        story_description="A day in the life of a working mom",
        selected_models=SELECTED_MODELS_FIXTURE,
    )

    prompt = result["clip_groups"][0]["seedance_prompt"]
    group = result["clip_groups"][0]
    assert "close-up" in prompt
    assert "主视图" in prompt
    assert "Sarah" in prompt
    assert "佩戴图" in prompt
    assert "客厅" in prompt
    assert "轻松陪伴和家庭氛围" in prompt
    assert "A day in the life of a working mom" in prompt
    assert "new mom" in prompt
    assert group["scene_beat"] == "vlog_intro"
    assert group["beat_summary"] == "close-up / 主视图 / Sarah -> mid-shot / 佩戴图"
    assert group["transition_intent"] == "bridge the opening product introduction into lived-in usage"
    assert "Narrative beat: vlog_intro." in prompt
    assert "Transition intent: bridge the opening product introduction into lived-in usage." in prompt


@pytest.mark.asyncio
async def test_s5_continuity_threads_scene_story_and_persona():
    pipeline = S5BrandVlogPipeline()

    result = await pipeline.run_step(
        "continuity_storyboard_grid",
        {
            "config": {
                "product_name": "X1 Pump",
                "scene_id": "living-room",
                "story_description": "A day in the life of a working mom",
                "selected_models": SELECTED_MODELS_FIXTURE,
            },
            "steps": {
                "vlog_strategy": {
                    "output": {
                        "shots": [
                            {
                                "shot_type": "mid-shot",
                                "duration_seconds": 6,
                                "visual_description": "Hands using the product in a calm home scene",
                                "product_angle": "佩戴图",
                                "model_in_shot": "Sarah",
                            }
                        ]
                    }
                }
            },
            "errors": [],
        },
    )

    identity = result["visual_identity"]
    group = result["clip_groups"][0]
    prompt = group["seedance_prompt"]

    assert identity["location"] == "客厅"
    assert identity["scene_desc"] == "轻松陪伴和家庭氛围"
    assert identity["story_arc"] == "A day in the life of a working mom"
    assert "Sarah" in identity["persona"]
    assert group["scene_beat"] == "vlog_intro"
    assert "mid-shot / 佩戴图 / Sarah" in group["beat_summary"]
    assert group["transition_intent"] == "bridge the opening product introduction into lived-in usage"
    assert "客厅" in prompt
    assert "轻松陪伴和家庭氛围" in prompt
    assert "A day in the life of a working mom" in prompt
    assert "Sarah" in prompt
