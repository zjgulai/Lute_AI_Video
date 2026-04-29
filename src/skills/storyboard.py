"""Storyboard skill — generates shot-by-shot storyboards from video scripts."""

from __future__ import annotations

from typing import Any

import structlog

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

SHOT_TYPES = ["CU", "MCU", "MS", "MLS", "LS", "POV", "Detail", "Aerial"]
CAMERA = ["Static", "Pan", "Tilt", "Dolly", "Handheld", "Zoom", "Push-in"]


class StoryboardSkill(SkillCallable):
    name = "storyboard-skill"
    description = "Generates shot-by-shot visual storyboards from scripts."

    def validate_params(self, params: dict) -> list[str]:
        errors = []
        if not params.get("scripts"):
            errors.append("'scripts' is required")
        return errors

    def validate_output(self, output: dict) -> list[str]:
        errors = []
        if not output:
            errors.append("output is None")
        return errors

    async def execute(self, params: dict) -> SkillResult:
        scripts = params["scripts"]
        storyboards = [self._gen(s) for s in scripts]
        return SkillResult(success=True, data={"storyboards": storyboards, "count": len(storyboards)})

    def _gen(self, script: dict) -> dict:
        segs = script.get("segments", [])
        shots = []
        for i, seg in enumerate(segs):
            st = seg.get("segment_type", seg.get("type", "body"))
            shots.append({
                "id": i + 1,
                "start_time": seg.get("start_time", seg.get("start", i*5)),
                "end_time": seg.get("end_time", seg.get("end", (i+1)*5)),
                "shot_type": {"hook":"CU","body":"MS","cta":"CU"}.get(st, SHOT_TYPES[i%len(SHOT_TYPES)]),
                "visual": seg.get("visual_description", f"Visual for {st}"),
                "text_overlay": " ".join(seg.get("voiceover","").split()[:3]) if seg.get("voiceover") else "",
                "camera": {"hook":"Handheld","body":"Pan","cta":"Zoom"}.get(st, CAMERA[i%len(CAMERA)]),
                "asset_needed": f"B-Roll: {st}",
            })
        return {"script_id": script.get("id",""), "total_duration": script.get("total_duration",30), "shots": shots}

    def fallback(self, params: dict) -> SkillResult:
        scripts = params.get("scripts", [{}])
        sbs = [self._gen(s) for s in scripts[:2]]
        return SkillResult(success=True, data={"storyboards": sbs, "count": len(sbs)})


SkillRegistry().register(StoryboardSkill())
logger.info("skill registered", name=StoryboardSkill.name)
