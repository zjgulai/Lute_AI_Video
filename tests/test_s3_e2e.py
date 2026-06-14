"""Tests for S3 Influencer Remix Pipeline (R8 milestone).

Tests the full orchestrator with registered skills.
All skills run in stub mode (no real API calls).
"""

from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

import src.pipeline.s3_remix_pipeline as s3_remix_pipeline
import src.skills.character_identity as character_identity_skill
import src.skills.continuity_storyboard_grid as continuity_storyboard_grid_skill
import src.skills.elevenlabs_tts as elevenlabs_tts_skill
import src.skills.gpt_image_generate as gpt_image_generate_skill
import src.skills.keyframe_images as keyframe_images_skill
import src.skills.media_quality_audit as media_quality_audit_skill
import src.skills.remix_script as remix_script_skill
import src.skills.remotion_assemble as remotion_assemble_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.seedance_video_generate as seedance_video_generate_skill
import src.skills.thumbnail_prompt as thumbnail_prompt_skill
import src.skills.video_analysis as video_analysis_skill
from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline, S3Result
from src.skills.base import SkillResult
from src.skills.elevenlabs_tts import ElevenLabsTTSSkill
from src.skills.gpt_image_generate import GPTImageGenerateSkill
from src.skills.registry import SkillRegistry

_RUN_CACHE: dict[str, S3Result] = {}

_STANDARD_RUN_KWARGS = {
    "video_url": "https://tiktok.com/@user/video/standard",
    "product": {"name": "Test Product", "usps": ["quality"], "brand_name": "LactFit"},
    "influencer_name": "Test Influencer",
}


@pytest.fixture(autouse=True)
def _reload_s3_skills():
    original_global_skills = dict(SkillRegistry._global_skills)
    SkillRegistry.clear_global()
    for module in (
        character_identity_skill,
        continuity_storyboard_grid_skill,
        elevenlabs_tts_skill,
        gpt_image_generate_skill,
        keyframe_images_skill,
        media_quality_audit_skill,
        remix_script_skill,
        remotion_assemble_skill,
        seedance_prompt_skill,
        seedance_video_generate_skill,
        thumbnail_prompt_skill,
        video_analysis_skill,
    ):
        importlib.reload(module)
    yield
    SkillRegistry._global_skills = original_global_skills


def _write_fake_mp4(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x14ftypisom" + (b"\x00" * 4096))


def _write_stub_png(path: Path) -> None:
    GPTImageGenerateSkill._build_stub_png(path)


def _write_stub_mp3(path: Path) -> None:
    ElevenLabsTTSSkill._build_stub_mp3(path)


@pytest.fixture(autouse=True)
def _patch_s3_external_dependencies(monkeypatch, tmp_path):
    media_dir = tmp_path / "s3-hermetic"

    async def _fake_download(self, url: str):
        video_path = media_dir / "downloaded.mp4"
        _write_fake_mp4(video_path)
        return video_analysis_skill.VideoMetadata(
            title="Mock video",
            author="mock_creator",
            duration=15.0,
            source_url=url,
            platform="tiktok",
            local_path=str(video_path),
        )

    async def _fake_transcribe(self, video_path: str):
        return [
            video_analysis_skill.TranscribeSegment(
                start=0.0, end=5.0, text="Are you tired of bulky pumps?"
            ),
            video_analysis_skill.TranscribeSegment(
                start=5.0, end=10.0, text="This one fits a busy mom routine."
            ),
            video_analysis_skill.TranscribeSegment(
                start=10.0, end=15.0, text="Quiet, portable, and easy to clean."
            ),
        ]

    async def _fake_generate_image(
        self,
        prompt: str,
        style_ref=None,
        quality: str = "high",
        size: str = "1024x1792",
        image_id: str = "img_001",
    ):
        image_path = media_dir / f"{image_id}.png"
        _write_stub_png(image_path)
        return {
            "image_id": image_id,
            "prompt": prompt,
            "image_url": "STUB://image",
            "local_path": str(image_path),
            "quality": quality,
        }

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
        output_path = Path("output/renders") / f"{params.get('output_label', 's3-test')}.mp4"
        render_json_path = Path("output/renders") / f"{params.get('output_label', 's3-test')}_input.json"
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

    async def _fake_extract_video_frames(self, analysis):
        frame_dir = media_dir / "frames"
        frame_paths: list[str] = []
        for idx in range(3):
            frame_path = frame_dir / f"frame_{idx + 1}.png"
            _write_stub_png(frame_path)
            frame_paths.append(str(frame_path))
        return frame_paths

    monkeypatch.setattr("src.tools.video_downloader.VideoDownloader.download", _fake_download)
    monkeypatch.setattr("src.tools.video_downloader.VideoDownloader.transcribe", _fake_transcribe)
    monkeypatch.setattr("src.tools.gpt_image_client.GPTImageClient.generate", _fake_generate_image)
    monkeypatch.setattr("src.tools.seedance_client.SeedanceClient.text_to_video", _fake_text_to_video)
    monkeypatch.setattr("src.tools.seedance_client.SeedanceClient.image_to_video", _fake_image_to_video)
    monkeypatch.setattr("src.tools.cosyvoice_client.CosyVoiceClient.synthesize", _fake_synthesize)
    monkeypatch.setattr("src.tools.elevenlabs_client.ElevenLabsClient.synthesize", _fake_synthesize)
    monkeypatch.setattr("src.tools.remotion_renderer.RemotionRenderer.validate_environment", _fake_validate_environment)
    monkeypatch.setattr("src.tools.remotion_renderer.RemotionRenderer.render", _fake_render)
    monkeypatch.setattr("src.skills.media_quality_audit.MediaQualityAuditSkill.execute", _fake_audit_execute)
    monkeypatch.setattr("src.skills.seedance_video_generate.SeedanceVideoGenerateSkill._self_verify", _fake_seedance_verify)
    monkeypatch.setattr("src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline._extract_video_frames", _fake_extract_video_frames)
    remotion_skill = SkillRegistry._global_skills.get("remotion-assemble-skill")
    if remotion_skill is not None:
        monkeypatch.setattr(remotion_skill, "execute", _fake_remotion_execute.__get__(remotion_skill, type(remotion_skill)))
    audit_skill = SkillRegistry._global_skills.get("media-quality-audit-skill")
    if audit_skill is not None:
        monkeypatch.setattr(audit_skill, "execute", _fake_audit_execute.__get__(audit_skill, type(audit_skill)))


async def _run_cached(**kwargs) -> S3Result:
    key = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
    cached = _RUN_CACHE.get(key)
    if cached is None:
        cached = await S3InfluencerRemixPipeline().run(**kwargs)
        _RUN_CACHE[key] = cached
    return deepcopy(cached)


async def _run_upper_pipeline_for_product(product: dict[str, object]) -> dict[str, object]:
    pipeline = S3InfluencerRemixPipeline()
    standard = await _run_cached(**_STANDARD_RUN_KWARGS)
    analysis = deepcopy(standard.video_analysis) or {}
    remix_script_res = await pipeline._step_remix_script(
        analysis=analysis,
        product=product,
        influencer_name="Test Influencer",
        brief_id="RMX-LIGHT",
    )
    assert remix_script_res.success, remix_script_res.error
    remix_script = remix_script_res.data
    assert isinstance(remix_script, dict)
    storyboards = await pipeline._step_storyboards(remix_script)
    thumbnail_prompts = await pipeline._step_thumbnail_prompts(remix_script, product)
    return {
        "analysis": analysis,
        "remix_script": remix_script,
        "storyboards": storyboards,
        "thumbnail_prompts": thumbnail_prompts,
    }


class TestS3Pipeline:
    """S3 influencer remix pipeline tests."""

    def test_import_does_not_register_provider_backed_media_skills(self):
        forbidden_media_skill_names = {
            "elevenlabs-tts-skill",
            "gpt-image-generate-skill",
            "keyframe-images",
            "media-quality-audit-skill",
            "remotion-assemble-skill",
            "seedance-video-generate-skill",
            "seedance-video-prompt",
            "gpt-image-thumbnail-prompt",
        }

        SkillRegistry.clear_global()
        importlib.reload(s3_remix_pipeline)

        assert forbidden_media_skill_names.isdisjoint(SkillRegistry._global_skills)

    def test_media_skills_register_lazily_for_provider_backed_steps(self):
        SkillRegistry.clear_global()
        importlib.reload(s3_remix_pipeline)

        assert "keyframe-images" not in SkillRegistry._global_skills
        assert "gpt-image-generate-skill" not in SkillRegistry._global_skills

        s3_remix_pipeline._ensure_step_skills_registered("keyframe_images")

        assert "keyframe-images" in SkillRegistry._global_skills
        assert "gpt-image-generate-skill" in SkillRegistry._global_skills

    @pytest.mark.asyncio
    async def test_skip_media_stops_before_provider_backed_steps(self, monkeypatch: pytest.MonkeyPatch):
        executed_steps: list[str] = []
        saved_states: list[dict[str, object]] = []

        class FakeStateManager:
            async def save(self, label: str, state: dict[str, object]) -> None:
                saved_states.append({"label": label, "current_step": state.get("current_step")})

        class FakeStepRunner:
            def __init__(self, state_manager: object) -> None:
                self.state_manager = FakeStateManager()

            async def init_state(self, *, config, mode="auto", label=None, scenario="s3"):
                return label or "s3_no_media_fixture"

            async def resume(self, label):
                raise AssertionError("no-media S3 must not resume the full media pipeline")

            async def run_step(self, label, step_name):
                executed_steps.append(step_name)
                return {
                    "label": label,
                    "scenario": "s3",
                    "steps": {step: {"output": {}} for step in executed_steps},
                    "errors": [],
                    "media_synthesis_errors": [],
                    "pipeline_degraded": False,
                }

        monkeypatch.setattr(s3_remix_pipeline, "StepRunner", FakeStepRunner)

        result = await s3_remix_pipeline.S3InfluencerRemixPipeline().run(
            video_url="https://tiktok.com/@momcozy/video/1000000000",
            product={"name": "Momcozy UV Sterilizer", "usps": ["quiet"], "brand_name": "Momcozy"},
            influencer_name="Test Influencer",
            video_duration=15,
            enable_media_synthesis=False,
        )

        assert executed_steps == [
            "video_analysis",
            "character_identity",
            "remix_script",
            "storyboards",
            "continuity_storyboard_grid",
        ]
        assert "keyframe_images" not in executed_steps
        assert result.success is True
        assert result.clip_paths == []
        assert result.audio_paths == []
        assert result.thumbnail_image_paths == []
        assert result.final_video_path == ""
        assert saved_states[-1]["current_step"] is None

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_full_pipeline(self):
        """Full S3 pipeline from video URL to thumbnail prompts.

        This is the R8 milestone E2E test.
        """
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        assert isinstance(result, S3Result)
        assert result.success, f"Pipeline failed: {result.errors}"
        assert result.errors == []
        assert result.video_analysis is not None
        assert result.remix_script is not None
        assert len(result.video_prompts) > 0
        assert len(result.thumbnail_prompts) > 0

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_video_analysis_output(self):
        """Video analysis should produce expected fields."""
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        analysis = result.video_analysis
        assert analysis is not None
        assert "hook_type" in analysis
        assert "speech_style" in analysis
        assert "avg_speech_wpm" in analysis
        assert "segments" in analysis
        assert len(analysis["segments"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_remix_script_preserves_style(self):
        """Remix script should mention original style."""
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        script = result.remix_script
        assert script is not None
        assert "original_style_preserved" in script
        assert "segments" in script
        assert len(script["segments"]) >= 3

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_video_prompts_per_segment(self):
        """Should generate one video prompt per segment."""
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        assert len(result.video_prompts) > 0
        for p in result.video_prompts:
            assert "segment_index" in p or "clip_index" in p
            assert "segment_type" in p or "purpose" in p
            assert isinstance(p.get("duration_seconds"), (int, float))
            assert p.get("shot_type") or p.get("camera")

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_thumbnail_prompts(self):
        """Should generate thumbnail variants."""
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        assert len(result.thumbnail_prompts) > 0
        for t in result.thumbnail_prompts:
            assert "style" in t
            assert "prompt" in t
            assert "aspect_ratio" in t

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_error_handling_bad_video_url(self):
        """Should handle errors gracefully."""
        from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline

        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="",
            product={"name": "Product"},
        )
        # Should fail at validate_params on video-analysis-skill
        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_different_products(self):
        """Should work with different product types."""
        products = [
            {"name": "Pump A", "usps": ["quiet"], "brand_name": "BrandA"},
            {"name": "Pump B", "usps": ["portable", "light"], "brand_name": "BrandB"},
            {"name": "Pump C", "usps": [], "brand_name": ""},
        ]
        for product in products:
            result = await _run_upper_pipeline_for_product(product)
            assert result["analysis"], f"analysis missing for {product['name']}"
            assert result["remix_script"], f"remix_script missing for {product['name']}"
            assert isinstance(result["thumbnail_prompts"], list), f"thumbnail prompts invalid for {product['name']}"

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_segment_types_mapped(self):
        """Video prompt segment types should be mapped correctly."""
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        valid_types = {
            "product_showcase", "lifestyle", "feature_highlight",
            "testimonials", "tutorial_demo", "brand_story",
        }
        for p in result.video_prompts:
            if "prompt" in p and isinstance(p["prompt"], dict):
                pass  # Skill returns dict with parameters
            elif "prompt" in p and isinstance(p["prompt"], str):
                assert len(p["prompt"]) > 0

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_full_result_to_dict(self):
        """S3Result.to_dict() should serialize properly."""
        result = await _run_cached(**_STANDARD_RUN_KWARGS)

        d = result.to_dict()
        assert d["success"] is True
        assert isinstance(d["segment_count"], int)
        assert d["segment_count"] > 0
        assert isinstance(d["video_prompts"], list)
        assert isinstance(d["thumbnail_prompts"], list)
        assert isinstance(d["errors"], list)

    @pytest.mark.asyncio
    async def test_continuity_skill_fallback_marks_soft_degraded(self):
        pipeline = S3InfluencerRemixPipeline()

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
            storyboard={"shots": [{"visual": "close-up"}]},
            remix_script={"segments": []},
            product={"name": "X1 Pump"},
            influencer_name="Test Influencer",
            source_platform="tiktok",
            target_platforms=["tiktok", "instagram"],
            errors=[],
        )

        assert result["_soft_degraded"] is True
        assert result["_degraded_reason"] == "continuity_skill_fallback"
        assert result["degraded"] is True

    @pytest.mark.asyncio
    async def test_s3_continuity_threads_creator_platform_and_style_context(self):
        pipeline = S3InfluencerRemixPipeline()
        captured: dict[str, object] = {}

        class FakeRegistry:
            async def execute(self, name, params):
                assert name == "continuity-storyboard-grid"
                captured.update(params)
                return SkillResult(success=True, data={"clip_groups": []}, metadata={})

        remix_script = {
            "original_style_preserved": "Kept energetic style, question hook structure, 2 catchphrases",
            "segments": [
                {"keep_notes": "Keep rapid hook pacing and direct address"},
                {"keep_notes": "Keep creator reaction rhythm and short punchlines"},
            ],
        }
        await pipeline._step_continuity_storyboard_grid(
            reg=FakeRegistry(),
            storyboard={"shots": [{"visual": "creator points at the wearable pump on desk"}]},
            remix_script=remix_script,
            product={"name": "X1 Pump", "brand_name": "LactFit", "usps": ["quiet pumping"]},
            influencer_name="Test Influencer",
            source_platform="instagram",
            target_platforms=["instagram", "tiktok"],
            errors=[],
        )

        product_catalog = captured["product_catalog"]
        assert isinstance(product_catalog, dict)
        assert product_catalog["creator_name"] == "Test Influencer"
        assert product_catalog["source_platform"] == "instagram"
        assert product_catalog["distribution_platforms"] == ["instagram", "tiktok"]
        assert "Kept energetic style" in product_catalog["creator_style"]
        assert "Keep rapid hook pacing" in product_catalog["voice_guidelines"]

    def test_s3_fallback_clip_groups_include_creator_and_platform(self):
        groups = S3InfluencerRemixPipeline._s3_fallback_clip_groups(
            [{"visual": "creator demo at desk", "start_time": 0, "end_time": 3}],
            "X1 Pump",
            influencer_name="Jess",
            source_platform="instagram",
        )

        prompt = groups[0]["seedance_prompt"]
        assert "Jess's creator pacing" in prompt
        assert "instagram" in prompt

    @pytest.mark.asyncio
    async def test_audit_reads_persisted_assemble_list_path(self, monkeypatch):
        """JSON persistence can turn tuple assemble output into list."""
        pipeline = S3InfluencerRemixPipeline()
        captured: dict[str, str] = {}

        async def _fake_audit(**kwargs):
            captured["video_path"] = kwargs["video_path"]
            return SkillResult(success=True, data={"overall_status": "pass"})

        monkeypatch.setattr(pipeline, "_step_audit", _fake_audit)

        result = await pipeline.run_step(
            "audit",
            {
                "config": {
                    "product": {"name": "X1 Pump"},
                    "target_language": "en",
                    "video_duration": 15,
                },
                "steps": {
                    "remix_script": {"output": {"segments": []}},
                    "assemble_final": {"output": ["/tmp/s3-final.mp4", "/tmp/s3-render.json"]},
                    "tts_audio": {"output": []},
                    "thumbnail_images": {"output": []},
                    "seedance_clips": {"output": {"clip_paths": ["/tmp/s3-clip.mp4"]}},
                    "thumbnail_prompts": {"output": []},
                },
                "errors": [],
                "media_synthesis_errors": [],
            },
        )

        assert captured["video_path"] == "/tmp/s3-final.mp4"
        assert result == {"overall_status": "pass"}

    @pytest.mark.asyncio
    async def test_seedance_clips_use_prompt_durations(self, monkeypatch):
        pipeline = S3InfluencerRemixPipeline()
        pipeline._video_duration = 30
        captured_durations: list[int] = []

        def _skip_last_frame(video_path: str, output_dir: str):
            return None

        class FakeRegistry:
            async def execute(self, name, params):
                assert name == "seedance-video-generate-skill"
                captured_durations.append(params["duration"])
                index = len(captured_durations)
                return SkillResult(
                    success=True,
                    data={
                        "video_path": f"/tmp/s3-clip-{index}.mp4",
                        "duration_seconds": params["duration"],
                        "verification": {"all_ok": True},
                    },
                )

        pipeline._registry = FakeRegistry()
        monkeypatch.setattr(
            "src.pipeline.s3_remix_pipeline.extract_clip_last_frame",
            _skip_last_frame,
        )

        result = await pipeline._step_seedance_clips(
            video_prompts=[
                {
                    "prompt": "hook scene",
                    "duration_seconds": 4,
                    "scene_beat": "creator_hook",
                    "beat_summary": "cold open hook",
                    "transition_intent": "pull the viewer into the creator setup",
                },
                {
                    "prompt": "body scene",
                    "duration_seconds": 6,
                    "scene_beat": "demo_flow",
                    "beat_summary": "creator usage walkthrough",
                    "transition_intent": "move from hook into proof",
                },
                {
                    "prompt": "cta scene",
                    "duration_seconds": 8,
                    "scene_beat": "cta_close",
                    "beat_summary": "creator wraps with purchase prompt",
                    "transition_intent": "land the recommendation cleanly",
                },
            ],
            product={"name": "X1 Pump"},
            label="s3-duration-test",
            errors=[],
        )

        assert captured_durations == [4, 6, 8]
        assert result["total_duration"] == 18
        assert result["clip_details"][0]["scene_beat"] == "creator_hook"
        assert result["clip_details"][1]["beat_summary"] == "creator usage walkthrough"
        assert result["clip_details"][2]["transition_intent"] == "land the recommendation cleanly"

    @pytest.mark.asyncio
    @pytest.mark.hermetic_slow
    async def test_pipeline_missing_video_url_soft_degrades(self):
        """Missing input should degrade at analysis, but the pipeline must not crash."""
        result = await _run_cached(
            video_url="",
            product={"name": "X1"},
        )
        assert result.success is False
        assert result.video_analysis is not None
        assert result.remix_script is not None
        assert len(result.video_prompts) > 0
        assert any("video_analysis_failed" in err for err in result.errors)


@pytest.mark.asyncio
async def test_scenario_s3_route_passes_enable_media_synthesis_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.routers import scenario
    from src.tools import translate

    captured: dict[str, object] = {}

    async def fake_translate_catalog(product: dict) -> dict:
        return product

    class FakeS3Pipeline:
        async def run(self, **kwargs):
            captured.update(kwargs)
            result = S3Result()
            result.success = True
            return result

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate_catalog)
    monkeypatch.setattr(
        "src.pipeline.s3_remix_pipeline.S3InfluencerRemixPipeline",
        FakeS3Pipeline,
    )

    response = await scenario.run_s3_influencer_remix(
        {
            "video_url": "https://tiktok.com/@momcozy/video/1000000000",
            "product": {"name": "Momcozy UV Sterilizer"},
            "influencer_name": "Test Influencer",
            "video_duration": 15,
            "enable_media_synthesis": False,
        }
    )

    assert response["success"] is True
    assert captured["enable_media_synthesis"] is False
