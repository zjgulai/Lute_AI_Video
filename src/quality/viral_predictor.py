"""Viral prediction framework — lightweight feature-based scoring for content potential.

Predicts short-form video virality using engineered features. Future: train
LightGBM/XGBoost on historical A/B test data (from ab_tracker.py).

Current implementation: rule-based ensemble using industry-known viral signals.
Future: swap _predict_rules() for a loaded LightGBM model.

Usage:
    from src.quality.viral_predictor import ViralPredictor
    score = ViralPredictor().predict(script_features, thumbnail_features)
    # score = {"viral_score": 0.72, "confidence": 0.6, "factors": {...}}
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class ViralPredictor:
    """Predict short-form video viral potential from content features."""

    def predict(
        self,
        script_features: dict[str, Any] | None = None,
        thumbnail_features: dict[str, Any] | None = None,
        video_features: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compute viral potential score from content features.

        Args:
            script_features: dict with keys like hook_duration, wps, has_cta, usp_count
            thumbnail_features: dict with keys like contrast_score, text_count, ctr_signals
            video_features: dict with keys like duration, has_captions, transition_count

        Returns:
            {"viral_score": float (0-1), "confidence": float (0-1),
             "factors": dict, "recommendation": str}
        """
        script_features = script_features or {}
        thumbnail_features = thumbnail_features or {}
        video_features = video_features or {}

        factors: dict[str, float] = {}

        # ── Script factors ──
        # Hook strength: ≤3s with attention signal = full points
        hook_dur = script_features.get("hook_duration", 0)
        hook_signal = script_features.get("has_hook_attention_signal", False)
        if hook_dur <= 3 and hook_signal:
            factors["hook"] = 1.0
        elif hook_dur <= 5:
            factors["hook"] = 0.6
        else:
            factors["hook"] = 0.2

        # Information density: 2.5-3.5 wps optimal
        wps = script_features.get("wps", 0)
        if 2.5 <= wps <= 3.5:
            factors["density"] = 1.0
        elif 2.0 <= wps < 2.5 or 3.5 < wps <= 4.0:
            factors["density"] = 0.7
        else:
            factors["density"] = 0.4

        # CTA urgency
        has_cta = script_features.get("has_cta", False)
        has_urgency = script_features.get("has_urgency", False)
        if has_cta and has_urgency:
            factors["cta"] = 1.0
        elif has_cta:
            factors["cta"] = 0.6
        else:
            factors["cta"] = 0.2

        # Emotional arc: negative→positive transition
        has_neg_pos = script_features.get("has_negative_positive_arc", False)
        factors["emotion"] = 1.0 if has_neg_pos else 0.5

        # ── Thumbnail factors ──
        contrast = thumbnail_features.get("contrast_score", 0.5)
        factors["thumbnail_contrast"] = min(1.0, contrast)

        ctr_signals = thumbnail_features.get("ctr_signal_count", 0)
        factors["thumbnail_ctr"] = min(1.0, ctr_signals / 3.0)

        # ── Video factors ──
        duration = video_features.get("duration", 30)
        if 20 <= duration <= 45:
            factors["duration"] = 1.0  # sweet spot for completion
        elif 15 <= duration < 20 or 45 < duration <= 60:
            factors["duration"] = 0.7
        else:
            factors["duration"] = 0.4

        has_captions = video_features.get("has_captions", False)
        factors["captions"] = 1.0 if has_captions else 0.6

        # ── Aggregate ──
        weights = {
            "hook": 0.20,
            "density": 0.10,
            "cta": 0.15,
            "emotion": 0.10,
            "thumbnail_contrast": 0.10,
            "thumbnail_ctr": 0.10,
            "duration": 0.15,
            "captions": 0.10,
        }
        viral_score = sum(factors.get(k, 0) * w for k, w in weights.items())
        viral_score = round(max(0.0, min(1.0, viral_score)), 3)

        # Confidence: how many features were actually provided
        provided = sum(1 for v in [script_features, thumbnail_features, video_features] if v)
        confidence = round(provided / 3.0, 2)

        # Recommendation
        if viral_score >= 0.75:
            rec = "Strong viral potential — prioritize this variant"
        elif viral_score >= 0.55:
            rec = "Moderate potential — consider improving weak factors"
        else:
            weak = [k for k, v in factors.items() if v < 0.5]
            rec = f"Low viral potential — strengthen: {', '.join(weak[:3])}"

        return {
            "viral_score": viral_score,
            "confidence": confidence,
            "factors": {k: round(v, 2) for k, v in factors.items()},
            "recommendation": rec,
        }
