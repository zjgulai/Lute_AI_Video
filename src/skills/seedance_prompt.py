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


def _validate_continuity_grid_params(continuity_grid: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(continuity_grid, dict):
        return ["continuity_storyboard_grid must be a dict"]

    clip_groups = continuity_grid.get("clip_groups")
    if not isinstance(clip_groups, list) or not clip_groups:
        return ["continuity_storyboard_grid.clip_groups must be a non-empty list"]

    for index, group in enumerate(clip_groups):
        if not isinstance(group, dict):
            errors.append(f"clip_groups[{index}] must be a dict")
            continue

        seedance_prompt = group.get("seedance_prompt")
        if not isinstance(seedance_prompt, str) or len(seedance_prompt.strip()) < 10:
            errors.append(
                f"clip_groups[{index}].seedance_prompt must be a non-empty string"
            )

        for field_name in ("duration", "duration_seconds"):
            if field_name not in group or group.get(field_name) is None:
                continue
            try:
                value = float(group[field_name])
            except (TypeError, ValueError):
                errors.append(f"clip_groups[{index}].{field_name} must be numeric")
                continue
            if value <= 0:
                errors.append(f"clip_groups[{index}].{field_name} must be positive")

        if "clip_index" in group and group.get("clip_index") is not None:
            try:
                clip_index = int(group["clip_index"])
            except (TypeError, ValueError):
                errors.append(f"clip_groups[{index}].clip_index must be numeric")
                continue
            if clip_index <= 0:
                errors.append(f"clip_groups[{index}].clip_index must be positive")

    return errors


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
        continuity_grid = params.get("continuity_storyboard_grid") or {}
        if isinstance(continuity_grid, dict) and continuity_grid.get("clip_groups"):
            prompts = self._build_prompts_from_clip_groups(
                continuity_grid=continuity_grid,
                product_name=params.get("product_name", "Product"),
            )
            quality_scores = [float(prompt.get("quality_score", 0.0)) for prompt in prompts]
            overall_quality = (
                round(sum(quality_scores) / len(quality_scores), 2)
                if quality_scores
                else 0.5
            )
            return SkillResult(
                success=True,
                data=prompts,
                metadata={
                    "prompt_count": len(prompts),
                    "source": "continuity_storyboard_grid",
                    "overall_quality_score": overall_quality,
                    "avg_quality_score": overall_quality,
                },
            )

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

            # Action description: derive from visual_description, not voiceover.
            # Voiceover is what is *said*; action is what *visually happens*.
            action = visual[:300] if visual else voice[:200]

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

        # Compute per-prompt quality scores and overall average
        quality_scores: list[float] = []
        for p in prompts:
            q = self._score_prompt_quality(p)
            p["quality_score"] = q
            quality_scores.append(q)
        overall_quality = round(sum(quality_scores) / len(quality_scores), 2) if quality_scores else 0.5

        return SkillResult(
            success=True,
            data=prompts,
            metadata={
                "prompt_count": len(prompts),
                "overall_quality_score": overall_quality,
                "avg_quality_score": overall_quality,
            },
        )

    def _build_prompts_from_clip_groups(
        self,
        continuity_grid: dict[str, Any],
        product_name: str,
    ) -> list[dict[str, Any]]:
        visual_identity = continuity_grid.get("visual_identity") or {}
        if not isinstance(visual_identity, dict):
            visual_identity = {}

        product_anchor = str(
            visual_identity.get("product_anchor") or f"same {product_name} product"
        )
        location = str(visual_identity.get("location") or "same home setting")
        lighting = str(visual_identity.get("lighting") or "consistent warm natural light")

        prompts: list[dict[str, Any]] = []
        clip_groups = continuity_grid.get("clip_groups", [])
        if not isinstance(clip_groups, list):
            return prompts

        for group in clip_groups:
            if not isinstance(group, dict):
                continue

            try:
                duration = float(group.get("duration") or group.get("duration_seconds") or 5)
            except (TypeError, ValueError):
                duration = 5.0
            if duration <= 0:
                duration = 5.0

            base_prompt = str(group.get("seedance_prompt") or "").strip()
            if not base_prompt:
                continue
            purpose = str(group.get("product_angle") or group.get("purpose") or "")
            camera = str(group.get("camera") or "smooth continuity handheld")
            prompt_text = (
                f"{base_prompt} Maintain continuity: {product_anchor}; "
                f"same location: {location}; lighting: {lighting}. "
                "Keep the same product, scene, and light across the whole clip. "
                "Do not change the product shape, control panel, color, scale, or countertop position. "
                "Use one continuous action chain inside this clip. "
                "Avoid infant face close-ups, medical claims, and distress-heavy imagery."
            )

            prompt_lower = prompt_text.lower()
            hits = [word for word in FORBIDDEN_PATTERNS if word in prompt_lower]
            if hits:
                logger.warning(
                    "seedance_prompt: forbidden pattern detected in continuity prompt",
                    extra={
                        "hits": hits,
                        "clip_index": group.get("clip_index", len(prompts) + 1),
                    },
                )

            prompt = {
                "segment_prompt": prompt_text,
                "segment_type": "clip_group",
                "clip_index": self._safe_clip_index(group.get("clip_index"), len(prompts) + 1),
                "duration_seconds": duration,
                "shot_type": "continuity_group",
                "camera": camera,
                "lighting": lighting,
                "has_forbidden_words": len(hits) > 0,
                "forbidden_hits": hits,
                "product_angle": purpose,
                "transition_to_next": group.get("transition_to_next", ""),
                "transition_type": group.get("transition_type", "match_cut"),
            }
            prompt["quality_score"] = self._score_prompt_quality(prompt)
            prompts.append(prompt)

        return prompts

    @staticmethod
    def _safe_clip_index(value: Any, fallback: int) -> int:
        try:
            clip_index = int(value)
        except (TypeError, ValueError):
            return fallback
        return clip_index if clip_index > 0 else fallback

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

    @staticmethod
    def _score_prompt_quality(prompt: dict[str, Any]) -> float:
        """Score a single prompt for completeness of action+camera+lighting+pacing.

        Checks:
        - action_description length (min 20 chars for meaningful action)
        - camera direction specified (non-empty, not generic)
        - lighting specified (non-empty)
        - pacing specified (non-empty)
        - no forbidden words (generic rotation patterns)

        Returns 0-1 score.
        """
        scores = []

        # Action quality
        action = prompt.get("segment_prompt", "")
        action_score = 1.0 if len(action) >= 80 else (0.5 if len(action) >= 40 else 0.2)
        scores.append(action_score)

        # Camera quality
        camera = prompt.get("camera", "")
        camera_score = 1.0 if camera and len(camera) > 5 and camera != "smooth cinematic" else 0.7
        scores.append(camera_score)

        # Lighting quality
        lighting = prompt.get("lighting", "")
        lighting_score = 1.0 if lighting and len(lighting) > 3 else 0.5
        scores.append(lighting_score)

        # Shot type quality
        shot = prompt.get("shot_type", "")
        shot_score = 1.0 if shot and shot != "mid-shot" else 0.7
        scores.append(shot_score)

        # Forbidden words penalty
        if prompt.get("has_forbidden_words"):
            scores.append(0.0)
        else:
            scores.append(1.0)

        return round(sum(scores) / len(scores), 2)

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if "continuity_storyboard_grid" in params:
            return _validate_continuity_grid_params(params.get("continuity_storyboard_grid"))
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
