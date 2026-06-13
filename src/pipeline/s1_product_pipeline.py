"""S1 (∪ S2) E2E pipeline — Unified Product/Brand Pipeline.

Two scenarios fold into one pipeline:
  • brand_mode=False (default) → "S1 Product Direct" — show the product itself
  • brand_mode=True             → "S1 Brand Mode" (formerly S2 Brand Campaign)
                                  — same flow + brand-compliance audit step

Outputs for either mode (when enable_media_synthesis=True):
  - Strategy briefs, scripts, storyboards, video prompts, thumbnail prompts
  - Real Seedance .mp4 clips
  - Real ElevenLabs .mp3 audio
  - Real GPT-Image .png thumbnails
  - Final assembled .mp4 via Remotion
  - Media-quality audit report (7 criteria)

All steps go through SkillRegistry — no hardcoded prompts. Self-verification
runs inside each media skill; cross-artifact audit runs at the end.

Backwards compat: run() still returns a dict so existing API callers in src/api.py
keep working unchanged.
"""

from __future__ import annotations

import asyncio
import importlib
import time
from pathlib import Path
from typing import Any

import structlog

import src.skills.brand_compliance  # noqa: F401
import src.skills.character_identity  # noqa: F401          ← Track 3: character identity
import src.skills.continuity_storyboard_grid  # noqa: F401

# Import-time pre-media skill auto-registration. Provider-backed media skills
# are registered lazily only when their steps run, so no-media S1 submits keep
# the production log window free of media skill registration noise.
import src.skills.product_strategy  # noqa: F401
import src.skills.script_writer  # noqa: F401
import src.skills.storyboard  # noqa: F401  (best-effort; may not exist in repo)
from src.config import DEFAULT_LANGUAGES, MAX_CLIPS_PER_DEMO, MAX_THUMBNAILS_PER_DEMO, OUTPUT_DIR
from src.pipeline.artifact_paths import extract_assemble_paths
from src.pipeline.continuity_utils import (
    all_clips_are_stubs,
    build_continuity_audit_summary,
    collect_captions,
    collect_shots,
    compute_expected_duration,
    extract_clip_last_frame,
    normalize_continuity_config,
)
from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.scenario_injection_plan import with_optional_injection_config
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner
from src.pipeline.step_utils import get_step_output
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()


def _safe_path_segment(value: Any, fallback: str) -> str:
    segment = str(value or fallback).strip() or fallback
    return segment.replace("/", "_").replace("\\", "_")


def _artifact_media_output_dir(
    state: dict[str, Any],
    config: dict[str, Any],
    media_kind: str,
) -> str | None:
    disposition = config.get("artifact_disposition", "default")
    if disposition not in {"pending_review", "quarantine"}:
        return None

    tenant_id = _safe_path_segment(state.get("tenant_id") or config.get("tenant_id"), "default")
    label = _safe_path_segment(config.get("output_label") or state.get("label"), "run")
    return str(OUTPUT_DIR / "tenants" / tenant_id / disposition / label / media_kind)

_LAZY_SKILL_MODULES_BY_STEP: dict[str, tuple[tuple[str, str], ...]] = {
    "keyframe_images": (
        ("src.skills.gpt_image_generate", "gpt-image-generate-skill"),
        ("src.skills.keyframe_images", "keyframe-images"),
    ),
    "video_prompts": (
        ("src.skills.seedance_prompt", "seedance-video-prompt"),
    ),
    "thumbnail_prompts": (
        ("src.skills.thumbnail_prompt", "gpt-image-thumbnail-prompt"),
    ),
    "seedance_clips": (
        ("src.skills.seedance_video_generate", "seedance-video-generate-skill"),
        ("src.skills.media_quality_audit", "media-quality-audit-skill"),
    ),
    "tts_audio": (
        ("src.skills.elevenlabs_tts", "elevenlabs-tts-skill"),
    ),
    "thumbnail_images": (
        ("src.skills.gpt_image_generate", "gpt-image-generate-skill"),
    ),
    "assemble_final": (
        ("src.skills.remotion_assemble", "remotion-assemble-skill"),
    ),
    "audit": (
        ("src.skills.media_quality_audit", "media-quality-audit-skill"),
    ),
}


def _ensure_step_skills_registered(step_name: str, config: dict[str, Any] | None = None) -> None:
    """Register media-step skills only when that step is actually executed."""
    modules = list(_LAZY_SKILL_MODULES_BY_STEP.get(step_name, ()))
    if step_name == "seedance_clips" and (config or {}).get("seedance_quality_gate_enabled") is False:
        modules = [
            module
            for module in modules
            if module[1] != "media-quality-audit-skill"
        ]
    for module_name, skill_name in modules:
        module = importlib.import_module(module_name)
        if skill_name not in SkillRegistry._global_skills:
            importlib.reload(module)

# Caps (each Seedance call is ~30-60s; cap for sane demo runs)
# Now configurable via MAX_CLIPS_PER_DEMO / MAX_THUMBNAILS_PER_DEMO env vars
# Defaults: 3 clips, 2 thumbnails


class S1ProductDirectPipeline:
    """Unified S1 (Product Direct) + S2 (Brand Campaign) pipeline.

    Usage:
        # S1 Product Direct (no brand compliance)
        r = await S1ProductDirectPipeline().run(product_catalog=..., brand_mode=False)

        # S1 Brand Mode (was S2 Brand Campaign — adds compliance audit)
        r = await S1ProductDirectPipeline().run(
            product_catalog=...,
            brand_guidelines=brand_package,
            brand_mode=True,
        )
    """

    async def run(
        self,
        product_catalog: dict[str, Any],
        brand_guidelines: dict[str, Any] | None = None,
        target_platforms: list[str] | None = None,
        target_languages: list[str] | None = None,
        week: str = "",
        brand_mode: bool = False,
        enable_media_synthesis: bool = True,
        output_label: str | None = None,
        video_duration: int = 30,
        continuity_mode: bool = True,
        continuity_generation_mode: str = "standard",
        storyboard_grid: int | str = 12,
        clip_group_size: int = 3,
        transition_style: str = "match_cut",
        commercial_injection_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run the full S1 pipeline end-to-end.

        Backwards-compatible: uses StepRunner internally but returns the same
        result dict shape as before.
        """
        # Clamp to valid 5-tier values: 15, 30, 45, 60, or 90 seconds
        valid = {15, 30, 45, 60, 90}
        video_duration = video_duration if video_duration in valid else 30

        platforms = target_platforms or ["tiktok", "shopify"]
        # Phase 2+3: force English output. Languages param is locked to
        # DEFAULT_LANGUAGES at the API layer; this is a safety net for direct
        # pipeline calls.
        languages = DEFAULT_LANGUAGES
        product_name = product_catalog.get("product_name") or product_catalog.get("name", "Product")
        brand_name = (brand_guidelines or {}).get("brand_name", "")
        target_language = "en"
        label = output_label or f"s1_{int(time.time())}"

        config = {
            "product_catalog": product_catalog,
            "brand_guidelines": brand_guidelines,
            "target_platforms": platforms,
            "target_languages": languages,
            "week": week,
            "brand_mode": brand_mode,
            "enable_media_synthesis": enable_media_synthesis,
            "output_label": label,
            "video_duration": video_duration,
            "product_name": product_name,
            "brand_name": brand_name,
            "target_language": target_language,
            "continuity_mode": continuity_mode,
            "continuity_generation_mode": continuity_generation_mode,
            "storyboard_grid": storyboard_grid,
            "clip_group_size": clip_group_size,
            "transition_style": transition_style,
        }
        config = with_optional_injection_config(
            config,
            commercial_injection_plan,
            expected_scenario="s1",
        )

        state_manager = PipelineStateManager()
        runner = StepRunner(state_manager)
        label = await runner.init_state(config=config, mode="auto", label=label)
        if enable_media_synthesis:
            final_state = await runner.resume(label)
        else:
            final_state = await self._resume_without_media_synthesis(runner, label)

        # Convert final state back to the legacy result dict for backwards compat
        steps = final_state.get("steps", {})
        result: dict[str, Any] = {
            "success": True,
            "scenario": final_state.get("scenario", "product_direct"),
            "brand_mode": brand_mode,
            "video_duration": video_duration,
            "errors": final_state.get("errors", []),
            "media_synthesis_errors": final_state.get("media_synthesis_errors", []),
            "briefs": self._get_step_output(steps, "strategy") or [],
            "scripts": self._get_step_output(steps, "scripts") or [],
            "storyboards": self._get_step_output(steps, "storyboards") or [],
            "keyframe_images": self._get_step_output(steps, "keyframe_images") or [],
            "video_prompts": self._get_step_output(steps, "video_prompts") or [],
            "thumbnail_sets": self._get_step_output(steps, "thumbnail_prompts") or [],
            "steps_completed": 7,
        }

        if brand_mode:
            result["compliance_reports"] = self._get_step_output(steps, "compliance") or []

        if not enable_media_synthesis:
            logger.info("s1: complete (no media synthesis)", label=label)
            return result

        seedance_output = self._get_step_output(steps, "seedance_clips") or {}
        result["clip_paths"] = seedance_output.get("clip_paths", []) if isinstance(seedance_output, dict) else (seedance_output if isinstance(seedance_output, list) else [])
        tts_output = self._get_step_output(steps, "tts_audio") or {}
        if isinstance(tts_output, dict):
            result["audio_paths"] = tts_output.get("audio_paths", [])
            result["lyrics_paths"] = tts_output.get("lyrics_paths", [])
        else:
            # Backwards compat: old list format
            result["audio_paths"] = tts_output if isinstance(tts_output, list) else []
            result["lyrics_paths"] = []
        result["thumbnail_image_paths"] = self._get_step_output(steps, "thumbnail_images") or []

        assemble_output = self._get_step_output(steps, "assemble_final") or {}
        final_video_path, render_json_path = self._extract_assemble_paths(assemble_output)
        result["final_video_path"] = final_video_path
        result["render_json_path"] = render_json_path

        result["audit_report"] = self._get_step_output(steps, "audit") or {}
        result["steps_completed"] = 12

        # Sprint 3 P3-1: C2PA Content Credentials signing for EU AI Act
        # compliance. No-op when C2PA_ENABLED is unset (default). Replaces
        # final_video_path with a signed copy when the env var is set and
        # cert/key are provisioned; on any failure, returns the unsigned
        # path so downstream consumers never break.
        if result.get("final_video_path"):
            from src.tools.c2pa_signer import sign_video
            result["final_video_path"] = sign_video(
                result["final_video_path"],
                title=f"{brand_name or product_name} (AI generated)",
            )

        # Sprint 3 P3-3: surface partial artifacts when degraded so callers
        # can salvage usable outputs (clips, audio, scripts) instead of
        # treating an empty final_video_path as silent failure.
        from src.pipeline.partial_artifacts import summarize_partial_artifacts
        partial = summarize_partial_artifacts(final_state)
        if partial["degraded"]:
            result["partial_artifacts"] = partial

        # Apply fallbacks for empty briefs/scripts to preserve old behavior
        if not result["briefs"]:
            result["briefs"] = self._fallback_briefs(product_name, brand_name, platforms[0])
        if not result["scripts"]:
            result["scripts"] = self._fallback_scripts(product_name, brand_name)

        logger.info("s1: pipeline complete",
                    brand_mode=brand_mode,
                    briefs=len(result["briefs"]),
                    scripts=len(result["scripts"]),
                    keyframes=bool(result.get("keyframe_images")),
                    clips=len(result["clip_paths"]),
                    audios=len(result["audio_paths"]),
                    thumbnails=len(result["thumbnail_image_paths"]),
                    final_video=bool(result["final_video_path"]),
                    audit_status=result["audit_report"].get("overall_status") if result["audit_report"] else None,
                    errors=len(result["errors"]))

        return result

    async def _resume_without_media_synthesis(self, runner: StepRunner, label: str) -> dict[str, Any]:
        """Run only pre-media steps; stop before provider-backed asset generation."""
        final_state: dict[str, Any] = {}
        for step_name in get_scenario_step_order("s1"):
            if step_name == "keyframe_images":
                break
            final_state = await runner.run_step(label, step_name)
            if final_state.get("pipeline_degraded"):
                break
        if final_state and not final_state.get("pipeline_degraded"):
            final_state["current_step"] = None
            save = getattr(runner.state_manager, "save", None)
            if callable(save):
                await save(label, final_state)
        return final_state

    @staticmethod
    def _get_step_output(steps: dict[str, Any], step_name: str) -> Any:
        """Retrieve output from a step, preferring edited_output if edited.

        Delegates to the canonical shared implementation in step_utils.py.
        """
        return get_step_output(steps, step_name)

    @staticmethod
    def _extract_assemble_paths(output: Any) -> tuple[str, str]:
        return extract_assemble_paths(output)

    @staticmethod
    def _transition_plan_from_clip_groups(clip_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "from_clip": group.get("clip_index"),
                "to_clip": int(group.get("clip_index", 0)) + 1,
                "transition": group.get("transition_to_next"),
                "transition_type": group.get("transition_type"),
            }
            for group in clip_groups
            if group.get("transition_to_next")
        ]

    @staticmethod
    def _continuity_output(
        grid: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clip_groups = grid.get("clip_groups", [])
        if not isinstance(clip_groups, list):
            clip_groups = []
        micro_shots = grid.get("micro_shots", [])
        if not isinstance(micro_shots, list):
            micro_shots = []
        output_metadata = metadata or {}
        status = "skipped" if grid.get("skipped") or output_metadata.get("skipped") else "done"
        continuity_grid = {
            **grid,
            "metadata": output_metadata,
            "status": status,
        }
        transition_plan = S1ProductDirectPipeline._transition_plan_from_clip_groups(
            [group for group in clip_groups if isinstance(group, dict)]
        )
        return {
            **continuity_grid,
            "continuity_storyboard_grid": continuity_grid,
            "continuity_micro_shots": micro_shots,
            "clip_groups": clip_groups,
            "transition_plan": transition_plan,
            "metadata": output_metadata,
            "status": status,
        }

    async def run_step(self, step_name: str, state: dict[str, Any]) -> Any:
        """Execute a single pipeline step given the current state dict.

        This is the entry point used by StepRunner. It reads inputs from
        previous steps in the state, instantiates a SkillRegistry, calls the
        appropriate internal _step_* method, and returns the step output.
        """
        config = state["config"]
        _ensure_step_skills_registered(step_name, config)
        reg = SkillRegistry()
        steps = state["steps"]
        errors = state["errors"]
        media_errors = state["media_synthesis_errors"]

        if step_name == "strategy":
            return await self._step_strategy(
                reg=reg,
                product_catalog=config["product_catalog"],
                brand_guidelines=config.get("brand_guidelines") or {},
                platforms=config["target_platforms"],
                languages=config["target_languages"],
                week=config.get("week", ""),
                brand_mode=config.get("brand_mode", False),
                errors=errors,
            )

        if step_name == "scripts":
            briefs = self._get_step_output(steps, "strategy") or []
            return await self._step_scripts(
                reg=reg,
                briefs=briefs,
                product_name=config.get("product_name", "Product"),
                brand_guidelines=config.get("brand_guidelines"),
                languages=config["target_languages"],
                video_duration=config.get("video_duration", 30),
                errors=errors,
            )

        if step_name == "compliance":
            scripts = self._get_step_output(steps, "scripts") or []
            return await self._step_compliance(
                reg=reg,
                scripts=scripts,
                brand_guidelines=config.get("brand_guidelines") or {},
                errors=errors,
            )

        if step_name == "storyboards":
            scripts = self._get_step_output(steps, "scripts") or []
            return await self._step_storyboards(
                reg=reg,
                scripts=scripts,
                errors=errors,
            )

        if step_name == "continuity_storyboard_grid":
            scripts = self._get_step_output(steps, "scripts") or []
            storyboards = self._get_step_output(steps, "storyboards") or []
            continuity_config = normalize_continuity_config(config)
            return await self._step_continuity_storyboard_grid(
                reg=reg,
                product_catalog=config.get("product_catalog", {}),
                brand_guidelines=config.get("brand_guidelines") or {},
                target_platforms=config.get("target_platforms") or [],
                scripts=scripts,
                storyboards=storyboards,
                errors=errors,
                continuity_mode=continuity_config["continuity_mode"],
                storyboard_grid=continuity_config["storyboard_grid"],
                clip_group_size=continuity_config["clip_group_size"],
                transition_style=continuity_config["transition_style"],
                video_duration=config.get("video_duration", 30),
            )

        if step_name == "keyframe_images":
            storyboards = self._get_step_output(steps, "storyboards") or []
            quality_attempt = int(steps.get("storyboards", {}).get("_quality_attempt", 0))
            if quality_attempt and storyboards:
                storyboards = [{**sb, "_quality_attempt": quality_attempt} for sb in storyboards]
            provider_job_caps = config.get("provider_job_caps") or {}
            return await self._step_keyframe_images(
                reg=reg,
                storyboards=storyboards,
                errors=errors,
                config=config,
                artifact_output_dir=_artifact_media_output_dir(state, config, "keyframes"),
                provider_max_retries=config.get("provider_max_retries"),
                image_job_cap=provider_job_caps.get("image"),
            )

        if step_name == "video_prompts":
            scripts = self._get_step_output(steps, "scripts") or []
            continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
            return await self._step_video_prompts(
                reg=reg,
                scripts=scripts,
                product_name=config.get("product_name", "Product"),
                errors=errors,
                continuity_storyboard_grid=continuity_grid,
            )

        if step_name == "thumbnail_prompts":
            scripts = self._get_step_output(steps, "scripts") or []
            return await self._step_thumbnail_prompts(
                reg=reg,
                scripts=scripts,
                product_name=config.get("product_name", "Product"),
                brand_name=config.get("brand_name", ""),
                errors=errors,
            )

        if step_name == "seedance_clips":
            prompts = self._get_step_output(steps, "video_prompts") or []
            keyframes = self._get_step_output(steps, "keyframe_images") or []
            continuity_config = normalize_continuity_config(config)
            provider_job_caps = config.get("provider_job_caps") or {}
            return await self._step_seedance_clips(
                reg=reg,
                video_prompts=prompts,
                keyframe_images=keyframes,
                product_name=config.get("product_name", "Product"),
                label=config.get("output_label", "s1"),
                errors=media_errors,
                video_duration=config.get("video_duration", 30),
                continuity_mode=continuity_config["continuity_generation_mode"],
                artifact_output_dir=_artifact_media_output_dir(state, config, "clips"),
                provider_max_retries=config.get("provider_max_retries"),
                video_job_cap=provider_job_caps.get("video"),
                quality_gate_enabled=config.get("seedance_quality_gate_enabled", True),
            )

        if step_name == "tts_audio":
            scripts = self._get_step_output(steps, "scripts") or []
            return await self._step_tts_audio(
                reg=reg,
                scripts=scripts,
                language=config.get("target_language", "en"),
                errors=media_errors,
            )

        if step_name == "thumbnail_images":
            thumbnails = self._get_step_output(steps, "thumbnail_prompts") or []
            return await self._step_thumbnail_images(
                reg=reg,
                thumbnail_sets=thumbnails,
                label=config.get("output_label", "s1"),
                errors=media_errors,
            )

        if step_name == "assemble_final":
            storyboards = self._get_step_output(steps, "storyboards") or []
            scripts = self._get_step_output(steps, "scripts") or []
            tts_output = self._get_step_output(steps, "tts_audio") or {}
            if isinstance(tts_output, dict):
                audio_paths = tts_output.get("audio_paths", [])
                lyrics_paths = tts_output.get("lyrics_paths", [])
            else:
                audio_paths = tts_output if isinstance(tts_output, list) else []
                lyrics_paths = []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else (seedance_out if isinstance(seedance_out, list) else [])
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            # Guard: if all clips are stubs, skip assembly — nothing to assemble
            if not clip_paths or all_clips_are_stubs(clip_paths, clip_details):
                media_errors.append("all_seedance_clips_are_stubs; skipping assembly")
                return "", ""
            return await self._step_assemble_final(
                reg=reg,
                storyboards=storyboards,
                scripts=scripts,
                audio_paths=audio_paths,
                lyrics_paths=lyrics_paths,
                clip_paths=clip_paths,
                clip_details=clip_details,
                brand_guidelines=config.get("brand_guidelines") or {},
                label=config.get("output_label", "s1"),
                errors=media_errors,
            )

        if step_name == "audit":
            final_video = ""
            assemble_output = self._get_step_output(steps, "assemble_final")
            final_video, _ = self._extract_assemble_paths(assemble_output)

            # tts_audio 返回 {"audio_paths": [...], "lyrics_paths": [...]};
            # 直接传 dict 给 audit 会被 isinstance 检查拒掉 → audio_coverage 误报 FAIL
            tts_output = self._get_step_output(steps, "tts_audio") or {}
            if isinstance(tts_output, dict):
                audio_paths = tts_output.get("audio_paths", [])
            else:
                audio_paths = tts_output if isinstance(tts_output, list) else []
            thumb_image_paths = self._get_step_output(steps, "thumbnail_images") or []
            continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else (seedance_out if isinstance(seedance_out, list) else [])
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            scripts = self._get_step_output(steps, "scripts") or []
            thumbnails = self._get_step_output(steps, "thumbnail_prompts") or []
            # Guard: if all clips are stubs, audit is meaningless
            if not clip_paths or all_clips_are_stubs(clip_paths, clip_details):
                media_errors.append("all_seedance_clips_are_stubs; skipping audit")
                return {}

            base_audit = await self._step_audit(
                reg=reg,
                video_path=final_video,
                audio_paths=audio_paths,
                thumbnail_paths=thumb_image_paths,
                clip_paths=clip_paths,
                product_name=config.get("product_name", "Product"),
                scripts=scripts,
                thumbnail_sets=thumbnails,
                language=config.get("target_language", "en"),
                expected_duration_seconds=float(config.get("video_duration", 30)),
                errors=errors,
            )
            return build_continuity_audit_summary(
                base_audit=base_audit,
                clip_details=clip_details,
                continuity_grid=continuity_grid,
                final_video_path=final_video,
            )

        raise ValueError(f"Unknown step name: {step_name}")

    # ═══ Step implementations ═══

    async def _step_continuity_storyboard_grid(
        self,
        reg: SkillRegistry,
        product_catalog: dict[str, Any],
        brand_guidelines: dict[str, Any],
        target_platforms: list[str],
        scripts: list[dict[str, Any]],
        storyboards: list[dict[str, Any]],
        errors: list[str],
        continuity_mode: bool,
        storyboard_grid: int,
        clip_group_size: int,
        transition_style: str,
        video_duration: int,
    ) -> dict[str, Any]:
        if not continuity_mode:
            product_name = product_catalog.get("product_name") or product_catalog.get("name") or "Product"
            skipped_grid = {
                "grid_type": "skipped",
                "product_name": product_name,
                "visual_identity": {},
                "micro_shots": [],
                "clip_groups": [],
                "storyboards": storyboards,
                "skipped": True,
            }
            return self._continuity_output(
                skipped_grid,
                {
                    "skipped": True,
                    "reason": "continuity_mode=false",
                    "storyboard_grid": storyboard_grid,
                    "clip_group_size": clip_group_size,
                },
            )

        continuity_catalog = self._build_continuity_product_context(
            product_catalog=product_catalog,
            brand_guidelines=brand_guidelines,
            target_platforms=target_platforms,
        )

        res = await reg.execute(
            "continuity-storyboard-grid",
            {
                "product_catalog": continuity_catalog,
                "scripts": scripts,
                "storyboards": storyboards,
                "storyboard_grid": storyboard_grid,
                "clip_group_size": clip_group_size,
                "continuity_mode": continuity_mode,
                "transition_style": transition_style,
                "video_duration": video_duration,
            },
        )
        if res.success and isinstance(res.data, dict):
            metadata = {
                **res.metadata,
                "storyboard_grid": storyboard_grid,
                "clip_group_size": clip_group_size,
                "continuity_mode": continuity_mode,
            }
            return self._continuity_output(res.data, metadata)

        errors.append(f"continuity_storyboard_grid_failed: {res.error}")
        fallback_grid = {
            "grid_type": "12-grid",
            "product_name": product_catalog.get("product_name") or product_catalog.get("name") or "Product",
            "visual_identity": {},
            "micro_shots": [],
            "clip_groups": [],
            "degraded": True,
        }
        return self._continuity_output(
            fallback_grid,
            {
                "degraded": True,
                "error": res.error,
                "storyboard_grid": storyboard_grid,
                "clip_group_size": clip_group_size,
                "continuity_mode": continuity_mode,
            },
        )

    @staticmethod
    def _build_continuity_product_context(
        product_catalog: dict[str, Any],
        brand_guidelines: dict[str, Any],
        target_platforms: list[str],
    ) -> dict[str, Any]:
        catalog = dict(product_catalog)

        if brand_guidelines.get("brand_name") and not catalog.get("brand_name"):
            catalog["brand_name"] = brand_guidelines["brand_name"]

        tone = brand_guidelines.get("tone")
        if isinstance(tone, str) and tone.strip():
            catalog.setdefault("tone_of_voice", tone.strip())
            catalog.setdefault("voice_guidelines", tone.strip())

        target_audience = brand_guidelines.get("target_audience")
        if isinstance(target_audience, str) and target_audience.strip():
            catalog.setdefault("target_audience", target_audience.strip())

        primary_color = brand_guidelines.get("primary_color")
        secondary_color = brand_guidelines.get("secondary_color")
        palette = [
            color.strip()
            for color in (primary_color, secondary_color)
            if isinstance(color, str) and color.strip()
        ]
        if palette and "color_palette" not in catalog:
            catalog["color_palette"] = palette

        distribution_platforms = [
            platform.strip().lower()
            for platform in target_platforms
            if isinstance(platform, str) and platform.strip()
        ]
        if distribution_platforms:
            catalog["distribution_platforms"] = distribution_platforms[:3]

        return catalog

    async def _step_strategy(
        self,
        reg: SkillRegistry,
        product_catalog: dict[str, Any],
        brand_guidelines: dict[str, Any],
        platforms: list[str],
        languages: list[str],
        week: str,
        brand_mode: bool,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        scenario = "brand_campaign" if brand_mode else "product_direct"
        # In brand_mode, push the brand_name through product_catalog so the strategy skill
        # treats the brand as the campaign subject (parallels original S2 behavior).
        catalog = dict(product_catalog)
        if brand_mode and brand_guidelines.get("brand_name"):
            catalog.setdefault("brand_name", brand_guidelines["brand_name"])
            catalog.setdefault("category", "brand_campaign")

        res = await reg.execute("product-to-video-strategy", {
            "product_catalog": catalog,
            "brand_guidelines": brand_guidelines,
            "target_platforms": platforms,
            "target_languages": languages,
            "content_calendar_week": week or "2026-W18",
            "content_scenario": scenario,
        })
        if res.success and res.data:
            briefs = res.data.get("briefs", [])
            # Force single-brief mode: only the first brief is used
            if len(briefs) > 1:
                logger.info("strategy: limiting to first brief (was %d)", len(briefs))
                briefs = briefs[:1]
            return briefs
        errors.append(f"strategy_failed: {res.error}")
        return []

    async def _step_scripts(
        self,
        reg: SkillRegistry,
        briefs: list[dict[str, Any]],
        product_name: str,
        brand_guidelines: dict[str, Any] | None,
        languages: list[str],
        video_duration: int,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        enriched_briefs = []
        for brief in briefs:
            if isinstance(brief, dict):
                enriched = dict(brief)
                enriched.setdefault("product_name", product_name)
                enriched_briefs.append(enriched)
            else:
                enriched_briefs.append(brief)
        res = await reg.execute("script-writer-skill", {
            "briefs": enriched_briefs,
            "brand_guidelines": brand_guidelines or {},
            "target_languages": languages,
            "video_duration": video_duration,
        })
        if res.success and res.data:
            return res.data.get("scripts", [])
        errors.append(f"scripts_failed: {res.error}")
        return []

    async def _step_compliance(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        brand_guidelines: dict[str, Any],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        res = await reg.execute("brand-compliance-skill", {
            "scripts": scripts,
            "brand_guidelines": brand_guidelines,
        })
        if res.success and res.data:
            return res.data.get("reports", [])
        errors.append(f"compliance_failed: {res.error}")
        return []

    async def _step_storyboards(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        storyboards: list[dict[str, Any]] = []
        for script in scripts[:MAX_CLIPS_PER_DEMO]:
            res = await reg.execute("storyboard-skill", {"scripts": [script]})
            if res.success and res.data:
                # storyboard-skill returns {"storyboards": [{shots, script_id, total_duration}], ...}
                sbs = res.data.get("storyboards", [])
                if sbs:
                    sb = sbs[0]
                    storyboards.append({
                        "script_id": sb.get("script_id") or script.get("id"),
                        "shots": sb.get("shots", []),
                        "total_duration": sb.get("total_duration", 30.0),
                    })
            else:
                errors.append(f"storyboard_{script.get('id')}_failed: {res.error}")
        return storyboards

    async def _step_keyframe_images(
        self,
        reg: SkillRegistry,
        storyboards: list[dict[str, Any]],
        errors: list[str],
        config: dict[str, Any] | None = None,
        artifact_output_dir: str | None = None,
        provider_max_retries: int | None = None,
        image_job_cap: int | None = None,
    ) -> list[dict[str, Any]]:
        """Generate keyframe images for each storyboard's shots.

        Serial generation: poyo.ai has strict concurrency limits on
        image generation tasks. Parallel requests cause queue rejects.

        TODO-D11: if any storyboard's quality gate triggers regenerate
        upstream, propagate the signal as a marker on the first returned
        storyboard. step_runner detects and dispatches the regenerate.
        """
        keyframe_results: list[dict[str, Any]] = []
        regenerate_signal: dict[str, Any] | None = None
        # P2-1: Estimate needed keyframes from video_duration (~10s per clip)
        estimated_clips = max(3, (config or {}).get("video_duration", 30) // 10)
        remaining_image_jobs = None if image_job_cap is None else max(0, int(image_job_cap))
        for sb in storyboards[:MAX_CLIPS_PER_DEMO]:
            if remaining_image_jobs is not None and remaining_image_jobs <= 0:
                break
            shot_cap = estimated_clips
            if remaining_image_jobs is not None:
                shot_cap = min(shot_cap, remaining_image_jobs)
            params: dict[str, Any] = {
                "storyboard": sb,
                "size": "1024x1792",
                "quality": "high",
                "_quality_attempt": sb.get("_quality_attempt", 0),
                "_max_shots": shot_cap,
            }
            if artifact_output_dir:
                params["output_dir"] = artifact_output_dir
            if provider_max_retries is not None:
                params["provider_max_retries"] = provider_max_retries
            res = await reg.execute("keyframe-images", params)
            if (
                not res.success
                and isinstance(res.data, dict)
                and res.data.get("regenerate_upstream")
                and regenerate_signal is None
            ):
                regenerate_signal = {
                    "_regenerate_upstream": res.data["regenerate_upstream"],
                    "reason": res.data.get("reason", ""),
                    "score": res.data.get("score"),
                    "consumer": res.data.get("consumer", "keyframe_images"),
                    "attempt": res.data.get("attempt", 0),
                }
                fallback_sb = dict(sb)
                fallback_sb.update(regenerate_signal)
                keyframe_results.append(fallback_sb)
                continue
            if res.success and res.data:
                keyframe_results.append(res.data)
            else:
                errors.append(f"keyframe_images_failed: {res.error}")
                fallback_sb = dict(sb)
                for shot in fallback_sb.get("shots", []):
                    shot["keyframe_image_path"] = ""
                keyframe_results.append(fallback_sb)
            if remaining_image_jobs is not None:
                remaining_image_jobs -= shot_cap
        return keyframe_results

    async def _step_quality_gate(
        self,
        reg: SkillRegistry,
        video_path: str,
        clip_paths: list[str],
        storyboards: list[dict[str, Any]],
        product_name: str,
        errors: list[str],
        video_duration: int,
    ) -> dict[str, Any]:
        """Run quality gate on generated clips AFTER seedance step.

        Quality gate NEVER blocks the pipeline — it produces a report
        but allows the pipeline to continue even on FAIL.
        """
        clip_video_paths = [p for p in clip_paths if p]

        res = await reg.execute("media-quality-audit-skill", {
            "video_path": video_path or "",
            "audio_paths": [],
            "thumbnail_paths": [],
            "clip_paths": clip_paths,
            "clip_video_paths": clip_video_paths,
            "expected_product_name": product_name,
            "expected_duration_seconds": float(video_duration),
            "expected_language": "en",
            "script_text": "",
            "thumbnail_prompts": [],
            "identity_card": None,
            "product_reference_image": None,
        })
        if res.success and res.data:
            report = res.data
            status = report.get("overall_status", "UNKNOWN")
            logger.info("quality_gate: report", status=status,
                        criteria=len(report.get("criteria", [])))
            return report

        logger.warning("quality_gate: failed to run", error=res.error)
        return {}

    async def _step_video_prompts(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        product_name: str,
        errors: list[str],
        continuity_storyboard_grid: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate per-segment structured video prompts (narrative shot architecture).

        Each script segment produces one prompt dict with shot_type, camera,
        action, lighting, and full visual_description — never a concatenated string.
        """
        if continuity_storyboard_grid and continuity_storyboard_grid.get("clip_groups"):
            res = await reg.execute(
                "seedance-video-prompt",
                {
                    "continuity_storyboard_grid": continuity_storyboard_grid,
                    "product_name": product_name,
                },
            )
            if res.success and res.data and isinstance(res.data, list):
                if not res.metadata.get("is_fallback"):
                    return res.data
            reason = (
                res.error
                or res.metadata.get("fallback_reason")
                or "fallback_result"
            )
            errors.append(f"video_prompts_continuity_failed: {reason}")

        all_prompts: list[dict[str, Any]] = []
        for script in scripts[:MAX_CLIPS_PER_DEMO]:
            segments = script.get("segments", [])
            if not segments:
                continue
            # Pass ALL segments together — seedance_prompt skill now returns list[dict]
            res = await reg.execute("seedance-video-prompt", {
                "script_segments": [
                    {
                        "segment_type": s.get("segment_type", "body"),
                        "visual_description": s.get("visual_description", "") or s.get("description", ""),
                        "voiceover": s.get("voiceover", ""),
                        "start_time": float(s.get("start_time", 0)),
                        "end_time": float(s.get("end_time", 5)),
                    }
                    for s in segments
                ],
                "product_name": script.get("product_name", product_name),
                "style_ref_images": [],
                "product_images": [],
            })
            if res.success and res.data and isinstance(res.data, list):
                for p_dict in res.data:
                    p_dict["script_id"] = script.get("id", "")
                    p_dict["product_name"] = script.get("product_name", product_name)
                all_prompts.extend(res.data)
            else:
                errors.append(f"video_prompt_{script.get('id', '?')}_failed: {res.error}")
        return all_prompts

    async def _step_thumbnail_prompts(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        product_name: str,
        brand_name: str,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        thumbnails: list[dict[str, Any]] = []
        for script in scripts[:MAX_CLIPS_PER_DEMO]:
            res = await reg.execute("gpt-image-thumbnail-prompt", {
                "product_name": script.get("product_name", product_name),
                "brand_name": brand_name,
                "hook_text": script.get("hook", "") or script.get("segments", [{}])[0].get("description", ""),
                "product_usp": script.get("usps", [""])[0] if script.get("usps") else "",
            })
            if res.success and res.data:
                thumbnails.append({
                    "script_id": script.get("id"),
                    "variants": res.data.get("variants", []),
                })
            else:
                errors.append(f"thumb_prompt_{script.get('id')}_failed: {res.error}")
        return thumbnails

    # ═══ Media synthesis steps (NEW) ═══

    async def _step_seedance_clips(
        self,
        reg: SkillRegistry,
        video_prompts: list[dict[str, Any]],
        product_name: str,
        label: str,
        errors: list[str],
        video_duration: int = 30,
        keyframe_images: list[dict[str, Any]] | None = None,
        continuity_mode: str = "standard",
        artifact_output_dir: str | None = None,
        provider_max_retries: int | None = None,
        video_job_cap: int | None = None,
        quality_gate_enabled: bool = True,
    ) -> dict[str, Any]:
        """Generate video clips per segment using Sora 2 Pro (25s cap).

        Each prompt dict from seedance-video-prompt is sent as a separate
        image_to_video call with keyframe anchoring. Continuity chain
        preserves visual consistency across segment boundaries.

        Phase 2 prereq (Oracle review #4): every gen_params dict carries the
        explicit model id from ModelRouter so S1 / S2 (brand_mode) routes
        through select_model() instead of inheriting the env-default fallback.
        """
        from src.pipeline.model_router import select_model
        s1_model = select_model("s1")
        continuity_mode = continuity_mode if continuity_mode == "high_quality" else "standard"
        active_video_prompts = list(video_prompts)
        if video_job_cap is not None:
            active_video_prompts = active_video_prompts[: max(0, int(video_job_cap))]

        clip_paths: list[str] = []

        # Collect keyframe image paths per segment
        kf_image_paths: list[str] = []
        if keyframe_images:
            for kf in keyframe_images:
                shots = kf.get("shots", [])
                for shot in shots:
                    path = shot.get("keyframe_image_path", "")
                    if path:
                        kf_image_paths.append(path)

        # ── Continuity chain: last frame of clip N feeds clip N+1 ──
        last_frame_path: str | None = None

        # Sora 2 Pro via PoYo: single call up to 25s
        VIDEO_MAX_DURATION = 15  # Happy Horse API limit
        per_clip_duration = min(VIDEO_MAX_DURATION, video_duration)

        clip_durations: list[float] = []
        clip_details: list[dict[str, Any]] = []
        continuity_frame_by_index: dict[int, bool] = {}
        continuity_frame_output_dir = (
            str(Path(artifact_output_dir).parent / "continuity_frames")
            if artifact_output_dir
            else str(OUTPUT_DIR / "seedance" / "continuity_frames")
        )

        # P1-16 (2026-05-10 OPT-E): Bounded concurrent clip generation.
        # poyo.ai default observed limit was 2; raised to 4 after 5000-log-line
        # audit showed zero 429s. Each clip-skill call already retries on
        # 429/5xx via src/tools/retry.py, so transient overshoot self-heals.
        _seedance_sem = asyncio.Semaphore(4)

        async def _gen_single_clip(i: int, vp: dict[str, Any], kf_path: str | None) -> tuple[int, Any]:
            """Generate one clip with bounded concurrency."""
            async with _seedance_sem:
                prompt_text = vp.get("segment_prompt", "") or vp.get("prompt", "")
                if isinstance(prompt_text, dict):
                    prompt_text = prompt_text.get("segment_prompt", "") or prompt_text.get("prompt", "")
                if not prompt_text:
                    prompt_text = str(vp) if vp else f"{product_name} in natural usage scene"

                seg_duration = float(vp.get("duration_seconds", per_clip_duration))
                seg_duration = max(4, min(seg_duration, VIDEO_MAX_DURATION))

                gen_params: dict[str, Any] = {
                    "prompt": prompt_text,
                    "duration": int(seg_duration),
                    "resolution": "720p",
                    "output_label": f"{label}_seg_{i}",
                    "model": s1_model,
                }
                if artifact_output_dir:
                    gen_params["output_dir"] = artifact_output_dir
                if provider_max_retries is not None:
                    gen_params["provider_max_retries"] = provider_max_retries

                # P1-16: In concurrent mode we rely on keyframe anchoring.
                # If no keyframe is available, the clip generates from text prompt.
                # Post-generation we extract last frames for any downstream filler needs.
                if kf_path:
                    gen_params["keyframe_image_path"] = kf_path

                continuity_frame = vp.get("_continuity_frame_path")
                if continuity_frame:
                    gen_params["continuity_frame_path"] = continuity_frame
                    continuity_frame_by_index[i] = True
                else:
                    continuity_frame_by_index[i] = False

                res = await reg.execute("seedance-video-generate-skill", gen_params)
                return i, res

        if continuity_mode == "high_quality":
            raw_results: list[Any] = []
            for i, vp in enumerate(active_video_prompts):
                kf_path = kf_image_paths[i] if i < len(kf_image_paths) and kf_image_paths[i] else None
                next_prompt = dict(vp)
                if last_frame_path:
                    next_prompt["_continuity_frame_path"] = last_frame_path
                try:
                    result = await _gen_single_clip(i, next_prompt, kf_path)
                except Exception as exc:
                    raw_results.append(exc)
                    last_frame_path = None
                    continue
                raw_results.append(result)
                if isinstance(result, tuple) and result[1].success and result[1].data:
                    generated_path = result[1].data.get("video_path", "")
                    last_frame_path = extract_clip_last_frame(
                        video_path=generated_path,
                        output_dir=continuity_frame_output_dir,
                    )
                else:
                    last_frame_path = None
        else:
            # Launch all clips concurrently (max 4 in flight at any time)
            clip_tasks = []
            for i, vp in enumerate(active_video_prompts):
                kf_path = kf_image_paths[i] if i < len(kf_image_paths) and kf_image_paths[i] else None
                clip_tasks.append(_gen_single_clip(i, vp, kf_path))

            raw_results = await asyncio.gather(*clip_tasks, return_exceptions=True)

        # Surface any unhandled exceptions raised by clip generators
        for raw in raw_results:
            if isinstance(raw, Exception):
                errors.append(f"clip_failed_with_exception: {raw}")

        # Process results in index order to maintain deterministic state
        for i, skill_result in sorted(
            [r for r in raw_results if isinstance(r, tuple)],
            key=lambda x: x[0],
        ):
            if skill_result.success and skill_result.data:
                p = skill_result.data.get("video_path", "")
                dur = float(skill_result.data.get("duration_seconds", 0.0))
                if p:
                    clip_paths.append(p)
                    clip_durations.append(dur)
                    clip_details.append({
                        "path": p,
                        "duration": dur,
                        "is_stub": skill_result.data.get("is_stub", False),
                        "file_size": skill_result.data.get("file_size_bytes", 0),
                        "verification": skill_result.data.get("verification", {}),
                        "prompt_used": skill_result.data.get("prompt_used", ""),
                        "segment_type": active_video_prompts[i].get("segment_type", "body"),
                        "shot_type": active_video_prompts[i].get("shot_type", ""),
                        "clip_index": active_video_prompts[i].get("clip_index", i + 1),
                        "transition_to_next": active_video_prompts[i].get("transition_to_next", ""),
                        "transition_type": active_video_prompts[i].get("transition_type", "clean"),
                        "scene_beat": active_video_prompts[i].get("scene_beat", ""),
                        "beat_summary": active_video_prompts[i].get("beat_summary", ""),
                        "transition_intent": active_video_prompts[i].get("transition_intent", ""),
                        "continuity_frame": continuity_frame_by_index.get(i, False),
                    })

                    if not skill_result.data.get("verification", {}).get("all_ok", True):
                        errors.append(f"clip_{i}_verification: {skill_result.data['verification']}")
            else:
                errors.append(f"clip_{i}_failed: {skill_result.error}")

        # P1-16: Post-generation: extract last frames from completed clips in order
        # for potential filler generation or downstream continuity needs.
        if continuity_mode == "standard":
            for p in clip_paths:
                frame = extract_clip_last_frame(
                    video_path=p,
                    output_dir=continuity_frame_output_dir,
                )
                if frame:
                    last_frame_path = frame
                else:
                    last_frame_path = None

        # ── Duration fallback: if total clip duration < 80% target, generate filler ──
        total_clip_duration = sum(clip_durations)
        min_required = video_duration * 0.8
        if video_job_cap is None and total_clip_duration < min_required and clip_paths:
            logger.warning(
                "seedance: total duration insufficient, generating filler",
                total=total_clip_duration,
                required=min_required,
                target=video_duration,
            )
            # Build filler from the last segment's prompt
            last_prompt = active_video_prompts[-1].get("segment_prompt", "") if active_video_prompts else ""
            filler_prompt = str(last_prompt) + " (extended continuation, seamless extension of previous scene)" if last_prompt else f"{product_name} natural usage scene, extended"
            filler_params: dict[str, Any] = {
                "prompt": filler_prompt,
                "duration": per_clip_duration,
                "resolution": "720p",
                "output_label": f"{label}_clip_filler",
                "model": s1_model,
            }
            if artifact_output_dir:
                filler_params["output_dir"] = artifact_output_dir
            if provider_max_retries is not None:
                filler_params["provider_max_retries"] = provider_max_retries
            if last_frame_path:
                filler_params["continuity_frame_path"] = last_frame_path
            elif len(kf_image_paths) > len(clip_paths) and kf_image_paths[len(clip_paths)]:
                filler_params["image_refs"] = [kf_image_paths[len(clip_paths)]]

            res = await reg.execute("seedance-video-generate-skill", filler_params)
            if res.success and res.data:
                p = res.data.get("video_path", "")
                if p:
                    clip_paths.append(p)
                    dur = float(res.data.get("duration_seconds", 0.0))
                    clip_durations.append(dur)
                    clip_details.append({
                        "path": p,
                        "duration": dur,
                        "is_stub": res.data.get("is_stub", False),
                        "file_size": res.data.get("file_size_bytes", 0),
                        "verification": res.data.get("verification", {}),
                        "prompt_used": res.data.get("prompt_used", ""),
                        "scene_beat": "",
                        "beat_summary": "",
                        "transition_intent": "",
                        "continuity_frame": bool(last_frame_path),
                        "is_filler": True,
                    })
                    logger.info(
                        "seedance: filler clip generated",
                        path=p,
                        new_total=sum(clip_durations),
                    )
            else:
                errors.append(f"filler_clip_failed: {res.error}")

        # ── Quality gate: run on generated clips, NEVER blocks pipeline ──
        quality_report = {}
        if quality_gate_enabled:
            quality_report = await self._step_quality_gate(
                reg=reg,
                video_path="",
                clip_paths=clip_paths,
                storyboards=keyframe_images or [],
                product_name=product_name,
                errors=errors,
                video_duration=video_duration,
            )
        if quality_report:
            status = quality_report.get("overall_status", "N/A")
            logger.info("seedance_clips: quality gate complete", status=status)

        return {
            "clip_paths": clip_paths,
            "clip_details": clip_details,
            "total_duration": sum(clip_durations),
            "target_duration": video_duration,
        }

    async def _step_tts_audio(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        language: str,
        errors: list[str],
    ) -> dict[str, Any]:
        """Generate one background audio track per script.

        Merges all segment voiceovers into a single prompt per script,
        reducing poyo.ai call count from N-segments to 1-per-script.
        Returns a dict with 'audio_paths' and 'lyrics_paths' so the assembly
        step can overlay lyrics as captions.
        """
        audio_paths: list[str] = []
        lyrics_paths: list[str] = []

        for script in scripts[:MAX_CLIPS_PER_DEMO]:
            # Collect all non-empty voiceovers from segments
            voiceover_parts: list[str] = []
            for seg in script.get("segments", []):
                text = (
                    seg.get("voiceover")
                    or seg.get("description")
                    or seg.get("visual_description")
                    or ""
                )
                if text and len(text) >= 2:
                    voiceover_parts.append(text.strip())

            if not voiceover_parts:
                logger.warning("tts: no voiceover text found for script", script_id=script.get("id"))
                continue

            # Merge with line breaks
            merged_text = "\n".join(voiceover_parts)

            # P2-2: poyo generate-music truncates at 200 chars. Warn if exceeded
            # so the user knows the TTS may be incomplete.
            if len(merged_text) > 200:
                logger.warning(
                    "tts: merged voiceover exceeds poyo 200-char limit — will be truncated",
                    script_id=script.get("id"),
                    char_count=len(merged_text),
                    text_preview=merged_text[:120],
                )

            res = await reg.execute("elevenlabs-tts-skill", {
                "text": merged_text,
                "language": language,
            })
            if res.success and res.data:
                p = res.data.get("audio_path", "")
                if p:
                    audio_paths.append(p)
                lp = res.data.get("lyrics_path", "")
                if lp:
                    lyrics_paths.append(lp)
                if not res.data.get("verification", {}).get("all_ok", True):
                    errors.append(f"tts_{script.get('id')}_verification")
            else:
                errors.append(f"tts_failed: {res.error}")

        return {"audio_paths": audio_paths, "lyrics_paths": lyrics_paths}

    async def _step_thumbnail_images(
        self,
        reg: SkillRegistry,
        thumbnail_sets: list[dict[str, Any]],
        label: str,
        errors: list[str],
    ) -> list[str]:
        thumb_paths: list[str] = []
        flat_prompts: list[str] = []
        for ts in thumbnail_sets:
            for v in ts.get("variants", []):
                p = v.get("prompt", "") if isinstance(v, dict) else str(v)
                if p:
                    flat_prompts.append(p)

        capped_prompts = flat_prompts[:MAX_THUMBNAILS_PER_DEMO]
        if not capped_prompts:
            return thumb_paths

        thumb_sem = asyncio.Semaphore(2)

        async def _gen_one(i: int, prompt: str) -> tuple[int, Any]:
            async with thumb_sem:
                res = await reg.execute("gpt-image-generate-skill", {
                    "prompt": prompt,
                    "size": "1024x1792",
                    "quality": "high",
                    "image_id": f"{label}_thumb_{i}",
                })
                return i, res

        tasks = [_gen_one(i, p) for i, p in enumerate(capped_prompts)]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for raw in raw_results:
            if isinstance(raw, Exception):
                errors.append(f"thumb_failed_with_exception: {raw}")
                continue
            if not isinstance(raw, tuple):
                continue
            i, res = raw
            if res.success and res.data:
                p = res.data.get("image_path", "")
                if p:
                    thumb_paths.append(p)
                if not res.data.get("verification", {}).get("all_ok", True):
                    errors.append(f"thumb_{i}_verification: {res.data['verification']}")
            else:
                errors.append(f"thumb_{i}_failed: {res.error}")
        return thumb_paths

    async def _step_assemble_final(
        self,
        reg: SkillRegistry,
        storyboards: list[dict[str, Any]],
        scripts: list[dict[str, Any]],
        audio_paths: list[str],
        lyrics_paths: list[str],
        clip_paths: list[str],
        brand_guidelines: dict[str, Any],
        label: str,
        errors: list[str],
        clip_details: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str]:
        # Flatten storyboards into a single shot list. If no storyboards, derive from scripts.
        shots = collect_shots(storyboards, scripts)
        captions = collect_captions(scripts)
        total_duration = max(
            (float(s.get("end_time", 0)) for s in shots),
            default=30.0,
        )
        transitions = []
        for idx, detail in enumerate(clip_details or []):
            transition_to_next = detail.get("transition_to_next", "")
            if idx >= len(clip_paths) - 1 or not transition_to_next:
                continue
            transition_type = detail.get("transition_type", "clean")
            transitions.append({
                "from_clip": idx + 1,
                "to_clip": idx + 2,
                "type": transition_type,
                "duration_frames": 12 if transition_type == "soft_crossfade" else 8,
                "description": transition_to_next,
            })

        res = await reg.execute("remotion-assemble-skill", {
            "shots": shots,
            "captions": captions,
            "audio_paths": audio_paths,
            "lyrics_paths": lyrics_paths,
            "clip_paths": clip_paths,
            "brand_guidelines": brand_guidelines,
            "output_label": label,
            "total_duration": total_duration,
            "transitions": transitions,
        })
        if res.success and res.data:
            return res.data.get("video_path", ""), res.data.get("render_json_path", "")
        errors.append(f"assemble_failed: {res.error}")
        return "", ""

    async def _step_audit(
        self,
        reg: SkillRegistry,
        video_path: str,
        audio_paths: list[str],
        thumbnail_paths: list[str],
        clip_paths: list[str],
        product_name: str,
        scripts: list[dict[str, Any]],
        thumbnail_sets: list[dict[str, Any]],
        language: str,
        expected_duration_seconds: float,
        errors: list[str],
    ) -> dict[str, Any]:
        # Compose a flat script_text for content checks
        script_text = " ".join([
            (seg.get("voiceover", "") or seg.get("description", "") or seg.get("visual_description", ""))
            for s in scripts[:MAX_CLIPS_PER_DEMO]
            for seg in s.get("segments", [])
        ])
        # Flatten thumbnail prompts for the audit
        flat_thumb_prompts: list[dict[str, Any]] = []
        for ts in thumbnail_sets:
            for v in ts.get("variants", []):
                if isinstance(v, dict):
                    flat_thumb_prompts.append(v)

        expected_duration = expected_duration_seconds or compute_expected_duration(scripts)

        res = await reg.execute("media-quality-audit-skill", {
            "video_path": video_path,
            "audio_paths": audio_paths,
            "thumbnail_paths": thumbnail_paths,
            "clip_paths": clip_paths,
            "expected_product_name": product_name,
            "expected_duration_seconds": expected_duration,
            "expected_language": language,
            "script_text": script_text,
            "thumbnail_prompts": flat_thumb_prompts,
        })
        if res.success and res.data:
            return res.data
        errors.append(f"audit_failed: {res.error}")
        return {}

    @staticmethod
    def _fallback_briefs(product_name: str, brand_name: str, platform: str) -> list[dict[str, Any]]:
        return [{
            "product_name": product_name,
            "brand_name": brand_name,
            "hook_type": "pain_point",
            "platform": platform,
            "description": f"Direct product showcase for {product_name}",
        }]

    @staticmethod
    def _fallback_scripts(product_name: str, brand_name: str) -> list[dict[str, Any]]:
        return [{
            "id": "S1-001",
            "product_name": product_name,
            "brand_name": brand_name,
            "segments": [
                {"segment_type": "hook", "description": f"Meet {product_name}",
                 "start_time": 0, "end_time": 3, "visual_description": "Product hero shot",
                 "voiceover": f"Have you tried {product_name}?"},
                {"segment_type": "body", "description": "Key features",
                 "start_time": 3, "end_time": 10, "visual_description": "Feature close-ups",
                 "voiceover": f"{product_name} is hands-free and quiet — the perfect everyday companion."},
                {"segment_type": "cta", "description": "Get yours now",
                 "start_time": 10, "end_time": 12, "visual_description": "CTA overlay",
                 "voiceover": f"Get your {product_name} today!"},
            ],
        }]
