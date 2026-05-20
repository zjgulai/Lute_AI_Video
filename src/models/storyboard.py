"""Models for storyboard and asset planning stages."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Shot(BaseModel):
    id: int
    start_time: float
    end_time: float
    shot_type: str  # e.g. "hook", "product_demo", "lifestyle"
    visual: str  # Natural language description
    text_overlay: str = ""
    camera: str = "Static"  # e.g. Static, Slow zoom, Pan
    asset_needed: str = ""  # Key for asset matching


class Storyboard(BaseModel):
    script_id: str
    total_duration: float
    aspect_ratio: str = "9:16"
    shots: list[Shot]
    generated_at: datetime = Field(default_factory=datetime.now)


class AssetCandidate(BaseModel):
    asset_id: str
    file_path: str
    description: str
    match_score: float  # 0–1
    source: Literal["library", "ugc", "ai_generated"]


class ShotAssetPlan(BaseModel):
    shot_id: int
    asset_needed: str
    candidates: list[AssetCandidate]
    selected_asset_id: str | None = None
    gap: bool = False  # True if no suitable asset found


class AssetPlan(BaseModel):
    storyboard_id: str
    shot_plans: list[ShotAssetPlan]
    gaps: list[str] = Field(default_factory=list)  # Descriptions of missing assets
