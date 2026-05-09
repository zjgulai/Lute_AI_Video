"""Storyboard Agent — converts scripts into visual shot lists.

Uses LLM to translate textual scripts into frame-by-frame shot descriptions.
"""

import structlog

from src.models import Script, Shot, Storyboard
from src.tools.llm_client import llm

logger = structlog.get_logger()

STORYBOARD_SYSTEM_PROMPT = """You are a visual storyboard artist for short-form video. 
Convert a video script into a detailed shot list. For each script segment, create 1-3 shots.

Output:
```json
{
  "script_id": "...",
  "total_duration": 45.0,
  "aspect_ratio": "9:16",
  "shots": [
    {"id": 1, "start_time": 0.0, "end_time": 2.5, "shot_type": "hook", "visual": "...", "text_overlay": "...", "camera": "Static", "asset_needed": "..."}
  ]
}
```
Camera options: Static, Slow zoom in, Slow zoom out, Pan left, Pan right, Handheld, Tracking
"""


class StoryboardAgent:
    def __init__(self, use_mock: bool = False, use_skills: bool = False):
        self.use_mock = use_mock
        self.use_skills = use_skills

    async def run(self, scripts: list[Script]) -> list[Storyboard]:
        storyboards = []
        for script in scripts:
            if self.use_mock:
                sb = self._mock_storyboard(script)
            elif self.use_skills:
                import src.skills.storyboard  # noqa: F401
                from src.skills.registry import SkillRegistry
                skill_result = await SkillRegistry().execute("storyboard-skill", {
                    "scripts": [script.model_dump(mode="json")],
                })
                if skill_result.success and skill_result.data:
                    sbs = skill_result.data.get("storyboards", [])
                    if sbs:
                        sb = Storyboard(**sbs[0])
                    else:
                        sb = self._mock_storyboard(script)
                else:
                    logger.warning("storyboard: skill failed, using mock", error=skill_result.error)
                    sb = self._mock_storyboard(script)
            else:
                try:
                    data = await llm.invoke_json(
                        STORYBOARD_SYSTEM_PROMPT,
                        f"Script:\n{script.model_dump_json(indent=2)}",
                    )
                    sb = Storyboard(**data)
                except Exception as e:
                    logger.error("storyboard: LLM failed", error=str(e))
                    sb = self._mock_storyboard(script)
            storyboards.append(sb)
        return storyboards

    def _mock_storyboard(self, script: Script) -> Storyboard:
        shots = []
        for i, seg in enumerate(script.segments):
            shots.append(
                Shot(
                    id=i + 1,
                    start_time=seg.start_time,
                    end_time=seg.end_time,
                    shot_type=seg.segment_type,
                    visual=seg.visual_description or f"Shot for: {seg.segment_type}",
                    text_overlay=seg.text_overlay,
                    camera="Static",
                    asset_needed=f"B-Roll: {seg.segment_type}",
                )
            )
        return Storyboard(
            script_id=script.id,
            total_duration=script.total_duration,
            shots=shots,
        )
