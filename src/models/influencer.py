"""Influencer profile and product link management.

An InfluencerProfile stores:
- Personal style/tone data (used for remix style cloning)
- Product links for commission-based promotion

This is the input model for the S3 (Influencer Remix) scenario.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InfluencerProductLink(BaseModel):
    """A product link associated with an influencer for commission."""
    product_id: str = ""
    product_name: str = ""
    platform_specific_urls: dict[str, str] = Field(
        default_factory=dict,
        description="URLs per platform: {shopify: url, amazon: url, tiktok: url}",
    )
    commission_rate: float = 0.0  # e.g., 0.15 = 15%
    is_active: bool = True


class InfluencerStyleProfile(BaseModel):
    """Extracted style characteristics from an influencer's original video.

    Populated by the influencer-remix-analysis skill.
    """
    hook_type: str = ""  # pain_point, counter_narrative, data_drop, scene_drop, question
    avg_speech_speed: float = 0.0  # words per second
    speech_style: str = ""  # casual, energetic, professional, storytelling
    catchphrases: list[str] = Field(default_factory=list)
    common_hooks: list[str] = Field(default_factory=list)
    emotion_curve: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {time: float, emotion: str, intensity: float}",
    )
    structure_segments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of {type: str, start: float, end: float, description: str}",
    )
    notes: str = ""


class InfluencerProfile(BaseModel):
    """Profile for a signed influencer."""
    influencer_id: str = ""
    name: str = ""
    handle: str = ""  # Social media handle
    platforms: list[str] = Field(default_factory=list)

    # Style
    style_tags: list[str] = Field(
        default_factory=list,
        description="Tags: unboxing, review, tutorial, lifestyle, comedy",
    )
    style_profile: InfluencerStyleProfile = Field(default_factory=InfluencerStyleProfile)

    # Product links
    product_links: list[InfluencerProductLink] = Field(default_factory=list)

    # Recent original video URLs (for remix analysis)
    recent_video_urls: list[str] = Field(default_factory=list)

    # Metadata
    notes: str = ""
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InfluencerProfile:
        return cls(**data)


class InfluencerRemixBrief(BaseModel):
    """Brief for an influencer remix video.

    Combines the influencer's style + the product to promote.
    """
    brief_id: str = ""
    influencer_id: str = ""
    original_video_url: str = ""
    product_id: str = ""
    product_name: str = ""
    product_image_url: str = ""
    product_link: str = ""
    commission_rate: float = 0.0
    target_platforms: list[str] = Field(default_factory=lambda: ["tiktok"])
    notes: str = ""
