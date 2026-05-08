"""Global state and helpers shared across routers (P1-11).

Extracted from api.py so domain routers can import shared state
without circular dependencies.
"""

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import DEFAULT_LANGUAGES, OUTPUT_DIR
from src.graph.pipeline import compile_pipeline

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

# Background task registry
_background_tasks: dict[str, dict[str, Any]] = {}

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
    # P1-C: 用户填的多供应商 key 通过此字段下发,scenario.py 入口注入 contextvars
    api_keys: dict[str, str] = {}


class S1StartRequest(BaseModel):
    product_catalog: dict[str, Any]
    brand_guidelines: dict[str, Any] = {}
    target_platforms: list[str] = []
    target_languages: list[str] = DEFAULT_LANGUAGES
    week: str = ""
    video_duration: int = 30
    mode: str = "auto"
    brand_mode: bool = False
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
    except Exception:
        pass


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
    except Exception:
        pass


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
# Re-export for backward compatibility.
from src.tasks.bg_registry import register_background_task as _register_background_task


# ── Scenario helpers ──

_SCENARIO_STEP_ORDER: dict[str, list[str]] = {
    "s1": [
        "strategy", "scripts", "compliance", "storyboards",
        "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips",
        "tts_audio", "thumbnail_images", "assemble_final", "audit",
    ],
}

_STEP_DURATIONS: dict[str, str] = {
    "strategy": "~5s",
    "scripts": "~5s",
    "compliance": "~2s",
    "storyboards": "~4s",
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

    Reads from the StepRunner-native structure ``state.steps[step_name].edited_output``
    so that user edits made through the gate approval flow are correctly picked up.
    """
    steps = state.get("steps", {})
    step_data = steps.get(step_name, {})
    if step_data.get("edited") and step_data.get("edited_output") is not None:
        return step_data["edited_output"]
    return step_data.get("output")
