"""Global state and helpers shared across routers (P1-11).

Extracted from api.py so domain routers can import shared state
without circular dependencies.
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.config import OUTPUT_DIR
from src.graph.pipeline import compile_pipeline

# ── Pipeline state ──
_pipeline = compile_pipeline()
_active_threads: dict[str, dict[str, Any]] = {}
_THREAD_INDEX_PATH = OUTPUT_DIR / ".thread_index.json"
_pipeline_semaphore = asyncio.Semaphore(10)  # P3-4: Max 10 concurrent pipelines

# Background task registry
_background_tasks: dict[str, dict[str, Any]] = {}

# Thread cache TTL
_THREAD_CACHE_TTL_SEC = 24 * 3600  # 24 hours
_thread_cache_meta: dict[str, float] = {}  # thread_id → last_accessed timestamp


# ── Pydantic models ──
class PipelineStartRequest(BaseModel):
    product_catalog: dict[str, Any] = {}
    brand_guidelines: dict[str, Any] = {}
    target_platforms: list[str] = ["shopify", "amazon", "tiktok", "reddit"]
    target_languages: list[str] = ["en"]
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


class S1StartRequest(BaseModel):
    product_catalog: dict[str, Any]
    brand_guidelines: dict[str, Any] = {}
    target_platforms: list[str] = []
    target_languages: list[str] = ["en"]
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


async def _get_config_for_thread(thread_id: str) -> dict:
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


# ── Background task registry ──

def _register_background_task(task: asyncio.Task, label: str) -> str:
    """Register a background task and attach completion callback."""
    import structlog
    log = structlog.get_logger()
    task_id = f"{label}_{id(task)}"
    started_at = time.time()
    _background_tasks[task_id] = {"task": task, "label": label, "started_at": started_at}

    def _on_done(t: asyncio.Task) -> None:
        duration_sec = time.time() - started_at
        try:
            exc = t.exception()
            if exc:
                log.error(
                    "background_task_failed",
                    task_id=task_id,
                    label=label,
                    duration_sec=round(duration_sec, 2),
                    error=str(exc)[:200],
                )
            else:
                log.info(
                    "background_task_completed",
                    task_id=task_id,
                    label=label,
                    duration_sec=round(duration_sec, 2),
                )
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            _background_tasks.pop(task_id, None)

    task.add_done_callback(_on_done)
    return task_id


# ── Scenario helpers ──

_SCENARIO_STEP_ORDER: dict[str, list[str]] = {
    "s1": [
        "strategy", "scripts", "compliance", "storyboards",
        "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips",
        "tts_audio", "thumbnail_images", "assemble_final", "audit",
    ],
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


def _get_step_output(state: dict, step_name: str) -> Any:
    """Extract step output from pipeline state (prefers edited over original)."""
    edited = state.get("edited_outputs", {})
    if step_name in edited:
        return edited[step_name]
    return state.get(step_name)
