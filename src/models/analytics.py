"""Models for analytics and metrics reporting."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import Platform, VideoType


class VideoMetrics(BaseModel):
    script_id: str
    platform: Platform
    views: int = 0
    completion_rate: float = 0.0
    engagement_rate: float = 0.0
    conversion_rate: float = 0.0
    shares: int = 0
    comments: int = 0
    collected_at: datetime = Field(default_factory=datetime.now)


class AnalyticsReport(BaseModel):
    week: str
    metrics: list[VideoMetrics]
    top_performing_type: VideoType | None = None
    recommendations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
