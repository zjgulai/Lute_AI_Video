"""Models for strategy and script pipeline stages."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models.enums import Language, Platform, VideoType


class Brief(BaseModel):
    """A single content brief from the strategy agent."""

    id: str = Field(..., description="Unique brief ID, e.g. BRIEF-001")
    video_type: VideoType
    topic: str
    target_audience: str
    target_platforms: list[Platform]
    target_languages: list[Language]
    key_message: str
    usp_priority: list[str]
    competitor_reference: str | None = None
    seasonal_hook: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)


class WeeklyCalendar(BaseModel):
    """Weekly content calendar output from Strategy Agent."""

    week: str = Field(..., description="ISO week, e.g. 2026-W17")
    briefs: list[Brief]
    generated_at: datetime = Field(default_factory=datetime.now)


class ScriptSegment(BaseModel):
    """A single segment of the video script."""

    segment_type: Literal[
        "hook", "pain_point", "solution", "trust_building", "cta",
        "body", "pitch", "intro", "conclusion", "scene_drop",
        "comparison", "data_drop", "question", "story_hook",
        "counter_narrative", "reaction", "emotional", "testimonial", "tutorial",
    ]
    start_time: float  # seconds
    end_time: float
    voiceover: str
    visual_description: str
    text_overlay: str = ""


class Script(BaseModel):
    """Complete script for one video."""

    id: str = Field(..., description="SCRIPT-{brief_id}-{lang}")
    brief_id: str
    platform: Platform
    language: Language
    total_duration: float
    segments: list[ScriptSegment]
    hashtags: list[str] = Field(default_factory=list)
    cta_text: str = ""
    generated_at: datetime = Field(default_factory=datetime.now)
