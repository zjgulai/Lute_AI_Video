"""Tests for configurable quality thresholds and enforce mode behavior."""

import pytest


class TestThresholdConfigurability:
    """Verify thresholds read from env vars with sensible defaults."""

    def test_frame_variance_mse_default(self):
        from src.config import FRAME_VARIANCE_MSE_THRESHOLD
        assert FRAME_VARIANCE_MSE_THRESHOLD == 50.0

    def test_frame_variance_brightness_default(self):
        from src.config import FRAME_VARIANCE_BRIGHTNESS_THRESHOLD
        assert FRAME_VARIANCE_BRIGHTNESS_THRESHOLD == 20.0

    def test_av_sync_defaults(self):
        from src.config import AV_SYNC_MAX_ABS_DIFF, AV_SYNC_MAX_REL_DIFF
        assert AV_SYNC_MAX_ABS_DIFF == 0.5
        assert AV_SYNC_MAX_REL_DIFF == 0.05

    def test_video_specs_defaults(self):
        from src.config import (
            VIDEO_ASPECT_RATIO_MAX,
            VIDEO_ASPECT_RATIO_MIN,
            VIDEO_CRITICAL_BITRATE_KBPS,
            VIDEO_CRITICAL_FPS,
            VIDEO_MIN_BITRATE_KBPS,
            VIDEO_MIN_FPS,
        )
        assert VIDEO_ASPECT_RATIO_MIN == 0.53
        assert VIDEO_ASPECT_RATIO_MAX == 0.60
        assert VIDEO_CRITICAL_FPS == 20.0
        assert VIDEO_MIN_FPS == 25.0
        assert VIDEO_CRITICAL_BITRATE_KBPS == 1000.0
        assert VIDEO_MIN_BITRATE_KBPS == 1500.0

    @pytest.mark.parametrize(
        "env_var,expected_attr,override_value,expected_type",
        [
            ("FRAME_VARIANCE_MSE_THRESHOLD", "FRAME_VARIANCE_MSE_THRESHOLD", "100.0", float),
            ("FRAME_VARIANCE_BRIGHTNESS_THRESHOLD", "FRAME_VARIANCE_BRIGHTNESS_THRESHOLD", "30.0", float),
            ("AV_SYNC_MAX_ABS_DIFF", "AV_SYNC_MAX_ABS_DIFF", "1.0", float),
            ("AV_SYNC_MAX_REL_DIFF", "AV_SYNC_MAX_REL_DIFF", "0.10", float),
            ("VIDEO_MIN_FPS", "VIDEO_MIN_FPS", "30.0", float),
            ("VIDEO_MIN_BITRATE_KBPS", "VIDEO_MIN_BITRATE_KBPS", "2000.0", float),
        ],
    )
    def test_env_override(self, monkeypatch, env_var, expected_attr, override_value, expected_type):
        """Each threshold can be overridden via environment variable."""
        monkeypatch.setenv(env_var, override_value)
        # Force re-import by clearing cache
        import importlib

        import src.config as config_mod

        importlib.reload(config_mod)
        actual = getattr(config_mod, expected_attr)
        assert isinstance(actual, expected_type)
        assert actual == expected_type(override_value)


class TestEnforceModeBehavior:
    """Verify enforce mode affects all_ok correctly."""

    @staticmethod
    def _patch_mode(monkeypatch, mode: str):
        """Patch QUALITY_MODE on imported modules without full reload."""
        import src.config as config_mod
        import src.skills.remotion_assemble as ra_mod
        import src.skills.seedance_video_generate as sdg_mod

        monkeypatch.setattr(config_mod, "QUALITY_MODE", mode)
        monkeypatch.setattr(sdg_mod, "QUALITY_MODE", mode)
        monkeypatch.setattr(ra_mod, "QUALITY_MODE", mode)
        return config_mod, sdg_mod, ra_mod

    def test_enforce_mode_blocks_on_frame_variance(self, sample_videos, monkeypatch):
        """In enforce mode, black screen video should fail all_ok."""
        _, sdg_mod, _ = self._patch_mode(monkeypatch, "enforce")
        skill = sdg_mod.SeedanceVideoGenerateSkill()
        verification = skill._self_verify(sample_videos["black"], is_stub=False)
        assert verification["all_ok"] is False
        assert verification["variance_ok"] is False
        assert any("black_screen" in f for f in verification["failures"])

    def test_enforce_mode_blocks_on_static_image(self, sample_videos, monkeypatch):
        """In enforce mode, static video should fail all_ok."""
        _, sdg_mod, _ = self._patch_mode(monkeypatch, "enforce")
        skill = sdg_mod.SeedanceVideoGenerateSkill()
        verification = skill._self_verify(sample_videos["static"], is_stub=False)
        assert verification["all_ok"] is False
        assert verification["variance_ok"] is False
        assert any("static_image" in f for f in verification["failures"])

    def test_enforce_mode_allows_normal_video(self, sample_videos, monkeypatch):
        """In enforce mode, normal video should pass all_ok."""
        _, sdg_mod, _ = self._patch_mode(monkeypatch, "enforce")
        skill = sdg_mod.SeedanceVideoGenerateSkill()
        verification = skill._self_verify(sample_videos["normal"], is_stub=False)
        assert verification["all_ok"] is True
        assert verification["variance_ok"] is True

    def test_enforce_mode_allows_no_audio_video(self, sample_videos, monkeypatch):
        """In enforce mode, video without audio should still pass av_sync."""
        _, _, ra_mod = self._patch_mode(monkeypatch, "enforce")
        result = ra_mod.RemotionAssembleSkill._check_av_sync(sample_videos["normal"])
        assert result["sync_ok"] is True
        assert result["audio_dur"] == 0.0

    def test_observe_mode_does_not_block_variance(self, sample_videos, monkeypatch):
        """In observe mode, variance is skipped for speed and never blocks all_ok."""
        _, sdg_mod, _ = self._patch_mode(monkeypatch, "observe")
        skill = sdg_mod.SeedanceVideoGenerateSkill()
        verification = skill._self_verify(sample_videos["black"], is_stub=False)
        # P0-3 speed contract: observe/off mode does not run ffmpeg frame variance.
        assert verification["variance_ok"] is True
        assert verification["variance_details"] is None
        assert verification["all_ok"] == (
            verification["size_ok"]
            and verification["header_ok"]
            and verification["duration_ok"]
            and verification["resolution_ok"]
        )
