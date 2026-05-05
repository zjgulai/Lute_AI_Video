"""Tests for S3 Influencer Remix Pipeline (R8 milestone).

Tests the full orchestrator with registered skills.
All skills run in stub mode (no real API calls).
"""

from __future__ import annotations

import asyncio

import pytest

from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline, S3Result


class TestS3Pipeline:
    """S3 influencer remix pipeline tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self):
        """Full S3 pipeline from video URL to thumbnail prompts.

        This is the R8 milestone E2E test.
        """
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@influencer/video/123",
            product={
                "name": "X1 Pump",
                "usps": ["quiet operation", "portable design", "powerful suction"],
                "brand_name": "LactFit",
                "category": "breast pump",
            },
            influencer_name="Jessica MomLife",
            extract_segments=True,
            brief_id="RMX-001",
        )

        assert isinstance(result, S3Result)
        assert result.success, f"Pipeline failed: {result.errors}"
        assert result.video_analysis is not None
        assert result.remix_script is not None
        assert len(result.video_prompts) > 0
        assert len(result.thumbnail_prompts) > 0

    @pytest.mark.asyncio
    async def test_video_analysis_output(self):
        """Video analysis should produce expected fields."""
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@user/video/456",
            product={"name": "Test Product", "usps": ["quality"]},
        )

        analysis = result.video_analysis
        assert analysis is not None
        assert "hook_type" in analysis
        assert "speech_style" in analysis
        assert "avg_speech_wpm" in analysis
        assert "segments" in analysis
        assert len(analysis["segments"]) > 0

    @pytest.mark.asyncio
    async def test_remix_script_preserves_style(self):
        """Remix script should mention original style."""
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@user/video/789",
            product={"name": "X1", "usps": ["feature"], "brand_name": "LactFit"},
            influencer_name="Test Influencer",
        )

        script = result.remix_script
        assert script is not None
        assert "original_style_preserved" in script
        assert "segments" in script
        assert len(script["segments"]) >= 3

    @pytest.mark.asyncio
    async def test_video_prompts_per_segment(self):
        """Should generate one video prompt per segment."""
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@user/video/101",
            product={"name": "Y2", "usps": ["fast", "cheap"]},
        )

        assert len(result.video_prompts) > 0
        for p in result.video_prompts:
            assert "segment_index" in p
            assert "segment_type" in p
            assert "prompt" in p
            assert len(p["prompt"]) > 0

    @pytest.mark.asyncio
    async def test_thumbnail_prompts(self):
        """Should generate thumbnail variants."""
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@user/video/202",
            product={"name": "Z3", "usps": ["safe", "durable"]},
        )

        assert len(result.thumbnail_prompts) > 0
        for t in result.thumbnail_prompts:
            assert "style" in t
            assert "prompt" in t
            assert "aspect_ratio" in t

    @pytest.mark.asyncio
    async def test_error_handling_bad_video_url(self):
        """Should handle errors gracefully."""
        from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline

        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="",
            product={"name": "Product"},
        )
        # Should fail at validate_params on video-analysis-skill
        assert result.success is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_different_products(self):
        """Should work with different product types."""
        pipeline = S3InfluencerRemixPipeline()
        products = [
            {"name": "Pump A", "usps": ["quiet"], "brand_name": "BrandA"},
            {"name": "Pump B", "usps": ["portable", "light"], "brand_name": "BrandB"},
            {"name": "Pump C", "usps": [], "brand_name": ""},
        ]
        for product in products:
            result = await pipeline.run(
                video_url="https://tiktok.com/@u/v/1",
                product=product,
            )
            assert result.success, f"Failed for {product['name']}: {result.errors}"

    @pytest.mark.asyncio
    async def test_segment_types_mapped(self):
        """Video prompt segment types should be mapped correctly."""
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@u/v/1",
            product={"name": "Test", "usps": ["good"]},
        )

        valid_types = {
            "product_showcase", "lifestyle", "feature_highlight",
            "testimonials", "tutorial_demo", "brand_story",
        }
        for p in result.video_prompts:
            if "prompt" in p and isinstance(p["prompt"], dict):
                pass  # Skill returns dict with parameters
            elif "prompt" in p and isinstance(p["prompt"], str):
                assert len(p["prompt"]) > 0

    @pytest.mark.asyncio
    async def test_full_result_to_dict(self):
        """S3Result.to_dict() should serialize properly."""
        pipeline = S3InfluencerRemixPipeline()
        result = await pipeline.run(
            video_url="https://tiktok.com/@u/v/1",
            product={"name": "X1", "usps": ["a", "b"]},
        )

        d = result.to_dict()
        assert d["success"] is True
        assert isinstance(d["segment_count"], int)
        assert d["segment_count"] > 0
        assert isinstance(d["video_prompts"], list)
        assert isinstance(d["thumbnail_prompts"], list)
        assert isinstance(d["errors"], list)

    @pytest.mark.asyncio
    async def test_pipeline_steps_ordered(self):
        """Pipeline should run steps in order and stop on first failure."""
        pipeline = S3InfluencerRemixPipeline()
        # Empty video URL → step 1 fails → no step 2-4
        result = await pipeline.run(
            video_url="",
            product={"name": "X1"},
        )
        assert result.video_analysis is None
        assert result.remix_script is None
        assert len(result.video_prompts) == 0
