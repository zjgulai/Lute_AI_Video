"""Quality-score-driven feedback gate for downstream consumers.

Pipeline stages emit `quality_score` (seedance_prompt, script_writer,
character_identity). Downstream consumers (keyframe_images,
seedance_video_generate, remotion_assemble) historically did not read
those scores — they always called the API regardless of upstream quality.

This module gives consumers a 3-state decision based on the upstream
score: proceed / warn / regenerate. See
docs/architecture/quality-score-feedback-loop-2026-05-15.md for thresholds,
risks, and pilot scope.

Usage (consumer side):

    from src.pipeline.feedback_gate import evaluate_upstream_quality

    decision, score, reason = evaluate_upstream_quality(
        upstream_data=storyboard_dict,
        consumer="keyframe_images",
        attempt=params.get("_quality_attempt", 0),
    )
    if decision == "regenerate":
        return SkillResult(success=False, data={
            "regenerate_upstream": "seedance_prompt",
            "reason": reason,
            "score": score,
        })
    if decision == "warn":
        params["_quality_warning"] = reason
    # proceed with normal logic
"""
from __future__ import annotations

from typing import Any, Literal

GateDecision = Literal["proceed", "warn", "regenerate"]


_CONSUMER_THRESHOLDS: dict[str, dict[str, float | int]] = {
    "keyframe_images": {
        "regenerate": 0.50,
        "warn": 0.70,
        "max_regenerate_attempts": 2,
    },
    "seedance_video_generate": {
        "regenerate": 0.55,
        "warn": 0.75,
        "max_regenerate_attempts": 2,
    },
    "remotion_assemble": {
        "regenerate": 0.45,
        "warn": 0.65,
        "max_regenerate_attempts": 1,
    },
}


def _extract_score(upstream_data: dict[str, Any], score_path: str) -> float | None:
    """Extract a quality score by dotted path. Returns None if missing/invalid.

    Examples:
        _extract_score({"quality_score": 0.8}, "quality_score") -> 0.8
        _extract_score({"data": {"overall_quality_score": 0.7}}, "data.overall_quality_score") -> 0.7
        _extract_score({"_self_check": {"score": 0.6}}, "_self_check.score") -> 0.6
    """
    cur: Any = upstream_data
    for part in score_path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
        if cur is None:
            return None
    if isinstance(cur, (int, float)):
        return float(cur)
    return None


def evaluate_upstream_quality(
    upstream_data: dict[str, Any],
    consumer: str,
    score_path: str = "quality_score",
    *,
    attempt: int = 0,
) -> tuple[GateDecision, float, str]:
    """Decide whether downstream consumer should proceed/warn/regenerate.

    Args:
        upstream_data: dict containing the upstream skill's output
        consumer: one of _CONSUMER_THRESHOLDS keys
        score_path: dotted path to the score field
        attempt: how many times this consumer has already retried via
                 regenerate_upstream loop (caller tracks)

    Returns:
        (decision, score_seen, human_readable_reason)
        - decision: 'proceed' / 'warn' / 'regenerate'
        - score_seen: the actual score (1.0 if missing — defaults to safe-proceed)
        - reason: brief decision string for logs/audit
    """
    if consumer not in _CONSUMER_THRESHOLDS:
        return "proceed", 1.0, f"unknown consumer '{consumer}', default proceed"

    thresholds = _CONSUMER_THRESHOLDS[consumer]
    score = _extract_score(upstream_data, score_path)

    if score is None:
        return "proceed", 1.0, f"{consumer}: no upstream score, default proceed"

    if attempt >= int(thresholds["max_regenerate_attempts"]):
        return (
            "warn",
            score,
            f"{consumer}: score={score:.2f} but attempts={attempt} exhausted, force proceed with warn",
        )

    if score < thresholds["regenerate"]:
        return (
            "regenerate",
            score,
            f"{consumer}: score={score:.2f} < {thresholds['regenerate']}, regenerate upstream",
        )
    if score < thresholds["warn"]:
        return (
            "warn",
            score,
            f"{consumer}: score={score:.2f} < {thresholds['warn']}, proceed but flag",
        )
    return "proceed", score, f"{consumer}: score={score:.2f} OK"


def get_thresholds(consumer: str) -> dict[str, float | int] | None:
    """Read-only accessor for consumer thresholds (for tests + telemetry)."""
    return _CONSUMER_THRESHOLDS.get(consumer)
