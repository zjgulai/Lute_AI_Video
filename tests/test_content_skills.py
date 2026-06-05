"""Tests for content generation skills.

Verifies:
1. ProductStrategySkill: prompt injection, fallback briefs, param validation
2. SeedancePromptSkill: prompt template selection, @material references
3. ThumbnailPromptSkill: variant generation, platform sizes, brand injection

All tests use stub/fallback mode — no real LLM calls.
"""

from __future__ import annotations

import pytest

from src.skills.product_strategy import ProductStrategySkill
from src.skills.seedance_prompt import (
    FORBIDDEN_PATTERNS,
    NARRATIVE_SHOT_TEMPLATE,
    SeedancePromptSkill,
    _shot_type_from_segment,
)
from src.skills.thumbnail_prompt import ThumbnailPromptSkill

# ==============================================================================
# ProductStrategySkill Tests
# ==============================================================================


class TestProductStrategySkillInit:
    """Skill initialization and registration."""

    def test_skill_has_name(self):
        skill = ProductStrategySkill()
        assert skill.name == "product-to-video-strategy"
        assert skill.description

    def test_skill_has_fallback(self):
        skill = ProductStrategySkill()
        result = skill.fallback({"content_calendar_week": "2026-W18"})
        assert result.success is True
        data = result.data
        assert "briefs" in data
        assert len(data["briefs"]) >= 1


class TestProductStrategySkillValidation:
    """Parameter and output validation."""

    @pytest.fixture
    def skill(self):
        return ProductStrategySkill()

    def test_validate_missing_params(self, skill):
        errors = skill.validate_params({})
        assert len(errors) > 0

    def test_validate_empty_product_catalog(self, skill):
        errors = skill.validate_params({"product_catalog": {}})
        assert len(errors) > 0

    def test_validate_valid_params(self, skill):
        errors = skill.validate_params({
            "product_catalog": {"product_name": "Test Product"},
        })
        assert len(errors) == 0

    def test_validate_output_empty(self, skill):
        errors = skill.validate_output(None)
        assert len(errors) > 0

    def test_validate_output_valid(self, skill):
        errors = skill.validate_output({"briefs": [{"id": "B1"}]})
        assert len(errors) == 0

    def test_validate_output_empty_briefs(self, skill):
        errors = skill.validate_output({"briefs": []})
        assert len(errors) > 0


class TestProductStrategySkillFallback:
    """Fallback brief generation."""

    @pytest.fixture
    def skill(self):
        return ProductStrategySkill()

    def test_fallback_injects_product_name(self, skill):
        result = skill.fallback({
            "product_catalog": {"product_name": "X1 Pump"},
        })
        briefs = result.data["briefs"]
        for b in briefs:
            # Product name should appear in topics
            topics = [b.get("topic", "") for b in briefs]
            # At least some topics should reference the product
            assert any("X1 Pump" in t for t in topics)

    def test_fallback_returns_valid_week(self, skill):
        result = skill.fallback({"content_calendar_week": "2026-W20"})
        assert result.data["week"] == "2026-W20"

    def test_fallback_no_params(self, skill):
        """Fallback should work with empty params."""
        result = skill.fallback({})
        assert result.success is True
        assert result.data is not None


# ==============================================================================
# SeedancePromptSkill Tests
# ==============================================================================


class TestSeedancePromptSkillInit:
    """Skill initialization."""

    def test_skill_has_name(self):
        skill = SeedancePromptSkill()
        assert skill.name == "seedance-video-prompt"

    def test_skill_has_templates(self):
        """Current contract uses one narrative template, not legacy product rotations."""
        assert "{visual_description}" in NARRATIVE_SHOT_TEMPLATE
        assert len(FORBIDDEN_PATTERNS) >= 5


class TestSeedancePromptSkillExecution:
    """Prompt generation."""

    @pytest.fixture
    def skill(self):
        return SeedancePromptSkill()

    @pytest.mark.asyncio
    async def test_execute_with_segments(self, skill):
        """Should generate prompt from script segments."""
        result = await skill.execute({
            "script_segments": [
                {
                    "segment_type": "hook",
                    "voiceover": "Introducing the new pump",
                    "visual_description": "Close-up of a compact wearable pump on a desk",
                    "start_time": 0,
                    "end_time": 3,
                },
                {
                    "segment_type": "solution",
                    "voiceover": "Here's how it works",
                    "visual_description": "Hands demonstrate quiet setup in a work bag",
                    "start_time": 3,
                    "end_time": 8,
                },
                {
                    "segment_type": "cta",
                    "voiceover": "Buy now at the link below",
                    "visual_description": "Clean final product beauty shot",
                    "start_time": 8,
                    "end_time": 10,
                },
            ],
            "product_name": "X1 Pump",
        })
        assert result.success is True
        data = result.data
        assert len(data) == 3
        assert data[0]["segment_type"] == "hook"
        assert "Close-up of a compact wearable pump" in data[0]["segment_prompt"]
        assert data[0]["duration_seconds"] == 3

    @pytest.mark.asyncio
    async def test_execute_no_segments(self, skill):
        """Should return fallback prompt when no segments."""
        result = await skill.execute({
            "script_segments": [],
            "product_name": "Product",
        })
        assert result.success is True
        data = result.data
        assert len(data) == 1
        assert data[0]["segment_type"] == "body"

    @pytest.mark.asyncio
    async def test_prompt_preserves_duration_seconds(self, skill):
        result = await skill.execute({
            "script_segments": [
                {"voiceover": "intro", "start_time": 0, "end_time": 4},
                {"voiceover": "body", "start_time": 4, "end_time": 10},
            ],
        })
        assert [item["duration_seconds"] for item in result.data] == [4.0, 6.0]

    @pytest.mark.asyncio
    async def test_prompt_includes_camera_and_lighting_spec(self, skill):
        result = await skill.execute({
            "script_segments": [{"voiceover": "test", "start_time": 0, "end_time": 3}],
        })
        prompt = result.data[0]["segment_prompt"]
        assert "Lighting:" in prompt
        assert "Camera:" in prompt


class TestSeedancePromptSegmentClassification:
    """Shot type classification."""

    @pytest.fixture
    def skill(self):
        return SeedancePromptSkill()

    def test_hook_segment_maps_to_close_up(self, skill):
        assert _shot_type_from_segment("hook", "", index=0, total=3) == "close-up"

    def test_first_segment_fallback_maps_to_close_up(self, skill):
        assert _shot_type_from_segment("", "This is great", index=0, total=3) == "close-up"

    def test_last_segment_cta(self, skill):
        assert _shot_type_from_segment("cta", "", index=2, total=3) == "static beauty shot"

    def test_comparison_segment(self, skill):
        assert _shot_type_from_segment("comparison", "", index=1, total=3) == "split-screen"

    def test_demo_step_segment(self, skill):
        assert _shot_type_from_segment("demo", "", index=1, total=3) == "over-shoulder"


class TestSeedancePromptValidation:
    """Parameter validation."""

    @pytest.fixture
    def skill(self):
        return SeedancePromptSkill()

    def test_validate_missing_segments(self, skill):
        errors = skill.validate_params({})
        assert len(errors) > 0

    def test_validate_empty_segments(self, skill):
        errors = skill.validate_params({"script_segments": []})
        assert len(errors) > 0

    def test_validate_valid(self, skill):
        errors = skill.validate_params({"script_segments": [{"voiceover": "test"}]})
        assert len(errors) == 0

    def test_validate_output_missing_prompt(self, skill):
        errors = skill.validate_output({})
        assert len(errors) > 0

    def test_validate_output_valid(self, skill):
        errors = skill.validate_output([
            {"segment_prompt": "a prompt that is definitely longer than ten characters"}
        ])
        assert len(errors) == 0


# ==============================================================================
# ThumbnailPromptSkill Tests
# ==============================================================================


class TestThumbnailPromptSkillInit:
    """Skill initialization."""

    def test_skill_has_name(self):
        skill = ThumbnailPromptSkill()
        assert skill.name == "gpt-image-thumbnail-prompt"


class TestThumbnailPromptSkillExecution:
    """Thumbnail prompt generation."""

    @pytest.fixture
    def skill(self):
        return ThumbnailPromptSkill()

    @pytest.mark.asyncio
    async def test_execute_returns_4_variants(self, skill):
        """Should return exactly 4 thumbnail variants."""
        result = await skill.execute({
            "hook_text": "Never pump in the bathroom again",
            "product_name": "X1 Pump",
            "brand_color": "#69FF68",
            "price": 299.99,
            "platform": "tiktok",
        })
        assert result.success is True
        data = result.data
        assert len(data["variants"]) == 4

    @pytest.mark.asyncio
    async def test_variants_have_different_styles(self, skill):
        """Each variant should have a different style."""
        result = await skill.execute({
            "hook_text": "Game changer",
            "product_name": "Product",
            "price": 49.99,
        })
        styles = [v["style"] for v in result.data["variants"]]
        assert len(set(styles)) >= 3  # At least 3 unique styles

    @pytest.mark.asyncio
    async def test_variants_include_product_name(self, skill):
        """Prompts should include the product name."""
        result = await skill.execute({
            "hook_text": "Best ever",
            "product_name": "X1 Ultra",
        })
        for v in result.data["variants"]:
            assert "X1 Ultra" in v["prompt"]

    @pytest.mark.asyncio
    async def test_platform_size_mapping(self, skill):
        """Size should match platform."""
        result = await skill.execute({
            "hook_text": "Test",
            "product_name": "P",
            "platform": "shopify",
        })
        for v in result.data["variants"]:
            assert v["size"] == "1536x1024"

    @pytest.mark.asyncio
    async def test_tiktok_size(self, skill):
        result = await skill.execute({
            "hook_text": "TikTok test",
            "product_name": "P",
            "platform": "tiktok",
        })
        for v in result.data["variants"]:
            assert v["size"] == "1024x1792"


class TestThumbnailPromptValidation:
    """Validation logic."""

    @pytest.fixture
    def skill(self):
        return ThumbnailPromptSkill()

    def test_validate_missing_all(self, skill):
        errors = skill.validate_params({})
        assert len(errors) > 0

    def test_validate_only_hook(self, skill):
        errors = skill.validate_params({"hook_text": "hello"})
        assert len(errors) == 0

    def test_validate_only_product(self, skill):
        errors = skill.validate_params({"product_name": "X1"})
        assert len(errors) == 0


class TestThumbnailPromptFallback:
    """Fallback behavior."""

    @pytest.fixture
    def skill(self):
        return ThumbnailPromptSkill()

    def test_fallback_returns_variants(self, skill):
        result = skill.fallback({"hook_text": "Amazing", "product_name": "P"})
        assert result.success is True
        assert len(result.data["variants"]) >= 2

    def test_fallback_includes_product(self, skill):
        result = skill.fallback({"hook_text": "Amazing", "product_name": "X1 Pump"})
        for v in result.data["variants"]:
            assert "X1 Pump" in v["prompt"] or "X1 Pump" in result.data["product_name"]
