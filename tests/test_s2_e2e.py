"""S2 Brand Campaign E2E test (Sprint 2 P2-3).

Verifies the new independent ``S2BrandCampaignPipeline`` (introduced
in Sprint 2 P2-1) end-to-end in mock mode — no real LLM / poyo calls.

Coverage areas (per diagnostic P0-3 requirement):
- run() returns the documented S2 result shape including
  scenario="brand_campaign" and always-populated compliance_reports key
- Brand identity correctly threaded into product_catalog
- Model routing resolves to S2's preferred model (kling-3-0/pro)
- Backwards-compat shim still exposes the class but emits DeprecationWarning
- Extreme inputs: empty brand_package, invalid video_duration, missing
  brand_name
"""

from __future__ import annotations

import importlib
import warnings
from typing import Any

import pytest

import src.skills.brand_compliance as brand_compliance_skill
import src.skills.elevenlabs_tts as elevenlabs_tts_skill
import src.skills.media_quality_audit as media_quality_audit_skill
import src.skills.remotion_assemble as remotion_assemble_skill
import src.skills.script_writer as script_writer_skill
import src.skills.seedance_prompt as seedance_prompt_skill
import src.skills.seedance_video_generate as seedance_video_generate_skill
import src.skills.storyboard as storyboard_skill
from src.pipeline import s2_brand_pipeline_v2
from src.pipeline.s1_product_pipeline import (
    S1ProductDirectPipeline,
    _artifact_media_output_dir,
    _ensure_step_skills_registered,
)
from src.pipeline.s2_brand_pipeline_v2 import (
    S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS,
    S2_SEGMENTED_MEDIA_STEP_ORDERS,
    S2BrandCampaignPipeline,
)
from src.routers._state import S1StartRequest, S2BrandCampaignRequest
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry


@pytest.fixture(autouse=True)
def _clear_registry():
    original_global_skills = dict(SkillRegistry._global_skills)
    SkillRegistry.clear_global()
    for module in (
        brand_compliance_skill,
        elevenlabs_tts_skill,
        media_quality_audit_skill,
        remotion_assemble_skill,
        script_writer_skill,
        seedance_prompt_skill,
        seedance_video_generate_skill,
        storyboard_skill,
    ):
        importlib.reload(module)
    yield
    SkillRegistry._global_skills = original_global_skills


BRAND_PACKAGE_FIXTURE: dict[str, Any] = {
    "brand_name": "MomCozy",
    "values": ["safety", "comfort", "modern motherhood"],
    "voice_guidelines": "warm, supportive, never preachy",
    "visual_constraints": "soft natural light; pastel palette",
    "competitor_context": "competitor X focuses on tech specs only",
}


class TestS2RunContract:
    @pytest.mark.asyncio
    async def test_run_returns_brand_campaign_scenario(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=30,
            enable_media_synthesis=False,
        )
        assert result["scenario"] == "brand_campaign"
        assert result["brand_name"] == "MomCozy"

    @pytest.mark.asyncio
    async def test_compliance_reports_key_always_present(self):
        """Diagnostic R-S2-ARCH: brand_mode compliance path must be observable
        in the result. Even when empty, the key must exist so consumers don't
        need to do .get() with a default."""
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        assert "compliance_reports" in result
        assert isinstance(result["compliance_reports"], list)

    @pytest.mark.asyncio
    async def test_run_routes_to_kling_3_0_pro(self):
        """S2 must route to its preferred model (kling-3-0/pro) per
        ModelRouter Sprint 1 contract — NOT seedance-2 (S1's preferred)."""
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        assert result["model_id"] == "kling-3.0/pro"

    @pytest.mark.asyncio
    async def test_run_brand_package_threaded_through(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        assert result["brand_package"] == BRAND_PACKAGE_FIXTURE


class TestS1BoundedMediaContract:
    def test_s1_request_accepts_bounded_media_controls(self):
        request = S1StartRequest(
            product_catalog={"product_name": "Momcozy Bottle Sterilizer"},
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=0,
            output_label="s1_bounded_media_fixture",
        )

        assert request.artifact_disposition == "pending_review"
        assert request.provider_max_retries == 0
        assert request.output_label == "s1_bounded_media_fixture"

    @pytest.mark.asyncio
    async def test_pending_review_media_pilot_stops_before_tts_and_assemble(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import src.pipeline.s1_product_pipeline as s1_pipeline

        executed_steps: list[str] = []
        saved_states: list[dict[str, Any]] = []

        class FakeStateManager:
            async def save(self, label: str, state: dict[str, Any]) -> None:
                saved_states.append({"label": label, "state": state})

        class FakeStepRunner:
            def __init__(self, state_manager: object) -> None:
                self.state_manager = FakeStateManager()

            async def init_state(self, *, config, mode="auto", label=None, scenario="s1"):
                assert config["artifact_disposition"] == "pending_review"
                assert config["provider_max_retries"] == 0
                assert config["provider_job_caps"] == {"image": 1, "video": 1}
                assert config["seedance_quality_gate_enabled"] is False
                return label or "s1_pending_review_media_pilot_fixture"

            async def resume(self, label):
                raise AssertionError("pending_review S1 media pilot must not resume through assemble_final")

            async def run_step(self, label, step_name):
                executed_steps.append(step_name)
                output: Any = []
                if step_name == "seedance_clips":
                    output = {"clip_paths": ["/tmp/pending_review/s1-clip.mp4"]}
                return {
                    "scenario": "s1",
                    "steps": {step: {"output": []} for step in executed_steps if step != "seedance_clips"}
                    | {"seedance_clips": {"output": output}},
                    "current_step": "tts_audio",
                    "errors": [],
                    "media_synthesis_errors": [],
                    "pipeline_degraded": False,
                }

        monkeypatch.setattr(s1_pipeline, "StepRunner", FakeStepRunner)

        result = await S1ProductDirectPipeline().run(
            product_catalog={"product_name": "Momcozy Bottle Sterilizer"},
            brand_guidelines={"brand_name": "Momcozy"},
            target_platforms=["tiktok"],
            video_duration=15,
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=3,
            output_label="s1_bounded_media_fixture",
        )

        assert executed_steps == [
            "strategy",
            "scripts",
            "storyboards",
            "continuity_storyboard_grid",
            "keyframe_images",
            "video_prompts",
            "seedance_clips",
        ]
        assert "thumbnail_prompts" not in executed_steps
        assert "tts_audio" not in executed_steps
        assert "thumbnail_images" not in executed_steps
        assert "assemble_final" not in executed_steps
        assert "audit" not in executed_steps
        assert result["artifact_disposition"] == "pending_review"
        assert result["artifact_storage_scope"] == "tenant_pending_review"
        assert result["provider_max_retries"] == 0
        assert result["provider_job_caps"] == {"image": 1, "video": 1}
        assert result["bounded_media_pilot"] is True
        assert result["bounded_media_stop_step"] == "seedance_clips"
        assert result["clip_paths"] == ["/tmp/pending_review/s1-clip.mp4"]
        assert result["audio_paths"] == []
        assert result["thumbnail_image_paths"] == []
        assert result["final_video_path"] == ""
        assert result["delivery_accepted"] is False
        assert result["publish_allowed"] is False
        assert result["approved_brand_token_write"] is False
        assert saved_states
        assert saved_states[-1]["state"]["current_step"] is None
        assert saved_states[-1]["state"]["bounded_media_pilot"] is True
        assert saved_states[-1]["state"]["provider_max_retries"] == 0
        assert saved_states[-1]["state"]["provider_job_caps"] == {"image": 1, "video": 1}


class TestS2RunResultShape:
    def test_request_accepts_pending_review_artifact_disposition(self):
        request = S2BrandCampaignRequest(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=0,
            output_label="s2_transport_readback_fixture",
            media_stop_step="tts_audio",
            media_refs={"clip_paths": ["/tmp/tenants/default/pending_review/ref/clip.mp4"]},
        )

        assert request.artifact_disposition == "pending_review"
        assert request.provider_max_retries == 0
        assert request.output_label == "s2_transport_readback_fixture"
        assert request.media_stop_step == "tts_audio"
        assert request.media_refs == {"clip_paths": ["/tmp/tenants/default/pending_review/ref/clip.mp4"]}

    @pytest.mark.asyncio
    async def test_run_uses_explicit_output_label(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
            output_label="s2_explicit_label_fixture",
        )

        assert result["label"] == "s2_explicit_label_fixture"

    @pytest.mark.asyncio
    async def test_skip_media_returns_briefs_only(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )
        for key in [
            "briefs", "scripts", "storyboards", "compliance_reports",
            "errors", "media_synthesis_errors",
        ]:
            assert key in result, f"missing top-level key: {key}"
        assert "final_video_path" not in result

    @pytest.mark.asyncio
    async def test_skip_media_stops_before_provider_backed_steps(self, monkeypatch: pytest.MonkeyPatch):
        executed_steps: list[str] = []

        class FakeStepRunner:
            def __init__(self, state_manager: object) -> None:
                self.state_manager = state_manager

            async def init_state(self, *, config, mode="auto", label=None, scenario="s2"):
                return label or "s2_no_media_fixture"

            async def resume(self, label):
                raise AssertionError("no-media S2 must not resume the full media pipeline")

            async def run_step(self, label, step_name):
                executed_steps.append(step_name)
                return {
                    "scenario": "s2",
                    "steps": {step: {"output": []} for step in executed_steps},
                    "errors": [],
                    "media_synthesis_errors": [],
                }

        monkeypatch.setattr(s2_brand_pipeline_v2, "StepRunner", FakeStepRunner)

        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            enable_media_synthesis=False,
        )

        assert executed_steps == [
            "strategy",
            "scripts",
            "compliance",
            "storyboards",
            "continuity_storyboard_grid",
        ]
        assert "keyframe_images" not in executed_steps
        assert result["keyframe_images"] == []
        assert "final_video_path" not in result

    @pytest.mark.asyncio
    async def test_pending_review_media_pilot_stops_before_tts_and_assemble(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        executed_steps: list[str] = []
        saved_states: list[dict[str, Any]] = []

        class FakeStateManager:
            async def save(self, label: str, state: dict[str, Any]) -> None:
                saved_states.append({"label": label, "state": state})

        class FakeStepRunner:
            def __init__(self, state_manager: object) -> None:
                self.state_manager = FakeStateManager()

            async def init_state(self, *, config, mode="auto", label=None, scenario="s2"):
                assert config["artifact_disposition"] == "pending_review"
                assert config["provider_max_retries"] == 0
                assert config["provider_job_caps"] == {"image": 1, "video": 1}
                assert config["seedance_quality_gate_enabled"] is False
                return label or "s2_pending_review_media_pilot_fixture"

            async def resume(self, label):
                raise AssertionError("pending_review S2 media pilot must not resume through assemble_final")

            async def run_step(self, label, step_name):
                executed_steps.append(step_name)
                output: Any = []
                if step_name == "seedance_clips":
                    output = {"clip_paths": ["/tmp/pending_review/s2-clip.mp4"]}
                return {
                    "scenario": "s2",
                    "steps": {step: {"output": []} for step in executed_steps if step != "seedance_clips"}
                    | {"seedance_clips": {"output": output}},
                    "current_step": "tts_audio",
                    "errors": [],
                    "media_synthesis_errors": [],
                    "pipeline_degraded": False,
                }

        monkeypatch.setattr(s2_brand_pipeline_v2, "StepRunner", FakeStepRunner)

        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=15,
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=3,
        )

        assert executed_steps == [
            "strategy",
            "scripts",
            "compliance",
            "storyboards",
            "continuity_storyboard_grid",
            "keyframe_images",
            "video_prompts",
            "seedance_clips",
        ]
        assert "thumbnail_prompts" not in executed_steps
        assert "tts_audio" not in executed_steps
        assert "thumbnail_images" not in executed_steps
        assert "assemble_final" not in executed_steps
        assert "audit" not in executed_steps
        assert result["artifact_disposition"] == "pending_review"
        assert result["artifact_storage_scope"] == "tenant_pending_review"
        assert result["provider_max_retries"] == 0
        assert result["provider_job_caps"] == {"image": 1, "video": 1}
        assert result["bounded_media_pilot"] is True
        assert result["bounded_media_stop_step"] == "seedance_clips"
        assert result["clip_paths"] == ["/tmp/pending_review/s2-clip.mp4"]
        assert result["audio_paths"] == []
        assert result["final_video_path"] == ""
        assert saved_states
        assert saved_states[-1]["state"]["current_step"] is None
        assert saved_states[-1]["state"]["bounded_media_pilot"] is True
        assert saved_states[-1]["state"]["provider_max_retries"] == 0
        assert saved_states[-1]["state"]["provider_job_caps"] == {"image": 1, "video": 1}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("stop_step", list(S2_SEGMENTED_MEDIA_STEP_ORDERS))
    async def test_segmented_media_stop_points_do_not_cross_boundaries(
        self,
        monkeypatch: pytest.MonkeyPatch,
        stop_step: str,
    ):
        executed_steps: list[str] = []
        saved_states: list[dict[str, Any]] = []
        expected_steps = S2_SEGMENTED_MEDIA_STEP_ORDERS[stop_step]  # type: ignore[index]
        expected_caps = S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS[stop_step]  # type: ignore[index]

        outputs: dict[str, Any] = {
            "strategy": [{"id": "brief-1", "description": "brand campaign brief"}],
            "scripts": [
                {
                    "id": "script-1",
                    "segments": [
                        {
                            "voiceover": "Warm product story",
                            "start_time": 0,
                            "end_time": 3,
                        }
                    ],
                }
            ],
            "compliance": [{"overall_status": "pass"}],
            "storyboards": [{"shots": [{"visual": "brand hero shot"}]}],
            "continuity_storyboard_grid": {
                "status": "refs_only",
                "micro_shots": [{"visual": "brand hero shot"}],
                "clip_groups": [],
            },
            "keyframe_images": [
                {"shots": [{"keyframe_image_path": "/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/keyframes/s2-keyframe.png"}]}
            ],
            "video_prompts": [{"prompt": "safe brand campaign clip"}],
            "seedance_clips": {
                "clip_paths": ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/clips/s2-clip.mp4"],
                "clip_details": [{"duration_seconds": 4, "is_stub": False}],
            },
            "tts_audio": {
                "audio_paths": ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/audio/s2-audio.mp3"],
                "lyrics_paths": ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/audio/s2-audio.txt"],
            },
            "thumbnail_prompts": [{"variants": [{"prompt": "thumbnail prompt"}]}],
            "thumbnail_images": ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/thumbnails/s2-thumbnail.png"],
            "assemble_final": {
                "video_path": "/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/assemble/s2-intermediate.mp4",
                "render_json_path": "/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/assemble/s2-render.json",
            },
            "audit": {"overall_status": "pass", "score": 0.91},
        }

        class FakeStateManager:
            def __init__(self) -> None:
                self.state: dict[str, Any] | None = None

            async def save(self, label: str, state: dict[str, Any]) -> None:
                self.state = state
                saved_states.append({"label": label, "state": state})

            async def load(self, label: str) -> dict[str, Any] | None:
                return self.state

        class FakeStepRunner:
            def __init__(self, state_manager: object) -> None:
                self.state_manager = FakeStateManager()

            async def init_state(self, *, config, mode="auto", label=None, scenario="s2"):
                assert config["artifact_disposition"] == "pending_review"
                assert config["provider_max_retries"] == 0
                assert config["provider_job_caps"] == expected_caps
                assert config["media_stop_step"] == stop_step
                assert config["seedance_quality_gate_enabled"] is False
                if stop_step == "assemble_final":
                    assert config["refs_only_media_assembly"] is True
                    assert config["media_refs"]["clip_paths"] == outputs["seedance_clips"]["clip_paths"]
                if stop_step == "audit":
                    assert config["refs_only_media_audit"] is True
                    assert config["media_refs"]["video_path"] == outputs["assemble_final"]["video_path"]
                test_label = label or "s2_segmented_media_fixture"
                self.state_manager.state = {
                    "label": test_label,
                    "scenario": "s2",
                    "tenant_id": "momcozy-marketing",
                    "config": config,
                    "steps": {
                        step: {"output": None, "status": "pending"}
                        for step in S2_SEGMENTED_MEDIA_STEP_ORDERS["audit"]
                    },
                    "current_step": "strategy",
                    "errors": [],
                    "media_synthesis_errors": [],
                    "pipeline_degraded": False,
                }
                return test_label

            async def resume(self, label):
                raise AssertionError("segmented S2 media pilot must not resume unrestricted pipeline")

            async def run_step(self, label, step_name):
                executed_steps.append(step_name)
                state = await self.state_manager.load(label)
                assert state is not None
                state["steps"][step_name] = {"output": outputs[step_name], "status": "done"}
                state["current_step"] = "downstream_placeholder"
                return state

        monkeypatch.setattr(s2_brand_pipeline_v2, "StepRunner", FakeStepRunner)

        media_refs = None
        if stop_step == "assemble_final":
            media_refs = {
                "clip_paths": outputs["seedance_clips"]["clip_paths"],
                "clip_details": outputs["seedance_clips"]["clip_details"],
                "audio_paths": outputs["tts_audio"]["audio_paths"],
                "lyrics_paths": outputs["tts_audio"]["lyrics_paths"],
                "thumbnail_image_paths": outputs["thumbnail_images"],
            }
        elif stop_step == "audit":
            media_refs = {
                "clip_paths": outputs["seedance_clips"]["clip_paths"],
                "clip_details": outputs["seedance_clips"]["clip_details"],
                "audio_paths": outputs["tts_audio"]["audio_paths"],
                "lyrics_paths": outputs["tts_audio"]["lyrics_paths"],
                "thumbnail_image_paths": outputs["thumbnail_images"],
                "thumbnail_prompts": outputs["thumbnail_prompts"],
                "video_path": outputs["assemble_final"]["video_path"],
                "render_json_path": outputs["assemble_final"]["render_json_path"],
                "scripts": outputs["scripts"],
                "storyboards": outputs["storyboards"],
                "continuity_storyboard_grid": outputs["continuity_storyboard_grid"],
            }

        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=15,
            enable_media_synthesis=True,
            artifact_disposition="pending_review",
            provider_max_retries=3,
            media_stop_step=stop_step,  # type: ignore[arg-type]
            media_refs=media_refs,
        )

        assert executed_steps == expected_steps
        for step_name in set(S2_SEGMENTED_MEDIA_STEP_ORDERS["audit"]) - set(expected_steps):
            assert step_name not in executed_steps
        assert result["artifact_disposition"] == "pending_review"
        assert result["artifact_storage_scope"] == "tenant_pending_review"
        assert result["provider_max_retries"] == 0
        assert result["provider_job_caps"] == expected_caps
        assert result["bounded_media_pilot"] is True
        assert result["bounded_media_stop_step"] == stop_step
        assert result["final_video_path"] == ""
        assert result["render_json_path"] == ""
        assert result["delivery_accepted"] is False
        assert result["publish_allowed"] is False
        assert result["approved_brand_token_write"] is False
        assert result["steps_completed"] == len(expected_steps)

        if stop_step == "seedance_clips":
            assert result["clip_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/clips/s2-clip.mp4"]
            assert result["audio_paths"] == []
            assert result["thumbnail_image_paths"] == []
            assert result["audit_report"] == {}
        elif stop_step == "tts_audio":
            assert result["clip_paths"] == []
            assert result["audio_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/audio/s2-audio.mp3"]
            assert result["thumbnail_image_paths"] == []
            assert result["audit_report"] == {}
        elif stop_step == "thumbnail_prompts":
            assert result["thumbnail_sets"] == [{"variants": [{"prompt": "thumbnail prompt"}]}]
            assert result["clip_paths"] == []
            assert result["audio_paths"] == []
            assert result["thumbnail_image_paths"] == []
            assert result["audit_report"] == {}
        elif stop_step == "thumbnail_images":
            assert result["clip_paths"] == []
            assert result["audio_paths"] == []
            assert result["thumbnail_image_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/thumbnails/s2-thumbnail.png"]
            assert result["audit_report"] == {}
        elif stop_step == "assemble_final":
            assert result["clip_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/clips/s2-clip.mp4"]
            assert result["audio_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/audio/s2-audio.mp3"]
            assert result["thumbnail_image_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/thumbnails/s2-thumbnail.png"]
            assert result["intermediate_video_path"] == "/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/assemble/s2-intermediate.mp4"
            assert result["refs_only_media_assembly"] is True
            assert result["audit_report"] == {}
        elif stop_step == "audit":
            assert result["clip_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/clips/s2-clip.mp4"]
            assert result["audio_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/audio/s2-audio.mp3"]
            assert result["thumbnail_image_paths"] == ["/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/thumbnails/s2-thumbnail.png"]
            assert result["intermediate_video_path"] == "/tmp/tenants/momcozy-marketing/pending_review/s2_segmented_media_fixture/assemble/s2-intermediate.mp4"
            assert result["refs_only_media_audit"] is True
            assert result["audit_report"] == {"overall_status": "pass", "score": 0.91}

        assert saved_states
        assert saved_states[-1]["state"]["current_step"] is None
        assert saved_states[-1]["state"]["bounded_media_stop_step"] == stop_step
        assert saved_states[-1]["state"]["config"]["media_stop_step"] == stop_step
        assert saved_states[-1]["state"]["provider_job_caps"] == expected_caps
        if stop_step == "assemble_final":
            assert saved_states[-1]["state"]["refs_only_media_assembly"] is True
            assert saved_states[-1]["state"]["config"]["refs_only_media_assembly"] is True
            assert saved_states[-1]["state"]["config"]["provider_job_caps"] == {}
        if stop_step == "audit":
            assert saved_states[-1]["state"]["refs_only_media_audit"] is True
            assert saved_states[-1]["state"]["config"]["refs_only_media_audit"] is True
            assert saved_states[-1]["state"]["config"]["provider_job_caps"] == {}
            steps = saved_states[-1]["state"]["steps"]
            assert executed_steps == ["audit"]
            assert steps["continuity_storyboard_grid"]["status"] == "done"
            assert steps["continuity_storyboard_grid"]["output"]["status"] == "refs_only"
            assert steps["assemble_final"]["status"] == "done"
            assert steps["assemble_final"]["output"]["refs_only"] is True
            assert steps.get("keyframe_images", {}).get("status", "pending") == "pending"
            assert steps.get("video_prompts", {}).get("status", "pending") == "pending"

    @pytest.mark.asyncio
    async def test_assemble_segment_requires_refs_only_media_refs(self):
        with pytest.raises(ValueError, match="requires media_refs"):
            await S2BrandCampaignPipeline().run(
                brand_package=BRAND_PACKAGE_FIXTURE,
                video_duration=15,
                enable_media_synthesis=True,
                artifact_disposition="pending_review",
                provider_max_retries=0,
                media_stop_step="assemble_final",
            )

    @pytest.mark.asyncio
    async def test_assemble_segment_rejects_non_review_scoped_refs(self):
        with pytest.raises(ValueError, match="forbidden artifact path"):
            await S2BrandCampaignPipeline().run(
                brand_package=BRAND_PACKAGE_FIXTURE,
                video_duration=15,
                enable_media_synthesis=True,
                artifact_disposition="pending_review",
                provider_max_retries=0,
                media_stop_step="assemble_final",
                media_refs={
                    "clip_paths": ["/app/output/tenants/momcozy-marketing/final_work/clip.mp4"],
                    "audio_paths": [
                        "/app/output/tenants/momcozy-marketing/pending_review/ref/audio.mp3"
                    ],
                    "thumbnail_image_paths": [
                        "/app/output/tenants/momcozy-marketing/pending_review/ref/thumb.png"
                    ],
                },
            )

    @pytest.mark.asyncio
    async def test_audit_segment_requires_refs_only_media_refs(self):
        with pytest.raises(ValueError, match="requires media_refs"):
            await S2BrandCampaignPipeline().run(
                brand_package=BRAND_PACKAGE_FIXTURE,
                video_duration=15,
                enable_media_synthesis=True,
                artifact_disposition="pending_review",
                provider_max_retries=0,
                media_stop_step="audit",
            )

    @pytest.mark.asyncio
    async def test_audit_segment_rejects_non_review_scoped_refs(self):
        with pytest.raises(ValueError, match="forbidden artifact path"):
            await S2BrandCampaignPipeline().run(
                brand_package=BRAND_PACKAGE_FIXTURE,
                video_duration=15,
                enable_media_synthesis=True,
                artifact_disposition="pending_review",
                provider_max_retries=0,
                media_stop_step="audit",
                media_refs={
                    "clip_paths": [
                        "/app/output/tenants/momcozy-marketing/pending_review/ref/clip.mp4"
                    ],
                    "audio_paths": [
                        "/app/output/tenants/momcozy-marketing/pending_review/ref/audio.mp3"
                    ],
                    "thumbnail_image_paths": [
                        "/app/output/tenants/momcozy-marketing/pending_review/ref/thumb.png"
                    ],
                    "video_path": "/app/output/tenants/momcozy-marketing/final_work/ref/final.mp4",
                },
            )

    def test_bounded_seedance_skill_registration_skips_audit_skill(self):
        SkillRegistry.clear_global()

        _ensure_step_skills_registered(
            "seedance_clips",
            {
                "artifact_disposition": "pending_review",
                "seedance_quality_gate_enabled": False,
            },
        )

        assert "seedance-video-generate-skill" in SkillRegistry._global_skills
        assert "media-quality-audit-skill" not in SkillRegistry._global_skills

    def test_pending_review_media_output_dir_is_tenant_scoped(self):
        output_dir = _artifact_media_output_dir(
            state={"tenant_id": "momcozy-marketing", "label": "ignored"},
            config={
                "artifact_disposition": "pending_review",
                "output_label": "s2_bounded_live",
            },
            media_kind="clips",
        )

        assert output_dir is not None
        assert "/tenants/momcozy-marketing/pending_review/s2_bounded_live/clips" in output_dir
        assert "/final_work/" not in output_dir
        assert "/renders/" not in output_dir
        assert "/seedance/" not in output_dir

    @pytest.mark.asyncio
    async def test_keyframe_step_passes_pending_review_output_dir_and_retry_zero(self):
        seen_params: list[dict[str, Any]] = []

        class FakeRegistry:
            async def execute(self, name: str, params: dict[str, Any]) -> SkillResult:
                assert name == "keyframe-images"
                seen_params.append(params)
                return SkillResult(
                    success=True,
                    data={
                        "shots": [
                            {
                                "visual": "safe product frame",
                                "keyframe_image_path": f"{params['output_dir']}/frame.png",
                            }
                        ]
                    },
                )

        result = await S1ProductDirectPipeline()._step_keyframe_images(
            reg=FakeRegistry(),  # type: ignore[arg-type]
            storyboards=[
                {"shots": [{"visual": "safe product frame"}, {"visual": "second frame"}]},
                {"shots": [{"visual": "third frame"}]},
            ],
            errors=[],
            config={"video_duration": 15},
            artifact_output_dir="/tmp/tenants/momcozy-marketing/pending_review/s2_run/keyframes",
            provider_max_retries=0,
            image_job_cap=1,
        )

        assert result[0]["shots"][0]["keyframe_image_path"].endswith("/keyframes/frame.png")
        assert len(result) == 1
        assert seen_params[0]["output_dir"].endswith("/pending_review/s2_run/keyframes")
        assert seen_params[0]["provider_max_retries"] == 0
        assert seen_params[0]["_max_shots"] == 1

    @pytest.mark.asyncio
    async def test_seedance_step_passes_pending_review_output_dir_retry_zero_and_hard_cap(self):
        seen_params: list[dict[str, Any]] = []

        class FakeRegistry:
            async def execute(self, name: str, params: dict[str, Any]) -> SkillResult:
                if name == "media-quality-audit-skill":
                    raise AssertionError("bounded S2 media pilot must not execute media quality audit")
                assert name == "seedance-video-generate-skill"
                seen_params.append(params)
                return SkillResult(
                    success=True,
                    data={
                        "video_path": f"{params['output_dir']}/clip.mp4",
                        "duration_seconds": 15,
                        "file_size_bytes": 2_000_000,
                        "is_stub": False,
                        "verification": {"all_ok": True},
                    },
                )

        result = await S1ProductDirectPipeline()._step_seedance_clips(
            reg=FakeRegistry(),  # type: ignore[arg-type]
            video_prompts=[
                {"prompt": "safe product demo", "duration_seconds": 4},
                {"prompt": "second product demo", "duration_seconds": 4},
            ],
            product_name="Momcozy bottle sterilizer",
            label="s2_run",
            errors=[],
            video_duration=15,
            keyframe_images=[],
            artifact_output_dir="/tmp/tenants/momcozy-marketing/pending_review/s2_run/clips",
            provider_max_retries=0,
            video_job_cap=1,
            quality_gate_enabled=False,
        )

        assert result["clip_paths"] == [
            "/tmp/tenants/momcozy-marketing/pending_review/s2_run/clips/clip.mp4"
        ]
        assert len(seen_params) == 1
        assert seen_params[0]["output_dir"].endswith("/pending_review/s2_run/clips")
        assert seen_params[0]["provider_max_retries"] == 0

    @pytest.mark.asyncio
    async def test_tts_step_passes_pending_review_output_dir_retry_zero_and_hard_cap(self):
        seen_params: list[dict[str, Any]] = []

        class FakeRegistry:
            async def execute(self, name: str, params: dict[str, Any]) -> SkillResult:
                assert name == "elevenlabs-tts-skill"
                seen_params.append(params)
                return SkillResult(
                    success=True,
                    data={
                        "audio_path": f"{params['output_dir']}/audio.mp3",
                        "lyrics_path": f"{params['output_dir']}/audio.txt",
                        "verification": {"all_ok": True},
                    },
                )

        result = await S1ProductDirectPipeline()._step_tts_audio(
            reg=FakeRegistry(),  # type: ignore[arg-type]
            scripts=[
                {"id": "script-1", "segments": [{"voiceover": "first voiceover"}]},
                {"id": "script-2", "segments": [{"voiceover": "second voiceover"}]},
            ],
            language="en",
            errors=[],
            artifact_output_dir="/tmp/tenants/momcozy-marketing/pending_review/s2_run/audio",
            provider_max_retries=0,
            tts_job_cap=1,
        )

        assert result["audio_paths"] == [
            "/tmp/tenants/momcozy-marketing/pending_review/s2_run/audio/audio.mp3"
        ]
        assert len(seen_params) == 1
        assert seen_params[0]["output_dir"].endswith("/pending_review/s2_run/audio")
        assert seen_params[0]["provider_max_retries"] == 0

    @pytest.mark.asyncio
    async def test_thumbnail_step_passes_pending_review_output_dir_retry_zero_and_hard_cap(self):
        seen_params: list[dict[str, Any]] = []

        class FakeRegistry:
            async def execute(self, name: str, params: dict[str, Any]) -> SkillResult:
                assert name == "gpt-image-generate-skill"
                seen_params.append(params)
                return SkillResult(
                    success=True,
                    data={
                        "image_path": f"{params['output_dir']}/thumb.png",
                        "verification": {"all_ok": True},
                    },
                )

        result = await S1ProductDirectPipeline()._step_thumbnail_images(
            reg=FakeRegistry(),  # type: ignore[arg-type]
            thumbnail_sets=[
                {"variants": [{"prompt": "first thumbnail"}, {"prompt": "second thumbnail"}]},
            ],
            label="s2_run",
            errors=[],
            artifact_output_dir="/tmp/tenants/momcozy-marketing/pending_review/s2_run/thumbnails",
            provider_max_retries=0,
            thumbnail_job_cap=1,
        )

        assert result == [
            "/tmp/tenants/momcozy-marketing/pending_review/s2_run/thumbnails/thumb.png"
        ]
        assert len(seen_params) == 1
        assert seen_params[0]["output_dir"].endswith("/pending_review/s2_run/thumbnails")
        assert seen_params[0]["provider_max_retries"] == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_returns_media_keys(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=15,
            enable_media_synthesis=True,
        )
        for key in [
            "clip_paths", "audio_paths", "lyrics_paths",
            "thumbnail_image_paths", "final_video_path", "audit_report",
        ]:
            assert key in result, f"missing media key: {key}"

    def test_build_result_preserves_persisted_assemble_list_paths(self):
        result = S2BrandCampaignPipeline()._build_result(
            final_state={
                "steps": {
                    "assemble_final": {
                        "output": ["/tmp/s2-final.mp4", "/tmp/s2-render.json"],
                    },
                },
                "errors": [],
                "media_synthesis_errors": [],
            },
            brand_name="MomCozy",
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=15,
            enable_media_synthesis=True,
            model_id="kling-3-0/pro",
            label="s2-test",
        )

        assert result["final_video_path"] == "/tmp/s2-final.mp4"
        assert result["render_json_path"] == "/tmp/s2-render.json"


class TestS2ExtremeInputs:
    @pytest.mark.asyncio
    async def test_empty_brand_package_uses_default_brand_name(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package={},
            enable_media_synthesis=False,
        )
        assert result["brand_name"] == "Brand"
        assert result["scenario"] == "brand_campaign"

    @pytest.mark.asyncio
    async def test_invalid_video_duration_falls_back_to_60(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=999,
            enable_media_synthesis=False,
        )
        assert result["video_duration"] == 60

    @pytest.mark.asyncio
    @pytest.mark.parametrize("duration", [15, 30, 45, 60, 90])
    async def test_valid_durations_preserved(self, duration):
        result = await S2BrandCampaignPipeline().run(
            brand_package=BRAND_PACKAGE_FIXTURE,
            video_duration=duration,
            enable_media_synthesis=False,
        )
        assert result["video_duration"] == duration

    @pytest.mark.asyncio
    async def test_brand_name_missing_does_not_crash(self):
        result = await S2BrandCampaignPipeline().run(
            brand_package={"values": ["x"], "voice_guidelines": ""},
            enable_media_synthesis=False,
        )
        assert result["success"] is True


class TestS2DeprecationShim:
    def test_old_import_path_emits_deprecation_warning(self):
        """src.pipeline.s2_brand_pipeline import path triggers
        DeprecationWarning per Sprint 2 P2-2 contract."""
        import importlib
        import sys

        # Force re-import to trigger the warning fresh
        sys.modules.pop("src.pipeline.s2_brand_pipeline", None)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            importlib.import_module("src.pipeline.s2_brand_pipeline")
            deprecation_warnings = [
                w for w in captured if issubclass(w.category, DeprecationWarning)
            ]
            assert deprecation_warnings, "shim must emit DeprecationWarning"
            assert "s2_brand_pipeline_v2" in str(deprecation_warnings[0].message)

    def test_shim_re_exports_v2_class(self):
        """Same class object via both import paths — no diverged copies."""
        import sys

        sys.modules.pop("src.pipeline.s2_brand_pipeline", None)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from src.pipeline.s2_brand_pipeline import (
                S2BrandCampaignPipeline as Old,
            )
        from src.pipeline.s2_brand_pipeline_v2 import (
            S2BrandCampaignPipeline as V2,
        )
        assert Old is V2
