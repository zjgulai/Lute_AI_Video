"""Phase 2 prereq regression: ModelRouter convergence across S1/S3/S4/fast_mode.

Oracle review #4 (2026-05-15) flagged that Sprint 1 P1-1 ModelRouter was only
wired into S2 / S5 / gate_manager. S1 / S3 / S4 / fast_mode still inherited
the env-default POYO_VIDEO_MODEL, producing diagnostic R-VENDOR-LOCK
mixed-state where some scenarios upgrade to seedance-2 but others stick on
the legacy default.

This file regression-asserts that all 5 entry points (4 pipelines + fast_mode)
import and call `select_model()` from ModelRouter so production is in a
consistent routing state.
"""

from __future__ import annotations

import inspect

import pytest

from src.pipeline.model_router import select_model


class TestModelRouterConvergence:
    """Each pipeline's seedance step must thread select_model() into gen_params."""

    def test_s1_step_seedance_clips_uses_router(self):
        from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
        src = inspect.getsource(S1ProductDirectPipeline._step_seedance_clips)
        assert "from src.pipeline.model_router import select_model" in src
        assert 'select_model("s1")' in src

    def test_s3_step_seedance_clips_uses_router(self):
        from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline
        src = inspect.getsource(S3InfluencerRemixPipeline._step_seedance_clips)
        assert "from src.pipeline.model_router import select_model" in src
        assert 'select_model("s3")' in src

    def test_s4_step_seedance_clips_uses_router(self):
        from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
        src = inspect.getsource(S4LiveShootPipeline._step_seedance_clips)
        assert "from src.pipeline.model_router import select_model" in src
        assert 'select_model("s4")' in src

    def test_fast_mode_uses_router(self):
        from src.services.fast_mode import FastModeService
        src = inspect.getsource(FastModeService)
        assert "select_model" in src
        # fast_mode is the S1 shortcut, so it routes via "s1"
        assert 'select_model("s1")' in src or "select_model('s1')" in src


class TestPreferredModelsMatchRoadmap:
    """Per docs/architecture/poyo-model-matrix-stable.md §三 preferred chain.

    These assertions lock in the per-scenario preferred model so future
    chain edits don't silently flip what production uses without doc updates.
    """

    def test_s1_preferred_is_seedance_2(self):
        assert select_model("s1") == "seedance-2"

    def test_s2_preferred_is_kling_3_0_pro(self):
        assert select_model("s2") == "kling-3.0/pro"

    def test_s3_preferred_is_kling_3_0_standard(self):
        assert select_model("s3") == "kling-3.0/standard"

    def test_s4_preferred_is_seedance_2_fast(self):
        assert select_model("s4") == "seedance-2-fast"

    def test_s5_preferred_is_seedance_2(self):
        """S5 brand VLOG shares S1's preferred model — same premium tier
        but different scenario-specific gate scoring weights."""
        assert select_model("s5") == "seedance-2"


class TestEnvDefaultDecoupled:
    """Even when POYO_VIDEO_MODEL env is set to something else, ModelRouter
    returns its scenario-specific preferred model. This is the contract
    that ensures Phase 2 deploy is predictable."""

    @pytest.mark.parametrize("scenario,expected", [
        ("s1", "seedance-2"),
        ("s2", "kling-3.0/pro"),
        ("s3", "kling-3.0/standard"),
        ("s4", "seedance-2-fast"),
        ("s5", "seedance-2"),
    ])
    def test_env_override_does_not_affect_router(self, scenario, expected, monkeypatch):
        # Even setting env to a different model shouldn't affect router output
        monkeypatch.setenv("POYO_VIDEO_MODEL", "happy-horse")
        assert select_model(scenario) == expected
