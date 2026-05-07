"""Brand asset package model and management.

A BrandAssetPackage contains all assets needed for a brand campaign:
logo, colors, fonts, intro/outro videos, tone-of-voice, and selected footage.

This is the input model for the S2 (Brand Campaign) scenario.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class BrandColor(BaseModel):
    """A brand color definition."""
    name: str = ""
    hex: str = "#000000"
    usage: str = "primary"  # primary, secondary, accent, background


class BrandFont(BaseModel):
    """A brand font definition."""
    name: str = ""
    family: str = ""
    weights: list[str] = ["regular", "bold"]


class BrandAssetPackage(BaseModel):
    """Complete brand asset package for a campaign.

    This is passed as input to the brand_campaign scenario pipeline.
    """
    package_id: str = ""
    brand_name: str = ""
    description: str = ""

    # Visual identity
    logo_url: str = ""
    logo_alt_text: str = ""
    colors: list[BrandColor] = []
    fonts: list[BrandFont] = []

    # Video templates
    intro_video_id: str = ""  # AssetStorage asset_id for intro template
    outro_video_id: str = ""  # AssetStorage asset_id for outro template
    intro_duration_seconds: float = 3.0
    outro_duration_seconds: float = 3.0

    # Brand guidelines
    tone_of_voice: str = ""  # Free-text description of brand voice
    forbidden_content: list[str] = Field(
        default_factory=list,
        description="Content that must be avoided (competitors, claims, etc.)",
    )
    target_audience: str = ""

    # Selected footage for this campaign
    selected_asset_ids: list[str] = Field(
        default_factory=list,
        description="AssetStorage IDs of footage selected for this campaign",
    )

    # Metadata
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrandAssetPackage:
        return cls(**data)


class BrandCampaignBrief(BaseModel):
    """Brief for a specific brand campaign video.

    This is what the strategy_agent produces for brand_campaign scenario.
    """
    brief_id: str = ""
    package_id: str = ""
    topic: str = ""
    target_duration_seconds: int = 30
    target_platforms: list[str] = ["tiktok"]
    key_message: str = ""
    call_to_action: str = ""
    mood: str = "professional"  # professional, warm, inspirational, educational

    # Which assets from the package to feature
    feature_asset_ids: list[str] = Field(default_factory=list)
