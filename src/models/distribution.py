"""Models for distribution (platform posting) stage."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import Platform


class PlatformPost(BaseModel):
    """A single post to a single platform.

    Each post is platform-specific: different title format, description
    style, link placement, and call-to-action.
    """
    platform: Platform
    title: str
    description: str
    hashtags: list[str]
    scheduled_time: datetime | None = None
    video_format: str = "9:16"
    product_link_placeholder: str = "{{product_url}}"
    cta_type: str = ""  # "add_to_cart" | "bio_link" | "embedded_link" | "learn_more"
    post_body: str = ""  # Full post text (Reddit-style) — title+body for long-form
    link_text: str = ""  # Display text for the product link


class DistributionPlan(BaseModel):
    """Multi-platform distribution plan for one brief.

    Contains one PlatformPost per target platform.
    Also includes a master brief_id for cross-platform grouping.
    """
    brief_id: str
    script_id: str
    posts: list[PlatformPost]
    generated_at: datetime = Field(default_factory=datetime.now)
