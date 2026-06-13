"""S2 Brand Campaign — independent pipeline (Sprint 2 P2-1).

Decision A (2026-05-13): S2 was previously a 60-line deprecated wrapper
around S1 (brand_mode=True). This file introduces an independent S2
pipeline class with its own:

- Public contract: takes ``brand_package``, returns brand-campaign-shaped
  result with always-populated ``compliance_reports``.
- Model selection: routes through ``ModelRouter.select_model("s2")`` →
  ``kling-3.0/pro`` (15s @ 1080p + 3-person character consistency)
  instead of S1's seedance-2.
- Pipeline scenario tag: "brand_campaign", driving gate_manager's
  scenario-specific gate definitions and candidate_scorer's S2-weighted
  scoring dimensions (P2-5).

Design note: the step implementations themselves are reused from
``S1ProductDirectPipeline.run_step`` because they are correct and well-
tested. What's "independent" is the **contract surface** — class, file,
public method signature, result shape, model routing, scenario tag. This
is a contract-level separation per AGENTS.md "DUPLICATION > PREMATURE
ABSTRACTION, but PREMATURE DUPLICATION is also bad": copying 1000+
lines of S1 step code would create a maintenance liability that adds
zero correctness value.

If you need true physical separation (zero S1 import) — e.g. to
diverge step implementations in future sprints — the right time to fork
is when an S2-specific step actually differs, not now.
"""

from __future__ import annotations

import time
from typing import Any, Literal

import structlog

from src.config import DEFAULT_LANGUAGES
from src.pipeline.artifact_paths import extract_assemble_paths
from src.pipeline.model_router import select_model
from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.scenario_injection_plan import with_optional_injection_config
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner

logger = structlog.get_logger()

S2ArtifactDisposition = Literal["default", "pending_review", "quarantine"]
S2_BOUNDED_MEDIA_STOP_STEP = "seedance_clips"
S2_BOUNDED_MEDIA_STEP_ORDER = [
    "strategy",
    "scripts",
    "compliance",
    "storyboards",
    "continuity_storyboard_grid",
    "keyframe_images",
    "video_prompts",
    "seedance_clips",
]
S2_BOUNDED_MEDIA_PROVIDER_JOB_CAPS = {"image": 1, "video": 1}


def _artifact_storage_scope(disposition: S2ArtifactDisposition) -> str:
    if disposition == "pending_review":
        return "tenant_pending_review"
    if disposition == "quarantine":
        return "tenant_quarantine"
    return "default"


class S2BrandCampaignPipeline:
    """Independent S2 Brand Campaign pipeline.

    Usage:
        result = await S2BrandCampaignPipeline().run(
            brand_package={"brand_name": "MomCozy", "values": [...], ...},
            target_platforms=["tiktok", "shopify"],
            video_duration=60,
        )
    """

    SCENARIO_TAG = "s2"
    MODEL_PROVIDER = "model_router"

    async def run_step(self, step_name: str, state: dict[str, Any]) -> Any:
        """Execute a single step via S1 (brand_mode=True already in config)."""
        s1 = S1ProductDirectPipeline()
        return await s1.run_step(step_name, state)

    async def run(
        self,
        brand_package: dict[str, Any],
        target_platforms: list[str] | None = None,
        target_languages: list[str] | None = None,
        week: str = "",
        video_duration: int = 60,
        enable_media_synthesis: bool = True,
        artifact_disposition: S2ArtifactDisposition = "default",
        provider_max_retries: int | None = None,
        output_label: str | None = None,
        commercial_injection_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the S2 Brand Campaign pipeline end-to-end.

        Args:
            brand_package: Brand identity dict — must include 'brand_name';
                may include values, voice_guidelines, visual_constraints,
                competitor_context, etc.
            target_platforms: Distribution platforms (default tiktok+shopify).
            target_languages: Output languages (default DEFAULT_LANGUAGES; S2
                forces English output via DEFAULT_LANGUAGES same as S1).
            week: Optional ISO week for analytics tagging.
            video_duration: Total video seconds. Valid: 15/30/45/60/90.
            enable_media_synthesis: When False, stops after script generation
                without invoking seedance/tts/assemble. Useful for fast tests.
            artifact_disposition: ``pending_review`` or ``quarantine`` runs a
                bounded media pilot that stops after Seedance clips and never
                assembles final work.
            provider_max_retries: Per-provider retry cap. Bounded media pilot
                forces this to 0 so a live smoke cannot silently spend extra
                provider calls.
            output_label: Override the auto-generated pipeline label.

        Returns:
            dict shaped for S2 callers:
              - scenario: "brand_campaign"
              - brand_name: from brand_package
              - briefs / scripts / storyboards / compliance_reports
              - clip_paths / audio_paths / lyrics_paths /
                thumbnail_image_paths / final_video_path
              - audit_report
              - errors / media_synthesis_errors
              - model_id: the poyo model selected by ModelRouter
              - steps_completed
        """
        brand_name = brand_package.get("brand_name", "Brand")
        valid_durations = {15, 30, 45, 60, 90}
        if video_duration not in valid_durations:
            video_duration = 60

        platforms = target_platforms or ["tiktok", "shopify"]
        languages = target_languages or DEFAULT_LANGUAGES
        label = output_label or f"s2_{brand_name.lower().replace(' ', '_')}_{int(time.time())}"
        model_id = select_model(self.SCENARIO_TAG)
        bounded_media_pilot = enable_media_synthesis and artifact_disposition in {"pending_review", "quarantine"}
        effective_provider_max_retries = 0 if bounded_media_pilot else provider_max_retries
        provider_job_caps = dict(S2_BOUNDED_MEDIA_PROVIDER_JOB_CAPS) if bounded_media_pilot else None

        # Brand campaign treats the brand itself as the "product" subject;
        # carry brand identity into product_catalog so reused S1 step
        # implementations can read brand fields without divergence.
        product_catalog = {
            "name": brand_name,
            "product_name": brand_name,
            **brand_package,
        }

        config: dict[str, Any] = {
            "product_catalog": product_catalog,
            "brand_guidelines": brand_package,
            "target_platforms": platforms,
            "target_languages": languages,
            "week": week,
            "brand_mode": True,
            "enable_media_synthesis": enable_media_synthesis,
            "output_label": label,
            "video_duration": video_duration,
            "product_name": brand_name,
            "brand_name": brand_name,
            "target_language": "en",
            "preferred_model_id": model_id,
            "artifact_disposition": artifact_disposition,
            "provider_max_retries": effective_provider_max_retries,
        }
        if bounded_media_pilot:
            config.update({
                "provider_job_caps": {"image": 1, "video": 1},
                "seedance_quality_gate_enabled": False,
            })
        config = with_optional_injection_config(
            config,
            commercial_injection_plan,
            expected_scenario=self.SCENARIO_TAG,
        )

        logger.info(
            "s2: starting brand campaign",
            brand=brand_name,
            model=model_id,
            duration=video_duration,
        )

        state_manager = PipelineStateManager()
        runner = StepRunner(state_manager)
        label = await runner.init_state(
            config=config,
            mode="auto",
            label=label,
            scenario=self.SCENARIO_TAG,
        )
        if enable_media_synthesis:
            if artifact_disposition in {"pending_review", "quarantine"}:
                final_state = await self._resume_bounded_media_pilot(
                    runner,
                    label,
                    artifact_disposition,
                    effective_provider_max_retries,
                )
            else:
                final_state = await runner.resume(label)
        else:
            final_state = await self._resume_without_media_synthesis(runner, label)

        return self._build_result(
            final_state=final_state,
            brand_name=brand_name,
            brand_package=brand_package,
            video_duration=video_duration,
            enable_media_synthesis=enable_media_synthesis,
            artifact_disposition=artifact_disposition,
            provider_max_retries=effective_provider_max_retries,
            provider_job_caps=provider_job_caps,
            bounded_media_pilot=bounded_media_pilot,
            model_id=model_id,
            label=label,
        )

    async def _resume_without_media_synthesis(self, runner: StepRunner, label: str) -> dict[str, Any]:
        """Run only pre-media steps; stop before provider-backed asset generation."""
        final_state: dict[str, Any] = {}
        for step_name in get_scenario_step_order(self.SCENARIO_TAG):
            if step_name == "keyframe_images":
                break
            final_state = await runner.run_step(label, step_name)
            if final_state.get("pipeline_degraded"):
                break
        return final_state

    async def _resume_bounded_media_pilot(
        self,
        runner: StepRunner,
        label: str,
        artifact_disposition: S2ArtifactDisposition,
        provider_max_retries: int | None,
    ) -> dict[str, Any]:
        """Run S2 media only through clips, never final assembly or publishable work."""
        final_state: dict[str, Any] = {}
        for step_name in S2_BOUNDED_MEDIA_STEP_ORDER:
            final_state = await runner.run_step(label, step_name)
            if final_state.get("pipeline_degraded"):
                break
            if step_name == S2_BOUNDED_MEDIA_STOP_STEP:
                final_state["current_step"] = None
                final_state["bounded_media_pilot"] = True
                final_state["bounded_media_stop_step"] = S2_BOUNDED_MEDIA_STOP_STEP
                final_state["artifact_disposition"] = artifact_disposition
                final_state["artifact_storage_scope"] = _artifact_storage_scope(artifact_disposition)
                final_state["provider_max_retries"] = provider_max_retries
                final_state["provider_job_caps"] = dict(S2_BOUNDED_MEDIA_PROVIDER_JOB_CAPS)
                final_state.setdefault("config", {})
                final_state["config"]["provider_max_retries"] = provider_max_retries
                final_state["config"]["provider_job_caps"] = dict(S2_BOUNDED_MEDIA_PROVIDER_JOB_CAPS)
                final_state["config"]["seedance_quality_gate_enabled"] = False
                save = getattr(runner.state_manager, "save", None)
                if callable(save):
                    await save(label, final_state)
                break
        return final_state

    def _build_result(
        self,
        *,
        final_state: dict[str, Any],
        brand_name: str,
        brand_package: dict[str, Any],
        video_duration: int,
        enable_media_synthesis: bool,
        artifact_disposition: S2ArtifactDisposition = "default",
        provider_max_retries: int | None = None,
        provider_job_caps: dict[str, int] | None = None,
        bounded_media_pilot: bool = False,
        model_id: str,
        label: str,
    ) -> dict[str, Any]:
        """Shape the S2 result dict from the final pipeline state."""
        steps = final_state.get("steps", {})
        get = S1ProductDirectPipeline._get_step_output

        result: dict[str, Any] = {
            "success": True,
            "scenario": "brand_campaign",
            "brand_name": brand_name,
            "brand_package": brand_package,
            "video_duration": video_duration,
            "model_id": model_id,
            "label": label,
            "artifact_disposition": artifact_disposition,
            "artifact_storage_scope": _artifact_storage_scope(artifact_disposition),
            "provider_max_retries": provider_max_retries,
            "provider_job_caps": provider_job_caps,
            "bounded_media_pilot": bounded_media_pilot,
            "bounded_media_stop_step": S2_BOUNDED_MEDIA_STOP_STEP if bounded_media_pilot else None,
            "errors": final_state.get("errors", []),
            "media_synthesis_errors": final_state.get("media_synthesis_errors", []),
            "briefs": get(steps, "strategy") or [],
            "scripts": get(steps, "scripts") or [],
            "storyboards": get(steps, "storyboards") or [],
            "keyframe_images": get(steps, "keyframe_images") or [],
            "video_prompts": get(steps, "video_prompts") or [],
            "thumbnail_sets": get(steps, "thumbnail_prompts") or [],
            "compliance_reports": get(steps, "compliance") or [],
            "steps_completed": 7,
        }

        if not enable_media_synthesis:
            logger.info("s2: complete (no media synthesis)", brand=brand_name, label=label)
            return result

        seedance_output = get(steps, "seedance_clips") or {}
        if isinstance(seedance_output, dict):
            result["clip_paths"] = seedance_output.get("clip_paths", [])
        elif isinstance(seedance_output, list):
            result["clip_paths"] = seedance_output
        else:
            result["clip_paths"] = []

        tts_output = get(steps, "tts_audio") or {}
        if isinstance(tts_output, dict):
            result["audio_paths"] = tts_output.get("audio_paths", [])
            result["lyrics_paths"] = tts_output.get("lyrics_paths", [])
        else:
            result["audio_paths"] = tts_output if isinstance(tts_output, list) else []
            result["lyrics_paths"] = []

        result["thumbnail_image_paths"] = get(steps, "thumbnail_images") or []

        assemble_output = get(steps, "assemble_final") or {}
        final_video_path, render_json_path = extract_assemble_paths(assemble_output)
        result["final_video_path"] = final_video_path
        result["render_json_path"] = render_json_path

        result["audit_report"] = get(steps, "audit") or {}
        if bounded_media_pilot:
            result["final_video_path"] = ""
            result["render_json_path"] = ""
            result["thumbnail_image_paths"] = []
            result["audit_report"] = {}
            result["delivery_accepted"] = False
            result["publish_allowed"] = False
            result["approved_brand_token_write"] = False
            result["provider_job_caps"] = provider_job_caps or final_state.get("provider_job_caps")
            result["steps_completed"] = S2_BOUNDED_MEDIA_STEP_ORDER.index(S2_BOUNDED_MEDIA_STOP_STEP) + 1
            logger.info(
                "s2: bounded media pilot complete",
                brand=brand_name,
                label=label,
                artifact_disposition=artifact_disposition,
                stop_step=S2_BOUNDED_MEDIA_STOP_STEP,
                clips=len(result["clip_paths"]),
            )
            return result

        result["steps_completed"] = 12

        # Sprint 3 P3-1: C2PA signing for EU AI Act compliance (no-op when
        # C2PA_ENABLED unset).
        if result.get("final_video_path"):
            from src.tools.c2pa_signer import sign_video
            result["final_video_path"] = sign_video(
                result["final_video_path"],
                title=f"{brand_name} brand campaign (AI generated)",
            )

        # Sprint 3 P3-3: partial artifacts when degraded
        from src.pipeline.partial_artifacts import summarize_partial_artifacts
        partial = summarize_partial_artifacts(final_state)
        if partial["degraded"]:
            result["partial_artifacts"] = partial

        logger.info(
            "s2: pipeline complete",
            brand=brand_name,
            model=model_id,
            briefs=len(result["briefs"]),
            scripts=len(result["scripts"]),
            compliance=len(result["compliance_reports"]),
            clips=len(result["clip_paths"]),
            audios=len(result["audio_paths"]),
            final_video=bool(result["final_video_path"]),
            errors=len(result["errors"]),
        )

        return result
