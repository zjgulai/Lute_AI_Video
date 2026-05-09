"""Dynamic threshold adjustment — auto-tunes audit thresholds based on feedback.

Reads A/B test results from ab_tracker.py and adjusts quality thresholds
to optimize for business outcomes (views, CTR, completion rate).

Usage:
    from src.quality.dynamic_thresholds import ThresholdOptimizer
    optimizer = ThresholdOptimizer()
    new_thresholds = optimizer.suggest_thresholds(metric="ctr")
    # new_thresholds = {"hook_duration_max": 2.5, "wps_target": (2.8, 3.2), ...}
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()

# Default thresholds (static baseline)
DEFAULT_THRESHOLDS = {
    "hook_duration_max": 3.0,
    "wps_target_min": 2.5,
    "wps_target_max": 3.5,
    "min_cta_length": 20,
    "min_segment_completeness": 0.8,
    "av_sync_max_diff": 0.5,
    "frame_variance_mse_threshold": 50.0,
    "black_brightness_threshold": 20.0,
    "resolution_fps_min": 25,
    "resolution_bitrate_min_kbps": 1500,
}


class ThresholdOptimizer:
    """Suggest threshold adjustments based on historical performance data."""

    def __init__(self):
        self._thresholds = dict(DEFAULT_THRESHOLDS)

    def get_thresholds(self) -> dict[str, Any]:
        """Return current thresholds."""
        return dict(self._thresholds)

    def suggest_thresholds(self, metric: str = "ctr") -> dict[str, Any]:
        """Analyze A/B data and suggest threshold adjustments.

        Args:
            metric: which metric to optimize for ("ctr", "completion_rate", "views")

        Returns:
            Dict of suggested threshold changes with rationale.
        """
        try:
            from src.quality.ab_tracker import ABTracker
            tracker = ABTracker()
            variant_perf = tracker.compute_variant_performance()
        except Exception:
            variant_perf = {}

        if not variant_perf:
            logger.info("threshold_optimizer: no A/B data yet — returning defaults")
            return {"thresholds": self._thresholds, "changes": {}, "rationale": "insufficient data"}

        suggestions: dict[str, Any] = {}
        rationale_parts: list[str] = []

        # Compare variants
        best_variant = max(variant_perf, key=lambda v: variant_perf[v].get(f"avg_{metric}", 0) or 0)
        best_data = variant_perf[best_variant]

        rationale_parts.append(f"Best variant: {best_variant} (avg_{metric}={best_data.get(f'avg_{metric}')})")

        # If creative performs better, loosen hook constraints
        if best_variant == "creative":
            suggestions["hook_duration_max"] = 4.0
            rationale_parts.append("Creative variant wins → loosen hook duration to 4s")
        elif best_variant == "conservative":
            suggestions["hook_duration_max"] = 2.5
            rationale_parts.append("Conservative variant wins → tighten hook duration to 2.5s")

        # If we have enough data, suggest wps adjustment
        if best_data.get("count", 0) >= 10:
            # With sufficient data, could do correlation analysis
            # For now, keep target range but flag for review
            rationale_parts.append(f"Sample size {best_data['count']} ≥ 10 — consider running regression")

        return {
            "thresholds": {**self._thresholds, **suggestions},
            "changes": suggestions,
            "rationale": "; ".join(rationale_parts),
            "variant_performance": variant_perf,
        }
