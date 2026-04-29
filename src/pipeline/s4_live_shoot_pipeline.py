"""S4 E2E pipeline — Live Shoot to Video.

Takes raw footage capture data and produces:
  1. Asset analysis (extract key scenes from raw footage)
  2. Script generation (structure footage into narrative)
  3. Seedance video generation prompts
  4. Thumbnail variants
"""

from __future__ import annotations

from typing import Any

import structlog

from src.skills.registry import SkillRegistry

import src.skills.script_writer  # noqa: F401
import src.skills.seedance_prompt  # noqa: F401
import src.skills.thumbnail_prompt  # noqa: F401

logger = structlog.get_logger()


class S4LiveShootPipeline:
    """Orchestrate S4 live-shoot to video pipeline."""

    async def run(
        self,
        footage_assets: list[dict],
        product_info: dict,
        topic: str = "",
        target_platforms: list[str] | None = None,
    ) -> dict:
        platforms = target_platforms or ["tiktok", "shopify"]
        reg = SkillRegistry()

        logger.info("s4: starting live-shoot pipeline",
                     assets=len(footage_assets),
                     product=product_info.get("name"))

        # Step 1: Generate script from footage descriptions + product
        brief_data = {
            "id": "LIVE-001",
            "topic": topic or product_info.get("name", "Product"),
            "product_name": product_info.get("name", "Product"),
            "brand_name": product_info.get("brand_name", ""),
            "usps": product_info.get("usps", ["quality"]),
            "hook_type": "scene_drop",
            "video_type": "tutorial",
            "target_platforms": platforms,
        }
        scripts_dict = []
        scr = await reg.execute("script-writer-skill", {
            "briefs": [brief_data],
            "brand_guidelines": {"footage_available": len(footage_assets)},
            "target_languages": ["en"],
        })
        if scr.success and scr.data:
            scripts_dict = scr.data.get("scripts", [])
        logger.info("s4: scripts complete", scripts=len(scripts_dict))

        if not scripts_dict:
            return {"success": False, "errors": ["Script generation failed"], "steps_completed": 0}

        # Step 2: Generate video prompts referencing footage
        prompts = []
        for script in scripts_dict[:3]:
            segs = script.get("segments", [])
            script_segs = []
            for s in segs:
                desc = s.get("visual_description", "")
                # Generate footage reference if assets available
                footage_ref = ""
                if footage_assets:
                    fa = footage_assets[min(len(script_segs), len(footage_assets)-1)]
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
        logger.info("s4: video prompts complete", prompts=len(prompts))

        # Step 3: Thumbnail prompts
        thumbnails = []
        for script in scripts_dict[:3]:
            tp = await reg.execute("gpt-image-thumbnail-prompt", {
                "product_name": script.get("product_name", "Product"),
                "hook_text": script.get("hook", "Real footage, real results"),
                "brand_name": product_info.get("brand_name", ""),
                "mood": "authentic",
            })
            if tp.success and tp.data:
                thumbnails.append({"script_id": script.get("id"), "variants": tp.data.get("variants", [])})
        logger.info("s4: thumbnails complete", sets=len(thumbnails))

        return {
            "success": True,
            "scripts": scripts_dict,
            "video_prompts": prompts,
            "thumbnail_sets": thumbnails,
            "steps_completed": 3,
        }
