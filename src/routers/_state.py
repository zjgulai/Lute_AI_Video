"""Global state and helpers shared across routers (P1-11).

Extracted from api.py so domain routers can import shared state
without circular dependencies.
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.config import DEFAULT_LANGUAGES, OUTPUT_DIR
from src.graph.pipeline import compile_pipeline
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.pipeline.step_utils import get_step_output_from_state

# ── Pipeline state ──
# P0-E: Pass DATABASE_URL so /pipeline/* uses PostgresSaver in production.
# 生产 LangGraph checkpoint 跨重启恢复依赖 PostgresSaver;无 DATABASE_URL 时
# compile_pipeline() 退回 MemorySaver(开发/测试模式)。
# fail-fast 行为由 src/graph/pipeline.py 内部处理:db_url 设置但连不上 → RuntimeError。
_DB_URL = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL") or None

# P2-5: Lazy-initialized pipeline factory — avoids building PostgresSaver connection
# at import time and makes the dependency explicit in router code.
_pipeline_instance = None


def get_pipeline():
    """Return the compiled LangGraph pipeline, initializing lazily on first call."""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = compile_pipeline(db_url=_DB_URL)
    return _pipeline_instance


_active_threads: dict[str, dict[str, Any]] = {}
_THREAD_INDEX_PATH = OUTPUT_DIR / ".thread_index.json"
_pipeline_semaphore = asyncio.Semaphore(10)  # P3-4: Max 10 concurrent pipelines

# Thread cache TTL
_THREAD_CACHE_TTL_SEC = 24 * 3600  # 24 hours
_thread_cache_meta: dict[str, float] = {}  # thread_id → last_accessed timestamp

# P4-4: Thread → StepRunner label mapping for LangGraph proxy layer
_thread_label_map: dict[str, str] = {}
_label_thread_map: dict[str, str] = {}


# ── Pydantic models ──
class PipelineStartRequest(BaseModel):
    product_catalog: dict[str, Any] = {}
    brand_guidelines: dict[str, Any] = {}
    target_platforms: list[str] = ["shopify", "amazon", "tiktok", "reddit"]
    target_languages: list[str] = DEFAULT_LANGUAGES
    content_calendar_week: str = "2026-W17"
    api_keys: dict[str, str] = {}
    content_scenario: str = "influencer_remix"


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "request_changes"
    reviewer_notes: str = ""


class FastModeRequest(BaseModel):
    user_prompt: str
    duration: int = 5
    enable_tts: bool = True
    artifact_disposition: Literal["default", "pending_review", "quarantine"] = "default"
    provider_max_retries: int | None = Field(default=None, ge=0, le=10)
    # P1-C: 用户填的多供应商 key 通过此字段下发,scenario.py 入口注入 contextvars
    api_keys: dict[str, str] = {}


class S1StartRequest(BaseModel):
    product_catalog: dict[str, Any]
    brand_guidelines: dict[str, Any] = {}
    target_platforms: list[str] = []
    target_languages: list[str] = DEFAULT_LANGUAGES
    week: str = ""
    video_duration: int = 30
    output_label: str | None = None
    mode: str = "auto"
    brand_mode: bool = False
    enable_media_synthesis: bool = True
    artifact_disposition: Literal["default", "pending_review", "quarantine"] = "default"
    provider_max_retries: int | None = Field(default=None, ge=0, le=10)
    continuity_mode: bool | str = True
    continuity_generation_mode: str = "standard"
    storyboard_grid: int = 12
    clip_group_size: int = 3
    transition_style: str = "match_cut"
    commercial_injection_plan: dict[str, Any] | None = None
    api_keys: dict[str, str] = {}


class S2BrandCampaignRequest(BaseModel):
    brand_package: dict[str, Any] = {}
    target_platforms: list[str] = ["tiktok", "shopify"]
    target_languages: list[str] = DEFAULT_LANGUAGES
    week: str = ""
    video_duration: int = 60
    output_label: str | None = None
    enable_media_synthesis: bool = True
    artifact_disposition: Literal["default", "pending_review", "quarantine"] = "default"
    provider_max_retries: int | None = Field(default=None, ge=0, le=10)
    commercial_injection_plan: dict[str, Any] | None = None
    api_keys: dict[str, str] = {}


class S3InfluencerRemixRequest(BaseModel):
    video_url: str = ""
    product: dict[str, Any] = {}
    influencer_name: str = "Influencer"
    brief_id: str = ""
    target_platforms: list[str] = ["tiktok"]
    target_languages: list[str] = DEFAULT_LANGUAGES
    video_duration: int = 30
    output_label: str | None = None
    enable_media_synthesis: bool = True
    artifact_disposition: Literal["default", "pending_review", "quarantine"] = "default"
    provider_max_retries: int | None = Field(default=None, ge=0, le=10)
    commercial_injection_plan: dict[str, Any] | None = None
    api_keys: dict[str, str] = {}


class S5BrandVlogRequest(BaseModel):
    brand_id: str = "momcozy"
    product_sku: dict[str, Any] = {}
    scene_id: str | None = None
    selected_models: list[dict[str, Any]] = []
    story_description: str = ""
    video_duration: int = 30
    commercial_injection_plan: dict[str, Any] | None = None
    api_keys: dict[str, str] = {}


# ── Thread cache helpers ──

def _save_thread_index():
    """Persist _active_threads keys to JSON for crash recovery."""
    try:
        from src.storage import HAS_STORAGE
    except ImportError:
        HAS_STORAGE = False

    if HAS_STORAGE:
        return
    try:
        _THREAD_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_THREAD_INDEX_PATH, "w") as f:
            json.dump(list(_active_threads.keys()), f)
    except Exception as exc:
        logging.getLogger("routers.state").warning(
            "thread index save failed: %s", exc
        )


def _restore_thread_index():
    """Restore thread IDs from disk on startup."""
    try:
        from src.storage import HAS_STORAGE
    except ImportError:
        HAS_STORAGE = False

    if HAS_STORAGE:
        return
    try:
        if _THREAD_INDEX_PATH.exists():
            with open(_THREAD_INDEX_PATH) as f:
                ids = json.load(f)
            for tid in ids:
                if isinstance(tid, str):
                    _active_threads[tid] = {"configurable": {"thread_id": tid}}
    except Exception as exc:
        logging.getLogger("routers.state").warning(
            "thread index restore failed: %s", exc
        )


def _touch_thread_cache(thread_id: str) -> None:
    _thread_cache_meta[thread_id] = time.time()


def _evict_stale_threads() -> None:
    now = time.time()
    stale = [
        tid for tid, last_access in _thread_cache_meta.items()
        if now - last_access > _THREAD_CACHE_TTL_SEC
    ]
    for tid in stale:
        _active_threads.pop(tid, None)
        _thread_cache_meta.pop(tid, None)


def _cleanup_thread_cache(thread_id: str) -> None:
    _active_threads.pop(thread_id, None)
    _thread_cache_meta.pop(thread_id, None)


async def _periodic_cache_eviction() -> None:
    while True:
        await asyncio.sleep(3600)
        _evict_stale_threads()


async def _get_config_for_thread(thread_id: str) -> dict[str, Any]:
    """Get config for thread from memory cache or DB."""
    try:
        from src.storage import HAS_STORAGE
    except ImportError:
        HAS_STORAGE = False

    config = _active_threads.get(thread_id)
    if config:
        _touch_thread_cache(thread_id)
        return config

    if HAS_STORAGE:
        from src.storage.repository import ThreadRepository
        repo = ThreadRepository()
        thread = await repo.get_by_field("thread_id", thread_id)
        if thread:
            config = {"configurable": {"thread_id": thread_id}}
            _active_threads[thread_id] = config
            _touch_thread_cache(thread_id)
            return config

    return {"configurable": {"thread_id": thread_id}}


# Background task registry moved to src.tasks.bg_registry to break circular import.
# Re-export for backward compatibility (used by src.routers.scenario).
from src.tasks.bg_registry import register_background_task as _register_background_task  # noqa: E402,F401,I001


# ── Scenario helpers ──

_SCENARIO_STEP_ORDER: dict[str, list[str]] = {
    scenario: list(order) for scenario, order in SCENARIO_STEP_ORDERS.items()
}

_STEP_DURATIONS: dict[str, str] = {
    "strategy": "~5s",
    "scripts": "~5s",
    "compliance": "~2s",
    "storyboards": "~4s",
    "continuity_storyboard_grid": "~1s",
    "keyframe_images": "~5-60s",
    "video_prompts": "~3s",
    "thumbnail_prompts": "~3s",
    "seedance_clips": "~6min",
    "tts_audio": "~3min",
    "thumbnail_images": "~2min",
    "assemble_final": "~15s",
    "audit": "~5s",
}


def _validate_scenario(scenario: str) -> None:
    from fastapi import HTTPException
    if scenario not in _SCENARIO_STEP_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scenario: {scenario}. Valid: {list(_SCENARIO_STEP_ORDER.keys())}",
        )


def _get_step_deps(scenario: str, step_name: str) -> list[str]:
    """Return steps that must be completed before step_name."""
    from fastapi import HTTPException
    order = _SCENARIO_STEP_ORDER[scenario]
    try:
        idx = order.index(step_name)
        return order[:idx]
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unknown step: {step_name}")


def _get_step_output(state: dict[str, Any], step_name: str) -> Any:
    """Extract step output from pipeline state (prefers edited over original).

    Delegates to the canonical shared implementation in step_utils.py.
    """
    return get_step_output_from_state(state, step_name)


VALID_VIDEO_DURATIONS = (15, 30, 45, 60, 90)
DEFAULT_VIDEO_DURATION = 30


def coerce_video_duration(body: dict[str, Any], default: int = DEFAULT_VIDEO_DURATION) -> int:
    """Coerce body['video_duration'] to a valid int from the 5-tier set.

    Defends the dict-typed submit endpoints (/scenario/s1, /s2, /s3, /s4, /s5,
    /scenario/{s}/submit) against non-numeric input that historically reached
    seedance and crashed with TypeError: '<' not supported between str and int
    (V-2 QA, 2026-05-11).

    Behavior:
      - Missing / None  -> default (30)
      - Numeric string  -> int(...) then clamped to nearest valid tier
      - int / float     -> clamped to nearest valid tier
      - Garbage string  -> raises HTTPException(422) with field-level detail
                            so the frontend's inline-form-error path renders.
    """
    from fastapi import HTTPException

    raw = body.get("video_duration")
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "video_duration"],
                "msg": "video_duration must be an integer in {15,30,45,60,90}",
                "type": "value_error.bool",
                "input": raw,
            }],
        )
    if isinstance(raw, (int, float)):
        n = int(raw)
    elif isinstance(raw, str):
        try:
            n = int(raw.strip())
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "loc": ["body", "video_duration"],
                    "msg": f"video_duration must be a number, got {raw!r}",
                    "type": "value_error.int",
                    "input": raw,
                }],
            ) from exc
    else:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "video_duration"],
                "msg": f"video_duration must be a number, got {type(raw).__name__}",
                "type": "value_error.type",
                "input": str(raw)[:100],
            }],
        )
    if n in VALID_VIDEO_DURATIONS:
        return n
    return min(VALID_VIDEO_DURATIONS, key=lambda v: abs(v - n))
