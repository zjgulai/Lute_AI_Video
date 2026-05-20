"""Models for editing, audio, caption, and thumbnail stages."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models.enums import Language


class EditTimelineEvent(BaseModel):
    shot_id: int
    asset_id: str
    start_time: float
    end_time: float
    transition: str = "cut"  # cut, dissolve, slide, zoom
    effects: list[str] = Field(default_factory=list)


class EditComposition(BaseModel):
    script_id: str
    total_duration: float
    aspect_ratio: str = "9:16"
    timeline: list[EditTimelineEvent]
    lut_preset: str = "brand_default"
    generated_at: datetime = Field(default_factory=datetime.now)


class AudioSegment(BaseModel):
    start_time: float
    end_time: float
    type: Literal["voiceover", "bgm", "sfx"]
    source: str  # TTS voice ID or BGM track ID
    text: str = ""  # For voiceover segments
    volume: float = 1.0


class AudioPlan(BaseModel):
    script_id: str
    voice_id: str
    bgm_track: str
    segments: list[AudioSegment]
    generated_at: datetime = Field(default_factory=datetime.now)


class CaptionEntry(BaseModel):
    index: int
    start_time: float
    end_time: float
    text: str
    style: str = "default"  # default, highlight, cta
    position: str = "bottom"  # bottom, center_top, custom


class CaptionPlan(BaseModel):
    script_id: str
    language: Language
    entries: list[CaptionEntry]
    font_family: str = "Inter"
    generated_at: datetime = Field(default_factory=datetime.now)


class ThumbnailVariant(BaseModel):
    variant_id: str  # A, B, C, D
    concept: str  # Description of the thumbnail concept
    prompt: str  # DALL-E / Flux generation prompt
    image_url: str = ""  # Populated after generation


class ThumbnailSet(BaseModel):
    script_id: str
    variants: list[ThumbnailVariant]
    selected_variant_id: str | None = None
    generated_at: datetime = Field(default_factory=datetime.now)
