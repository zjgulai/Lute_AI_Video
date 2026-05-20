"""Pydantic models for all pipeline data structures.

Every node's input/output is validated against these schemas.
This guarantees data integrity across the 12-node pipeline.

Re-exports from domain-specific submodules for backward compatibility.
"""

from __future__ import annotations

# Analytics
from src.models.analytics import (
    AnalyticsReport,
    VideoMetrics,
)

# Audit
from src.models.audit import (
    AuditCriterion,
    AuditReport,
)

# Compliance
from src.models.compliance import (
    ComplianceFlag,
    ComplianceReport,
)

# Distribution
from src.models.distribution import (
    DistributionPlan,
    PlatformPost,
)

# Enums
from src.models.enums import (
    ApprovalStatus,
    AuditCheckpoint,
    AuditCriterionStatus,
    ComplianceStatus,
    ContentScenario,
    ErrorCode,
    Language,
    Platform,
    Severity,
    VideoType,
)

# Error
from src.models.error import (
    PipelineError,
)

# Media (editing, audio, caption, thumbnail)
from src.models.media import (
    AudioPlan,
    AudioSegment,
    CaptionEntry,
    CaptionPlan,
    EditComposition,
    EditTimelineEvent,
    ThumbnailSet,
    ThumbnailVariant,
)

# Pipeline
from src.models.pipeline import (
    Brief,
    Script,
    ScriptSegment,
    WeeklyCalendar,
)

# Review
from src.models.review import (
    HumanReview,
)

# Storyboard & Assets
from src.models.storyboard import (
    AssetCandidate,
    AssetPlan,
    Shot,
    ShotAssetPlan,
    Storyboard,
)

# Global constants (used across pipeline, API, and frontend)
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

__all__ = [
    # Enums
    "ApprovalStatus",
    "AuditCheckpoint",
    "AuditCriterionStatus",
    "ComplianceStatus",
    "ContentScenario",
    "ErrorCode",
    "Language",
    "Platform",
    "Severity",
    "VideoType",
    # Pipeline
    "Brief",
    "Script",
    "ScriptSegment",
    "WeeklyCalendar",
    # Storyboard
    "AssetCandidate",
    "AssetPlan",
    "Shot",
    "ShotAssetPlan",
    "Storyboard",
    # Media
    "AudioPlan",
    "AudioSegment",
    "CaptionEntry",
    "CaptionPlan",
    "EditComposition",
    "EditTimelineEvent",
    "ThumbnailSet",
    "ThumbnailVariant",
    # Distribution
    "DistributionPlan",
    "PlatformPost",
    # Analytics
    "AnalyticsReport",
    "VideoMetrics",
    # Audit
    "AuditCriterion",
    "AuditReport",
    # Compliance
    "ComplianceFlag",
    "ComplianceReport",
    # Error
    "PipelineError",
    # Review
    "HumanReview",
    # Constants
    "REVIEW_NODES",
    "PipelineErrors",
]
