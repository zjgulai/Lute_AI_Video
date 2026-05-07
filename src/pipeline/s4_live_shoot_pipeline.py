"""S4 E2E pipeline — Live Shoot to Video.

Supports two execution modes:
  • StepRunner mode: run_step(step_name, state) — used by step-by-step / auto pipelines
  • Legacy mode: run(footage_assets, product_info, ...) — backwards-compatible full run

Steps (3):
  1. scripts          — script-writer-skill from footage + product
  2. video_prompts    — seedance-video-prompt per script segment
  3. thumbnails       — gpt-image-thumbnail-prompt variants
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

    async def run_step(self, step_name: str, state: dict) -> Any:
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

        raise ValueError(f"Unknown step name: {step_name}")

    async def _step_scripts(
        self,
        reg: SkillRegistry,
        config: dict,
        steps: dict,
        errors: list[str],
    ) -> list[dict]:
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
        config: dict,
        steps: dict,
        errors: list[str],
    ) -> list[dict]:
        """Generate Seedance video prompts referencing footage assets."""
        scripts_dict = self._get_step_output(steps, "scripts") or []
        footage_assets = config.get("footage_assets", [])

        prompts: list[dict] = []
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
            if vp.success and vp.data:
                prompts.append({"script_id": script.get("id"), "prompt": vp.data})
            else:
                errors.append(f"video_prompt_{script.get('id', '?')}_failed: {vp.error}")

        logger.info("s4: video prompts complete", prompts=len(prompts))
        return prompts

    async def _step_thumbnails(
        self,
        reg: SkillRegistry,
        config: dict,
        steps: dict,
        errors: list[str],
    ) -> list[dict]:
        """Generate thumbnail prompt variants per script."""
        scripts_dict = self._get_step_output(steps, "scripts") or []
        product_info = config.get("product_info", {})
        brand_name = config.get("brand_name") or product_info.get("brand_name", "")

        thumbnails: list[dict] = []
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
    def _get_step_output(steps: dict, step_name: str) -> Any:
        """Retrieve output from a step, preferring edited_output if edited."""
        step_data = steps.get(step_name, {})
        if step_data.get("edited") and step_data.get("edited_output") is not None:
            return step_data["edited_output"]
        return step_data.get("output")

    # ═══ Backwards-compatible full pipeline ═══

    async def run(
        self,
        footage_assets: list[dict],
        product_info: dict,
        topic: str = "",
        target_platforms: list[str] | None = None,
    ) -> dict:
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
        result: dict[str, Any] = {
            "success": True,
            "scenario": "s4_live_shoot",
            "scripts": self._get_step_output(steps, "scripts") or [],
            "video_prompts": self._get_step_output(steps, "video_prompts") or [],
            "thumbnail_sets": self._get_step_output(steps, "thumbnails") or [],
            "steps_completed": 3,
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
