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

import asyncio
import time
from typing import Any

import structlog

import src.skills.continuity_storyboard_grid  # noqa: F401
import src.skills.script_writer  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.thumbnail_prompt  # noqa: F401
from src.config import DEFAULT_LANGUAGES
from src.pipeline.artifact_paths import extract_assemble_paths
from src.pipeline.continuity_utils import (
    build_continuity_audit_summary,
    build_transitions_from_clip_details,
)
from src.pipeline.step_utils import get_step_output
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import StepRunner
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

# Caps for demo runs
MAX_SCRIPTS_PER_RUN = 3


class S4LiveShootPipeline:
    """Orchestrate S4 live-shoot to video pipeline."""

    # ═══ StepRunner interface ═══

    @staticmethod
    def _validate_footage_assets(
        footage_assets: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """TODO-D10 PR3: split footage into valid + invalid lists.

        An asset is invalid when it has no filename / path / url, OR carries
        an explicit `is_corrupted=True` marker (set by upload/ffprobe step),
        OR its file_size is 0. The split keeps validation cheap (no ffprobe
        call here) — heavier checks belong to the upload pipeline.
        """
        valid: list[dict[str, Any]] = []
        invalid: list[dict[str, Any]] = []
        for fa in footage_assets:
            if not isinstance(fa, dict):
                invalid.append({"raw": fa, "reason": "not_a_dict"})
                continue
            if fa.get("is_corrupted") is True:
                invalid.append({**fa, "reason": "is_corrupted"})
                continue
            if fa.get("file_size") == 0:
                invalid.append({**fa, "reason": "zero_size"})
                continue
            has_ref = bool(
                fa.get("filename")
                or fa.get("path")
                or fa.get("url")
                or fa.get("file_url")
                or fa.get("asset_id"),
            )
            if not has_ref:
                invalid.append({**fa, "reason": "no_reference"})
                continue
            valid.append(fa)
        return valid, invalid

    @staticmethod
    def _extract_stock_footage_urls(brand_guidelines: dict[str, Any]) -> list[str]:
        """TODO-D10 PR3: read brand_package.stock_footage_urls if present.

        Backward-compatible: if brand_guidelines is missing or lacks the
        key, returns []. Callers treat [] as 'no stock fallback available'.
        """
        if not isinstance(brand_guidelines, dict):
            return []
        urls = brand_guidelines.get("stock_footage_urls") or []
        if not isinstance(urls, list):
            return []
        return [u for u in urls if isinstance(u, str) and u]

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

        if step_name == "continuity_storyboard_grid":
            scripts = self._get_step_output(steps, "scripts") or []
            product_name = config.get("product_name", "Product")
            return await self._step_continuity_storyboard_grid(
                reg=reg,
                scripts=scripts,
                product_name=product_name,
                topic=config.get("topic", ""),
                product_info=config.get("product_info", {}),
                brand_guidelines=config.get("brand_guidelines", {}),
                errors=errors,
            )

        if step_name == "video_prompts":
            continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
            return await self._step_video_prompts(
                reg=reg, config=config, steps=steps, errors=errors,
                continuity_storyboard_grid=continuity_grid,
            )

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
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            return await self._step_assemble_final(
                reg=reg,
                scripts=scripts,
                audio_paths=audio_paths,
                lyrics_paths=lyrics_paths,
                clip_paths=clip_paths,
                clip_details=clip_details,
                brand_guidelines=config.get("brand_guidelines") or {},
                label=config.get("output_label", "s4"),
                errors=errors,
            )

        if step_name == "audit":
            assemble_output = self._get_step_output(steps, "assemble_final")
            final_video, _ = extract_assemble_paths(assemble_output)
            tts_output = self._get_step_output(steps, "tts_audio") or {}
            audio_paths = tts_output.get("audio_paths", []) if isinstance(tts_output, dict) else []
            thumbnail_sets = self._get_step_output(steps, "thumbnails") or []
            product_name = config.get("product_name", "Product")
            scripts = self._get_step_output(steps, "scripts") or []
            seedance_out = self._get_step_output(steps, "seedance_clips") or {}
            clip_paths = seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else []
            clip_details = seedance_out.get("clip_details", []) if isinstance(seedance_out, dict) else []
            continuity_grid = self._get_step_output(steps, "continuity_storyboard_grid") or {}
            return await self._step_audit(
                reg=reg,
                video_path=final_video,
                audio_paths=audio_paths,
                thumbnail_paths=[],
                clip_paths=clip_paths,
                clip_details=clip_details,
                product_name=product_name,
                scripts=scripts,
                thumbnail_sets=thumbnail_sets,
                language=config.get("target_language", "en"),
                errors=errors,
                continuity_grid=continuity_grid,
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
        raw_footage = config.get("footage_assets", [])
        product_info = config.get("product_info", {})
        topic = config.get("topic", "")
        platforms = config.get("target_platforms", ["tiktok", "shopify"])
        product_name = config.get("product_name") or product_info.get("name", "Product")
        brand_guidelines = config.get("brand_guidelines") or {}

        valid_footage, invalid_footage = self._validate_footage_assets(raw_footage)
        all_invalid = bool(raw_footage) and not valid_footage
        soft_signal: dict[str, Any] | None = None

        if all_invalid:
            stock_urls = self._extract_stock_footage_urls(brand_guidelines)
            if stock_urls:
                stock_assets = [{"filename": u, "url": u, "is_stock": True} for u in stock_urls]
                config["footage_assets"] = stock_assets
                soft_signal = {
                    "_soft_degraded": True,
                    "_degraded_reason": "footage_invalid_using_stock_fallback",
                    "_degraded_detail": (
                        f"all {len(raw_footage)} uploaded footage invalid; "
                        f"using {len(stock_assets)} stock asset(s) from brand_guidelines"
                    ),
                }
                logger.warning(
                    "s4: all footage invalid, using stock fallback",
                    invalid_count=len(invalid_footage),
                    stock_count=len(stock_assets),
                )
            else:
                config["footage_assets"] = []
                soft_signal = {
                    "_soft_degraded": True,
                    "_degraded_reason": "footage_invalid_no_stock_fallback",
                    "_degraded_detail": (
                        f"all {len(raw_footage)} uploaded footage invalid; "
                        "no brand_guidelines.stock_footage_urls available; "
                        "proceeding without footage references"
                    ),
                }
                logger.warning(
                    "s4: all footage invalid, no stock fallback",
                    invalid_count=len(invalid_footage),
                )
        elif invalid_footage:
            config["footage_assets"] = valid_footage
            logger.info(
                "s4: filtered invalid footage assets",
                valid=len(valid_footage),
                invalid=len(invalid_footage),
            )

        footage_assets_used = config.get("footage_assets", [])

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
            "brand_guidelines": {"footage_available": len(footage_assets_used)},
            "target_languages": DEFAULT_LANGUAGES,
            "video_duration": config.get("video_duration", 30),
        })
        if scr.success and scr.data:
            scripts = scr.data.get("scripts", [])
            logger.info("s4: scripts complete", scripts=len(scripts))
            if soft_signal is not None and scripts:
                scripts = [{**soft_signal, **scripts[0]}, *scripts[1:]]
            elif soft_signal is not None:
                scripts = [soft_signal]
            return scripts

        errors.append(f"scripts_failed: {scr.error}")
        logger.warning("s4: script generation failed", error=scr.error)
        if soft_signal is not None:
            return [soft_signal]
        return []

    async def _step_continuity_storyboard_grid(
        self,
        reg: SkillRegistry,
        scripts: list[dict[str, Any]],
        product_name: str,
        topic: str,
        product_info: dict[str, Any],
        brand_guidelines: dict[str, Any],
        errors: list[str],
    ) -> dict[str, Any]:
        """Build continuity clip groups from S4 scripts.

        Delegates to continuity-storyboard-grid skill, falling back to
        synthetic clip_groups derived from script segments.
        """
        logger.info("s4: step 1b — continuity storyboard grid")

        # Derive shots from scripts for the skill
        shots: list[dict[str, Any]] = []
        for script in scripts[:MAX_SCRIPTS_PER_RUN]:
            for seg in script.get("segments", []):
                shots.append({
                    "id": len(shots) + 1,
                    "start_time": seg.get("start_time", 0),
                    "end_time": seg.get("end_time", 5),
                    "text_overlay": seg.get("text_overlay", ""),
                    "visual": seg.get("visual_description", ""),
                    "shot_type": seg.get("segment_type", "body"),
                })

        stock_urls = self._extract_stock_footage_urls(brand_guidelines)
        raw_visual_constraints = brand_guidelines.get("visual_constraints")
        visual_constraints: list[str] = []
        if isinstance(raw_visual_constraints, str) and raw_visual_constraints.strip():
            visual_constraints.extend(
                part.strip()
                for part in raw_visual_constraints.replace(";", ",").split(",")
                if part.strip()
            )
        elif isinstance(raw_visual_constraints, list):
            visual_constraints.extend(
                item.strip()
                for item in raw_visual_constraints
                if isinstance(item, str) and item.strip()
            )
        if stock_urls:
            visual_constraints.append(
                f"use authentic live-shoot continuity grounded in {len(stock_urls)} approved stock footage reference(s)"
            )

        product_catalog = {
            "product_name": product_name,
            "name": product_name,
            "category": "product",
            "brand_name": (
                product_info.get("brand_name")
                if isinstance(product_info.get("brand_name"), str)
                else brand_guidelines.get("brand_name", "")
            ),
            "usage_scenario": topic or product_info.get("usage_scenario", ""),
            "usps": product_info.get("usps", []),
            "colors": brand_guidelines.get("colors") or {},
            "tone_of_voice": brand_guidelines.get("tone_of_voice") or {},
            "voice_guidelines": brand_guidelines.get("voice_guidelines", ""),
            "values": brand_guidelines.get("values") or brand_guidelines.get("brand_values") or [],
            "visual_constraints": visual_constraints,
        }
        res = await reg.execute("continuity-storyboard-grid", {
            "product_catalog": product_catalog,
            "storyboards": [{"shots": shots}] if shots else [],
            "storyboard_grid": "12",
            "clip_group_size": 3,
            "transition_style": "match_cut",
        })
        if res.success and res.data and isinstance(res.data, dict):
            if res.metadata.get("is_fallback") is True:
                logger.warning(
                    "s4: continuity grid fallback used",
                    reason=res.metadata.get("fallback_reason", ""),
                )
                return {
                    **res.data,
                    "_soft_degraded": True,
                    "_degraded_reason": "continuity_skill_fallback",
                    "_degraded_detail": str(
                        res.metadata.get("fallback_reason", "fallback_used")
                    )[:200],
                    "degraded": True,
                }
            logger.info("s4: continuity grid done", clip_groups=len(res.data.get("clip_groups", [])))
            return res.data
        errors.append(f"continuity_storyboard_grid_failed: {res.error}")
        return {
            "grid_type": "12-grid",
            "product_name": product_name,
            "visual_identity": {},
            "micro_shots": [],
            "clip_groups": self._s4_fallback_clip_groups(
                shots,
                product_name,
                topic=topic,
                stock_footage_count=len(stock_urls),
            ),
            "_soft_degraded": True,
            "_degraded_reason": "continuity_skill_execution_failed",
            "_degraded_detail": str(res.error or "unknown")[:200],
            "degraded": True,
        }

    @staticmethod
    def _s4_fallback_clip_groups(
        shots: list[dict[str, Any]],
        product_name: str,
        topic: str = "",
        stock_footage_count: int = 0,
    ) -> list[dict[str, Any]]:
        """Derive clip_groups from script shots when skill fails."""
        groups: list[dict[str, Any]] = []
        group_size = 3
        for idx in range(0, len(shots), group_size):
            chunk = shots[idx:idx + group_size]
            group_idx = len(groups) + 1
            shot_indices = list(range(idx + 1, idx + len(chunk) + 1))
            duration = sum(
                float(s.get("end_time", 0)) - float(s.get("start_time", 0))
                for s in chunk
            )
            duration = max(duration, 1.0)
            prompt_parts = [
                (s.get("visual", "") or s.get("text_overlay", ""))[:80]
                for s in chunk
            ]
            topic_clause = f" Topic: {topic}." if topic else ""
            stock_clause = (
                f" Preserve continuity against {stock_footage_count} approved stock/live reference asset(s)."
                if stock_footage_count > 0
                else ""
            )
            group = {
                "clip_index": group_idx,
                "shot_indices": shot_indices,
                "duration": duration,
                "purpose": f"group_{group_idx}",
                "seedance_prompt": (
                    f"{product_name} live shoot scene: {'; '.join(p for p in prompt_parts if p)}. "
                    f"Natural lighting, authentic usage footage.{topic_clause}{stock_clause}"
                ),
                "transition_type": "match_cut",
            }
            if idx + group_size < len(shots):
                group["transition_to_next"] = "match cut to next scene"
            groups.append(group)
        return groups

    async def _step_video_prompts(
        self,
        reg: SkillRegistry,
        config: dict[str, Any],
        steps: dict[str, Any],
        errors: list[str],
        continuity_storyboard_grid: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate Seedance video prompts referencing footage assets.

        Returns a flat list of prompt dicts (one per segment) — same shape as
        S1's _step_video_prompts so downstream _step_seedance_clips can use
        vp.get("segment_prompt") directly.
        """
        # Priority: continuity_grid clip_groups > segment-based fallback
        if continuity_storyboard_grid and continuity_storyboard_grid.get("clip_groups"):
            result = await reg.execute("seedance-video-prompt", {
                "continuity_storyboard_grid": continuity_storyboard_grid,
                "product_name": config.get("product_name", "Product"),
            })
            if result.success and result.data and isinstance(result.data, list):
                return result.data
            logger.warning("s4: continuity video_prompts failed, falling back", error=result.error)

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
        """Retrieve output from a step, preferring edited_output if edited.

        Delegates to the canonical shared implementation in step_utils.py.
        """
        return get_step_output(steps, step_name)

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

        Phase 2 prereq (Oracle review #4): route through ModelRouter.
        Default S4 model is seedance-2-fast (cheap turbo for live-shoot iteration).
        """
        from src.pipeline.model_router import select_model

        s4_model = select_model("s4")
        clip_paths: list[str] = []
        clip_details: list[dict[str, Any]] = []

        # P0-2: S4 clips 并发化 — Live Shoot 场景各 clip 为独立使用场景，无需 clip-to-clip 连续性
        _seedance_sem = asyncio.Semaphore(4)

        async def _gen_concurrent(i: int, vp: dict[str, Any]) -> tuple[int, Any]:
            async with _seedance_sem:
                prompt_text = vp.get("prompt", "") or vp.get("segment_prompt", "")
                if isinstance(prompt_text, dict):
                    prompt_text = prompt_text.get("prompt", "")
                if not prompt_text:
                    prompt_text = f"{product_name} in natural usage scene"
                raw_duration = vp.get("duration_seconds", 5)
                try:
                    duration = int(float(raw_duration))
                except (TypeError, ValueError):
                    duration = 5
                duration = max(4, min(duration, 15))
                params: dict[str, Any] = {
                    "prompt": prompt_text,
                    "duration": duration,
                    "resolution": "720p",
                    "output_label": f"{label}_seg_{i}",
                    "model": s4_model,
                }
                res = await reg.execute("seedance-video-generate-skill", params)
                return i, res

        tasks = [_gen_concurrent(i, vp) for i, vp in enumerate(video_prompts)]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        for raw in raw_results:
            if isinstance(raw, Exception):
                errors.append(f"clip_failed_with_exception: {raw}")
                continue
            i, skill_result = raw
            if skill_result.success and skill_result.data:
                p = skill_result.data.get("video_path", "")
                if p:
                    clip_paths.append(p)
                    clip_details.append({
                        "path": p,
                        "duration": skill_result.data.get("duration_seconds", 0),
                        "is_stub": skill_result.data.get("is_stub", False),
                        "verification": skill_result.data.get("verification", {}),
                        "continuity_frame_used": None,
                        "transition_to_next": video_prompts[i].get("transition_to_next", ""),
                        "transition_type": video_prompts[i].get("transition_type", "clean"),
                        "scene_beat": video_prompts[i].get("scene_beat", ""),
                        "beat_summary": video_prompts[i].get("beat_summary", ""),
                        "transition_intent": video_prompts[i].get("transition_intent", ""),
                        "clip_index": video_prompts[i].get("clip_index", i + 1),
                        "segment_type": video_prompts[i].get("segment_type", "body"),
                        "shot_type": video_prompts[i].get("shot_type", ""),
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
        clip_details: list[dict[str, Any]],
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

        transitions = build_transitions_from_clip_details(clip_details or [])

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
        clip_details: list[dict[str, Any]],
        product_name: str,
        scripts: list[dict[str, Any]],
        thumbnail_sets: list[dict[str, Any]],
        language: str,
        errors: list[str],
        continuity_grid: dict[str, Any] | None = None,
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
            base_audit = res.data
            return build_continuity_audit_summary(
                base_audit=base_audit,
                clip_details=clip_details or [],
                continuity_grid=continuity_grid,
                final_video_path=video_path or "",
            )
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
        final_video, render_json_path = extract_assemble_paths(assemble_out)

        result: dict[str, Any] = {
            "success": True,
            "scenario": "s4_live_shoot",
            "scripts": self._get_step_output(steps, "scripts") or [],
            "video_prompts": self._get_step_output(steps, "video_prompts") or [],
            "thumbnail_sets": self._get_step_output(steps, "thumbnails") or [],
            "seedance_clips": seedance_out.get("clip_paths", []) if isinstance(seedance_out, dict) else [],
            "final_video_path": final_video,
            "render_json_path": render_json_path,
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
