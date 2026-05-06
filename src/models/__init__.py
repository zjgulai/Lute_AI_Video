"""Pydantic models for all pipeline data structures.

Every node's input/output is validated against these schemas.
This guarantees data integrity across the 12-node pipeline.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class VideoType(StrEnum):
    PRODUCT_USAGE = "product_usage"
    BRAND_PROMOTION = "brand_promotion"
    SHORT_VIDEO_SALES = "short_video_sales"
    PRODUCT_REVIEW = "product_review"
    TUTORIAL = "tutorial"
    UNBOXING = "unboxing"
    CUSTOMER_TESTIMONIAL = "customer_testimonial"
    INDUSTRY_INSIGHT = "industry_insight"
    TREND_JACKING = "trend_jacking"
    COMPARISON = "comparison"


class ContentScenario(StrEnum):
    """Video content creation scenario — determines prompt templates and audit weights.

    - general: default, no special handling
    - influencer_remix: employee IP / KOL content with product links
    - brand_campaign: brand-controlled, formal, multi-layer review
    - live_shoot_to_video: existing footage re-edited with AI narration
    """
    GENERAL = "general"
    PRODUCT_DIRECT = "product_direct"
    INFLUENCER_REMIX = "influencer_remix"
    BRAND_CAMPAIGN = "brand_campaign"
    LIVE_SHOOT_TO_VIDEO = "live_shoot_to_video"


class Platform(StrEnum):
    TIKTOK = "tiktok"
    YOUTUBE_SHORTS = "youtube_shorts"
    FACEBOOK = "facebook"
    SHOPIFY = "shopify"
    AMAZON = "amazon"            # Amazon A+ / EBC content
    REDDIT = "reddit"           # Community posts with embedded video


class Language(StrEnum):
    EN = "en"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class ComplianceStatus(StrEnum):
    PASS = "PASS"
    FLAGGED = "FLAGGED"
    BLOCKED = "BLOCKED"


class Severity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ──────────────────────────────────────────────
# Node 1: Strategy Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 2: Script Writer Agent
# ──────────────────────────────────────────────


class ScriptSegment(BaseModel):
    """A single segment of the video script."""

    segment_type: Literal["hook", "pain_point", "solution", "trust_building", "cta"]
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


# ──────────────────────────────────────────────
# Node 3: Compliance Agent
# ──────────────────────────────────────────────


class ComplianceFlag(BaseModel):
    severity: Severity
    line_index: int
    text: str
    issue: str
    suggestion: str


class ComplianceReport(BaseModel):
    script_id: str
    status: ComplianceStatus
    flags: list[ComplianceFlag] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=datetime.now)


# ──────────────────────────────────────────────
# Node 4: Storyboard Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 5–6: Asset Sourcing & Generation
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 7: Editing Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 8: Audio Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 9: Caption Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 10: Thumbnail Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 11: Distribution Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Node 12: Analytics Agent
# ──────────────────────────────────────────────


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


# ──────────────────────────────────────────────
# Self-Audit (runs before human review at each checkpoint)
# ──────────────────────────────────────────────


class AuditCriterionStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class AuditCriterion(BaseModel):
    """A single scored criterion within an audit report."""

    name: str  # e.g. "Platform Coverage", "Hook Strength"
    status: AuditCriterionStatus
    score: float = Field(ge=0.0, le=1.0, description="0-1 score for this criterion")
    observation: str  # What the auditor observed
    recommendation: str = ""  # How to improve if not PASS


class AuditCheckpoint(StrEnum):
    STRATEGY = "strategy"
    SCRIPT = "script"
    EDIT = "edit"
    THUMBNAIL = "thumbnail"


class AuditReport(BaseModel):
    """Self-audit report generated at a checkpoint before human review."""

    audit_id: str  # e.g. "AUDIT-STRATEGY-001"
    checkpoint: AuditCheckpoint
    target_artifact_id: str  # The artifact being audited (brief/script/composition)
    overall_score: float = Field(ge=0.0, le=1.0)
    overall_status: AuditCriterionStatus
    criteria: list[AuditCriterion]
    summary: str  # Human-readable summary of findings
    generated_at: datetime = Field(default_factory=datetime.now)


# ──────────────────────────────────────────────
# Human Review
# ──────────────────────────────────────────────


class HumanReview(BaseModel):
    node: str  # strategy_review, script_review, edit_review, thumbnail_review
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_notes: str = ""
    content_snapshot: dict[str, Any] = Field(default_factory=dict)
    reviewed_at: datetime | None = None


# ──────────────────────────────────────────────
# Error Taxonomy (GAP-20)
# ──────────────────────────────────────────────


class ErrorCode(StrEnum):
    """Standardized error codes for pipeline error classification.

    Convention:
        INPUT_*     — Timeout / connectivity issues
        LLM_*       — AI provider errors
        AUDIT_*     — Pipeline audit / compliance blocks
        ASSET_*     — Asset sourcing / library errors
        CONFIG_*    — Missing config / API keys
        INTERNAL_*  — LangGraph / framework errors
    """
    # Timeouts & Connectivity
    INPUT_TIMEOUT = "INPUT_TIMEOUT"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    DALLE_TIMEOUT = "DALLE_TIMEOUT"
    ELEVENLABS_TIMEOUT = "ELEVENLABS_TIMEOUT"

    # AI Provider Errors
    LLM_API_ERROR = "LLM_API_ERROR"
    DALLE_API_ERROR = "DALLE_API_ERROR"
    ELEVENLABS_API_ERROR = "ELEVENLABS_API_ERROR"

    # Pipeline Blocks
    AUDIT_BLOCKED = "AUDIT_BLOCKED"
    COMPLIANCE_BLOCKED = "COMPLIANCE_BLOCKED"
    AUDIT_REJECTED = "AUDIT_REJECTED"

    # Asset Sourcing
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"
    ASSET_LIBRARY_UNAVAILABLE = "ASSET_LIBRARY_UNAVAILABLE"

    # Configuration
    API_KEY_MISSING = "API_KEY_MISSING"
    CONFIG_ERROR = "CONFIG_ERROR"

    # Framework / Infrastructure
    MSGPACK_SERIALIZE = "MSGPACK_SERIALIZE"
    WEBHOOK_FAILED = "WEBHOOK_FAILED"
    POSTGRES_UNAVAILABLE = "POSTGRES_UNAVAILABLE"

    # Fallback
    UNKNOWN_NODE_ERROR = "UNKNOWN_NODE_ERROR"


class PipelineError(BaseModel):
    """Structured error with classification, context, and recoverability hint."""

    code: ErrorCode
    message: str
    node: str | None = None
    recoverable: bool = True
    detail: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_legacy(self) -> str:
        """Return backward-compatible string format for the errors list."""
        node_prefix = f"[{self.node}] " if self.node else ""
        return f"{node_prefix}{self.code.value}: {self.message}"


# ──────────────────────────────────────────────
# Global Constants (used across pipeline, API, and frontend)
# ──────────────────────────────────────────────


REVIEW_NODES: list[str] = [
    "strategy_review",
    "script_review",
    "edit_review",
    "thumbnail_review",
]
"""Ordered list of human review node keys.

Used by: routing.py (review key lookup), api.py (state inspection),
frontend page.tsx (review panel rendering).

WARNING: These keys are coupled to graph node names in pipeline.py.
If changed, update routing.py review key lookups AND pipeline.py
interrupt_after list AND add_conditional_edges path_map AND
frontend REVIEW_NODES / REVIEW_NODE_ORDER constants in tandem.
"""


# Re-export types for convenient access
PipelineErrors = list[PipelineError]
