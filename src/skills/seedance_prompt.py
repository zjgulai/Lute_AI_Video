"""Sora-compatible Video Prompt Skill (Narrative Shot architecture).

Generates structured, per-segment prompts designed for Sora 2 Pro / Seedance 2.0.
Each script segment produces a self-contained prompt with explicit shot type,
camera direction, action, and scene description — never a generic product rotation.

Key design decisions:
- Per-segment output: one prompt per narrative beat (not a concatenated long string)
- Direct segment_type usage: no keyword-guessing classifier — trust the script's own labels
- Full visual_description: never truncate the scene description
- Forbidden word detection: "product showcase", "360", "rotation" trigger validation warnings
"""

from __future__ import annotations

import logging
from typing import Any

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

# ── Words that indicate a generic product-rotation prompt ──
FORBIDDEN_PATTERNS = [
    "product showcase", "product rotation", "360 rotation",
    "camera slowly orbits", "slowly rotate", "360 view",
    "product 360", "turntable", "spinning product",
]

# ── Narrative shot template ──
# Each segment gets its own prompt built from the script's visual_description.
# No template.format() with truncated strings — use the full description directly.

NARRATIVE_SHOT_TEMPLATE = (
    "Scene: {visual_description}. "
    "Shot type: {shot_type}. "
    "Action: {action_description}. "
    "Lighting: {lighting}. "
    "Camera: {camera_direction}. "
    "Pacing: {pacing}."
)


def _build_single_prompt(
    segment: dict[str, Any],
    shot_type: str,
    action_desc: str,
    lighting: str,
    camera: str,
    pacing: str,
    duration: float,
) -> dict[str, Any]:
    """Build a single structured prompt dict for one segment."""
    visual = (segment.get("visual_description", "") or
              segment.get("description", "") or
              segment.get("voiceover", ""))

    prompt_text = NARRATIVE_SHOT_TEMPLATE.format(
        visual_description=visual,
        shot_type=shot_type,
        action_description=action_desc,
        lighting=lighting,
        camera_direction=camera,
        pacing=pacing,
    )

    # Detect and warn on forbidden patterns
    prompt_lower = prompt_text.lower()
    hits = [w for w in FORBIDDEN_PATTERNS if w in prompt_lower]
    if hits:
        logger.warning(
            "seedance_prompt: forbidden pattern detected in prompt — hits=%s segment_type=%s",
            hits,
            segment.get("segment_type", "?"),
        )

    return {
        "segment_prompt": prompt_text,
        "segment_type": segment.get("segment_type", "body"),
        "duration_seconds": duration,
        "shot_type": shot_type,
        "camera": camera,
        "lighting": lighting,
        "has_forbidden_words": len(hits) > 0,
        "forbidden_hits": hits,
        "product_angle": segment.get("product_angle", ""),
    }


def _shot_type_from_segment(seg_type: str, description: str, index: int, total: int) -> str:
    """Derive shot type from the script's own segment_type label (not keyword guessing)."""
    seg = (seg_type or "").lower()
    desc = (description or "").lower()

    if "hook" in seg:
        return "close-up"
    if "pain" in seg or "problem" in seg:
        return "mid-shot"
    if "solution" in seg or "demo" in seg or "tutorial" in seg:
        return "over-shoulder"
    if "trust" in seg or "testimonial" in seg or "social" in seg:
        return "mid-shot"
    if "cta" in seg or "conclusion" in seg:
        return "static beauty shot"
    if "comparison" in seg:
        return "split-screen"
    if "before" in seg and "after" in seg:
        return "transition"

    # Fallback: use description heuristics as soft hint
    if "close" in desc or "detail" in desc or "texture" in desc:
        return "close-up"
    if "over-shoulder" in desc or "over shoulder" in desc or "behind" in desc:
        return "over-shoulder"

    # First segment defaults to establishing close-up, last to beauty
    if index == 0 and total > 1:
        return "close-up"
    if index == total - 1 and total > 1:
        return "static beauty shot"

    return "mid-shot"


class SeedancePromptSkill(SkillCallable):
    """Generates per-segment structured video prompts for Sora 2 Pro / Seedance 2.0.

    Returns a list of prompt dicts — one per script segment — each with
    explicit shot type, camera, action, and full visual description.
    """

    name = "seedance-video-prompt"
    description = "Generates per-segment structured video prompts (narrative shot architecture)"
    max_retries = 2

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        """Build one prompt per script segment using the narrative_shot template."""
        segments = params.get("script_segments", [])
        product_name = params.get("product_name", "Product")

        if not segments:
            return SkillResult(success=True, data=[self._build_single_fallback(product_name)])

        prompts: list[dict[str, Any]] = []
        total = len(segments)

        for i, seg in enumerate(segments):
            seg_type = seg.get("segment_type", "") or seg.get("type", "body")
            visual = (seg.get("visual_description", "") or
                      seg.get("description", "") or
                      seg.get("voiceover", ""))
            voice = seg.get("voiceover", "") or visual
            start_t = float(seg.get("start_time", 0))
            end_t = float(seg.get("end_time", start_t + 5))
            duration = max(1.0, end_t - start_t)

            shot_type = _shot_type_from_segment(seg_type, visual, i, total)

            # Action description: use voiceover as the "what happens" anchor
            action = voice[:200] if voice else visual[:200]

            prompt_dict = _build_single_prompt(
                segment=seg,
                shot_type=shot_type,
                action_desc=action,
                lighting="natural warm daylight" if "warm" in (visual + voice).lower() else "natural clean lighting",
                camera="handheld intimate" if i == 0 else "smooth cinematic",
                pacing="fast cut, urgent" if i == 0 else ("slow reveal, breathing room" if i == total - 1 else "steady informative"),
                duration=duration,
            )
            prompts.append(prompt_dict)

        return SkillResult(success=True, data=prompts)

    def _build_single_fallback(self, product_name: str) -> dict[str, Any]:
        """Safe fallback: structured prompt without rotation keywords."""
        return {
            "segment_prompt": (
                f"Scene: {product_name} in a real home setting. "
                "Shot type: mid-shot. "
                "Action: person interacts naturally with the product. "
                "Lighting: natural window light. "
                "Camera: smooth handheld. "
                "Pacing: calm and authentic."
            ),
            "segment_type": "body",
            "duration_seconds": 10.0,
            "shot_type": "mid-shot",
            "camera": "smooth handheld",
            "lighting": "natural window light",
            "has_forbidden_words": False,
            "forbidden_hits": [],
            "_fallback": True,
        }

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("script_segments"):
            errors.append("missing or empty 'script_segments'")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        if not isinstance(data, list):
            return [f"output must be list[dict], got {type(data).__name__}"]
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                errors.append(f"item[{i}] is not dict")
                continue
            prompt = item.get("segment_prompt", "")
            if len(prompt) < 10:
                errors.append(f"item[{i}] segment_prompt too short")
            # Check forbidden words
            pl = prompt.lower()
            for w in FORBIDDEN_PATTERNS:
                if w in pl:
                    errors.append(f"item[{i}] contains forbidden word: '{w}'")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        product_name = params.get("product_name", "Product")
        return SkillResult(success=True, data=[self._build_single_fallback(product_name)])


# Auto-register
try:
    SkillRegistry.register(SeedancePromptSkill())
    logger.info("seedance_prompt_skill: registered (narrative shot architecture)")
except ValueError:
    pass
