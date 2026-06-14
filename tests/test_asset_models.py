"""Tests for asset system models and API.

Verifies:
1. BrandAssetPackage: creation, serialization
2. InfluencerProfile: creation, product links, style profile
3. API endpoints: upload, brand packages, influencers

All tests use in-memory/mock storage — no real filesystem or API calls.
"""

from __future__ import annotations

from src.models.brand import BrandAssetPackage, BrandCampaignBrief, BrandColor, BrandFont
from src.models.influencer import (
    InfluencerProductLink,
    InfluencerProfile,
    InfluencerRemixBrief,
    InfluencerStyleProfile,
)

# ==============================================================================
# BrandAssetPackage Tests
# ==============================================================================


class TestBrandAssetPackage:
    """Brand asset package model."""

    def test_create_minimal(self):
        """Should create with minimal fields."""
        pkg = BrandAssetPackage(brand_name="TestBrand")
        assert pkg.brand_name == "TestBrand"
        assert pkg.colors == []
        assert pkg.fonts == []

    def test_create_full(self):
        """Should create with all fields."""
        pkg = BrandAssetPackage(
            package_id="BPKG-001",
            brand_name="LactFit",
            description="LactFit brand package",
            logo_url="https://cdn.lactfit.com/logo.png",
            colors=[
                BrandColor(name="primary", hex="#6B8E8E"),
                BrandColor(name="secondary", hex="#F5E6D3"),
            ],
            fonts=[
                BrandFont(name="heading", family="Inter", weights=["regular", "bold"]),
            ],
            intro_video_id="ASSET-INTRO-001",
            outro_video_id="ASSET-OUTRO-001",
            tone_of_voice="warm, empowering, real",
            forbidden_content=["medical claims", "competitor bashing"],
            target_audience="Working mothers 25-40",
            selected_asset_ids=["ASSET-001", "ASSET-002"],
        )
        assert len(pkg.colors) == 2
        assert pkg.colors[0].hex == "#6B8E8E"
        assert len(pkg.selected_asset_ids) == 2

    def test_to_dict(self):
        """Should serialize to dict."""
        pkg = BrandAssetPackage(brand_name="Test")
        d = pkg.to_dict()
        assert d["brand_name"] == "Test"
        assert "colors" in d

    def test_from_dict(self):
        """Should deserialize from dict."""
        data = {
            "brand_name": "LactFit",
            "colors": [{"name": "primary", "hex": "#6B8E8E"}],
        }
        pkg = BrandAssetPackage.from_dict(data)
        assert pkg.brand_name == "LactFit"
        assert len(pkg.colors) == 1

    def test_colors_default_factory(self):
        """Colors should default to empty list."""
        pkg = BrandAssetPackage(brand_name="Test")
        assert pkg.colors == []
        pkg.colors.append(BrandColor(name="accent", hex="#FF0000"))
        assert len(pkg.colors) == 1

    def test_forbidden_content(self):
        """Forbidden content should be stored."""
        pkg = BrandAssetPackage(
            brand_name="Safe",
            forbidden_content=["medical", "fear"],
        )
        assert len(pkg.forbidden_content) == 2


class TestBrandColor:
    """Brand color model."""

    def test_defaults(self):
        color = BrandColor()
        assert color.name == ""
        assert color.hex == "#000000"
        assert color.usage == "primary"


class TestBrandFont:
    """Brand font model."""

    def test_defaults(self):
        font = BrandFont()
        assert font.family == ""
        assert font.weights == ["regular", "bold"]


class TestBrandCampaignBrief:
    """Brand campaign brief model."""

    def test_create(self):
        brief = BrandCampaignBrief(
            brief_id="BC-001",
            package_id="BPKG-001",
            topic="Summer collection launch",
            target_duration_seconds=30,
            mood="warm",
        )
        assert brief.brief_id == "BC-001"
        assert brief.mood == "warm"

    def test_defaults(self):
        brief = BrandCampaignBrief()
        assert brief.mood == "professional"
        assert brief.target_platforms == ["tiktok"]


# ==============================================================================
# Influencer Model Tests
# ==============================================================================


class TestInfluencerStyleProfile:
    """Influencer style profile."""

    def test_create(self):
        profile = InfluencerStyleProfile(
            hook_type="question",
            avg_speech_speed=3.5,
            speech_style="casual",
            catchphrases=["oh my god", "you guys"],
            common_hooks=["have you ever wondered"],
        )
        assert profile.hook_type == "question"
        assert len(profile.catchphrases) == 2
        assert profile.avg_speech_speed == 3.5

    def test_defaults(self):
        profile = InfluencerStyleProfile()
        assert profile.catchphrases == []


class TestInfluencerProductLink:
    """Influencer product link."""

    def test_create(self):
        link = InfluencerProductLink(
            product_id="PROD-001",
            product_name="X1 Pump",
            platform_specific_urls={
                "tiktok": "https://tiktok.com/@shop/123",
                "shopify": "https://shopify.com/products/x1",
            },
            commission_rate=0.15,
        )
        assert link.product_name == "X1 Pump"
        assert link.commission_rate == 0.15
        assert link.is_active is True

    def test_multi_platform_links(self):
        """Should support multiple platform URLs."""
        link = InfluencerProductLink(
            product_id="P1",
            product_name="Product",
            platform_specific_urls={
                "shopify": "https://shop.example.com/p1",
                "amazon": "https://amazon.com/dp/B001",
                "tiktok": "https://tiktok.com/shop/123",
            },
        )
        assert len(link.platform_specific_urls) == 3


class TestInfluencerProfile:
    """Influencer profile model."""

    def test_create_minimal(self):
        profile = InfluencerProfile(
            influencer_id="INFL-001",
            name="Jessica MomLife",
            handle="@jessica_momlife",
        )
        assert profile.name == "Jessica MomLife"
        assert profile.style_tags == []

    def test_create_with_style(self):
        profile = InfluencerProfile(
            influencer_id="INFL-002",
            name="Test Influencer",
            platforms=["tiktok", "instagram"],
            style_tags=["unboxing", "review", "tutorial"],
            style_profile=InfluencerStyleProfile(
                hook_type="pain_point",
                speech_style="energetic",
            ),
            product_links=[
                InfluencerProductLink(
                    product_id="PROD-001",
                    product_name="X1 Pump",
                    commission_rate=0.15,
                ),
            ],
            recent_video_urls=[
                "https://tiktok.com/@test/video/1",
                "https://tiktok.com/@test/video/2",
            ],
        )
        assert len(profile.style_tags) == 3
        assert profile.style_profile.speech_style == "energetic"
        assert len(profile.product_links) == 1

    def test_to_dict_roundtrip(self):
        """Should serialize and deserialize."""
        original = InfluencerProfile(
            influencer_id="INFL-003",
            name="Test",
            style_tags=["review"],
        )
        data = original.to_dict()
        restored = InfluencerProfile.from_dict(data)
        assert restored.influencer_id == "INFL-003"
        assert restored.style_tags == ["review"]

    def test_inactive_profile(self):
        profile = InfluencerProfile(
            influencer_id="INFL-004",
            name="Inactive",
            is_active=False,
        )
        assert profile.is_active is False


class TestInfluencerRemixBrief:
    """Influencer remix brief."""

    def test_create(self):
        brief = InfluencerRemixBrief(
            brief_id="RMX-001",
            influencer_id="INFL-001",
            original_video_url="https://tiktok.com/@user/video/123",
            product_id="PROD-001",
            product_name="X1 Pump",
            commission_rate=0.15,
        )
        assert brief.product_name == "X1 Pump"
        assert brief.commission_rate == 0.15

    def test_defaults(self):
        brief = InfluencerRemixBrief()
        assert brief.target_platforms == ["tiktok"]
