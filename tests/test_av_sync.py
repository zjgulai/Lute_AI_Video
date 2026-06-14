"""Tests for remotion_assemble audio-video sync detection (P0-2)."""

from pathlib import Path

import pytest

from src.config import QUALITY_MODE
from src.skills.remotion_assemble import RemotionAssembleSkill


class TestAVSync:
    def test_no_audio_stream_ok(self, sample_videos):
        """Video without audio should return sync_ok=True."""
        result = RemotionAssembleSkill._check_av_sync(sample_videos["normal"])
        assert result["sync_ok"] is True
        assert result["audio_dur"] == 0.0

    def test_with_audio_sync_ok(self, sample_videos):
        """Video with matching audio should return sync_ok=True."""
        result = RemotionAssembleSkill._check_av_sync(sample_videos["with_audio"])
        assert result["sync_ok"] is True
        assert result["audio_dur"] > 0.0
        assert result["diff"] < 0.5

    def test_nonexistent_file_returns_no_video(self):
        """Missing file should return no_video_stream failure."""
        result = RemotionAssembleSkill._check_av_sync(Path("/dev/null"))
        assert result["sync_ok"] is False
        assert "no_video_stream" in result["failure"]

    def test_observation_mode_does_not_block(self, sample_videos):
        """In observe/off mode, all_ok should not depend on av_sync."""
        if QUALITY_MODE == "enforce":
            pytest.skip("Skipping because QUALITY_MODE=enforce")

        skill = RemotionAssembleSkill()
        verification = skill._self_verify(sample_videos["with_audio"], is_stub=False)
        # all_ok should be based on size/header/duration only
        assert verification["all_ok"] == (
            verification["size_ok"] and verification["header_ok"]
            and verification["duration_ok"]
        )
