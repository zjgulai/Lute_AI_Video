"""CTR / conversion rate estimation framework.

Provides lightweight heuristic-based CTR estimation for thumbnails and scripts.
Future: integrate with historical performance data from ab_tracker.py.

Usage:
    from src.quality.ctr_estimator import CTREstimator
    est = CTREstimator().estimate_thumbnail(thumbnail_prompt, platform="tiktok")
    # est = {"ctr_estimate": 0.035, "confidence": 0.5, "factors": {...}}
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


class CTREstimator:
    """Estimate CTR and conversion rate from content features."""

    def estimate_thumbnail(
        self,
        prompt: str,
        platform: str = "tiktok",
    ) -> dict[str, Any]:
        """Estimate thumbnail CTR from prompt text analysis.

        Uses heuristics based on industry CTR drivers:
        - Curiosity gap (question, number, contrast)
        - Emotional triggers (fear, surprise, joy)
        - Visual clarity (product visible, text readable)
        - Color/contrast signals
        """
        if not prompt:
            return {"ctr_estimate": 0.0, "confidence": 0.0, "factors": {}, "recommendation": "empty prompt"}

        p = prompt.lower()
        factors: dict[str, float] = {}

        # Curiosity signals
        curiosity = sum(1 for w in ["what", "how", "why", "secret", "truth", "mistake"] if w in p)
        factors["curiosity"] = min(1.0, curiosity / 2.0)

        # Number specificity
        import re
        has_number = bool(re.search(r"\d", p))
        factors["specificity"] = 1.0 if has_number else 0.5

        # Emotional trigger
        emotion = sum(1 for w in ["shocking", "surprising", "amazing", "never", "worst", "best"] if w in p)
        factors["emotion"] = min(1.0, emotion / 1.0)

        # Product visibility
        product_visible = "product" in p or "close-up" in p or "detail" in p
        factors["product_visible"] = 1.0 if product_visible else 0.5

        # Text overlay
        has_text = "text" in p or "caption" in p or '"' in p
        factors["text_overlay"] = 1.0 if has_text else 0.5

        # Platform-specific baseline CTR
        baseline = {"tiktok": 0.025, "youtube_shorts": 0.030, "instagram_reels": 0.020}.get(platform, 0.025)

        # Weighted factor impact on CTR
        impact = (
            factors["curiosity"] * 0.25 +
            factors["specificity"] * 0.15 +
            factors["emotion"] * 0.20 +
            factors["product_visible"] * 0.20 +
            factors["text_overlay"] * 0.20
        )
        # Impact 0-1 maps to CTR multiplier 0.5x-2.0x
        multiplier = 0.5 + impact * 1.5
        ctr = baseline * multiplier

        return {
            "ctr_estimate": round(ctr, 4),
            "baseline": baseline,
            "confidence": 0.5,  # heuristic-based, not data-driven yet
            "factors": {k: round(v, 2) for k, v in factors.items()},
            "recommendation": (
                "Strong thumbnail CTR potential" if ctr >= baseline * 1.5
                else "Add curiosity gap or emotional trigger to improve CTR"
            ),
        }

    def estimate_conversion(
        self,
        script_features: dict[str, Any],
        platform: str = "tiktok",
    ) -> dict[str, Any]:
        """Estimate conversion rate from script features.

        Key drivers: CTA clarity, urgency, social proof, guarantee.
        """
        sf = script_features or {}
        factors: dict[str, float] = {}

        factors["cta_clarity"] = 1.0 if sf.get("cta_length", 0) > 20 else 0.5
        factors["urgency"] = 1.0 if sf.get("has_urgency", False) else 0.3
        factors["social_proof"] = 1.0 if sf.get("has_social_proof", False) else 0.4
        factors["guarantee"] = 1.0 if sf.get("has_guarantee", False) else 0.5
        factors["product_mention"] = 1.0 if sf.get("product_mentions", 0) >= 2 else 0.5

        baseline = {"tiktok": 0.015, "youtube_shorts": 0.012, "instagram_reels": 0.010}.get(platform, 0.015)
        impact = sum(factors.values()) / len(factors)
        multiplier = 0.5 + impact * 1.5
        cvr = baseline * multiplier

        return {
            "conversion_estimate": round(cvr, 4),
            "baseline": baseline,
            "confidence": 0.5,
            "factors": {k: round(v, 2) for k, v in factors.items()},
            "recommendation": (
                "Strong conversion potential" if cvr >= baseline * 1.5
                else "Strengthen CTA urgency and social proof"
            ),
        }
