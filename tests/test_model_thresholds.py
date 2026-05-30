"""Tests for src/pipeline/model_thresholds.py (Decision F, 2026-05-13)."""

import os

from src.pipeline.model_thresholds import (
    _DEFAULT_THRESHOLD,
    _LLM_STEP_THRESHOLD,
    _MODEL_THRESHOLDS,
    get_threshold,
    is_acceptable,
    model_for_step,
)


class TestModelForStep:
    def test_video_step_returns_video_model(self):
        assert model_for_step("seedance_clips") == os.environ.get(
            "POYO_VIDEO_MODEL", "seedance-2"
        )

    def test_image_step_returns_image_model(self):
        assert model_for_step("keyframe_images") == os.environ.get(
            "POYO_IMAGE_MODEL", "gpt-image-2"
        )
        assert model_for_step("thumbnail_images") == os.environ.get(
            "POYO_IMAGE_MODEL", "gpt-image-2"
        )

    def test_llm_step_returns_none(self):
        for step in ("strategy", "scripts", "vlog_strategy", "remix_script", "storyboards"):
            assert model_for_step(step) is None, step

    def test_unknown_step_returns_none(self):
        assert model_for_step("not_a_real_step") is None


class TestGetThreshold:
    def test_llm_backed_steps_use_llm_threshold(self):
        for step in ("strategy", "scripts", "vlog_strategy", "remix_script"):
            assert get_threshold(step) == _LLM_STEP_THRESHOLD, step

    def test_seedance_2_threshold_is_065(self):
        assert get_threshold("seedance_clips", model_id="seedance-2") == 0.65

    def test_kling_3_0_threshold_is_060(self):
        assert get_threshold("seedance_clips", model_id="kling-3-0/pro") == 0.60

    def test_wan_2_7_threshold_is_055(self):
        assert get_threshold("seedance_clips", model_id="wan-2-7-video") == 0.55

    def test_wan_2_2_fast_threshold_is_050(self):
        assert get_threshold("seedance_clips", model_id="wan-2-2-fast") == 0.50

    def test_veo_3_1_threshold_is_058(self):
        assert get_threshold("seedance_clips", model_id="veo-3-1") == 0.58

    def test_unknown_model_falls_back_to_default(self):
        assert get_threshold("seedance_clips", model_id="completely-fake-model") == _DEFAULT_THRESHOLD

    def test_explicit_model_id_overrides_step_default(self):
        seedance_default = get_threshold("seedance_clips")
        kling_override = get_threshold("seedance_clips", model_id="kling-2-5-turbo-pro")
        assert kling_override == 0.55
        assert kling_override != seedance_default

    def test_llm_step_ignores_model_id(self):
        assert get_threshold("scripts", model_id="seedance-2") == _LLM_STEP_THRESHOLD

    def test_post_processing_step_returns_default(self):
        assert get_threshold("assemble_final") == _DEFAULT_THRESHOLD


class TestIsAcceptable:
    def test_above_threshold_seedance(self):
        assert is_acceptable(0.66, "seedance_clips", model_id="seedance-2")

    def test_at_threshold_seedance(self):
        assert is_acceptable(0.65, "seedance_clips", model_id="seedance-2")

    def test_below_threshold_seedance(self):
        assert not is_acceptable(0.64, "seedance_clips", model_id="seedance-2")

    def test_above_threshold_wan_budget(self):
        assert is_acceptable(0.50, "seedance_clips", model_id="wan-2-2-fast")

    def test_below_threshold_wan_budget(self):
        assert not is_acceptable(0.49, "seedance_clips", model_id="wan-2-2-fast")

    def test_diagnostic_double_door_bypass_now_rejects(self):
        """诊断 §3.2 中举的 0.42/0.45/0.48 全部 sub-threshold 案例必须全员 reject。"""
        for s in (0.42, 0.45, 0.48):
            assert not is_acceptable(s, "seedance_clips", model_id="seedance-2"), s
            assert not is_acceptable(s, "seedance_clips", model_id="wan-2-2-fast"), s

    def test_llm_step_uses_060_baseline(self):
        assert is_acceptable(0.60, "scripts")
        assert not is_acceptable(0.59, "scripts")


class TestThresholdCoverage:
    def test_all_premium_models_present(self):
        """Sanity check: poyo's 2026-05 premium catalog has thresholds defined."""
        for premium_model in (
            "seedance-2", "kling-3-0/pro", "veo-3-1", "runway-gen-4-5",
            "wan-2-7-video", "gpt-image-2",
        ):
            assert premium_model in _MODEL_THRESHOLDS, premium_model

    def test_thresholds_in_valid_range(self):
        for model, thr in _MODEL_THRESHOLDS.items():
            assert 0.0 <= thr <= 1.0, f"{model}: {thr} out of [0,1]"

    def test_premium_higher_than_budget(self):
        assert _MODEL_THRESHOLDS["seedance-2"] > _MODEL_THRESHOLDS["wan-2-2-fast"]
        assert _MODEL_THRESHOLDS["kling-3-0/pro"] >= _MODEL_THRESHOLDS["kling-2-5-turbo-pro"]
