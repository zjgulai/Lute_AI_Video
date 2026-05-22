"""S3 E2E integration — influencer remix pipeline.

Takes an influencer video URL + product info, produces:
  - Video analysis (hook, style, segments)
  - Remix script (style-preserving product script)
  - Seedance video prompts
  - Thumbnail prompts
  - Real Seedance clips (.mp4)
  - Real TTS audio (.mp3)
  - Real thumbnail images (.png)
  - Final assembled video (.mp4) via Remotion
  - Media-quality audit report

All steps use registered skills via SkillRegistry, no hardcoded prompts.
Self-verification runs inside each media skill; cross-artifact audit runs at the end.
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from pathlib import Path
from typing import Any

import structlog

import src.skills.character_identity  # noqa: F401 — auto-register (NEW)
import src.skills.elevenlabs_tts  # noqa: F401 — auto-register (NEW)
import src.skills.gpt_image_generate  # noqa: F401 — auto-register (NEW)
import src.skills.keyframe_images  # noqa: F401 — auto-register (NEW)
import src.skills.media_quality_audit  # noqa: F401 — auto-register (NEW)
import src.skills.remix_script  # noqa: F401 — auto-register
import src.skills.remotion_assemble  # noqa: F401 — auto-register (NEW)
import src.skills.seedance_prompt  # noqa: F401 — auto-register
import src.skills.seedance_video_generate  # noqa: F401 — auto-register (NEW)
import src.skills.thumbnail_prompt  # noqa: F401 — auto-register
import src.skills.video_analysis  # noqa: F401 — auto-register
from src.config import OUTPUT_DIR, S3_VIRAL_EXTRACT_DISABLED
from src.pipeline.artifact_paths import extract_assemble_paths
from src.skills.base import SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

# Caps to keep demo timeline sane (each Seedance call ~30-60s)
MAX_CLIPS_PER_DEMO = 3
MAX_THUMBNAILS_PER_DEMO = 4


class S3Result:
    """Complete S3 pipeline output."""

    def __init__(self):
        self.success: bool = False
        self.video_analysis: dict[str, Any] | None = None
        self.identity_card: dict[str, Any] | None = None
        self.remix_script: dict[str, Any] | None = None
        self.storyboard_with_keyframes: dict[str, Any] | None = None
        self.video_prompts: list[dict[str, Any]] = []
        self.thumbnail_sets: list[dict[str, Any]] = []
        # NEW: real media artifacts
        self.clip_paths: list[str] = []
        self.audio_paths: list[str] = []
        self.thumbnail_image_paths: list[str] = []
        self.final_video_path: str = ""
        self.render_json_path: str = ""
        self.audit_report: dict[str, Any] | None = None
        self.media_synthesis_errors: list[str] = []
        self.errors: list[str] = []

    # Back-compat alias used by some tests
    @property
    def thumbnail_prompts(self) -> list[dict[str, Any]]:
        return self.thumbnail_sets

    def to_dict(self) -> dict[str, Any]:
        segments = []
        if self.remix_script and "segments" in self.remix_script:
            segments = self.remix_script["segments"]

        return {
            "success": self.success,
            "video_analysis": self.video_analysis,
            "identity_card": self.identity_card,
            "remix_script": self.remix_script,
            "storyboard_with_keyframes": self.storyboard_with_keyframes,
            "video_prompts": self.video_prompts,
            "thumbnail_sets": self.thumbnail_sets,
            "thumbnail_prompts": self.thumbnail_sets,  # alias for compat
            "clip_paths": self.clip_paths,
            "audio_paths": self.audio_paths,
            "thumbnail_image_paths": self.thumbnail_image_paths,
            "final_video_path": self.final_video_path,
            "render_json_path": self.render_json_path,
            "audit_report": self.audit_report,
            "media_synthesis_errors": self.media_synthesis_errors,
            "errors": self.errors,
            "segment_count": len(segments),
        }


class S3InfluencerRemixPipeline:
    """Orchestrate the S3 influencer remix pipeline.

    Usage:
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@user/video/123",
            product={"name": "X1 Pump", "usps": ["quiet", "portable"], "brand_name": "LactFit"},
            influencer_name="Jessica",
            enable_media_synthesis=True,
        )
    """

    def __init__(self):
        self._registry = SkillRegistry()
        self._video_duration: int = 30  # default, overridden in run()

    # ═══ StepRunner interface ═══

    async def run_step(self, step_name: str, state: dict[str, Any]) -> Any:
        """Execute a single pipeline step (used by StepRunner)."""
        config = state["config"]
        reg = SkillRegistry()
        steps = state["steps"]
        errors = state["errors"]
        media_errors = state.get("media_synthesis_errors", [])
        self._video_duration = config.get("video_duration", 30)

        if step_name == "video_analysis":
            res = await self._step_video_analysis(
                video_url=config["video_url"],
                extract_segments=config.get("extract_segments", True),
            )
            if not res.success:
                disabled_by_policy = res.error == "s3_viral_extract_disabled_by_policy"
                errors.append(f"video_analysis_failed: {res.error}")
                return {
                    "_soft_degraded": True,
                    "_degraded_reason": (
                        "s3_viral_extract_disabled_adr004"
                        if disabled_by_policy
                        else "video_analysis_failed_using_fallback"
                    ),
                    "_degraded_detail": str(res.error or "unknown")[:200],
                    "viral_segments": [],
                    "fallback_prompt": (
                        "Generic product remix from original creator's segment. "
                        "Original video unavailable; emphasize product benefits + "
                        "creator's signature delivery style."
                    ),
                    "hook_type": "question",
                    "speech_style": "neutral",
                    "segments": [],
                    "emotion_curve": [],
                }
            return res.data

        if step_name == "character_identity":
            analysis = self._get_step_output(steps, "video_analysis") or {}
            return await self._step_character_identity(analysis=analysis)

        if step_name == "remix_script":
            analysis = self._get_step_output(steps, "video_analysis") or {}
            res = await self._step_remix_script(
                analysis=analysis,
                product=config["product"],
                influencer_name=config.get("influencer_name", "Influencer"),
                brief_id=config.get("brief_id", ""),
            )
            if not res.success:
                errors.append(f"remix_script_failed: {res.error}")
                return {}
            return res.data

        if step_name == "storyboards":
            script = self._get_step_output(steps, "remix_script") or {}
            return await self._step_storyboards(remix_script=script)

        if step_name == "keyframe_images":
            storyboard = self._get_step_output(steps, "storyboards") or {}
            identity = self._get_step_output(steps, "character_identity") or {}
            return await self._step_keyframe_images(storyboard=storyboard, identity_card=identity)

        if step_name == "video_prompts":
            script = self._get_step_output(steps, "remix_script") or {}
            return await self._step_video_prompts(remix_script=script, product=config["product"])

        if step_name == "thumbnail_prompts":
            script = self._get_step_output(steps, "remix_script") or {}
            return await self._step_thumbnail_prompts(remix_script=script, product=config["product"])

        if step_name == "seedance_clips":
            prompts = self._get_step_output(steps, "video_prompts") or []
            keyframes = self._get_step_output(steps, "keyframe_images") or {}
            return await self._step_seedance_clips(
                video_prompts=prompts,
                product=config["product"],
                label=config.get("output_label", "s3"),
                errors=media_errors,
                keyframe_images=keyframes,
            )

        if step_name == "tts_audio":
            script = self._get_step_output(steps, "remix_script") or {}
            return await self._step_tts_audio(
                remix_script=script,
                language=config.get("target_language", "en"),
                errors=media_errors,
            )

        if step_name == "thumbnail_images":
            thumbnails = self._get_step_output(steps, "thumbnail_prompts") or []
            return await self._step_thumbnail_images(
                thumbnail_prompts=thumbnails,
                label=config.get("output_label", "s3"),
                errors=media_errors,
            )

        if step_name == "assemble_final":
            script = self._get_step_output(steps, "remix_script") or {}
            audio = self._get_step_output(steps, "tts_audio") or []
            audio_paths = audio if isinstance(audio, list) else []
            clips = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = clips.get("clip_paths", []) if isinstance(clips, dict) else []
            res = await self._step_assemble_final(
                remix_script=script,
                captions=self._extract_captions(script),
                audio_paths=audio_paths,
                clip_paths=clip_paths,
                label=config.get("output_label", "s3"),
            )
            if res.success and res.data:
                return res.data
            errors.append(f"assemble_failed: {res.error}")
            return {}

        if step_name == "audit":
            script = self._get_step_output(steps, "remix_script") or {}
            assemble = self._get_step_output(steps, "assemble_final") or {}
            video_path, _ = extract_assemble_paths(assemble)
            audio = self._get_step_output(steps, "tts_audio") or []
            audio_paths = audio if isinstance(audio, list) else []
            thumbnails = self._get_step_output(steps, "thumbnail_images") or []
            thumb_paths = thumbnails if isinstance(thumbnails, list) else []
            clips = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = clips.get("clip_paths", []) if isinstance(clips, dict) else []
            thumb_prompts = self._get_step_output(steps, "thumbnail_prompts") or []
            res = await self._step_audit(
                video_path=video_path,
                audio_paths=audio_paths,
                thumbnail_paths=thumb_paths,
                clip_paths=clip_paths,
                product=config["product"],
                remix_script=script,
                thumbnail_prompts=thumb_prompts,
                language=config.get("target_language", "en"),
            )
            if res.success and res.data:
                return res.data
            errors.append(f"audit_failed: {res.error}")
            return {}

        raise ValueError(f"Unknown step name: {step_name}")

    @staticmethod
    def _get_step_output(steps: dict[str, Any], step_name: str) -> Any:
        """Retrieve output from a step, preferring edited_output if edited."""
        step_data = steps.get(step_name, {})
        if step_data.get("edited") and step_data.get("edited_output") is not None:
            return step_data["edited_output"]
        return step_data.get("output")

    # ═══ Backwards-compatible full pipeline ═══

    async def run(
        self,
        video_url: str,
        product: dict[str, Any],
        influencer_name: str = "Influencer",
        extract_segments: bool = True,
        brief_id: str = "",
        enable_media_synthesis: bool = True,
        target_language: str = "en",
        output_label: str | None = None,
        video_duration: int = 30,
    ) -> S3Result:
        """Run the full S3 pipeline end-to-end.

        Backwards-compatible: uses StepRunner internally but returns the same
        S3Result shape as before.
        """
        self._video_duration = video_duration if video_duration in {15, 30, 45, 60, 90} else 30
        label = output_label or f"s3_{int(time.time())}"

        logger.info("s3: starting influencer remix pipeline",
                    video_url=video_url, product=product.get("name"),
                    enable_media_synthesis=enable_media_synthesis)

        config = {
            "video_url": video_url,
            "product": product,
            "influencer_name": influencer_name,
            "extract_segments": extract_segments,
            "brief_id": brief_id,
            "target_language": target_language,
            "video_duration": self._video_duration,
            "output_label": label,
        }

        from src.pipeline.state_manager import PipelineStateManager
        from src.pipeline.step_runner import StepRunner

        state_manager = PipelineStateManager()
        runner = StepRunner(state_manager)
        label = await runner.init_state(config=config, mode="auto", label=label, scenario="s3")

        try:
            final_state = await runner.resume(label)
        except Exception as e:
            logger.error("s3: pipeline failed", error=str(e))
            result = S3Result()
            result.errors.append(str(e))
            return result

        steps = final_state.get("steps", {})
        errors = final_state.get("errors", [])

        result = S3Result()
        result.video_analysis = self._get_step_output(steps, "video_analysis")
        result.identity_card = self._get_step_output(steps, "character_identity")
        result.remix_script = self._get_step_output(steps, "remix_script")
        result.storyboard_with_keyframes = self._get_step_output(steps, "keyframe_images")
        result.video_prompts = self._get_step_output(steps, "video_prompts") or []
        result.thumbnail_sets = self._get_step_output(steps, "thumbnail_prompts") or []

        if enable_media_synthesis:
            clips = self._get_step_output(steps, "seedance_clips") or {}
            result.clip_paths = clips.get("clip_paths", []) if isinstance(clips, dict) else []
            audio = self._get_step_output(steps, "tts_audio") or []
            result.audio_paths = audio if isinstance(audio, list) else []
            thumbs = self._get_step_output(steps, "thumbnail_images") or []
            result.thumbnail_image_paths = thumbs if isinstance(thumbs, list) else []
            assemble = self._get_step_output(steps, "assemble_final") or {}
            result.final_video_path, result.render_json_path = extract_assemble_paths(assemble)
            result.audit_report = self._get_step_output(steps, "audit")
            result.media_synthesis_errors = final_state.get("media_synthesis_errors", [])

        result.errors = errors
        result.success = len(errors) == 0
        logger.info("s3: pipeline complete",
                    success=result.success,
                    prompts=len(result.video_prompts),
                    thumbnails=len(result.thumbnail_sets),
                    clips=len(result.clip_paths),
                    audio_segments=len(result.audio_paths),
                    final_video=bool(result.final_video_path),
                    audit=result.audit_report and result.audit_report.get("overall_status"),
                    errors=len(result.errors))
        return result

    # ═══ Step 1-4: existing data-producing steps ═══

    async def _step_video_analysis(
        self,
        video_url: str,
        extract_segments: bool,
    ) -> SkillResult:
        if S3_VIRAL_EXTRACT_DISABLED:
            logger.warning(
                "s3: video_analysis skipped — S3_VIRAL_EXTRACT_DISABLED=1 (ADR-004 Option D)",
                video_url=video_url,
            )
            return SkillResult(
                success=False,
                error="s3_viral_extract_disabled_by_policy",
                data=None,
            )
        logger.info("s3: step 1 — video analysis")
        return await self._registry.execute("video-analysis-skill", {
            "video_url": video_url,
            "extract_segments": extract_segments,
            "extract_emotions": True,
        })

    async def _step_remix_script(
        self,
        analysis: dict[str, Any],
        product: dict[str, Any],
        influencer_name: str,
        brief_id: str,
    ) -> SkillResult:
        logger.info("s3: step 2 — remix script")
        product_context = {
            "pain_points": product.get("pain_points", []),
            "target_audience": product.get("target_audience", ""),
            "competitor_context": product.get("competitor_context", []),
            "usage_scenario": product.get("usage_scenario", ""),
        }
        params = {
            "analysis": analysis,
            "product": product,
            "product_context": product_context,
            "influencer_name": influencer_name,
            "brief_id": brief_id,
        }
        if analysis.get("_soft_degraded") and analysis.get("fallback_prompt"):
            params["fallback_prompt"] = analysis["fallback_prompt"]
            params["upstream_degraded"] = True
            logger.warning(
                "s3: remix_script proceeding with video_analysis fallback prompt",
                reason=analysis.get("_degraded_reason"),
            )
        return await self._registry.execute("remix-script-skill", params)

    async def _step_video_prompts(
        self,
        remix_script: dict[str, Any],
        product: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate Seedance video prompts from remix segments."""
        logger.info("s3: step 3 — video prompts")
        segments = remix_script.get("segments", [])
        if not segments:
            return []

        script_segments = []
        for i, seg in enumerate(segments):
            seg_type = seg.get("segment_type", "body")
            description = seg.get("remix_description", "") or seg.get("keep_notes", "")
            per_seg_dur = max(5, self._video_duration // max(len(segments), 1))
            script_segments.append({
                "type": self._map_segment_to_video_type(seg_type),
                "description": description,
                "duration_seconds": per_seg_dur,
            })

        result = await self._registry.execute("seedance-video-prompt", {
            "script_segments": script_segments,
            "product_name": product.get("name", "Product"),
            "style_refs": [],
            "product_images": [],
        })

        if result.success and result.data:
            if isinstance(result.data, list):
                # New narrative_shot architecture: list[dict] per segment
                return [
                    {
                        "segment_index": i,
                        "segment_type": p.get("segment_type", "body"),
                        "prompt": p.get("segment_prompt", ""),
                        "shot_type": p.get("shot_type", ""),
                        "duration_seconds": p.get("duration_seconds", 5.0),
                    }
                    for i, p in enumerate(result.data)
                ]
            else:
                # Backward compat: old dict format with seedance_prompt key
                prompt_data = result.data.get("seedance_prompt", "") if isinstance(result.data, dict) else str(result.data)
                return [
                    {
                        "segment_index": i,
                        "segment_type": seg.get("segment_type", "body"),
                        "prompt": prompt_data,
                    }
                    for i, seg in enumerate(segments)
                ]

        return []

    async def _step_thumbnail_prompts(
        self,
        remix_script: dict[str, Any],
        product: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Generate thumbnail image prompts from remix script."""
        logger.info("s3: step 4 — thumbnail prompts")
        result = await self._registry.execute("gpt-image-thumbnail-prompt", {
            "product_name": product.get("name", "Product"),
            "brand_name": product.get("brand_name", ""),
            "product_usp": (product.get("usps") or [""])[0],
            "hook_type": "pain_point",
            "mood": "lifestyle",
            "scenario": remix_script.get("original_style_preserved", "energetic")[:50],
        })

        if result.success and result.data:
            variants = result.data.get("variants", [])
            return [
                {
                    "style": v.get("style", "default"),
                    "prompt": v.get("prompt", ""),
                    "aspect_ratio": v.get("aspect_ratio", "9:16"),
                }
                for v in variants
            ]

        return []

    # ═══ Step 2: Character Identity ═══

    async def _step_character_identity(
        self,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        """Extract character identity (face reference frames) from video analysis.

        Uses the video-analysis result to locate downloaded video frames, then
        calls the character-identity skill to detect faces and select best-quality
        reference images. Falls back to a minimal identity card on failure.
        """
        logger.info("s3: step 2 — character identity")

        # Extract frame paths from the downloaded video
        frame_paths = await self._extract_video_frames(analysis)
        if not frame_paths:
            logger.warning("s3: character_identity - no frames to analyze, using fallback")
            return {
                "reference_frames": [],
                "attributes": {
                    "face_count": 0,
                    "face_quality_score": 0.0,
                    "dominant_colors": ["#E8C9A0", "#4A3728"],
                    "estimated_age_range": "25-35",
                },
                "_fallback": True,
            }

        try:
            res = await self._registry.execute("character-identity", {
                "frame_paths": frame_paths,
            })
            if res.success and res.data:
                logger.info("s3: character_identity done",
                            faces=res.data.get("attributes", {}).get("face_count"),
                            refs=len(res.data.get("reference_frames", [])))
                return res.data
        except Exception as exc:
            logger.error("s3: character_identity skill failed", error=str(exc))

        # Fallback: return minimal identity card
        logger.warning("s3: character_identity - using fallback identity card")
        return {
            "reference_frames": frame_paths[:3] if frame_paths else [],
            "attributes": {
                "face_count": 1,
                "face_quality_score": 0.5,
                "dominant_colors": ["#E8C9A0", "#4A3728"],
                "estimated_age_range": "25-35",
            },
            "_fallback": True,
        }

    # ═══ Step 4: Storyboards ═══

    async def _step_storyboards(
        self,
        remix_script: dict[str, Any],
    ) -> dict[str, Any]:
        """Build a storyboard dict from the remix script segments.

        Converts each segment into a shot with visual description, shot type,
        camera movement, and timing - matching the schema that keyframe-images
        skill expects.
        """
        logger.info("s3: step 4 - storyboards")
        shots = self._extract_shots(remix_script)
        storyboard = {
            "shots": shots,
            "total_duration": self._compute_total_duration(shots),
        }
        logger.info("s3: storyboards done", shots=len(shots))
        return storyboard

    # ═══ Step 5: Keyframe Images ═══

    async def _step_keyframe_images(
        self,
        storyboard: dict[str, Any],
        identity_card: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate keyframe images for each storyboard shot using GPT-Image.

        Calls the keyframe-images skill which enriches shot visual + camera +
        shot_type with character identity attributes, then generates images
        via GPT-Image. Falls back to placeholder paths on failure.
        """
        logger.info("s3: step 5 - keyframe images",
                     shots=len(storyboard.get("shots", [])))

        try:
            res = await self._registry.execute("keyframe-images", {
                "storyboard": storyboard,
                "identity_card": identity_card,
                "size": "1024x1792",
                "quality": "high",
            })
            if res.success and res.data:
                generated = res.data.get("keyframes_generated", 0)
                logger.info("s3: keyframe images done", generated=generated)
                return res.data
        except Exception as exc:
            logger.error("s3: keyframe-images skill failed", error=str(exc))

        # Fallback: add empty keyframe_image_path to each shot
        logger.warning("s3: keyframe_images - using placeholder paths")
        fallback = dict(storyboard)
        for shot in fallback.get("shots", []):
            shot["keyframe_image_path"] = ""
            shot["keyframe_prompt"] = shot.get("visual", "")
        fallback["keyframes_generated"] = len(fallback.get("shots", []))
        return fallback

    # ═══ Step 8-12: NEW media-producing steps ═══

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
                subprocess.CalledProcessError, Exception) as e:
            logger.warning("s3: _extract_clip_last_frame ffmpeg failed",
                           video_path=str(video_path), error=str(e)[:200])
        return None

    async def _step_seedance_clips(
        self,
        video_prompts: list[dict[str, Any]],
        product: dict[str, Any],
        label: str,
        errors: list[str],
        keyframe_images: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Step 8: invoke seedance-video-generate-skill with bounded concurrency.

        Uses asyncio.Semaphore(4) to cap concurrent API calls to poyo.ai limits.
        Returns a unified dict {clip_paths, clip_details, total_duration} matching S1 format.

        Continuity chain: the last frame of clip N becomes the
        continuity_frame_path for clip N+1, ensuring visual consistency.
        """
        import asyncio

        logger.info("s3: step 8 — seedance clips", count=len(video_prompts))
        if not video_prompts:
            return {"clip_paths": [], "clip_details": [], "total_duration": 0}

        clip_paths: list[str] = []
        clip_details: list[dict[str, Any]] = []
        product_name = product.get("name", "Product")

        # Phase 2 prereq (Oracle review #4): route S3 through ModelRouter.
        # Default S3 model is kling-3-0/standard (character consistency for
        # influencer remix). Without this, S3 inherited POYO_VIDEO_MODEL env
        # default, producing diagnostic R-VENDOR-LOCK mixed-state.
        from src.pipeline.model_router import select_model
        s3_model = select_model("s3")

        # Collect keyframe image paths for image_to_video mode
        kf_image_paths: list[str] = []
        if keyframe_images:
            shots = keyframe_images.get("shots", [])
            for shot in shots:
                path = shot.get("keyframe_image_path", "")
                if path:
                    kf_image_paths.append(path)

        capped = video_prompts[:MAX_CLIPS_PER_DEMO]
        VIDEO_MAX_DURATION = 15
        clip_duration = min(VIDEO_MAX_DURATION, max(4, self._video_duration // max(len(capped), 1)))

        _sem = asyncio.Semaphore(4)

        async def _gen_single(i: int, vp: dict[str, Any], last_frame: str | None) -> tuple[int, Any, str | None]:
            async with _sem:
                prompt = vp.get("segment_prompt", "") or vp.get("prompt", "") or f"{product_name} in natural usage scene, authentic real-world context"
                gen_params: dict[str, Any] = {
                    "prompt": prompt,
                    "duration": clip_duration,
                    "resolution": "720p",
                    "output_label": f"{label}_clip_{i}",
                    "model": s3_model,
                }
                if last_frame:
                    gen_params["continuity_frame_path"] = last_frame
                elif i < len(kf_image_paths) and kf_image_paths[i]:
                    gen_params["image_refs"] = [kf_image_paths[i]]

                res = await self._registry.execute("seedance-video-generate-skill", gen_params)

                # Extract last frame for next clip continuity
                next_frame: str | None = None
                if res.success and res.data:
                    path = res.data.get("video_path", "")
                    if path:
                        frame = self._extract_clip_last_frame(
                            video_path=path,
                            output_dir=str(OUTPUT_DIR / "seedance" / "continuity_frames"),
                        )
                        next_frame = frame
                return i, res, next_frame

        # ── Serial execution with continuity chain (N+1 depends on N's last frame) ──
        # NOTE: Clips cannot be fully parallel because clip N+1 needs clip N's last frame.
        # Semaphore(2) is kept for consistency with S1; here it acts as a no-op
        # since only one clip generates at a time.
        last_frame_path: str | None = None
        for i, vp in enumerate(capped):
            i, res, next_frame = await _gen_single(i, vp, last_frame_path)

            if res.success and res.data:
                path = res.data.get("video_path", "")
                if path:
                    clip_paths.append(path)
                    clip_details.append({
                        "path": path,
                        "duration": res.data.get("duration_seconds", clip_duration),
                        "is_stub": res.data.get("is_stub", False),
                        "verification": res.data.get("verification", {}),
                        "prompt_used": res.data.get("prompt_used", ""),
                    })
                    last_frame_path = next_frame

                if not res.data.get("verification", {}).get("all_ok", True):
                    errors.append(f"clip_{i}_verification_failed: {res.data['verification']}")
            else:
                errors.append(f"clip_{i}_failed: {res.error}")
                last_frame_path = None

        total_duration = sum(d.get("duration", clip_duration) for d in clip_details)
        logger.info("s3: step 8 done", produced=len(clip_paths), capped_to=MAX_CLIPS_PER_DEMO)
        return {"clip_paths": clip_paths, "clip_details": clip_details, "total_duration": total_duration}

    async def _step_tts_audio(
        self,
        remix_script: dict[str, Any],
        language: str,
        errors: list[str],
    ) -> list[str]:
        """Step 6: invoke elevenlabs-tts-skill per script segment."""
        logger.info("s3: step 6 — tts audio")
        segments = remix_script.get("segments", [])
        if not segments:
            return []

        audio_paths: list[str] = []
        for i, seg in enumerate(segments):
            text = (
                seg.get("voiceover")
                or seg.get("remix_description")
                or seg.get("keep_notes")
                or ""
            )
            if not text or len(text) < 2:
                continue

            res = await self._registry.execute("elevenlabs-tts-skill", {
                "text": text,
                "language": language,
            })
            if res.success and res.data:
                path = res.data.get("audio_path", "")
                if path:
                    audio_paths.append(path)
                if not res.data.get("verification", {}).get("all_ok", True):
                    errors.append(f"tts_{i}_verification: {res.data['verification']}")
            else:
                errors.append(f"tts_{i}_failed: {res.error}")

        logger.info("s3: step 6 done", segments=len(audio_paths))
        return audio_paths

    async def _step_thumbnail_images(
        self,
        thumbnail_prompts: list[dict[str, Any]],
        label: str,
        errors: list[str],
    ) -> list[str]:
        """Step 7: invoke gpt-image-generate-skill for each thumbnail prompt."""
        logger.info("s3: step 7 — thumbnail images", count=len(thumbnail_prompts))
        if not thumbnail_prompts:
            return []

        thumbnail_paths: list[str] = []
        capped = thumbnail_prompts[:MAX_THUMBNAILS_PER_DEMO]
        valid = [(i, tp.get("prompt", "")) for i, tp in enumerate(capped) if tp.get("prompt") and len(tp.get("prompt", "")) >= 5]
        if not valid:
            logger.info("s3: step 7 done", thumbnails=0)
            return thumbnail_paths

        thumb_sem = asyncio.Semaphore(2)

        async def _gen_one(i: int, prompt: str) -> tuple[int, Any]:
            async with thumb_sem:
                res = await self._registry.execute("gpt-image-generate-skill", {
                    "prompt": prompt,
                    "size": "1024x1792",
                    "quality": "high",
                    "image_id": f"{label}_thumb_{i}",
                })
                return i, res

        tasks = [_gen_one(i, prompt) for i, prompt in valid]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for raw in raw_results:
            if isinstance(raw, Exception):
                errors.append(f"thumb_failed_with_exception: {raw}")
                continue
            if not isinstance(raw, tuple):
                continue
            i, res = raw
            if res.success and res.data:
                path = res.data.get("image_path", "")
                if path:
                    thumbnail_paths.append(path)
                if not res.data.get("verification", {}).get("all_ok", True):
                    errors.append(f"thumb_{i}_verification: {res.data['verification']}")
            else:
                errors.append(f"thumb_{i}_failed: {res.error}")

        logger.info("s3: step 7 done", thumbnails=len(thumbnail_paths))
        return thumbnail_paths

    async def _step_assemble_final(
        self,
        remix_script: dict[str, Any],
        captions: list[dict[str, Any]],
        audio_paths: list[str],
        clip_paths: list[str],
        label: str,
    ) -> SkillResult:
        """Step 8: invoke remotion-assemble-skill to produce final mp4."""
        logger.info("s3: step 8 — assemble final video")
        shots = self._extract_shots(remix_script)
        return await self._registry.execute("remotion-assemble-skill", {
            "shots": shots,
            "captions": captions,
            "audio_paths": audio_paths,
            "clip_paths": clip_paths,
            "brand_guidelines": {},
            "output_label": label,
            "total_duration": self._compute_total_duration(shots),
        })

    async def _step_audit(
        self,
        video_path: str,
        audio_paths: list[str],
        thumbnail_paths: list[str],
        clip_paths: list[str],
        product: dict[str, Any],
        remix_script: dict[str, Any],
        thumbnail_prompts: list[dict[str, Any]],
        language: str,
    ) -> SkillResult:
        """Step 9: invoke media-quality-audit-skill."""
        logger.info("s3: step 9 — audit")
        # Compose a flat script_text for content-mention checks
        script_text = " ".join([
            seg.get("voiceover", "") or seg.get("remix_description", "") or seg.get("keep_notes", "")
            for seg in remix_script.get("segments", [])
        ])
        expected_duration = self._compute_total_duration(self._extract_shots(remix_script))

        return await self._registry.execute("media-quality-audit-skill", {
            "video_path": video_path,
            "audio_paths": audio_paths,
            "thumbnail_paths": thumbnail_paths,
            "clip_paths": clip_paths,
            "expected_product_name": product.get("name", ""),
            "expected_duration_seconds": expected_duration,
            "expected_language": language,
            "script_text": script_text,
            "thumbnail_prompts": thumbnail_prompts,
        })

    # ═══ Helpers ═══

    @staticmethod
    def _extract_shots(remix_script: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert remix_script segments into Storyboard.shots schema."""
        segments = remix_script.get("segments", [])
        shots = []
        cursor = 0.0
        for i, seg in enumerate(segments):
            duration = float(seg.get("duration_seconds", 10))
            shots.append({
                "id": i + 1,
                "start_time": cursor,
                "end_time": cursor + duration,
                "text_overlay": (seg.get("voiceover", "") or seg.get("remix_description", ""))[:60],
                "visual": seg.get("remix_description", "") or seg.get("keep_notes", ""),
            })
            cursor += duration
        return shots

    @staticmethod
    def _extract_captions(remix_script: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert remix_script segments into caption entries."""
        segments = remix_script.get("segments", [])
        captions = []
        cursor = 0.0
        for seg in segments:
            duration = float(seg.get("duration_seconds", 10))
            text = seg.get("voiceover", "") or seg.get("remix_description", "")
            if text:
                # Split long text into ~3-second chunks for caption pacing
                chunks = S3InfluencerRemixPipeline._split_caption_text(text, duration)
                chunk_dur = duration / max(len(chunks), 1)
                for i, chunk in enumerate(chunks):
                    captions.append({
                        "start_time": cursor + i * chunk_dur,
                        "end_time": cursor + (i + 1) * chunk_dur,
                        "text": chunk,
                    })
            cursor += duration
        return captions

    @staticmethod
    def _split_caption_text(text: str, total_duration: float) -> list[str]:
        """Split caption text into ~3 second chunks of visible text."""
        # Roughly 12-15 chars per second of speech is comfortable
        max_chars_per_chunk = 60
        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        for word in words:
            current.append(word)
            if len(" ".join(current)) >= max_chars_per_chunk:
                chunks.append(" ".join(current))
                current = []
        if current:
            chunks.append(" ".join(current))
        return chunks or [text]

    @staticmethod
    def _compute_total_duration(shots: list[dict[str, Any]]) -> float:
        if not shots:
            return 30.0
        return max((float(s.get("end_time", 0)) for s in shots), default=30.0)

    def _map_segment_to_video_type(self, seg_type: str) -> str:
        """Map remix segment type to SeedancePromptSkill video_type."""
        mapping = {
            "hook": "product_showcase",
            "intro": "lifestyle",
            "body": "feature_highlight",
            "transition": "lifestyle",
            "pitch": "testimonials",
            "demo": "tutorial_demo",
            "testimonial": "testimonials",
            "cta": "product_showcase",
            "outro": "brand_story",
        }
        return mapping.get(seg_type, "product_showcase")

    # ═══ Frame extraction ═══

    async def _extract_video_frames(self, analysis: dict[str, Any]) -> list[str]:
        """Extract key frames from the downloaded video for character identity.

        Tries to locate the downloaded video from the analysis result, then uses
        ffmpeg to extract evenly-spaced frames. Falls back to returning an empty
        list if the video can't be found or ffmpeg is unavailable.
        """
        video_url = analysis.get("video_url", "")
        if not video_url:
            logger.warning("extract_frames: no video_url in analysis")
            return []

        # Try to locate the downloaded video in the standard output directory
        download_dir = OUTPUT_DIR / "downloaded_videos"
        candidates: list[Path] = []
        if download_dir.exists():
            candidates = sorted(download_dir.iterdir())

        if not candidates:
            logger.warning("extract_frames: no downloaded video files found")
            return []

        # Pick the most recent video file
        video_path = candidates[-1]
        logger.info("extract_frames: using video", path=str(video_path))

        frames_dir = OUTPUT_DIR / "character_identity_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        frame_paths: list[str] = []

        # Try ffmpeg frame extraction
        try:
            import asyncio

            duration = analysis.get("duration_seconds", 15.0)
            # Extract ~6 evenly-spaced frames
            num_frames = min(6, max(3, int(duration // 3)))
            sample_interval = max(duration / num_frames, 0.5)

            for i in range(num_frames):
                timestamp = i * sample_interval
                out_path = frames_dir / f"frame_{i:03d}.jpg"

                result = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y",
                    "-ss", str(timestamp),
                    "-i", str(video_path),
                    "-vframes", "1",
                    "-q:v", "2",
                    str(out_path),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await result.wait()

                if out_path.exists() and out_path.stat().st_size > 0:
                    frame_paths.append(str(out_path))

            if frame_paths:
                logger.info("extract_frames: extracted frames", count=len(frame_paths))
                return frame_paths

        except (FileNotFoundError, Exception) as exc:
            logger.warning("extract_frames: ffmpeg failed or unavailable", error=str(exc))

        # Fallback: if we can't extract frames, return empty
        logger.warning("extract_frames: no frames extracted")
        return []
