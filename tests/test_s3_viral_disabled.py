"""S3 viral extraction disable flag tests (ADR-004 Option D).

When `S3_VIRAL_EXTRACT_DISABLED=1`, the s3 pipeline must:
  1. Not call video-analysis-skill (no network / no KOL fetch)
  2. Return _soft_degraded=True with _degraded_reason="s3_viral_extract_disabled_adr004"
  3. Still allow downstream steps to proceed via fallback_prompt
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline


@pytest.mark.asyncio
async def test_video_analysis_disabled_returns_degraded_stub():
    pipeline = S3InfluencerRemixPipeline()
    state = {
        "config": {
            "video_url": "https://tiktok.com/@kol/video/999",
            "extract_segments": True,
            "video_duration": 30,
            "product": {"name": "X1", "usps": ["a"], "brand_name": "B", "category": "c"},
        },
        "steps": [],
        "errors": [],
    }

    with patch("src.pipeline.s3_remix_pipeline.S3_VIRAL_EXTRACT_DISABLED", True):
        result = await pipeline.run_step("video_analysis", state)

    assert result["_soft_degraded"] is True
    assert result["_degraded_reason"] == "s3_viral_extract_disabled_adr004"
    assert result["viral_segments"] == []
    assert result["segments"] == []
    assert "fallback_prompt" in result
    assert any("video_analysis_failed" in e for e in state["errors"])


@pytest.mark.asyncio
async def test_video_analysis_enabled_calls_skill():
    pipeline = S3InfluencerRemixPipeline()
    state = {
        "config": {
            "video_url": "https://tiktok.com/@kol/video/999",
            "extract_segments": True,
            "video_duration": 30,
            "product": {"name": "X1", "usps": ["a"], "brand_name": "B", "category": "c"},
        },
        "steps": [],
        "errors": [],
    }

    with patch("src.pipeline.s3_remix_pipeline.S3_VIRAL_EXTRACT_DISABLED", False):
        result = await pipeline.run_step("video_analysis", state)

    assert isinstance(result, dict)
    assert result.get("_degraded_reason") != "s3_viral_extract_disabled_adr004"


@pytest.mark.asyncio
async def test_step_video_analysis_method_returns_failure_when_disabled():
    pipeline = S3InfluencerRemixPipeline()

    with patch("src.pipeline.s3_remix_pipeline.S3_VIRAL_EXTRACT_DISABLED", True):
        result = await pipeline._step_video_analysis(
            video_url="https://tiktok.com/@kol/video/999",
            extract_segments=True,
        )

    assert result.success is False
    assert result.error == "s3_viral_extract_disabled_by_policy"
    assert result.data is None
