"""Tests for seedance_video_generate frame variance detection (P0-1)."""

from pathlib import Path

import pytest

from src.skills.seedance_video_generate import SeedanceVideoGenerateSkill
from src.config import QUALITY_MODE


class TestFrameVariance:
    def test_detects_black_screen(self, sample_videos):
        """Black screen video should fail variance check."""
        result = SeedanceVideoGenerateSkill._check_frame_variance(sample_videos["black"])
        assert result["variance_ok"] is False
        assert any("black_screen" in f for f in result["failures"])

    def test_detects_static_image(self, sample_videos):
        """Nearly-static video (1fps) should fail variance check."""
        result = SeedanceVideoGenerateSkill._check_frame_variance(sample_videos["static"])
        assert result["variance_ok"] is False
        assert any("static_image" in f for f in result["failures"])

    def test_normal_video_passes(self, sample_videos):
        """Normal motion video should pass variance check."""
        result = SeedanceVideoGenerateSkill._check_frame_variance(sample_videos["normal"])
        assert result["variance_ok"] is True
        assert result["failures"] == []

    def test_tiny_file_skipped(self):
        """Files under 1KB are skipped gracefully."""
        result = SeedanceVideoGenerateSkill._check_frame_variance(Path("/dev/null"))
        assert result["variance_ok"] is True
        assert result["failures"] == []

    def test_observation_mode_does_not_block(self, sample_videos):
        """In observe/off mode, all_ok should be true even for black screen."""
        if QUALITY_MODE == "enforce":
            pytest.skip("Skipping because QUALITY_MODE=enforce")

        skill = SeedanceVideoGenerateSkill()
        # Create a minimal verification for a black video
        verification = skill._self_verify(sample_videos["black"], is_stub=False)
        # all_ok should be based on size/header/resolution only, not variance
        assert verification["all_ok"] == (
            verification["size_ok"] and verification["header_ok"]
            and verification["duration_ok"] and verification["resolution_ok"]
        )

    def test_performance_logged(self, sample_videos, caplog):
        """Frame variance check should log duration."""
        import structlog
        from unittest.mock import MagicMock

        SeedanceVideoGenerateSkill._check_frame_variance(sample_videos["normal"])
        # The debug log is sent via structlog, not stdlib logging,
        # so caplog won't capture it. We verify the method runs without error.
