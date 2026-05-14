"""Tests for src/skills/video_continuity_manager.py (Sprint 1 P1-3)."""

import asyncio
import subprocess
from pathlib import Path

import pytest

from src.skills.video_continuity_manager import (
    VideoContinuityManagerSkill,
    extract_last_frame,
)


@pytest.fixture
def tiny_mp4(tmp_path: Path) -> Path:
    """Generate a 1-second red mp4 fixture via ffmpeg."""
    src = tmp_path / "test.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "color=c=red:s=320x240:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(src),
        ],
        check=True, capture_output=True,
    )
    assert src.exists() and src.stat().st_size > 100
    return src


class TestExtractLastFrame:
    @pytest.mark.asyncio
    async def test_extract_produces_png(self, tiny_mp4: Path, tmp_path: Path):
        frame = await extract_last_frame(tiny_mp4, output_dir=tmp_path)
        assert frame.exists()
        assert frame.suffix == ".png"
        assert frame.stat().st_size > 100

    @pytest.mark.asyncio
    async def test_extract_defaults_to_source_dir(self, tiny_mp4: Path):
        frame = await extract_last_frame(tiny_mp4)
        assert frame.parent == tiny_mp4.parent

    @pytest.mark.asyncio
    async def test_extract_missing_source_raises(self):
        with pytest.raises(FileNotFoundError):
            await extract_last_frame("/nonexistent/video.mp4")

    @pytest.mark.asyncio
    async def test_extract_empty_file_raises(self, tmp_path: Path):
        empty = tmp_path / "empty.mp4"
        empty.touch()
        with pytest.raises(FileNotFoundError):
            await extract_last_frame(empty)


class TestVideoContinuityManagerSkill:
    @pytest.mark.asyncio
    async def test_happy_path(self, tiny_mp4: Path, tmp_path: Path):
        skill = VideoContinuityManagerSkill()
        result = await skill.safe_execute({
            "video_path": str(tiny_mp4),
            "output_dir": str(tmp_path),
        })
        assert result.success is True
        assert result.data["continuity_frame_path"]
        assert Path(result.data["continuity_frame_path"]).exists()
        assert result.data["source_video"] == str(tiny_mp4)

    @pytest.mark.asyncio
    async def test_param_validation_missing_video_path(self):
        skill = VideoContinuityManagerSkill()
        result = await skill.safe_execute({})
        assert result.success is False
        assert "video_path" in result.error

    @pytest.mark.asyncio
    async def test_fallback_triggered_on_missing_source(self):
        skill = VideoContinuityManagerSkill()
        result = await skill.safe_execute({
            "video_path": "/nonexistent.mp4",
        })
        # Fallback returns success=True (safe degradation, NOT halt)
        # with is_fallback=True so downstream can distinguish from real success.
        assert result.success is True
        assert result.data["continuity_frame_path"] is None
        assert result.metadata.get("is_fallback") is True

    @pytest.mark.asyncio
    async def test_output_validation_rejects_nonexistent_path(self):
        skill = VideoContinuityManagerSkill()
        errors = skill.validate_output({
            "continuity_frame_path": "/nonexistent/frame.png",
        })
        assert any("does not exist" in e for e in errors)

    @pytest.mark.asyncio
    async def test_output_validation_accepts_none_path(self):
        # None continuity_frame_path is valid (fallback signal to caller).
        skill = VideoContinuityManagerSkill()
        errors = skill.validate_output({"continuity_frame_path": None})
        assert errors == []
