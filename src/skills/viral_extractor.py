"""Viral element extractor — extracts reusable viral patterns from analysis.

Takes a VideoAnalysisSkill output (or any analysis), extracts:
  - Hook formula (reusable template: hook_type + phrasing pattern)
  - Engagement pacing (optimal segment timing)
  - Emotional triggers (which emotions drive highest engagement)
  - Pattern signature (hashable fingerprint for pattern matching)

Auto-registers with SkillRegistry on import as "viral-extractor-skill".
"""

from __future__ import annotations

import hashlib
from typing import Any

import structlog

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()


HOOK_FORMULAS = {
    "pain_point": "Pain → Solution → Transformation",
    "counter_narrative": "Myth → Reality → New Truth",
    "data_drop": "Stat → Context → Implication",
    "scene_drop": "Scene → Context → Resolution",
    "question": "Question → Exploration → Answer",
    "story_hook": "Story → Connection → Lesson",
    "comparison": "Before → After → Verdict",
}


class ViralExtractorSkill(SkillCallable):
    """Extract viral pattern from video analysis.

    Input params:
      analysis: dict — output of video-analysis-skill
      segments: list[dict] — optional remix script segments

    Returns dict with:
      hook_formula, engagement_pacing, emotional_triggers, pattern_signature
    """

    name = "viral-extractor-skill"
    description = "Extracts reusable viral patterns (hook, pacing, emotion) from video analysis."

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("analysis"):
            errors.append("'analysis' is required")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            errors.append("output is None")
        return errors

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        analysis = params["analysis"]
        segments = params.get("segments", [])

        hook_type = analysis.get("hook_type", "question")
        emotion_curve = analysis.get("emotion_curve", [])
        segs = analysis.get("segments", []) or segments

        hook_formula = self._extract_hook_formula(hook_type)
        pacing = self._extract_pacing(segs)
        emotions = self._extract_emotions(emotion_curve)
        signature = self._compute_signature(analysis, hook_type)

        return SkillResult(success=True, data={
            "hook_formula": hook_formula,
            "engagement_pacing": pacing,
            "emotional_triggers": emotions,
            "pattern_signature": signature,
        })

    def _extract_hook_formula(self, hook_type: str) -> dict[str, Any]:
        return {
            "hook_type": hook_type,
            "formula": HOOK_FORMULAS.get(hook_type, "Generic → Detail → Action"),
            "reusable": True,
        }

    def _extract_pacing(self, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not segments:
            return [{"position": "open", "duration_pct": 15, "purpose": "hook"},
                    {"position": "body", "duration_pct": 60, "purpose": "value"},
                    {"position": "close", "duration_pct": 25, "purpose": "cta"}]
        output = []
        for s in segments:
            output.append({
                "type": s.get("type", s.get("segment_type", "body")),
                "start": s.get("start", s.get("start_time", 0)),
                "end": s.get("end", s.get("end_time", 0)),
                "purpose": s.get("description", "")[:80],
            })
        return output

    def _extract_emotions(self, curve: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not curve:
            return [{"emotion": "curiosity", "peak": True, "frequency": "open"},
                    {"emotion": "urgency", "peak": True, "frequency": "close"}]
        seen = set()
        emotions = []
        for point in curve:
            e = point.get("emotion", "neutral")
            if e not in seen:
                seen.add(e)
                emotions.append({"emotion": e, "intensity": point.get("intensity", 0.5)})
        return emotions

    def _compute_signature(self, analysis: dict[str, Any], hook_type: str) -> str:
        raw = f"{hook_type}:{analysis.get('speech_style','')}:{len(analysis.get('segments',[]))}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        analysis = params.get("analysis", {})
        hook_type = analysis.get("hook_type", "question")
        return SkillResult(success=True, data={
            "hook_formula": self._extract_hook_formula(hook_type),
            "engagement_pacing": self._extract_pacing([]),
            "emotional_triggers": self._extract_emotions([]),
            "pattern_signature": self._compute_signature(analysis, hook_type),
        })


SkillRegistry().register(ViralExtractorSkill())
logger.info("skill registered", name=ViralExtractorSkill.name)
