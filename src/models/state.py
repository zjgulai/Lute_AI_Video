"""LangGraph state definition for the video creation pipeline.

The state is the single source of truth flowing through all 12 nodes.
Each node reads from and writes to specific state fields.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages

from src.models import (
    AnalyticsReport,
    AssetPlan,
    AudioPlan,
    AuditReport,
    CaptionPlan,
    ComplianceReport,
    DistributionPlan,
    EditComposition,
    HumanReview,
    Script,
    Storyboard,
    ThumbnailSet,
    WeeklyCalendar,
)

# Sprint 3 P3-5: current schema version. Increment when a state-shape change
# would break old consumers (field removed, type narrowed, semantics changed).
# Adding new optional fields with total=False does NOT require a bump.
# Persisted states missing `schema_version` are treated as version 0.
STATE_SCHEMA_VERSION: int = 1


class VideoPipelineState(TypedDict, total=False):
    """Master state flowing through the 12-node video creation pipeline.

    Fields are TypedDict with total=False so nodes can add fields incrementally.

    Schema versioning (Sprint 3 P3-5):
        ``schema_version`` is a monotonically-increasing integer. Bump it
        whenever the state shape changes in a way that would break old
        consumers (removing a field, narrowing a type, renaming a key).
        Adding new optional fields does NOT require a bump. See
        ``STATE_SCHEMA_VERSION`` constant below — that's the runtime value
        set by StepRunner.init_state. PipelineStateManager.load logs a
        warning when a persisted state's version differs from current.
    """

    # ── Schema versioning ──
    schema_version: int  # Sprint 3 P3-5; missing → treated as 0

    # ── Input Configuration ──
    product_catalog: dict[str, Any]  # Product info, USPs, specs
    brand_guidelines: dict[str, Any]  # Brand tone, colors, fonts, compliance rules
    target_platforms: list[str]  # e.g. ["tiktok", "facebook"]
    target_languages: list[str]  # e.g. ["en"]
    content_calendar_week: str  # ISO week string "2026-W17"
    mock_quality: str  # Quality level for mock data ("perfect"|"medium"|"poor")
    content_scenario: str  # ContentScenario enum value — drives prompt/audit selection
    live_shoot_brief: dict[str, Any]  # Live-shoot scenario: uploaded footage metadata + user narration intent

    # ── Pipeline Data (populated node by node) ──
    weekly_calendar: WeeklyCalendar  # Node 1 output
    scripts: list[Script]  # Node 2 output (one per platform)
    compliance_reports: list[ComplianceReport]  # Node 3 output
    storyboards: list[Storyboard]  # Node 4 output
    asset_plans: list[AssetPlan]  # Node 5 output
    generated_assets: list[dict[str, Any]]  # Node 6 output
    edit_compositions: list[EditComposition]  # Node 7 output
    audio_plans: list[AudioPlan]  # Node 8 output
    caption_plans: list[CaptionPlan]  # Node 9 output
    thumbnail_sets: list[ThumbnailSet]  # Node 10 output
    distribution_plans: list[DistributionPlan]  # Node 11 output
    analytics_reports: list[AnalyticsReport]  # Node 12 output

    # ── Human Review ──
    human_reviews: dict[str, HumanReview]  # Keyed by node name
    current_review_node: str  # Which review node is currently waiting

    # ── Self-Audit Reports ──
    audit_reports: dict[str, AuditReport]  # Keyed by checkpoint (strategy/script/edit/thumbnail)

    # ── Control Flow ──
    current_step: str  # Which pipeline step we're at
    errors: list[str]  # Accumulated errors (legacy string format)
    structured_errors: list[dict[str, Any]]  # Structured PipelineError dicts (GAP-20)
    messages: Annotated[list[Any], add_messages]  # Human-in-the-loop communication
    pipeline_complete: bool

    # ── Resilience ──
    retry_counts: dict[str, int]  # Node-level retry counters (strategy/script/edit/thumbnail)

    # ── Human Rejection Feedback (L4.4) ──
    rejection_feedback: dict[str, str]  # Keyed by node_key, value = reviewer_notes

    # ── Self-Verification (L5.x) ──
    self_verifications: dict[str, dict[str, Any]]  # Keyed by node_name

    # ── Resilience ──
    pipeline_degraded: bool  # P0-2: Any node failure sets this; routing functions check it and terminate pipeline

    # ── Telemetry ──
    trace_id: str  # Request/run trace id shared by node timing and error collection
    pipeline_metrics: dict[str, Any]  # PipelineMetrics serialized as dict
