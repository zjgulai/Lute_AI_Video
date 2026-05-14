"""Model-aware Gate score thresholds (Decision F, 2026-05-13).

Decouples Gate min-score threshold from the global hardcoded value so that
candidates produced by less-strict models (e.g., wan-2-2-fast) are not
rejected by the same bar that applies to Seedance 2.

Lookup contract:
- ``get_threshold(step_name, model_id)`` returns the min `overall` score
  below which a candidate must be flagged as not-acceptable.
- ``is_acceptable(score, step_name, model_id)`` returns True/False.

Step-to-model mapping is derived from `POYO_IMAGE_MODEL` / `POYO_VIDEO_MODEL`
config at runtime; pass `model_id=None` to use the env default.
"""

from __future__ import annotations

from src.config import POYO_IMAGE_MODEL, POYO_VIDEO_MODEL

# Per-model min_threshold (Decision F, 2026-05-13).
# Numbers calibrated to model quality tier — premium models held to higher bar.
_MODEL_THRESHOLDS: dict[str, float] = {
    "seedance-2": 0.65,
    "seedance-2-fast": 0.65,
    "seedance-1-5-pro": 0.62,
    "seedance-1-0-pro": 0.55,
    "seedance-2.0": 0.65,
    "kling-3-0/standard": 0.60,
    "kling-3-0/pro": 0.60,
    "kling-3-0/4k": 0.60,
    "kling-o3": 0.58,
    "kling-o3-4k": 0.58,
    "kling-2-6": 0.58,
    "kling-2-5-turbo-pro": 0.55,
    "kling-2-1": 0.55,
    "runway-gen-4-5": 0.62,
    "veo-3-1": 0.58,
    "wan-2-7-video": 0.55,
    "wan-2-6": 0.55,
    "wan-2-5": 0.55,
    "wan-2-2-fast": 0.50,
    "hailuo-2-3": 0.55,
    "happy-horse": 0.55,
    "gpt-image-2": 0.65,
    "gpt-4o-image": 0.65,
    "seedream-5-0-lite": 0.62,
    "seedream-4-5": 0.60,
    "flux-2": 0.60,
    "nano-banana-pro": 0.60,
    "nano-banana": 0.55,
}

_DEFAULT_THRESHOLD = 0.60
_LLM_STEP_THRESHOLD = 0.60

# Steps that generate via an LLM (DeepSeek/Anthropic), not a poyo model.
# These use _LLM_STEP_THRESHOLD because LLM quality is independent of model
# slug mapping.
_LLM_BACKED_STEPS: frozenset[str] = frozenset({
    "strategy",
    "scripts",
    "remix_script",
    "vlog_strategy",
    "storyboards",
    "video_prompts",
    "thumbnail_prompts",
    "character_identity",
})

_VIDEO_STEPS: frozenset[str] = frozenset({"seedance_clips"})
_IMAGE_STEPS: frozenset[str] = frozenset({"keyframe_images", "thumbnail_images"})


def model_for_step(step_name: str) -> str | None:
    """Return the model_id that produces `step_name`, or None for LLM/post steps."""
    if step_name in _VIDEO_STEPS:
        return POYO_VIDEO_MODEL
    if step_name in _IMAGE_STEPS:
        return POYO_IMAGE_MODEL
    return None


def get_threshold(step_name: str, model_id: str | None = None) -> float:
    """Resolve min acceptance threshold for a candidate score.

    Resolution order:
    1. If `step_name` is LLM-backed (no poyo model), return _LLM_STEP_THRESHOLD.
    2. If `model_id` provided and known, return its threshold.
    3. If `step_name` maps to a poyo model via config, use that model's threshold.
    4. Else fall back to _DEFAULT_THRESHOLD.
    """
    if step_name in _LLM_BACKED_STEPS:
        return _LLM_STEP_THRESHOLD

    candidate_model = model_id or model_for_step(step_name)
    if candidate_model and candidate_model in _MODEL_THRESHOLDS:
        return _MODEL_THRESHOLDS[candidate_model]
    return _DEFAULT_THRESHOLD


def is_acceptable(score: float, step_name: str, model_id: str | None = None) -> bool:
    """True if `score` meets the threshold for `step_name`/`model_id`."""
    return score >= get_threshold(step_name, model_id)
