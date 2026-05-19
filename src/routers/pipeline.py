"""pipeline router — LangGraph proxy layer (P4-4).

All endpoints retain their original API contract, but internally delegate to
StepRunner instead of LangGraph. This provides backward compatibility for:
- External callers using /pipeline/* endpoints
- Historical thread IDs (pre-StepRunner migration)
- Testing and integration scenarios

New pipeline runs are started via StepRunner and their state is queried
through PipelineStateManager.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

try:
    from src.storage import HAS_STORAGE
except ImportError:
    HAS_STORAGE = False

from src.config import DEFAULT_LANGUAGES
from src.models import REVIEW_NODES, ApprovalStatus
from src.routers._deps import _inject_api_keys, _safe_error, get_auth_context, verify_api_key
from src.routers._state import (
    PipelineStartRequest,
    ReviewAction,
    _active_threads,
    _cleanup_thread_cache,
    _label_thread_map,
    _save_thread_index,
    _thread_label_map,
    _touch_thread_cache,
)

router = APIRouter()


# ── State conversion helpers ──


def _steprunner_state_to_legacy(label: str, state: dict[str, Any] | None) -> dict[str, Any]:
    """Convert StepRunner state dict to legacy LangGraph-compatible format.

    This is a best-effort conversion — fields that don't exist in StepRunner
    (e.g., human_reviews, mock_quality) are omitted or defaulted.
    """
    if state is None:
        return {"label": label, "status": "not_found"}

    config = state.get("config", {})
    steps = state.get("steps", {})

    # Flatten step outputs into top-level fields (legacy format expectation)
    legacy_state: dict[str, Any] = {
        "product_catalog": config.get("product_catalog", {}),
        "brand_guidelines": config.get("brand_guidelines", {}),
        "target_platforms": config.get("target_platforms", []),
        "target_languages": config.get("target_languages", DEFAULT_LANGUAGES),
        "content_calendar_week": config.get("week", ""),
        "content_scenario": config.get("content_scenario", "product_direct"),
        "current_step": state.get("current_step", ""),
        "errors": state.get("errors", []),
        "structured_errors": [],
        "pipeline_complete": False,
    }

    # Map step outputs to legacy field names
    step_output_map = {
        "strategy": "briefs",
        "scripts": "scripts",
        "compliance": "compliance_report",
        "storyboards": "storyboards",
        "keyframe_images": "keyframe_images",
        "video_prompts": "video_prompts",
        "thumbnail_prompts": "thumbnail_sets",
        "seedance_clips": "seedance_output",
        "tts_audio": "audio_paths",
        "thumbnail_images": "thumbnail_image_paths",
        "assemble_final": "final_video_path",
        "audit": "audit_report",
    }
    for step_name, legacy_key in step_output_map.items():
        step_data = steps.get(step_name, {})
        if isinstance(step_data, dict):
            legacy_state[legacy_key] = step_data.get("output")
        else:
            legacy_state[legacy_key] = step_data

    # Distribution plans (may be in assemble_final or a separate step)
    assemble = steps.get("assemble_final", {})
    if isinstance(assemble, dict):
        legacy_state["distribution_plans"] = assemble.get("output", {}).get("distribution_plans", []) if isinstance(assemble.get("output"), dict) else []
    legacy_state["analytics_reports"] = steps.get("audit", {}).get("output", {}) if isinstance(steps.get("audit"), dict) else {}

    # Human reviews — StepRunner doesn't have checkpoint reviews; default empty
    legacy_state["human_reviews"] = {}
    legacy_state["pipeline_complete"] = all(
        s.get("status") == "done"
        for s in steps.values()
        if isinstance(s, dict)
    ) and len(steps) > 0

    return legacy_state


def _get_state_status(legacy_state: dict[str, Any]) -> str:
    """Derive status string from legacy state."""
    if legacy_state.get("pipeline_complete"):
        return "complete"
    if legacy_state.get("status") == "not_found":
        return "not_found"
    return "interrupted"


def _assert_state_access(state: dict[str, Any] | None) -> None:
    """Reject cross-tenant access to StepRunner-backed legacy pipeline state."""
    if state is None:
        return
    ctx = get_auth_context()
    if ctx is None:
        return
    state_tenant = state.get("tenant_id")
    if not state_tenant:
        if ctx.tenant_id in {"default", "test-bundle"}:
            return
        raise HTTPException(status_code=404, detail="Pipeline not found")
    if state_tenant != ctx.tenant_id:
        raise HTTPException(status_code=404, detail="Pipeline not found")


async def _load_steprunner_state(label: str) -> dict[str, Any] | None:
    """Load state from PipelineStateManager by label."""
    from src.pipeline.state_manager import PipelineStateManager
    manager = PipelineStateManager()
    return await manager.load(label)


# ═══════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════


@router.post("/pipeline/start", dependencies=[Depends(verify_api_key)])
async def start_pipeline(req: PipelineStartRequest):
    """Start a new pipeline run via StepRunner.

    Returns a synthetic thread_id for backward compatibility.
    The actual execution is delegated to StepRunner.
    """
    from src.pipeline.state_manager import PipelineStateManager
    from src.pipeline.step_runner import StepRunner
    from src.routers._state import _register_background_task
    from src.tools.translate import translate_catalog_to_english

    thread_id = str(uuid.uuid4())

    # Inject API keys from request into environment
    if req.api_keys:
        _inject_api_keys(req.api_keys)

    # Translate Chinese product inputs to English
    product_catalog = dict(req.product_catalog) if isinstance(req.product_catalog, dict) else {}
    product_catalog = await translate_catalog_to_english(product_catalog)

    config = {
        "product_catalog": product_catalog,
        "brand_guidelines": req.brand_guidelines,
        "target_platforms": req.target_platforms,
        "target_languages": DEFAULT_LANGUAGES,
        "week": req.content_calendar_week,
        "video_duration": 30,
        "brand_mode": False,
        "enable_media_synthesis": True,
        "content_scenario": req.content_scenario,
    }

    state_manager = PipelineStateManager()
    step_runner = StepRunner(state_manager)

    # Initialize state
    label = await step_runner.init_state(config=config, mode="auto")

    # Map thread_id ↔ label for subsequent queries
    _thread_label_map[thread_id] = label
    _label_thread_map[label] = thread_id
    _active_threads[thread_id] = {"configurable": {"thread_id": thread_id}, "label": label}
    _touch_thread_cache(thread_id)
    _save_thread_index()

    # Start pipeline in background (non-blocking)
    async def _resume():
        try:
            await step_runner.resume(label)
        except Exception as exc:
            import structlog
            log = structlog.get_logger()
            log.error("pipeline_proxy: resume failed", thread_id=thread_id, label=label, error=str(exc)[:200])

    _register_background_task(
        asyncio.create_task(_resume()),
        label=f"pipeline_proxy:{thread_id}",
    )

    return {
        "thread_id": thread_id,
        "status": "started",
        "label": label,
        "events": [],
    }


@router.get("/pipeline/{thread_id}/state", dependencies=[Depends(verify_api_key)])
async def get_pipeline_state(thread_id: str):
    """Get current pipeline state for a thread (proxied to StepRunner)."""
    label = _thread_label_map.get(thread_id)
    if not label:
        # Legacy: check if this is an old LangGraph thread
        if thread_id in _active_threads:
            return {"thread_id": thread_id, "status": "legacy", "message": "Legacy LangGraph thread — state no longer available"}
        return {"thread_id": thread_id, "status": "not_found"}

    _touch_thread_cache(thread_id)

    try:
        state = await _load_steprunner_state(label)
        _assert_state_access(state)
        legacy = _steprunner_state_to_legacy(label, state)
        status = _get_state_status(legacy)

        # Determine current review node (StepRunner has no checkpoint reviews)
        current_review = None
        if status != "complete":
            for node_name in REVIEW_NODES:
                current_review = node_name
                break

        if status == "complete":
            _cleanup_thread_cache(thread_id)

        return {
            "thread_id": thread_id,
            "status": status,
            "current_review": current_review,
            "pipeline_complete": legacy.get("pipeline_complete", False),
            "state": legacy,
        }
    except Exception as e:
        return {"thread_id": thread_id, "status": "error", "detail": _safe_error(e)}


@router.post("/pipeline/{thread_id}/review/{review_node}", dependencies=[Depends(verify_api_key)])
async def submit_review(thread_id: str, review_node: str, action: ReviewAction):
    """Submit human review for a pipeline checkpoint.

    P4-4: StepRunner does not use LangGraph checkpoint reviews.
    All review submissions are treated as idempotent no-ops.
    The pipeline continues autonomously; gate approvals use
    /scenario/{s}/gate/{label}/{gate_id}/approve instead.
    """
    import structlog
    log = structlog.get_logger()

    log.warning(
        "pipeline_proxy: review submitted on StepRunner-backed thread",
        thread_id=thread_id,
        review_node=review_node,
        action=action.action,
    )

    status_map = {
        "approve": ApprovalStatus.APPROVED,
        "reject": ApprovalStatus.REJECTED,
        "request_changes": ApprovalStatus.CHANGES_REQUESTED,
    }
    _ = status_map.get(action.action, ApprovalStatus.APPROVED)

    return {
        "thread_id": thread_id,
        "review_node": review_node,
        "action": action.action,
        "status": "idempotent_skip",
        "message": (
            "StepRunner pipelines do not use checkpoint reviews. "
            "Use /scenario/{s}/gate/{label}/{gate_id}/approve for gate approval."
        ),
        "events": [],
    }


@router.get("/pipeline/{thread_id}/output", dependencies=[Depends(verify_api_key)])
async def get_pipeline_output(thread_id: str):
    """Get final pipeline output as JSON."""
    label = _thread_label_map.get(thread_id)
    if not label:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    state = await _load_steprunner_state(label)
    if state is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    _assert_state_access(state)

    return _steprunner_state_to_legacy(label, state)


@router.get("/pipeline/{thread_id}/distribution", dependencies=[Depends(verify_api_key)])
async def get_distribution_plans(thread_id: str):
    """Get distribution plans with platform-specific post content."""
    label = _thread_label_map.get(thread_id)
    if not label:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    state = await _load_steprunner_state(label)
    if state is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    _assert_state_access(state)

    legacy = _steprunner_state_to_legacy(label, state)
    plans = legacy.get("distribution_plans", [])
    return {"distribution_plans": plans}


@router.get("/pipeline/{thread_id}/export", dependencies=[Depends(verify_api_key)])
async def export_pipeline_output(thread_id: str):
    """Clean export: only user-facing fields, no internal state."""
    label = _thread_label_map.get(thread_id)
    if not label:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    state = await _load_steprunner_state(label)
    if state is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    _assert_state_access(state)

    legacy = _steprunner_state_to_legacy(label, state)

    # Internal fields to strip
    _internal = {
        "retry_counts", "self_verifications", "rejection_feedback",
        "pipeline_metrics", "messages", "errors", "structured_errors",
        "current_step", "pipeline_complete", "mock_quality",
    }

    export = {k: v for k, v in legacy.items() if k not in _internal}
    export["human_review_summary"] = []

    return export
