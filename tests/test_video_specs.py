"""Tests for media_quality_audit video specs parsing (P0-3)."""

from pathlib import Path

from src.skills.media_quality_audit import MediaQualityAuditSkill


class TestVideoSpecs:
    def test_parses_normal_video(self, sample_videos):
        """Should correctly parse width/height/fps/bitrate from a real video."""
        specs = MediaQualityAuditSkill._get_video_specs(sample_videos["normal"])
        assert specs is not None
        assert specs["width"] == 720
        assert specs["height"] == 1280
        assert specs["fps"] == 30.0
        assert specs["bitrate_kbps"] > 0

    def test_returns_none_for_invalid_file(self):
        """Non-video file should return None gracefully."""
        specs = MediaQualityAuditSkill._get_video_specs(Path("/dev/null"))
        assert specs is None

    def test_returns_none_for_missing_file(self):
        """Missing file should return None gracefully."""
        specs = MediaQualityAuditSkill._get_video_specs(Path("/nonexistent/path.mp4"))
        assert specs is None
