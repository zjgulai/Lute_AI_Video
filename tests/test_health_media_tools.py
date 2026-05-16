"""Health endpoint media_tools observability (T3 / D13).

Verifies /health reports yt-dlp + faster-whisper availability so deploys
can confirm S3 KOL video-analysis isn't silently falling back to mock.
"""

from __future__ import annotations

import pytest

from src.routers.health import health


@pytest.mark.asyncio
async def test_health_exposes_media_tools():
    result = await health()
    assert "media_tools" in result
    mt = result["media_tools"]
    assert "ytdlp_available" in mt
    assert "whisper_available" in mt
    assert "clip_available" in mt
    assert isinstance(mt["ytdlp_available"], bool)
    assert isinstance(mt["whisper_available"], bool)
    assert isinstance(mt["clip_available"], bool)


@pytest.mark.asyncio
async def test_health_version_bumped():
    result = await health()
    assert result["version"] == "0.2.5"
