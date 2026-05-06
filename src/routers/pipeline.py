"""pipeline router — extracted from api.py (P1-11)."""

import asyncio
import uuid

from fastapi import APIRouter, HTTPException, Depends

try:
    from src.storage import HAS_STORAGE
    from src.storage.repository import ThreadRepository, PipelineStateRepository
except ImportError:
    HAS_STORAGE = False

from src.config import DEFAULT_LANGUAGES
from src.models import ApprovalStatus, ContentScenario, HumanReview, REVIEW_NODES
from src.routers._deps import _serialize, _safe_error, _inject_api_keys, verify_api_key
from src.routers._state import (
    get_pipeline,
    _active_threads,
    _pipeline_semaphore,
    _touch_thread_cache,
    _cleanup_thread_cache,
    _save_thread_index,
    _get_config_for_thread,
    PipelineStartRequest,
    ReviewAction,
)


router = APIRouter()

@router.post("/pipeline/start", dependencies=[Depends(verify_api_key)])
async def start_pipeline(req: PipelineStartRequest):
    pipeline = await asyncio.to_thread(get_pipeline)
    """Start a new pipeline run. Returns thread_id for tracking.

    Phase 2+3: Translates Chinese product inputs to English before
    pipeline execution and forces target_languages to ``["en"]``.

    Accepts optional api_keys dict to override .env values for this process.
    """
    from src.tools.translate import translate_catalog_to_english

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Inject API keys from request into environment
    if req.api_keys:
        _inject_api_keys(req.api_keys)

    # Translate Chinese product name / USPs to English
    product_catalog = dict(req.product_catalog) if isinstance(req.product_catalog, dict) else req.product_catalog
    product_catalog = await translate_catalog_to_english(product_catalog)

    initial_state = {
        "product_catalog": product_catalog,
        "brand_guidelines": req.brand_guidelines,
        "target_platforms": req.target_platforms,
        "target_languages": DEFAULT_LANGUAGES,  # Lock pipeline to English output
        "content_calendar_week": req.content_calendar_week,
        "content_scenario": req.content_scenario,
        "current_step": "init",
        "errors": [],
        "structured_errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    # Run until first interrupt
    events = []
    try:
        async with _pipeline_semaphore:
            async for event in pipeline.astream(initial_state, config):
                events.append(event)
    except Exception as e:
        import logging
        logging.error("pipeline start failed: %s", e)
        raise HTTPException(status_code=500, detail=_safe_error(e))

    # P1-10: Write to PG first (single source of truth), then cache in memory.
    # This ensures other workers can see the thread immediately.
    if HAS_STORAGE:
        repo = ThreadRepository()
        await repo.create({
            "thread_id": thread_id,
            "state": initial_state,
            "current_step": "init",
            "pipeline_complete": False,
        })
    _active_threads[thread_id] = config
    _touch_thread_cache(thread_id)
    _save_thread_index()
    return {
        "thread_id": thread_id,
        "status": "interrupted",
        "events": _serialize(events),
    }


@router.get("/pipeline/{thread_id}/state", dependencies=[Depends(verify_api_key)])
async def get_pipeline_state(thread_id: str):
    pipeline = await asyncio.to_thread(get_pipeline)
    """Get current pipeline state for a thread."""
    config = _active_threads.get(thread_id)
    if config:
        _touch_thread_cache(thread_id)
    if not config and HAS_STORAGE:
        repo = ThreadRepository()
        thread = await repo.get_by_field("thread_id", thread_id)
        if thread:
            config = {"configurable": {"thread_id": thread_id}}
            _active_threads[thread_id] = config
            _touch_thread_cache(thread_id)
    if not config:
        config = {"configurable": {"thread_id": thread_id}}

    try:
        snapshot = pipeline.get_state(config)
        if snapshot is None or snapshot.values is None:
            return {"thread_id": thread_id, "status": "not_found"}

        values = _serialize(snapshot.values)

        # Determine current review node
        current_review = None
        reviews = snapshot.values.get("human_reviews", {}) if snapshot.values else {}
        for node_name in REVIEW_NODES:
            if node_name not in reviews or reviews[node_name].get("status") == "pending":
                current_review = node_name
                break

        has_pipeline_complete = snapshot.values.get("pipeline_complete", False) if snapshot.values else False

        # P1-1: Active cleanup on pipeline completion to prevent memory leak.
        if has_pipeline_complete:
            _cleanup_thread_cache(thread_id)

        return {
            "thread_id": thread_id,
            "status": "complete" if has_pipeline_complete else ("interrupted" if snapshot.next else "complete"),
            "current_review": current_review,
            "pipeline_complete": has_pipeline_complete,
            "state": values,
        }
    except Exception as e:
        import logging
        logging.error("pipeline state failed: %s", e)
        return {"thread_id": thread_id, "status": "error", "detail": _safe_error(e)}


@router.post("/pipeline/{thread_id}/review/{review_node}", dependencies=[Depends(verify_api_key)])
async def submit_review(thread_id: str, review_node: str, action: ReviewAction):
    pipeline = await asyncio.to_thread(get_pipeline)
    """Submit human review for a pipeline checkpoint. Resumes execution.

    D9: Double-click guard — if the pipeline has already moved past the
    requested review_node, return a no-op success to prevent double-resume.

    IMPORTANT: For reject, the pipeline is terminated directly.
    For other actions, we must use astream with the updated reviews
    as input (not update_state + astream(None)) because LangGraph
    checkpoint recovery does not preserve update_state across the
    astream boundary in interrupt_after resume scenarios.
    """
    config = _active_threads.get(thread_id)
    if config:
        _touch_thread_cache(thread_id)
    if not config and HAS_STORAGE:
        repo = ThreadRepository()
        thread = await repo.get_by_field("thread_id", thread_id)
        if thread:
            config = {"configurable": {"thread_id": thread_id}}
            _active_threads[thread_id] = config
            _touch_thread_cache(thread_id)
    if not config:
        config = {"configurable": {"thread_id": thread_id}}
    import structlog
    log = structlog.get_logger()

    status_map = {
        "approve": ApprovalStatus.APPROVED,
        "reject": ApprovalStatus.REJECTED,
        "request_changes": ApprovalStatus.CHANGES_REQUESTED,
    }
    status = status_map.get(action.action, ApprovalStatus.APPROVED)

    # D9: Get snapshot and check double-click guard
    snapshot = pipeline.get_state(config)

    # If no snapshot or no human_reviews yet, we're still in the right place
    if snapshot and snapshot.values:
        current_reviews = dict(snapshot.values.get("human_reviews", {}))

        # Double-click guard: if this review_node already has a non-pending
        # status, someone already processed it — return idempotent success.
        existing = current_reviews.get(review_node, {})
        if isinstance(existing, dict) and existing.get("status", "pending") != "pending":
            log.warning(
                "pipeline: double-click guard triggered",
                review_node=review_node,
                existing_status=existing.get("status"),
            )
            return {
                "thread_id": thread_id,
                "review_node": review_node,
                "action": action.action,
                "status": "idempotent_skip",
                "message": "Review already processed",
                "events": [],
            }
    else:
        current_reviews = {}

    review_entry = HumanReview(
        node=review_node,
        status=status,
        reviewer_notes=action.reviewer_notes,
    ).model_dump()
    current_reviews[review_node] = review_entry

    # Update checkpoint with the new review
    pipeline.update_state(config, {"human_reviews": current_reviews})

    # Handle reject: terminate pipeline directly, no resume needed
    if action.action == "reject":
        pipeline.update_state(config, {"pipeline_complete": True, "current_step": "rejected"})
        _cleanup_thread_cache(thread_id)
        return {
            "thread_id": thread_id,
            "review_node": review_node,
            "action": action.action,
            "status": "rejected",
            "events": [],
        }

    
    # D10: Set routing override for this checkpoint
    # This is the only way the routing function can see the review decision,
    # because LangGraph checkpoint recovery overwrites update_state values
    # during astream(None) resume.
    from src.graph.routing import _set_override
    checkpoint_key = review_node.replace("_review", "")
    _set_override(checkpoint_key, {
        "node_key": checkpoint_key,
        "status": action.action,
    })

    events = []
    try:
        # D10: Use astream(None) — pure resume without overwriting checkpoint state.
        # The update_state(...) call above already persisted the human review.
        # _set_override (set above) ensures routing reads the decision.
        async with _pipeline_semaphore:
            async for event in pipeline.astream(None, config):
                events.append(event)

    except Exception as e:
        import traceback

        log.error("pipeline: resume failed", error=str(e), traceback=traceback.format_exc())
        raise HTTPException(status_code=500, detail=_safe_error(e))

    # Pipeline complete: if last review approved, mark pipeline complete
    # (mock mode analytics_node doesn't set this)
    # NOTE: review_node comes from URL path parameter and matches REVIEW_NODES
    # which are "strategy_review"/"script_review"/"edit_review"/"thumbnail_review"
    if review_node == "thumbnail_review" and action.action == "approve":
        pipeline.update_state(config, {"pipeline_complete": True})
        _cleanup_thread_cache(thread_id)

    return {
        "thread_id": thread_id,
        "review_node": review_node,
        "action": action.action,
        "status": "resumed",
        "events": _serialize(events),
    }


@router.get("/pipeline/{thread_id}/output", dependencies=[Depends(verify_api_key)])
async def get_pipeline_output(thread_id: str):
    pipeline = await asyncio.to_thread(get_pipeline)
    """Get final pipeline output as JSON."""
    config = await _get_config_for_thread(thread_id)
    snapshot = pipeline.get_state(config)
    if snapshot is None or snapshot.values is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    return _serialize(snapshot.values)


@router.get("/pipeline/{thread_id}/distribution", dependencies=[Depends(verify_api_key)])
async def get_distribution_plans(thread_id: str):
    pipeline = await asyncio.to_thread(get_pipeline)
    """Get distribution plans with platform-specific post content.

    Returns distribution_plans array, each with brief_id, script_id,
    and 4 platform posts (shopify/amazon/tiktok/reddit) containing
    CTA, video_format, product_link_placeholder, and platform-specific body.
    """
    config = await _get_config_for_thread(thread_id)
    snapshot = pipeline.get_state(config)
    if snapshot is None or snapshot.values is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    plans = _serialize(snapshot.values).get("distribution_plans", [])
    return {"distribution_plans": plans}


@router.get("/pipeline/{thread_id}/export", dependencies=[Depends(verify_api_key)])
async def export_pipeline_output(thread_id: str):
    pipeline = await asyncio.to_thread(get_pipeline)
    """Clean export: only user-facing fields, no internal state.

    Strips out internal-only fields: retry_counts, self_verifications,
    rejection_feedback, pipeline_metrics, messages, errors, structured_errors.
    Returns only what matters for rendering: scripts, captions, thumbnails,
    distribution plans, analytics reports, and human review timeline.
    """
    config = await _get_config_for_thread(thread_id)
    snapshot = pipeline.get_state(config)
    if snapshot is None or snapshot.values is None:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    values = _serialize(snapshot.values)

    # Internal fields to strip
    _internal = {
        "retry_counts", "self_verifications", "rejection_feedback",
        "pipeline_metrics", "messages", "errors", "structured_errors",
        "current_step", "pipeline_complete", "mock_quality",
    }

    # User-facing fields to include
    export = {
        k: v for k, v in values.items()
        if k not in _internal
    }

    # Add the human review timeline as a summary
    reviews = values.get("human_reviews", {})
    if isinstance(reviews, dict):
        export["human_review_summary"] = [
            {
                "node": node_name,
                "status": r.get("status", "unknown"),
                "notes": r.get("reviewer_notes", ""),
            }
            for node_name, r in reviews.items()
            if isinstance(r, dict)
        ]

    return export


