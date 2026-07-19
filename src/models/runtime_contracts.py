"""Typed runtime contracts for cross-module pipeline outputs.

These are intentionally lightweight ``TypedDict`` definitions, not runtime
validators. They document shapes that are passed across services, routers, and
frontend-facing APIs where plain ``dict[str, Any]`` has caused drift.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired

from typing_extensions import TypedDict  # noqa: UP035 - FastAPI/Pydantic needs this on Python 3.11.


class SeedanceVideoResult(TypedDict, total=False):
    video_url: str
    local_path: str
    prompt_used: str
    duration: int
    _stub_mode: str
    _poyo_state: Literal["submitted", "settled", "released"]
    task_id: str


class FastModeTiming(TypedDict):
    llm_ms: int
    video_ms: int
    tts_ms: int


class FastModeModelInfo(TypedDict):
    llm: str
    llm_model: str
    video: str
    tts: str | None


class FastModeResult(TypedDict):
    status: Literal["completed_bounded", "completed_full", "error"]
    lifecycle_status: Literal["completed_bounded", "completed_full", "error"]
    completion_kind: Literal[
        "no_media", "bounded_media", "full_media", "execution_failed"
    ]
    request_succeeded: bool
    success: bool
    full_media_success: bool
    pipeline_complete: bool
    publish_allowed: bool
    delivery_accepted: bool
    video_path: str
    video_url: str
    filename: str
    llm_prompt: str
    scene_description: str
    user_prompt: str
    duration_seconds: int
    file_size_bytes: int
    generation_time_ms: int
    timing: FastModeTiming
    model_info: FastModeModelInfo
    is_stub: bool
    tts_path: str | None
    tts_is_fallback: bool
    tts_fallback_reason: str | None
    error: NotRequired[str]
    artifact_disposition: NotRequired[str]
    artifact_review_status: NotRequired[str | None]
    artifact_storage_scope: NotRequired[str]
    artifact_run_id: NotRequired[str | None]
    effective_policy_version: NotRequired[str]


class ClipDetail(TypedDict, total=False):
    clip_index: int
    clip_path: str
    duration: int | float
    is_stub: bool
    transition_to_next: str
    transition_type: str
    segment_type: str
    shot_type: str
    scene_beat: str
    beat_summary: str
    transition_intent: str
    continuity_frame: bool
    continuity_frame_used: str | None


class TransitionMetadata(TypedDict):
    from_clip: int
    to_clip: int
    type: str
    duration_frames: int
    description: str


class AssetReadyChecks(TypedDict):
    non_stub_clips: bool
    transition_metadata: bool
    micro_shot_continuity: bool
    director_intent_metadata: bool
    final_video_present: bool


class AssetReadyAudit(TypedDict):
    status: str
    checks: AssetReadyChecks


class PublishReadyAudit(TypedDict):
    status: str
    overall_status: str
    overall_score: Any
    base_score: Any
    criteria: list[Any]


class ContinuityDirection(TypedDict):
    scene_beat: str
    beat_summary: str
    transition_intent: str


class ContinuityDirectionSummary(TypedDict):
    clip_directions: list[ContinuityDirection]
    scene_beats: list[str]
    transition_intents: list[str]


class ContinuityAuditSummary(TypedDict, total=False):
    asset_ready_audit: AssetReadyAudit
    publish_ready_audit: PublishReadyAudit
    continuity_direction_summary: ContinuityDirectionSummary
    continuity_score: float


class TelemetryStepStats(TypedDict):
    total_executions: int
    success_count: int
    failure_count: int
    avg_duration_ms: float
    total_duration_ms: float


class TelemetrySummary(TypedDict):
    total_runs: int
    avg_duration_ms: float
    success_rate: float
    total_errors: int
    per_step_stats: dict[str, TelemetryStepStats]
    labels: list[str]


class TelemetryErrorEntry(TypedDict):
    label: str
    trace_id: str
    step: str
    error: str
    context: dict[str, Any]
    timestamp: str


class TelemetryErrorsResponse(TypedDict):
    errors: list[TelemetryErrorEntry]
    count: int
    label_filter: str | None
