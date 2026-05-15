"""Tests for src.pipeline.feedback_gate (quality_score consumer gate)."""
from __future__ import annotations

from src.pipeline.feedback_gate import (
    _extract_score,
    evaluate_upstream_quality,
    get_thresholds,
)


class TestExtractScore:
    def test_flat_path(self):
        assert _extract_score({"quality_score": 0.8}, "quality_score") == 0.8

    def test_nested_path(self):
        data = {"data": {"overall_quality_score": 0.7}}
        assert _extract_score(data, "data.overall_quality_score") == 0.7

    def test_self_check_score(self):
        data = {"_self_check": {"score": 0.6}}
        assert _extract_score(data, "_self_check.score") == 0.6

    def test_missing_returns_none(self):
        assert _extract_score({}, "quality_score") is None
        assert _extract_score({"foo": "bar"}, "quality_score") is None
        assert _extract_score({"quality_score": "not a number"}, "quality_score") is None

    def test_int_score_coerced_to_float(self):
        assert _extract_score({"quality_score": 1}, "quality_score") == 1.0


class TestEvaluateUpstreamQuality:
    def test_score_above_warn_threshold_proceeds(self):
        decision, score, reason = evaluate_upstream_quality(
            {"quality_score": 0.85}, "keyframe_images"
        )
        assert decision == "proceed"
        assert score == 0.85
        assert "OK" in reason

    def test_score_in_warn_band_warns(self):
        decision, score, reason = evaluate_upstream_quality(
            {"quality_score": 0.65}, "keyframe_images"
        )
        assert decision == "warn"
        assert score == 0.65
        assert "0.65" in reason
        assert "0.7" in reason

    def test_score_below_regenerate_threshold_regenerates(self):
        decision, score, reason = evaluate_upstream_quality(
            {"quality_score": 0.40}, "keyframe_images"
        )
        assert decision == "regenerate"
        assert score == 0.40
        assert "regenerate upstream" in reason

    def test_attempts_exhausted_forces_proceed_with_warn(self):
        decision, score, reason = evaluate_upstream_quality(
            {"quality_score": 0.40},
            "keyframe_images",
            attempt=2,
        )
        assert decision == "warn"
        assert score == 0.40
        assert "exhausted" in reason

    def test_missing_score_proceeds_safely(self):
        decision, score, reason = evaluate_upstream_quality(
            {"some_other_field": 1}, "keyframe_images"
        )
        assert decision == "proceed"
        assert score == 1.0
        assert "no upstream score" in reason

    def test_unknown_consumer_proceeds_safely(self):
        decision, score, reason = evaluate_upstream_quality(
            {"quality_score": 0.10}, "totally_unknown_consumer"
        )
        assert decision == "proceed"
        assert score == 1.0
        assert "unknown consumer" in reason

    def test_seedance_video_generate_thresholds_higher(self):
        # At score=0.54: keyframe_images regenerate=0.50 -> proceed via warn-band;
        # seedance_video_generate regenerate=0.55 -> regenerate.
        # Demonstrates that seedance has stricter threshold than keyframe.
        score = 0.54
        decision_kf, _, _ = evaluate_upstream_quality(
            {"quality_score": score}, "keyframe_images"
        )
        decision_sd, _, _ = evaluate_upstream_quality(
            {"quality_score": score}, "seedance_video_generate"
        )
        assert decision_kf == "warn"
        assert decision_sd == "regenerate"

    def test_remotion_only_one_attempt_allowed(self):
        decision_attempt0, _, _ = evaluate_upstream_quality(
            {"quality_score": 0.30}, "remotion_assemble", attempt=0
        )
        decision_attempt1, _, _ = evaluate_upstream_quality(
            {"quality_score": 0.30}, "remotion_assemble", attempt=1
        )
        assert decision_attempt0 == "regenerate"
        assert decision_attempt1 == "warn"

    def test_custom_score_path(self):
        data = {"_self_check": {"score": 0.40}}
        decision, score, _ = evaluate_upstream_quality(
            data, "keyframe_images", score_path="_self_check.score"
        )
        assert decision == "regenerate"
        assert score == 0.40


class TestGetThresholds:
    def test_known_consumer(self):
        t = get_thresholds("keyframe_images")
        assert t is not None
        assert t["regenerate"] == 0.50
        assert t["warn"] == 0.70
        assert t["max_regenerate_attempts"] == 2

    def test_unknown_consumer_returns_none(self):
        assert get_thresholds("nonexistent") is None
