"""S1 Product Direct E2E integration test.

Verifies the S1 (Product to Video) scenario end-to-end using skills:
1. ProductStrategySkill generates content briefs
2. SeedancePromptSkill generates video prompts
3. ThumbnailPromptSkill generates thumbnail prompts

This test runs the entire skill pipeline in a single python process.
Uses fallback/mock mode — no real LLM calls.
"""

from __future__ import annotations

import asyncio

import pytest

from src.skills.product_strategy import ProductStrategySkill
from src.skills.registry import SkillRegistry
from src.skills.seedance_prompt import SeedancePromptSkill
from src.skills.thumbnail_prompt import ThumbnailPromptSkill


# Ensure skills are registered
@pytest.fixture(autouse=True, scope="session")
def register_skills():
    original_global_skills = dict(SkillRegistry._global_skills)
    SkillRegistry.register(ProductStrategySkill())
    SkillRegistry.register(SeedancePromptSkill())
    SkillRegistry.register(ThumbnailPromptSkill())
    yield
    SkillRegistry._global_skills = original_global_skills


# A realistic product fixture matching the LactFit brand
PRODUCT_FIXTURE = {
    "product_catalog": {
        "product_id": "PROD-001",
        "product_name": "LactFit Wearable Breast Pump X1",
        "brand": "LactFit",
        "description": "A silent, hands-free wearable breast pump designed for working mothers.",
        "usps": [
            "Ultra-silent motor (under 40dB)",
            "Hands-free wear, fits in standard bra",
            "2-hour battery life",
            "Easy one-piece clean design",
        ],
        "image_url": "https://cdn.lactfit.com/x1_hero.jpg",
        "price": 299.99,
        "category": "breast_pumps",
    },
    "brand_guidelines": {
        "brand_name": "LactFit",
        "tone": "warm, empowering, real, professional",
        "primary_color": "#6B8E8E",
        "secondary_color": "#F5E6D3",
        "forbidden_claims": [
            "medical claims",
            "competitor name-calling",
            "fear-based marketing",
        ],
        "target_audience": "Working mothers 25-40",
    },
    "target_platforms": ["tiktok", "shopify", "amazon"],
    "target_languages": ["en"],
    "content_calendar_week": "2026-W18",
    "content_scenario": "product_direct",
}


class TestS1E2EProductStrategy:
    """Step 1: Generate content briefs."""

    def test_strategy_generates_briefs(self):
        """Should generate weekly briefs from product info."""
        result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", PRODUCT_FIXTURE))
        assert result.success is True
        data = result.data
        assert "briefs" in data
        briefs = data["briefs"]

        # Verify brief structure
        for brief in briefs:
            assert "id" in brief, f"Brief missing id: {brief}"
            assert "topic" in brief, f"Brief missing topic: {brief}"
            assert "key_message" in brief, f"Brief missing key_message: {brief}"

    def test_strategy_respects_product_catalog(self):
        """Strategy should reference the product's USPs."""
        result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", PRODUCT_FIXTURE))
        briefs = result.data["briefs"]

        # Check that USPs are referenced in briefs
        all_topics = " ".join(b.get("topic", "") for b in briefs).lower()
        all_messages = " ".join(b.get("key_message", "") for b in briefs).lower()

        # At least one brief should mention the product name or key USPs
        product_name = PRODUCT_FIXTURE["product_catalog"]["product_name"].lower()
        has_product_ref = product_name in all_topics or "lactfit" in all_topics
        assert has_product_ref, "No product reference found in briefs"

    def test_strategy_covers_video_types(self):
        """Briefs should cover different video types."""
        result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", PRODUCT_FIXTURE))
        briefs = result.data["briefs"]
        types = set(b.get("video_type", "") for b in briefs)

        # Should have at least 3 different video types
        assert len(types) >= 2, f"Too few video types: {types}"

    def test_strategy_targets_correct_platforms(self):
        """Each brief should target valid platforms."""
        result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", PRODUCT_FIXTURE))
        briefs = result.data["briefs"]
        valid_platforms = {"tiktok", "shopify", "amazon", "youtube_shorts", "facebook", "reddit"}

        for brief in briefs:
            platforms = brief.get("target_platforms", [])
            for p in platforms:
                assert p in valid_platforms, f"Invalid platform '{p}' in brief {brief['id']}"


class TestS1E2EVideoPrompt:
    """Step 2: Generate Seedance video prompts from a sample brief."""

    def test_video_prompt_from_brief(self):
        """Should generate a Seedance prompt from a brief."""
        sample_brief = PRODUCT_FIXTURE["product_catalog"]
        script_segments = [
            {
                "voiceover": "Meet the LactFit X1 — the pump that fits your life, not the other way around.",
                "visual_description": "Product slowly rotating on clean white background",
                "start_time": 0,
                "end_time": 4,
                "duration_seconds": 4,
            },
            {
                "voiceover": "With its ultra-silent motor, you can pump during meetings without anyone knowing.",
                "visual_description": "Woman in office using pump discreetly",
                "start_time": 4,
                "end_time": 10,
                "duration_seconds": 6,
            },
            {
                "voiceover": "Just 3 parts to clean — it's that simple.",
                "visual_description": "Hands disassembling pump for cleaning",
                "start_time": 10,
                "end_time": 14,
                "duration_seconds": 4,
            },
            {
                "voiceover": "Get yours at the link below and start pumping on your terms.",
                "visual_description": "Product with call-to-action overlay",
                "start_time": 14,
                "end_time": 17,
                "duration_seconds": 3,
            },
        ]

        result = asyncio.run(SkillRegistry().execute("seedance-video-prompt", {
            "script_segments": script_segments,
            "product_name": sample_brief.get("product_name", "X1"),
            "style_ref_images": ["https://cdn.lactfit.com/x1_hero.jpg"],
        }))

        assert result.success is True
        prompts = result.data
        assert isinstance(prompts, list)
        assert len(prompts) == len(script_segments)
        assert result.metadata["prompt_count"] == len(prompts)

        for prompt in prompts:
            assert isinstance(prompt, dict)
            assert isinstance(prompt["segment_prompt"], str)
            assert prompt["segment_prompt"].strip()
            assert "duration_seconds" in prompt
            assert prompt["duration_seconds"] > 0
            assert "has_forbidden_words" in prompt
            assert prompt["has_forbidden_words"] is False
            assert isinstance(prompt["segment_type"], str)
            assert prompt["segment_type"]
            assert isinstance(prompt["shot_type"], str)
            assert prompt["shot_type"]
            assert isinstance(prompt["camera"], str)
            assert prompt["camera"]
            assert isinstance(prompt["lighting"], str)
            assert prompt["lighting"]

        for segment, prompt in zip(script_segments, prompts, strict=True):
            assert segment["visual_description"] in prompt["segment_prompt"]

        assert [prompt["duration_seconds"] for prompt in prompts] == [4, 6, 4, 3]


class TestS1E2EThumbnailPrompt:
    """Step 3: Generate thumbnail prompts from a brief's hook."""

    def test_thumbnail_prompts_from_script(self):
        """Should generate 4 thumbnail variants from a script hook."""
        result = asyncio.run(SkillRegistry().execute("gpt-image-thumbnail-prompt", {
            "hook_text": "Pump during Zoom calls? Yes, it's that quiet.",
            "product_name": "LactFit X1",
            "brand_color": "#6B8E8E",
            "price": 299.99,
            "platform": "tiktok",
        }))

        assert result.success is True
        data = result.data
        assert len(data["variants"]) == 4

        # Verify each variant has required fields
        for variant in data["variants"]:
            assert "variant_id" in variant
            assert "prompt" in variant
            assert "size" in variant
            assert "style" in variant
            # All variants should reference the product
            assert "LactFit X1" in variant["prompt"]

    def test_thumbnail_platform_size(self):
        """Platform-specific sizes should be correct."""
        platform_cases = [
            ("tiktok", "1024x1792"),
            ("shopify", "1536x1024"),
            ("amazon", "1536x1024"),
            ("reddit", "1024x1024"),
        ]

        for platform, expected_size in platform_cases:
            result = asyncio.run(SkillRegistry().execute("gpt-image-thumbnail-prompt", {
                "hook_text": "Test hook",
                "product_name": "Product",
                "platform": platform,
            }))
            for variant in result.data["variants"]:
                assert variant["size"] == expected_size,                     f"Platform {platform} expected {expected_size}, got {variant['size']}"


class TestS1E2EIntegration:
    """Full S1 flow: strategy -> video prompt -> thumbnail prompt."""

    def test_full_s1_pipeline(self):
        """Complete S1 flow should produce all outputs."""
        # Step 1: Strategy
        strategy_result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", PRODUCT_FIXTURE))
        assert strategy_result.success is True
        briefs = strategy_result.data["briefs"]
        assert len(briefs) > 0

        first_brief = briefs[0]
        topic = first_brief.get("topic", "Product demo")
        usp = first_brief.get("usp_priority", ["feature"])[0]

        # Step 2: Video prompt (using brief info)
        sample_segments = [
            {"voiceover": topic[:100], "start_time": 0, "end_time": 4, "duration_seconds": 4},
            {"voiceover": f"Featuring {usp}", "start_time": 4, "end_time": 9, "duration_seconds": 5},
        ]
        video_result = asyncio.run(SkillRegistry().execute("seedance-video-prompt", {
            "script_segments": sample_segments,
            "product_name": PRODUCT_FIXTURE["product_catalog"]["product_name"],
        }))
        assert video_result.success is True
        video_prompts = video_result.data
        assert isinstance(video_prompts, list)
        assert len(video_prompts) == len(sample_segments)
        assert video_result.metadata["prompt_count"] == len(sample_segments)
        assert sum(prompt["duration_seconds"] for prompt in video_prompts) == 9

        # Step 3: Thumbnail from topic
        thumb_result = asyncio.run(SkillRegistry().execute("gpt-image-thumbnail-prompt", {
            "hook_text": topic[:60],
            "product_name": PRODUCT_FIXTURE["product_catalog"]["product_name"],
            "brand_color": PRODUCT_FIXTURE["brand_guidelines"]["primary_color"],
            "price": PRODUCT_FIXTURE["product_catalog"]["price"],
            "platform": "tiktok",
        }))
        assert thumb_result.success is True
        assert len(thumb_result.data["variants"]) == 4

        # Summary
        print("\n=== S1 E2E Pipeline Summary ===")
        print(f"Strategy: {len(briefs)} briefs generated")
        print(f"  First brief topic: {briefs[0].get('topic', 'N/A')[:80]}")
        print(f"Video prompts: {len(video_prompts)} segments")
        print(f"Thumbnail variants: {len(thumb_result.data['variants'])}")

    def test_s1_with_minimal_input(self):
        """S1 should work with minimal input (fallback mode)."""
        minimal_input = {
            "product_catalog": {"product_name": "Test Product"},
            "brand_guidelines": {"brand_name": "Test"},
            "target_platforms": ["tiktok"],
        }

        # Strategy should fallback gracefully
        result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", minimal_input))
        assert result.success is True
        assert result.data is not None

    def test_s1_error_handling(self):
        """S1 should handle missing input gracefully."""
        # Completely empty input
        result = asyncio.run(SkillRegistry().execute("product-to-video-strategy", {}))
        assert result.success is False
        error_msg = result.error or ""
        assert "Parameter validation" in error_msg
