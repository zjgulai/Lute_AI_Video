"""Shared enums used across pipeline data models."""

from __future__ import annotations

from enum import StrEnum


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


class AuditCriterionStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class AuditCheckpoint(StrEnum):
    STRATEGY = "strategy"
    SCRIPT = "script"
    EDIT = "edit"
    THUMBNAIL = "thumbnail"


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
