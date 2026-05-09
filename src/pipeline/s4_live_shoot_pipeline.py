"""S4 E2E pipeline — Live Shoot to Video.

Supports two execution modes:
  • StepRunner mode: run_step(step_name, state) — used by step-by-step / auto pipelines
  • Legacy mode: run(footage_assets, product_info, ...) — backwards-compatible full run

Steps (7):
  1. scripts          — script-writer-skill from footage + product
  2. video_prompts    — seedance-video-prompt per script segment
  3. thumbnails       — gpt-image-thumbnail-prompt variants
  4. seedance_clips   — generate video clips from prompts
  5. tts_audio        — synthesize voiceover audio
  6. assemble_final   — assemble final video via Remotion
  7. audit            — quality audit
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from src.config import DEFAULT_LANGUAGES
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner
from src.skills.registry import SkillRegistry

import src.skills.script_writer  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.thumbnail_prompt  # noqa: F401

logger = structlog.get_logger()

# Caps for demo runs
MAX_SCRIPTS_PER_RUN = 3


class S4LiveShootPipeline:
    """Orchestrate S4 live-shoot to video pipeline."""

    # ═══ StepRunner interface ═══

    async def run_step(self, step_name: str, state: dict[str, Any]) -> Any:
        """Execute a single pipeline step given the current state dict.

        Entry point used by StepRunner. Reads inputs from state, calls the
        appropriate _step_* method, and returns the step output.
        """
        config = state["config"]
        reg = SkillRegistry()
        steps = state["steps"]
        errors = state["errors"]

        if step_name == "scripts":
            return await self._step_scripts(reg, config, steps, errors)

        if step_name == "video_prompts":
            return await self._step_video_prompts(reg, config, steps, errors)

        if step_name == "thumbnails":
            return await self._step_thumbnails(reg, config, steps, errors)

        if step_name == "seedance_clips":
            prompts = self._get_step_output(steps, "video_prompts") or []
            return await self._step_seedance_clips(
                reg=reg,
                video_prompts=prompts,
                product_name=config.get("product_name", "Product"),
                label=config.get("output_label", "s4"),
                errors=errors,
            )

        if step_name == "tts_audio":
            scripts = self._get_step_output(steps, "scripts") or []
            return await self._step_tts_audio(
                reg=reg,
                scripts=scripts,
                language=config.get("target_language", "en"),
                errors=errors,
            )

        if step_name == "assemble_final":
            scripts = self._get_step_output(steps, "scripts") or []
            tts_output = self._get_step_output(steps, "tts_audio") or {}
            audio_paths = tts_output.get("audio_paths", []) if isinstance(tts_output, dict) else []
            lyrics_paths = tts_output.get("lyrics_paths", []) if isinstance(tts_output, dict) else []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else []
            return await self._step_assemble_final(
                reg=reg,
                scripts=scripts,
                audio_paths=audio_paths,
                lyrics_paths=lyrics_paths,
                clip_paths=clip_paths,
                brand_guidelines=config.get("brand_guidelines") or {},
                label=config.get("output_label", "s4"),
                errors=errors,
            )

        if step_name == "audit":
            final_video = ""
            assemble_output = self._get_step_output(steps, "assemble_final")
            if isinstance(assemble_output, tuple) and len(assemble_output) > 0:
                final_video = assemble_output[0]
            elif isinstance(assemble_output, dict):
                final_video = assemble_output.get("video_path", "")
            tts_output = self._get_step_output(steps, "tts_audio") or {}
            audio_paths = tts_output.get("audio_paths", []) if isinstance(tts_output, dict) else []
            thumbnail_sets = self._get_step_output(steps, "thumbnails") or []
            product_name = config.get("product_name", "Product")
            scripts = self._get_step_output(steps, "scripts") or []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else []
            return await self._step_audit(
                reg=reg,
                video_path=final_video,
                audio_paths=audio_paths,
                thumbnail_paths=[],
                clip_paths=clip_paths,
                product_name=product_name,
                scripts=scripts,
                thumbnail_sets=thumbnail_sets,
                language=config.get("target_language", "en"),
                errors=errors,
            )

        raise ValueError(f"Unknown step name: {step_name}")

    async def _step_scripts(
        self,
        reg: SkillRegistry,
        config: dict[str, Any],
        steps: dict[str, Any],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Generate scripts from footage descriptions + product info."""
        footage_assets = config.get("footage_assets", [])
        product_info = config.get("product_info", {})
        topic = config.get("topic", "")
        platforms = config.get("target_platforms", ["tiktok", "shopify"])
        product_name = config.get("product_name") or product_info.get("name", "Product")

        brief_data = {
            "id": "LIVE-001",
            "topic": topic or product_name,
            "product_name": product_name,
            "brand_name": product_info.get("brand_name", ""),
            "usps": product_info.get("usps", ["quality"]),
            "hook_type": "scene_drop",
            "video_type": "tutorial",
            "target_platforms": platforms,
        }

        scr = await reg.execute("script-writer-skill", {
            "briefs": [brief_data],
            "brand_guidelines": {"footage_available": len(footage_assets)},
            "target_languages": DEFAULT_LANGUAGES,
        })
        if scr.success and scr.data:
            scripts = scr.data.get("scripts", [])
            logger.info("s4: scripts complete", scripts=len(scripts))
            return scripts

        errors.append(f"scripts_failed: {scr.error}")
        logger.warning("s4: script generation failed", error=scr.error)
        return []

    async def _step_video_prompts(
        self,
        reg: SkillRegistry,
        config: dict[str, Any],
        steps: dict[str, Any],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Generate Seedance video prompts referencing footage assets.

        Returns a flat list of prompt dicts (one per segment) — same shape as
        S1's _step_video_prompts so downstream _step_seedance_clips can use
        vp.get("segment_prompt") directly.
        """
        scripts_dict = self._get_step_output(steps, "scripts") or []
        footage_assets = config.get("footage_assets", [])

        all_prompts: list[dict[str, Any]] = []
        for script in scripts_dict[:MAX_SCRIPTS_PER_RUN]:
            segs = script.get("segments", [])
            script_segs = []
            for i, s in enumerate(segs):
                desc = s.get("visual_description", "")
                footage_ref = ""
                if footage_assets:
                    fa = footage_assets[min(i, len(footage_assets) - 1)]
                    footage_ref = f"@material '{fa.get('filename', 'footage')}'"
                script_segs.append({
                    "type": s.get("segment_type", "body"),
                    "description": f"{footage_ref} {desc}" if footage_ref else desc,
                    "duration_seconds": s.get("end_time", 5) - s.get("start_time", 0),
                })

            vp = await reg.execute("seedance-video-prompt", {
                "script_segments": script_segs,
                "product_name": script.get("product_name", "Product"),
            })
            if vp.success and vp.data and isinstance(vp.data, list):
                for p_dict in vp.data:
                    p_dict["script_id"] = script.get("id", "")
                    p_dict["product_name"] = script.get("product_name", "Product")
                all_prompts.extend(vp.data)
            else:
                errors.append(f"video_prompt_{script.get('id', '?')}_failed: {vp.error}")

        logger.info("s4: video prompts complete", prompts=len(all_prompts))
        return all_prompts

    async def _step_thumbnails(
        self,
        reg: SkillRegistry,
        config: dict[str, Any],
        steps: dict[str, Any],
        errors: list[str],
    ) -> list[dict[str, Any]]:
        """Generate thumbnail prompt variants per script."""
        scripts_dict = self._get_step_output(steps, "scripts") or []
        product_info = config.get("product_info", {})
        brand_name = config.get("brand_name") or product_info.get("brand_name", "")

        thumbnails: list[dict[str, Any]] = []
        for script in scripts_dict[:MAX_SCRIPTS_PER_RUN]:
            tp = await reg.execute("gpt-image-thumbnail-prompt", {
                "product_name": script.get("product_name", "Product"),
                "hook_text": script.get("hook", "Real footage, real results"),
                "brand_name": brand_name,
                "mood": "authentic",
            })
            if tp.success and tp.data:
                thumbnails.append({
                    "script_id": script.get("id"),
                    "variants": tp.data.get("variants", []),
                })
            else:
                errors.append(f"thumb_prompt_{script.get('id', '?')}_failed: {tp.error}")

        logger.info("s4: thumbnails complete", sets=len(thumbnails))
        return thumbnails

    @staticmethod
    def _get_step_output(steps: dict[str, Any], step_name: str) -> Any:
        """Retrieve output from a step, preferring edited_output if edited."""
        step_data = steps.get(step_name, {})
        if step_data.get("edited") and step_data.get("edited_output") is not None:
            return step_data["edited_output"]
        return step_data.get("output")

    # ═══ Video synthesis steps (added to complete the video pipeline) ═══

    async def _step_seedance_clips(
        self,
        reg: SkillRegistry,
        video_prompts: list[dict[str, Any]],
        product_name: str,
        label: str,
        errors: list[str],
    ) -> dict[str, Any]:
        """Generate video clips from Seedance prompts.

        S4 has no keyframe_images step, so clips generate from text prompts only.
        """
        import asyncio
        from src.config import OUTPUT_DIR

        clip_paths: list[str] = []
        clip_details: list[dict[str, Any]] = []
        _sem = asyncio.Semaphore(2)

        async def _gen(i: int, vp: dict[str, Any]) -> tuple[int, Any]:
            async with _sem:
                prompt_text = vp.get("prompt", "") or vp.get("segment_prompt", "")
                if isinstance(prompt_text, dict):
                    prompt_text = prompt_text.get("prompt", "")
                if not prompt_text:
                    prompt_text = f"{product_name} in natural usage scene"
                res = await reg.execute("seedance-video-generate-skill", {
                    "prompt": prompt_text,
                    "duration": 5,
                    "resolution": "720p",
                    "output_label": f"{label}_seg_{i}",
                })
                return i, res

        tasks = [_gen(i, vp) for i, vp in enumerate(video_prompts)]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for raw in raw_results:
            if isinstance(raw, Exception):
                errors.append(f"clip_failed_with_exception: {raw}")

        for i, skill_result in sorted(
            [r for r in raw_results if isinstance(r, tuple)],
            key=lambda x: x[0],
        ):
            if skill_result.success and skill_result.data:
                p = skill_result.data.get("video_path", "")
                if p:
                    clip_paths.append(p)
                    clip_details.append({
                        "path": p,
                        "is_stub": skill_result.data.get("is_stub", False),
                        "verification": skill_result.data.get("verification", {}),
                    })
            else:
                errors.append(f"clip_{i}_failed: {skill_result.error}")

        return {
            "clip_paths": clip_paths,
            "clip_details": clip_details,
            "total_duration": sum(d.get("duration", 5) for d in clip_details),
        }

    async def _step_tts_audio(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        language: str,
        errors: list[str],
    ) -> dict[str, Any]:
        """Generate voiceover audio from script segments."""
        audio_paths: list[str] = []
        lyrics_paths: list[str] = []

        for script in scripts[:MAX_SCRIPTS_PER_RUN]:
            voiceover_parts: list[str] = []
            for seg in script.get("segments", []):
                text = seg.get("voiceover") or seg.get("description") or ""
                if text and len(text) >= 2:
                    voiceover_parts.append(text.strip())
            if not voiceover_parts:
                continue
            merged_text = "\n".join(voiceover_parts)
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
            else:
                errors.append(f"tts_failed: {res.error}")

        return {"audio_paths": audio_paths, "lyrics_paths": lyrics_paths}

    async def _step_assemble_final(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        audio_paths: list[str],
        lyrics_paths: list[str],
        clip_paths: list[str],
        brand_guidelines: dict[str, Any],
        label: str,
        errors: list[str],
    ) -> tuple[str, str]:
        """Assemble final video via Remotion."""
        # Derive shots from scripts (S4 has no storyboards)
        shots: list[dict[str, Any]] = []
        for script in scripts:
            for seg in script.get("segments", []):
                shots.append({
                    "id": len(shots) + 1,
                    "start_time": seg.get("start_time", 0),
                    "end_time": seg.get("end_time", 5),
                    "text_overlay": seg.get("text_overlay", ""),
                    "visual": seg.get("visual_description", ""),
                })

        captions = []
        for script in scripts:
            for seg in script.get("segments", []):
                text = seg.get("text_overlay", "")
                if text:
                    captions.append({
                        "start_time": seg.get("start_time", 0),
                        "end_time": seg.get("end_time", 5),
                        "text": text,
                    })

        total_duration = max((s.get("end_time", 0) for s in shots), default=30.0)

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
        """Run quality audit on final outputs."""
        script_text = " ".join([
            (seg.get("voiceover", "") or seg.get("description", ""))
            for s in scripts
            for seg in s.get("segments", [])
        ])
        flat_thumb_prompts: list[dict[str, Any]] = []
        for ts in thumbnail_sets:
            for v in ts.get("variants", []):
                if isinstance(v, dict):
                    flat_thumb_prompts.append(v)

        expected_duration = sum(
            s.get("end_time", 5) - s.get("start_time", 0)
            for sc in scripts
            for s in sc.get("segments", [])
        )

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

    # ═══ Backwards-compatible full pipeline ═══

    async def run(
        self,
        footage_assets: list[dict[str, Any]],
        product_info: dict[str, Any],
        topic: str = "",
        target_platforms: list[str] | None = None,
    ) -> dict[str, Any]:
        """Run the full S4 pipeline end-to-end.

        Backwards-compatible: uses StepRunner internally but returns the same
        result dict shape as before.
        """
        platforms = target_platforms or ["tiktok", "shopify"]
        product_name = product_info.get("name", "Product")
        brand_name = product_info.get("brand_name", "")
        label = f"s4_{int(time.time())}"

        config = {
            "footage_assets": footage_assets,
            "product_info": product_info,
            "topic": topic,
            "target_platforms": platforms,
            "product_name": product_name,
            "brand_name": brand_name,
        }

        state_manager = PipelineStateManager()
        runner = StepRunner(state_manager)
        label = await runner.init_state(config=config, mode="auto", label=label, scenario="s4")
        final_state = await runner.resume(label)

        # Convert final state back to the legacy result dict
        steps = final_state.get("steps", {})
        seedance_out = self._get_step_output(steps, "seedance_clips") or {}
        assemble_out = self._get_step_output(steps, "assemble_final")
        final_video = ""
        if isinstance(assemble_out, tuple) and len(assemble_out) > 0:
            final_video = assemble_out[0]
        elif isinstance(assemble_out, dict):
            final_video = assemble_out.get("video_path", "")

        result: dict[str, Any] = {
            "success": True,
            "scenario": "s4_live_shoot",
            "scripts": self._get_step_output(steps, "scripts") or [],
            "video_prompts": self._get_step_output(steps, "video_prompts") or [],
            "thumbnail_sets": self._get_step_output(steps, "thumbnails") or [],
            "seedance_clips": seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else [],
            "final_video_path": final_video,
            "steps_completed": 7,
            "errors": final_state.get("errors", []),
        }

        if final_state.get("pipeline_degraded"):
            result["success"] = False
            result["errors"] = final_state.get("errors", ["Pipeline degraded"])

        if not result["scripts"]:
            result["success"] = False
            result.setdefault("errors", []).append("Script generation failed")

        logger.info(
            "s4: pipeline complete",
            scripts=len(result["scripts"]),
            prompts=len(result["video_prompts"]),
            thumbnails=len(result["thumbnail_sets"]),
            errors=len(result.get("errors", [])),
        )
        return result
