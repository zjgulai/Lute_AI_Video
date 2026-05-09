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
import subprocess
import time
from pathlib import Path
from typing import Any

import structlog

import src.skills.brand_compliance  # noqa: F401
import src.skills.character_identity  # noqa: F401          ← Track 3: character identity
import src.skills.elevenlabs_tts  # noqa: F401              ← NEW media
import src.skills.gpt_image_generate  # noqa: F401          ← NEW media
import src.skills.keyframe_images  # noqa: F401             ← Track 3: keyframe images
import src.skills.media_quality_audit  # noqa: F401         ← NEW audit

# Import-time skill auto-registration
import src.skills.product_strategy  # noqa: F401
import src.skills.remotion_assemble  # noqa: F401           ← NEW media
import src.skills.script_writer  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.seedance_video_generate  # noqa: F401  ← NEW media
import src.skills.storyboard  # noqa: F401  (best-effort; may not exist in repo)
import src.skills.thumbnail_prompt  # noqa: F401
from src.config import DEFAULT_LANGUAGES, OUTPUT_DIR
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

# Caps (each Seedance call is ~30-60s; cap for sane demo runs)
MAX_CLIPS_PER_DEMO = 3
MAX_THUMBNAILS_PER_DEMO = 2


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
        }

        state_manager = PipelineStateManager()
        runner = StepRunner(state_manager)
        label = await runner.init_state(config=config, mode="auto", label=label)
        final_state = await runner.resume(label)

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
        if isinstance(assemble_output, tuple):
            result["final_video_path"] = assemble_output[0] if len(assemble_output) > 0 else ""
            result["render_json_path"] = assemble_output[1] if len(assemble_output) > 1 else ""
        elif isinstance(assemble_output, dict):
            result["final_video_path"] = assemble_output.get("video_path", "")
            result["render_json_path"] = assemble_output.get("render_json_path", "")
        else:
            result["final_video_path"] = ""
            result["render_json_path"] = ""

        result["audit_report"] = self._get_step_output(steps, "audit") or {}
        result["steps_completed"] = 12

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

    @staticmethod
    def _get_step_output(steps: dict[str, Any], step_name: str) -> Any:
        """Retrieve output from a step, preferring edited_output if edited."""
        step_data = steps.get(step_name, {})
        if step_data.get("edited") and step_data.get("edited_output") is not None:
            return step_data["edited_output"]
        return step_data.get("output")

    @staticmethod
    def _all_clips_are_stubs(clip_paths: list[str], clip_details: list[dict[str, Any]] | None = None) -> bool:
        """Detect whether every clip is a stub file.

        Uses explicit is_stub metadata from clip_details when available,
        falling back to filename-based detection (stub files start with 'stub_').
        This avoids false positives from legitimate paths containing 'stub'
        as a substring (e.g. '/data/stubborn/product.mp4').
        """
        if not clip_paths:
            return True
        if clip_details and len(clip_details) == len(clip_paths):
            return all(d.get("is_stub", False) for d in clip_details)
        # Filename fallback: stub files generated by SeedanceClient._stub_result
        # follow the pattern 'stub_<mode>_<hash>.mp4'
        import os
        return all(os.path.basename(str(p)).lower().startswith("stub_") for p in clip_paths)

    async def run_step(self, step_name: str, state: dict[str, Any]) -> Any:
        """Execute a single pipeline step given the current state dict.

        This is the entry point used by StepRunner. It reads inputs from
        previous steps in the state, instantiates a SkillRegistry, calls the
        appropriate internal _step_* method, and returns the step output.
        """
        config = state["config"]
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
                brand_guidelines=config.get("brand_guidelines"),
                languages=config["target_languages"],
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

        if step_name == "keyframe_images":
            storyboards = self._get_step_output(steps, "storyboards") or []
            return await self._step_keyframe_images(
                reg=reg,
                storyboards=storyboards,
                errors=errors,
            )

        if step_name == "video_prompts":
            scripts = self._get_step_output(steps, "scripts") or []
            return await self._step_video_prompts(
                reg=reg,
                scripts=scripts,
                product_name=config.get("product_name", "Product"),
                errors=errors,
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
            return await self._step_seedance_clips(
                reg=reg,
                video_prompts=prompts,
                keyframe_images=keyframes,
                product_name=config.get("product_name", "Product"),
                label=config.get("output_label", "s1"),
                errors=media_errors,
                video_duration=config.get("video_duration", 30),
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
            if not clip_paths or self._all_clips_are_stubs(clip_paths, clip_details):
                media_errors.append("all_seedance_clips_are_stubs; skipping assembly")
                return "", ""
            return await self._step_assemble_final(
                reg=reg,
                storyboards=storyboards,
                scripts=scripts,
                audio_paths=audio_paths,
                lyrics_paths=lyrics_paths,
                clip_paths=clip_paths,
                brand_guidelines=config.get("brand_guidelines") or {},
                label=config.get("output_label", "s1"),
                errors=media_errors,
            )

        if step_name == "audit":
            final_video = ""
            assemble_output = self._get_step_output(steps, "assemble_final")
            if isinstance(assemble_output, tuple) and len(assemble_output) > 0:
                final_video = assemble_output[0]
            elif isinstance(assemble_output, dict):
                final_video = assemble_output.get("video_path", "")

            # tts_audio 返回 {"audio_paths": [...], "lyrics_paths": [...]};
            # 直接传 dict 给 audit 会被 isinstance 检查拒掉 → audio_coverage 误报 FAIL
            tts_output = self._get_step_output(steps, "tts_audio") or {}
            if isinstance(tts_output, dict):
                audio_paths = tts_output.get("audio_paths", [])
            else:
                audio_paths = tts_output if isinstance(tts_output, list) else []
            thumb_image_paths = self._get_step_output(steps, "thumbnail_images") or []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else (seedance_out if isinstance(seedance_out, list) else [])
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            scripts = self._get_step_output(steps, "scripts") or []
            thumbnails = self._get_step_output(steps, "thumbnail_prompts") or []
            # Guard: if all clips are stubs, audit is meaningless
            if not clip_paths or self._all_clips_are_stubs(clip_paths, clip_details):
                media_errors.append("all_seedance_clips_are_stubs; skipping audit")
                return {}

            return await self._step_audit(
                reg=reg,
                video_path=final_video,
                audio_paths=audio_paths,
                thumbnail_paths=thumb_image_paths,
                clip_paths=clip_paths,
                product_name=config.get("product_name", "Product"),
                scripts=scripts,
                thumbnail_sets=thumbnails,
                language=config.get("target_language", "en"),
                errors=errors,
            )

        raise ValueError(f"Unknown step name: {step_name}")

    # ═══ Step implementations ═══

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
        brand_guidelines: dict[str, Any] | None,
        languages: list[str],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        res = await reg.execute("script-writer-skill", {
            "briefs": briefs,
            "brand_guidelines": brand_guidelines or {},
            "target_languages": languages,
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
    ) -> list[dict[str, Any]]:
        """Generate keyframe images for each storyboard's shots.

        Serial generation: poyo.ai has strict concurrency limits on
        image generation tasks. Parallel requests cause queue rejects.
        """
        keyframe_results: list[dict[str, Any]] = []
        for sb in storyboards[:MAX_CLIPS_PER_DEMO]:
            res = await reg.execute("keyframe-images", {
                "storyboard": sb,
                "size": "1024x1792",
                "quality": "high",
            })
            if res.success and res.data:
                keyframe_results.append(res.data)
            else:
                errors.append(f"keyframe_images_failed: {res.error}")
                fallback_sb = dict(sb)
                for shot in fallback_sb.get("shots", []):
                    shot["keyframe_image_path"] = ""
                keyframe_results.append(fallback_sb)
        return keyframe_results

    async def _step_quality_gate(
        self,
        reg: SkillRegistry,
        video_path: str,
        clip_paths: list[str],
        storyboards: list[dict[str, Any]],
        product_name: str,
        errors: list[str],
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
            "expected_duration_seconds": 30.0,
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
    ) -> list[dict[str, Any]]:
        """Generate per-segment structured video prompts (narrative shot architecture).

        Each script segment produces one prompt dict with shot_type, camera,
        action, lighting, and full visual_description — never a concatenated string.
        """
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

    @staticmethod
    def _extract_clip_last_frame(video_path: str, output_dir: str) -> str | None:
        """Extract the last frame of a video clip as a JPEG for continuity.

        Uses ffmpeg to seek to the last frame: ffmpeg -sseof -1 -i {video_path}
        -frames:v 1 -q:v 2 {output_path}.

        Args:
            video_path: Absolute path to the source .mp4 clip.
            output_dir: Directory to write the extracted frame into.

        Returns:
            Absolute path to the extracted JPEG, or None on any failure (missing
            ffmpeg, corrupt file, etc.).
        """
        src = Path(video_path)
        if not src.exists() or src.stat().st_size < 100:
            return None

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        frame_path = out_dir / f"last_frame_{src.stem}.jpg"

        try:
            cmd = [
                "ffmpeg", "-y",
                "-sseof", "-1",
                "-i", str(src),
                "-frames:v", "1",
                "-q:v", "2",
                str(frame_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=15, check=True)
            if frame_path.exists() and frame_path.stat().st_size > 100:
                return str(frame_path)
        except (FileNotFoundError, subprocess.TimeoutExpired,
                subprocess.CalledProcessError, Exception):
            pass
        return None

    async def _step_seedance_clips(
        self,
        reg: SkillRegistry,
        video_prompts: list[dict[str, Any]],
        product_name: str,
        label: str,
        errors: list[str],
        video_duration: int = 30,
        keyframe_images: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generate video clips per segment using Sora 2 Pro (25s cap).

        Each prompt dict from seedance-video-prompt is sent as a separate
        image_to_video call with keyframe anchoring. Continuity chain
        preserves visual consistency across segment boundaries.
        """
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

        # P1-16: Bounded concurrent clip generation (poyo.ai limit = 2).
        # Previously: serial for-loop with 3s sleep between clips = ~5 min for 5 clips.
        # Now: asyncio.Semaphore(2) + gather = ~1.5 min for 5 clips.
        #
        # Continuity note: we use keyframe anchoring per clip (pre-generated by
        # storyboard node). The old last_frame chain is replaced by post-generation
        # extraction — all clips generate in parallel, then we extract frames in order.
        _seedance_sem = asyncio.Semaphore(2)

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
                }

                # P1-16: In concurrent mode we rely on keyframe anchoring.
                # If no keyframe is available, the clip generates from text prompt.
                # Post-generation we extract last frames for any downstream filler needs.
                if kf_path:
                    gen_params["keyframe_image_path"] = kf_path

                res = await reg.execute("seedance-video-generate-skill", gen_params)
                return i, res

        # Launch all clips concurrently (max 2 in flight at any time)
        clip_tasks = []
        for i, vp in enumerate(video_prompts):
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
                        "segment_type": video_prompts[i].get("segment_type", "body"),
                        "shot_type": video_prompts[i].get("shot_type", ""),
                        "continuity_frame": False,  # P1-16: keyframe-based in concurrent mode
                    })

                    if not skill_result.data.get("verification", {}).get("all_ok", True):
                        errors.append(f"clip_{i}_verification: {skill_result.data['verification']}")
            else:
                errors.append(f"clip_{i}_failed: {skill_result.error}")

        # P1-16: Post-generation: extract last frames from completed clips in order
        # for potential filler generation or downstream continuity needs.
        for p in clip_paths:
            frame = self._extract_clip_last_frame(
                video_path=p,
                output_dir=str(OUTPUT_DIR / "seedance" / "continuity_frames"),
            )
            if frame:
                last_frame_path = frame
            else:
                last_frame_path = None

        # ── Duration fallback: if total clip duration < 80% target, generate filler ──
        total_clip_duration = sum(clip_durations)
        min_required = video_duration * 0.8
        if total_clip_duration < min_required and clip_paths:
            logger.warning(
                "seedance: total duration insufficient, generating filler",
                total=total_clip_duration,
                required=min_required,
                target=video_duration,
            )
            # Build filler from the last segment's prompt
            last_prompt = video_prompts[-1].get("segment_prompt", "") if video_prompts else ""
            filler_prompt = str(last_prompt) + " (extended continuation, seamless extension of previous scene)" if last_prompt else f"{product_name} natural usage scene, extended"
            filler_params: dict[str, Any] = {
                "prompt": filler_prompt,
                "duration": per_clip_duration,
                "resolution": "720p",
                "output_label": f"{label}_clip_filler",
            }
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
        quality_report = await self._step_quality_gate(
            reg=reg,
            video_path="",
            clip_paths=clip_paths,
            storyboards=keyframe_images or [],
            product_name=product_name,
            errors=errors,
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
        # Flatten variants across scripts and cap
        flat_prompts: list[str] = []
        for ts in thumbnail_sets:
            for v in ts.get("variants", []):
                p = v.get("prompt", "") if isinstance(v, dict) else str(v)
                if p:
                    flat_prompts.append(p)

        for i, prompt in enumerate(flat_prompts[:MAX_THUMBNAILS_PER_DEMO]):
            res = await reg.execute("gpt-image-generate-skill", {
                "prompt": prompt,
                "size": "1024x1792",
                "quality": "high",
                "image_id": f"{label}_thumb_{i}",
            })
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
    ) -> tuple[str, str]:
        # Flatten storyboards into a single shot list. If no storyboards, derive from scripts.
        shots = self._collect_shots(storyboards, scripts)
        captions = self._collect_captions(scripts)
        total_duration = max(
            (float(s.get("end_time", 0)) for s in shots),
            default=30.0,
        )

        res = await reg.execute("remotion-assemble-skill", {
            "shots": shots,
            "captions": captions,
            "audio_paths": audio_paths,
            "lyrics_paths": lyrics_paths,
            "clip_paths": clip_paths,
            "brand_guidelines": brand_guidelines,
            "output_label": label,
            "total_duration": total_duration,
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

        expected_duration = self._compute_expected_duration(scripts)

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

    # ═══ Helpers ═══

    @staticmethod
    def _collect_shots(storyboards: list[dict[str, Any]], scripts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Flatten storyboards into a single shot list with absolute timing."""
        shots: list[dict[str, Any]] = []
        cursor = 0.0

        if storyboards:
            for board in storyboards:
                for shot in board.get("shots", []):
                    duration = float(shot.get("end_time", 0)) - float(shot.get("start_time", 0))
                    duration = max(duration, 1.0)
                    shots.append({
                        "id": len(shots) + 1,
                        "start_time": cursor,
                        "end_time": cursor + duration,
                        "text_overlay": shot.get("text_overlay", "") or shot.get("description", ""),
                        "visual": shot.get("visual", "") or shot.get("description", ""),
                    })
                    cursor += duration
        else:
            # Derive shots from the first 3 scripts' segments
            for script in scripts[:3]:
                for seg in script.get("segments", []):
                    duration = float(seg.get("end_time", 5)) - float(seg.get("start_time", 0))
                    duration = max(duration, 1.0)
                    shots.append({
                        "id": len(shots) + 1,
                        "start_time": cursor,
                        "end_time": cursor + duration,
                        "text_overlay": seg.get("description", "")[:60],
                        "visual": seg.get("visual_description", "") or seg.get("description", ""),
                    })
                    cursor += duration
        return shots

    @staticmethod
    def _collect_captions(scripts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        captions: list[dict[str, Any]] = []
        cursor = 0.0
        for script in scripts[:MAX_CLIPS_PER_DEMO]:
            for seg in script.get("segments", []):
                duration = float(seg.get("end_time", 5)) - float(seg.get("start_time", 0))
                text = seg.get("voiceover", "") or seg.get("description", "")
                if text:
                    captions.append({
                        "start_time": cursor,
                        "end_time": cursor + max(duration, 1.0),
                        "text": text[:80],
                    })
                cursor += max(duration, 1.0)
        return captions

    @staticmethod
    def _compute_expected_duration(scripts: list[dict[str, Any]]) -> float:
        total = 0.0
        for script in scripts[:MAX_CLIPS_PER_DEMO]:
            for seg in script.get("segments", []):
                duration = float(seg.get("end_time", 5)) - float(seg.get("start_time", 0))
                total += max(duration, 1.0)
        return total or 30.0

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
