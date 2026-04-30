"""FastAPI backend — exposes pipeline state and human review endpoints.

Run with: uvicorn src.api:app --reload --port 8001

API keys can be submitted at pipeline start via the api_keys field.
When provided, they are stored in a per-request context (contextvars) so that
concurrent pipelines do not contaminate each other's keys.
If not provided, the server falls back to .env file values (or mock mode).
"""

import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from urllib.parse import quote
from typing import Any

# Load .env so API_KEY, DATABASE_URL, etc. are available before fastapi starts
from dotenv import load_dotenv
load_dotenv()

try:
    from fastapi import FastAPI, HTTPException, Header, Depends
    from fastapi.middleware.cors import CORSMiddleware
    HAS_FASTAPI = True
except ImportError:
    FastAPI = None  # type: ignore
    HTTPException = None  # type: ignore
    CORSMiddleware = None  # type: ignore
    Header = None  # type: ignore
    Depends = None  # type: ignore
    HAS_FASTAPI = False

try:
    from src.storage import get_pool, init_db
    from src.storage.repository import ThreadRepository, PipelineStateRepository, PublishLogRepository
    from src.storage.metrics_repository import VideoMetricsRepository
    HAS_STORAGE = True
except ImportError:
    HAS_STORAGE = False

from pydantic import BaseModel

from src.graph.pipeline import compile_pipeline
from src.models import ApprovalStatus, ContentScenario, HumanReview, REVIEW_NODES

# Global pipeline instance (one per process)
_pipeline = compile_pipeline()
_active_threads: dict[str, dict[str, Any]] = {}

# P2-1: Thread index persistence file — survives process restarts.
# P1-14: Use OUTPUT_DIR (env-configurable) instead of hard-coded repo path.
_THREAD_INDEX_PATH = OUTPUT_DIR / ".thread_index.json"

import asyncio as _asyncio
_pipeline_semaphore = _asyncio.Semaphore(10)  # P3-4: Max 10 concurrent pipelines

# Background task registry — tracks async tasks spawned by API endpoints
# Maps task_id → {"task": Task, "label": str, "started_at": float}
_background_tasks: dict[str, dict[str, Any]] = {}


def _register_background_task(task: _asyncio.Task, label: str) -> str:
    """Register a background task and attach completion callback."""
    import structlog
    log = structlog.get_logger()
    task_id = f"{label}_{id(task)}"
    started_at = time.time()
    _background_tasks[task_id] = {"task": task, "label": label, "started_at": started_at}

    def _on_done(t: _asyncio.Task) -> None:
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
        except (_asyncio.CancelledError, Exception):
            pass
        finally:
            _background_tasks.pop(task_id, None)

    task.add_done_callback(_on_done)
    return task_id


class PipelineStartRequest(BaseModel):
    product_catalog: dict[str, Any] = {}
    brand_guidelines: dict[str, Any] = {}
    target_platforms: list[str] = ["shopify", "amazon", "tiktok", "reddit"]
    target_languages: list[str] = ["en"]
    content_calendar_week: str = "2026-W17"
    api_keys: dict[str, str] = {}  # Keys sent from WebUI
    content_scenario: str = "influencer_remix"  # Default: influencer remix for employee IP


class ReviewAction(BaseModel):
    action: str  # "approve" | "reject" | "request_changes"
    reviewer_notes: str = ""


def _inject_api_keys(api_keys: dict[str, str]) -> None:
    """Store API keys in request context (not process-wide os.environ).

    Using contextvars ensures concurrent requests do not contaminate each
    other's keys. The LLM client reads from request context first, then
    falls back to os.environ — no global client cache clearing needed.
    """
    if not api_keys:
        return

    key_map = {
        "openai": "OPENAI_API_KEY",
        "OPENAI_API_KEY": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY",
        "elevenlabs": "ELEVENLABS_API_KEY",
        "ELEVENLABS_API_KEY": "ELEVENLABS_API_KEY",
        "poyo": "POYO_API_KEY",
        "POYO_API_KEY": "POYO_API_KEY",
        "supabase_url": "SUPABASE_URL",
        "SUPABASE_URL": "SUPABASE_URL",
        "supabase_key": "SUPABASE_SERVICE_KEY",
        "SUPABASE_SERVICE_KEY": "SUPABASE_SERVICE_KEY",
    }
    normalized: dict[str, str] = {}
    for key_or_alias, value in api_keys.items():
        if value and value.strip():
            env_key = key_map.get(key_or_alias, key_or_alias)
            normalized[env_key] = value.strip()

    # Store in request context — isolated per asyncio task
    from src.tools.llm_client import set_request_api_keys
    set_request_api_keys(normalized)


def _serialize(obj: Any) -> Any:
    """Recursively serialize Pydantic models to JSON-safe dicts."""
    from pydantic import BaseModel as PydanticBase

    if isinstance(obj, PydanticBase):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _safe_error(exc: Exception, is_dev: bool = False) -> str:
    """Return a generic error message unless in dev mode. Includes trace_id for production debugging."""
    if is_dev:
        return str(exc)
    import uuid as _uuid
    _trace = str(_uuid.uuid4())[:8]
    import logging
    logging.getLogger("api.error").error("internal_error trace_id=%s error=%s", _trace, str(exc)[:200])
    return f"Internal server error [trace: {_trace}]"


# ── FastAPI app — only defined when fastapi is installed ──

if HAS_FASTAPI:

    app = FastAPI(title="Short Video Agent API", version="0.2.0")

    @app.on_event("startup")
    async def startup():
        if HAS_STORAGE:
            await init_db()
            try:
                from src.storage.db import check_pg_health, is_pg_available
                health = await check_pg_health()
                import logging
                _log = logging.getLogger("api.startup")
                _log.info(
                    "Persistence backend: %s (status=%s, pg_available=%s)",
                    health.get("backend"),
                    health.get("status"),
                    is_pg_available(),
                )
            except Exception:
                pass
        # P2-1: Restore active threads from disk (standalone mode only)
        _restore_thread_index()
        # P1-10: Start background thread cache eviction loop
        _asyncio.create_task(_periodic_cache_eviction())

    API_KEY = os.getenv("API_KEY", "")
    if not API_KEY:
        import logging
        logging.warning("SECURITY: API_KEY environment variable is not set. Generating a temporary key for this session.")
        API_KEY = secrets.token_urlsafe(32)
        logging.warning("SECURITY: Temporary API_KEY = %s  (set this in your .env for persistence)", API_KEY)

    def verify_api_key(x_api_key: str | None = Header(None)):
        if x_api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
        return True

    # CORS: allow comma-separated origins via CORS_ORIGINS env var
    _cors_env = os.getenv("CORS_ORIGINS", "")
    _default_origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost",
        "https://lute-ai-video.tcloudbaseapp.com",
        "https://*.tcloudbaseapp.com",
    ]
    if _cors_env:
        allow_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
    else:
        allow_origins = _default_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
    )

    # ── P2-1: Thread persistence helpers ──

    def _save_thread_index():
        """Persist _active_threads keys to JSON for crash recovery.

        P1-10: When PostgreSQL is available, skip JSON — PG is the single source
        of truth across workers. JSON only serves standalone (no-DB) deployments.
        """
        if HAS_STORAGE:
            return  # PG handles persistence; JSON is meaningless across K8s replicas
        try:
            _THREAD_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_THREAD_INDEX_PATH, "w") as f:
                json.dump(list(_active_threads.keys()), f)
        except Exception:
            pass  # Non-critical — best-effort persistence

    def _restore_thread_index():
        """Restore thread IDs from disk on startup.

        P1-10: When PostgreSQL is available, skip JSON restore — threads are
        loaded on-demand via _get_config_for_thread PG fallback.
        """
        if HAS_STORAGE:
            return  # PG is the source of truth; JSON may be stale from another replica
        try:
            if _THREAD_INDEX_PATH.exists():
                with open(_THREAD_INDEX_PATH) as f:
                    ids = json.load(f)
                for tid in ids:
                    if isinstance(tid, str):
                        _active_threads[tid] = {"configurable": {"thread_id": tid}}
        except Exception:
            pass

    import json as _json

    # Restore on module load
    _restore_thread_index()

    # ── P1-10: In-memory thread cache TTL cleanup ──
    # _active_threads is a local cache only. Threads are persisted in PG.
    # Stale entries are evicted after 24h to prevent unbounded growth.
    _THREAD_CACHE_TTL_SEC = 24 * 3600  # 24 hours
    _thread_cache_meta: dict[str, float] = {}  # thread_id → last_accessed timestamp

    def _touch_thread_cache(thread_id: str) -> None:
        """Update last-accessed timestamp for a cached thread."""
        _thread_cache_meta[thread_id] = time.time()

    def _evict_stale_threads() -> None:
        """Remove threads from memory cache that haven't been accessed recently."""
        now = time.time()
        stale = [
            tid for tid, last_access in _thread_cache_meta.items()
            if now - last_access > _THREAD_CACHE_TTL_SEC
        ]
        for tid in stale:
            _active_threads.pop(tid, None)
            _thread_cache_meta.pop(tid, None)

    def _cleanup_thread_cache(thread_id: str) -> None:
        """P1-1: Remove thread from in-memory cache when pipeline terminates.

        Called on pipeline completion/rejection/failure to prevent
        _active_threads from growing unbounded.
        """
        _active_threads.pop(thread_id, None)
        _thread_cache_meta.pop(thread_id, None)

    async def _periodic_cache_eviction() -> None:
        """Background loop: evict stale thread cache entries every hour."""
        while True:
            await _asyncio.sleep(3600)
            _evict_stale_threads()

    # ── P3-1: Rate limiting middleware (sliding window + LRU eviction) ──
    # Anti-pattern fixed: replaced global _rate_store.clear() with per-IP TTL + LRU eviction.
    # This prevents attackers from using 1001 fake IPs to force a global reset and evade rate limits.

    _rate_window_sec = 60
    _rate_max_requests = 120  # 120 requests per 60s = 2 req/s average
    _rate_max_ips = 1000      # Max distinct IPs tracked; oldest touched IP is evicted (LRU)

    from collections import OrderedDict
    _rate_store: OrderedDict[str, list[float]] = OrderedDict()  # client_ip → [timestamps]

    @app.middleware("http")
    async def rate_limit_middleware(request, call_next):
        from fastapi import Request, Response
        from fastapi.responses import JSONResponse

        # Skip health endpoint
        if request.url.path == "/health":
            return await call_next(request)

        # Prefer X-Forwarded-For when behind a reverse proxy; fall back to direct client IP
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        now = time.time()

        # Move accessed IP to the end (most-recently-used)
        if client_ip in _rate_store:
            _rate_store.move_to_end(client_ip)

        timestamps = _rate_store.get(client_ip, [])
        # Remove expired entries within this IP's window
        timestamps = [t for t in timestamps if now - t < _rate_window_sec]

        if len(timestamps) >= _rate_max_requests:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down.", "retry_after_sec": _rate_window_sec},
            )

        timestamps.append(now)
        _rate_store[client_ip] = timestamps

        # LRU eviction: only drop the least-recently-used IP, never clear everything
        while len(_rate_store) > _rate_max_ips:
            _rate_store.popitem(last=False)

        return await call_next(request)

    # ── Request logging middleware ──
    _request_log = logging.getLogger("api.request")

    @app.middleware("http")
    async def request_log_middleware(request, call_next):
        _start = time.perf_counter()
        response = await call_next(request)
        _duration_ms = (time.perf_counter() - _start) * 1000
        _request_log.info(
            "%s %s → %s (%.0fms)",
            request.method, request.url.path, response.status_code, _duration_ms,
        )
        return response

    # Mount asset management endpoints (requires python-multipart for File/Form)
    try:
        from src import api_assets
        app.include_router(api_assets.router, dependencies=[Depends(verify_api_key)])
    except (ImportError, RuntimeError) as _e:
        import logging
        logging.warning("api_assets router skipped: %s", _e)
        logging.warning("Install python-multipart to enable asset upload endpoints")

    # Mount telemetry endpoints
    try:
        from src import telemetry_endpoint
        if telemetry_endpoint.router:
            app.include_router(
                telemetry_endpoint.router,
                dependencies=[Depends(verify_api_key)],
            )
    except (ImportError, RuntimeError) as _e:
        import logging
        logging.warning("telemetry router skipped: %s", _e)

    # ── Pipeline endpoints ──

    @app.post("/pipeline/start", dependencies=[Depends(verify_api_key)])
    async def start_pipeline(req: PipelineStartRequest):
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
            "target_languages": ["en"],  # Lock pipeline to English output
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
                async for event in _pipeline.astream(initial_state, config):
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

    @app.get("/pipeline/{thread_id}/state", dependencies=[Depends(verify_api_key)])
    async def get_pipeline_state(thread_id: str):
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
            snapshot = _pipeline.get_state(config)
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

    @app.post("/pipeline/{thread_id}/review/{review_node}", dependencies=[Depends(verify_api_key)])
    async def submit_review(thread_id: str, review_node: str, action: ReviewAction):
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
        snapshot = _pipeline.get_state(config)

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
        _pipeline.update_state(config, {"human_reviews": current_reviews})

        # Handle reject: terminate pipeline directly, no resume needed
        if action.action == "reject":
            _pipeline.update_state(config, {"pipeline_complete": True, "current_step": "rejected"})
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
                async for event in _pipeline.astream(None, config):
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
            _pipeline.update_state(config, {"pipeline_complete": True})
            _cleanup_thread_cache(thread_id)

        return {
            "thread_id": thread_id,
            "review_node": review_node,
            "action": action.action,
            "status": "resumed",
            "events": _serialize(events),
        }

    async def _get_config_for_thread(thread_id: str) -> dict:
        """Get config for thread from memory cache or DB.

        P1-10: Memory cache is a local optimization; PG is the single source of
        truth. On cache miss, load from PG and backfill. _touch_thread_cache
        keeps recently-used entries alive across TTL sweeps.
        """
        config = _active_threads.get(thread_id)
        if config:
            _touch_thread_cache(thread_id)
            return config

        if HAS_STORAGE:
            repo = ThreadRepository()
            thread = await repo.get_by_field("thread_id", thread_id)
            if thread:
                config = {"configurable": {"thread_id": thread_id}}
                _active_threads[thread_id] = config
                _touch_thread_cache(thread_id)
                return config

        # Fallback: build a minimal config (pipeline may 404 if checkpoint missing)
        return {"configurable": {"thread_id": thread_id}}

    @app.get("/pipeline/{thread_id}/output", dependencies=[Depends(verify_api_key)])
    async def get_pipeline_output(thread_id: str):
        """Get final pipeline output as JSON."""
        config = await _get_config_for_thread(thread_id)
        snapshot = _pipeline.get_state(config)
        if snapshot is None or snapshot.values is None:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        return _serialize(snapshot.values)

    @app.get("/pipeline/{thread_id}/distribution", dependencies=[Depends(verify_api_key)])
    async def get_distribution_plans(thread_id: str):
        """Get distribution plans with platform-specific post content.

        Returns distribution_plans array, each with brief_id, script_id,
        and 4 platform posts (shopify/amazon/tiktok/reddit) containing
        CTA, video_format, product_link_placeholder, and platform-specific body.
        """
        config = await _get_config_for_thread(thread_id)
        snapshot = _pipeline.get_state(config)
        if snapshot is None or snapshot.values is None:
            raise HTTPException(status_code=404, detail="Pipeline not found")

        plans = _serialize(snapshot.values).get("distribution_plans", [])
        return {"distribution_plans": plans}

    @app.get("/pipeline/{thread_id}/export", dependencies=[Depends(verify_api_key)])
    async def export_pipeline_output(thread_id: str):
        """Clean export: only user-facing fields, no internal state.

        Strips out internal-only fields: retry_counts, self_verifications,
        rejection_feedback, pipeline_metrics, messages, errors, structured_errors.
        Returns only what matters for rendering: scripts, captions, thumbnails,
        distribution plans, analytics reports, and human review timeline.
        """
        config = await _get_config_for_thread(thread_id)
        snapshot = _pipeline.get_state(config)
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

    @app.get("/health")
    async def health():
        """Health check with persistence and Remotion status."""
        from src.tools.remotion_renderer import RemotionRenderer

        renderer = RemotionRenderer()
        remotion_env = renderer.validate_environment()

        persistence_status: dict = {"backend": "filesystem", "pg_available": False}
        if HAS_STORAGE:
            try:
                from src.storage.db import check_pg_health, is_pg_available
                persistence_status = await check_pg_health()
                persistence_status["pg_available"] = is_pg_available()
            except Exception as e:
                persistence_status["error"] = str(e)[:200]

        return {
            "status": "ok",
            "version": "0.2.0",
            "remotion": remotion_env,
            "persistence": persistence_status,
        }


    @staticmethod
    def _get_step_output(steps: dict, step_name: str) -> Any:
        """Extract output from a step's state data.

        Prefers edited_output if the step has been edited by human review.
        """
        step = steps.get(step_name, {})
        return step.get("edited_output") if step.get("edited") else step.get("output")

    @app.post("/scenario/s1", dependencies=[Depends(verify_api_key)])
    async def run_s1_product_direct(body: dict):
        """Run S1 Product Direct pipeline (auto mode via StepRunner for progress visibility).

        Uses StepRunner.init_state() + StepRunner.resume() directly so that
        pipeline state is saved after each step, enabling real-time progress
        monitoring by StageProgress polling.

        Phase 2+3: Translates Chinese product inputs to English before
        pipeline execution and forces target_languages to ``["en"]``.
        Original Chinese values are stored in ``_original_zh`` within
        the product_catalog so the frontend can display them.
        """
        from src.tools.translate import translate_catalog_to_english
        from src.pipeline.step_runner import StepRunner
        from src.pipeline.state_manager import PipelineStateManager

        product_catalog = body.get("product_catalog", {})
        product_catalog = await translate_catalog_to_english(product_catalog)

        config = {
            "product_catalog": product_catalog,
            "brand_guidelines": body.get("brand_guidelines"),
            "target_platforms": body.get("target_platforms", ["tiktok", "shopify"]),
            "target_languages": ["en"],
            "week": body.get("week", ""),
            "video_duration": body.get("video_duration", 30),
            "brand_mode": body.get("brand_mode", False),
            "enable_media_synthesis": body.get("enable_media_synthesis", True),
        }

        state_manager = PipelineStateManager()
        step_runner = StepRunner(state_manager)

        # Initialize state (saved immediately so polling can see it) and run to completion
        label = await step_runner.init_state(config=config, mode="auto")
        try:
            final_state = await step_runner.resume(label)
        except TypeError as te:
            # structlog kwarg compatibility — fall back to legacy pipeline
            import logging as _log
            _log.warning("auto pipeline: StepRunner resume failed (structlog), falling back to S1ProductDirectPipeline: %s", te)
            from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline
            p = S1ProductDirectPipeline()
            final_state = await p.run(
                product_catalog=product_catalog,
                brand_guidelines=body.get("brand_guidelines"),
                target_platforms=body.get("target_platforms", ["tiktok", "shopify"]),
                target_languages=["en"],
                week=body.get("week", ""),
                brand_mode=body.get("brand_mode", False),
                enable_media_synthesis=body.get("enable_media_synthesis", True),
                video_duration=body.get("video_duration", 30),
            )
            # S1ProductDirectPipeline returns a dict differently — extract steps from the state
            return final_state

        # Convert back to the result dict format expected by frontend
        steps = final_state.get("steps", {})
        seedance_raw = _get_step_output(steps, "seedance_clips") or {}
        seedance_output = seedance_raw if isinstance(seedance_raw, dict) else {}
        clip_paths = seedance_output.get("clip_paths", []) if isinstance(seedance_raw, dict) else (seedance_raw if isinstance(seedance_raw, list) else [])

        tts_raw = _get_step_output(steps, "tts_audio") or {}
        if isinstance(tts_raw, dict):
            audio_paths = tts_raw.get("audio_paths", [])
            lyrics_paths = tts_raw.get("lyrics_paths", [])
        else:
            audio_paths = tts_raw if isinstance(tts_raw, list) else []
            lyrics_paths = []

        result = {
            "success": True,
            "label": label,
            "scenario": final_state.get("scenario", "product_direct"),
            "video_duration": config["video_duration"],
            "errors": final_state.get("errors", []),
            "media_synthesis_errors": final_state.get("media_synthesis_errors", []),
            "briefs": _get_step_output(steps, "strategy") or [],
            "scripts": _get_step_output(steps, "scripts") or [],
            "storyboards": _get_step_output(steps, "storyboards") or [],
            "keyframe_images": _get_step_output(steps, "keyframe_images") or [],
            "video_prompts": _get_step_output(steps, "video_prompts") or [],
            "thumbnail_sets": _get_step_output(steps, "thumbnail_prompts") or [],
            "seedance_output": seedance_output,
            "clip_paths": clip_paths,
            "audio_paths": audio_paths,
            "lyrics_paths": lyrics_paths,
            "thumbnail_image_paths": _get_step_output(steps, "thumbnail_images") or [],
            "steps_completed": len(_SCENARIO_STEP_ORDER.get("s1", [])),
        }

        # Extract assemble_final output (may be tuple or dict)
        assemble = _get_step_output(steps, "assemble_final")
        if isinstance(assemble, tuple):
            result["final_video_path"] = assemble[0] if len(assemble) > 0 else ""
            result["render_json_path"] = assemble[1] if len(assemble) > 1 else ""
        elif isinstance(assemble, dict):
            result["final_video_path"] = assemble.get("video_path", "")
            result["render_json_path"] = assemble.get("render_json_path", "")
        else:
            result["final_video_path"] = ""
            result["render_json_path"] = ""

        result["audit_report"] = _get_step_output(steps, "audit") or {}
        return result

    @app.post("/scenario/s2", dependencies=[Depends(verify_api_key)])
    async def run_s2_brand_campaign(body: dict):
        """Run S2 Brand Campaign pipeline."""
        from src.pipeline.s2_brand_pipeline import S2BrandCampaignPipeline
        p = S2BrandCampaignPipeline()
        r = await p.run(
            brand_package=body.get("brand_package", {}),
            target_platforms=body.get("target_platforms", ["tiktok", "shopify"]),
            target_languages=body.get("target_languages", ["en"]),
            week=body.get("week", ""),
        )
        return r

    @app.post("/scenario/s3", dependencies=[Depends(verify_api_key)])
    async def run_s3_influencer_remix(body: dict):
        """Run S3 Influencer Remix pipeline.

        Phase 2+3: Translates Chinese product inputs to English before
        pipeline execution and forces target_languages to ``["en"]``.
        Original Chinese values are stored in ``_original_zh`` within
        the product dict so the frontend can display them.

        Request body:
            video_url: str
            product: dict (with name, usps, etc.)
            influencer_name: str (optional)
            brief_id: str (optional)
            video_duration: int (optional, default 30, valid: 15/30/45/60/90)
        """
        from src.tools.translate import translate_catalog_to_english
        from src.pipeline.s3_remix_pipeline import S3InfluencerRemixPipeline

        product = body.get("product", {})
        if isinstance(product, dict):
            product = await translate_catalog_to_english(product)
            body["product"] = product

        p = S3InfluencerRemixPipeline()
        r = await p.run(
            video_url=body.get("video_url", ""),
            product=product,
            influencer_name=body.get("influencer_name", "Influencer"),
            brief_id=body.get("brief_id", ""),
            video_duration=body.get("video_duration", 30),
        )
        return r.to_dict()

    @app.post("/scenario/s4", dependencies=[Depends(verify_api_key)])
    async def run_s4_live_shoot(body: dict):
        """Run S4 Live Shoot to Video pipeline."""
        from src.pipeline.s4_live_shoot_pipeline import S4LiveShootPipeline
        p = S4LiveShootPipeline()
        r = await p.run(
            footage_assets=body.get("footage_assets", []),
            product_info=body.get("product_info", {}),
            topic=body.get("topic", ""),
            target_platforms=body.get("target_platforms", ["tiktok"]),
        )
        return r

    @app.post("/scenario/s5", dependencies=[Depends(verify_api_key)])
    async def run_s5_brand_vlog(body: dict):
        """Run S5 Brand VLOG pipeline.

        Request body:
            brand_id: str — brand identifier (e.g. "momcozy")
            product_sku: dict — product SKU with views[] (six-view angles)
            scene_id: str — scene identifier (office/living-room/bedroom/nursery/outdoor/kitchen)
            selected_models: list[dict] — model profiles with name/role/description
            story_description: str — user's story direction (max 300 chars)
            video_duration: int — target video seconds (15/30/45/60/90)
        """
        from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline
        p = S5BrandVlogPipeline()
        r = await p.run(
            brand_id=body.get("brand_id", "momcozy"),
            product_sku=body.get("product_sku", {}),
            scene_id=body.get("scene_id", "living-room"),
            selected_models=body.get("selected_models", []),
            story_description=body.get("story_description", ""),
            video_duration=body.get("video_duration", 30),
        )
        return r

    # ── Fast Mode: direct text-to-video (no pipeline) ──

    class FastModeRequest(BaseModel):
        user_prompt: str
        duration: int = 15
        enable_tts: bool = False

    @app.post("/fast/generate", dependencies=[Depends(verify_api_key)])
    async def fast_generate(req: FastModeRequest):
        """Fast Mode: direct text-to-video generation without pipeline.

        Uses LLM to enhance user prompt, then calls Seedance directly.
        No LangGraph, no steps, no gates. Returns video + debug info.

        Request:
            user_prompt: Simple text description (any language)
            duration: 10 or 15 seconds (default 15)
            enable_tts: Whether to generate CosyVoice voiceover

        Returns:
            {
                success: bool,
                video_path: str,
                video_url: str,
                filename: str,
                llm_prompt: str,
                scene_description: str,
                duration_seconds: int,
                file_size_bytes: int,
                generation_time_ms: int,
                timing: { llm_ms, video_ms, tts_ms },
                model_info: { llm, video, tts },
                is_stub: bool,
                tts_path: str | null,
            }
        """
        from src.services.fast_mode import get_fast_mode_service

        service = get_fast_mode_service()
        try:
            result = await service.generate(
                user_prompt=req.user_prompt,
                duration=max(10, min(15, req.duration)),
                enable_tts=req.enable_tts,
            )
            return result
        except Exception as e:
            logger.error("fast_mode failed", error=str(e))
            raise HTTPException(status_code=500, detail=_safe_error(e))

    # ── S1 Pipeline Controllability (P0-1) ──

    @app.post("/scenario/s1/start", dependencies=[Depends(verify_api_key)])
    async def start_s1_pipeline(body: dict):
        """Start a new S1 pipeline run in either "auto" or "step_by_step" mode.

        Request body:
            product_catalog: dict
            brand_guidelines: dict
            target_platforms: list[str]
            target_languages: list[str]
            week: str
            video_duration: int
            mode: "auto" | "step_by_step" (default: "auto")
            brand_mode: bool (default: false)

        Returns:
            Initialized state dict with label, mode, status, and current_step.
            If mode is "auto", runs to completion and returns final state.
        """
        from src.pipeline.step_runner import StepRunner
        from src.pipeline.state_manager import PipelineStateManager

        try:
            step_runner = StepRunner(PipelineStateManager())
            mode = body.get("mode", "auto")
            label = await step_runner.init_state(config=body, mode=mode)

            if mode == "auto":
                result = await step_runner.resume(label)
                return result

            return {
                "label": label,
                "mode": mode,
                "status": "initialized",
                "current_step": None,
            }
        except Exception as e:
            import logging
            logging.error("s1 pipeline failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/s1/step/{step_name}", dependencies=[Depends(verify_api_key)])
    async def run_s1_step(step_name: str, body: dict):
        """Execute a single step of the S1 pipeline.

        Args:
            step_name: One of the valid pipeline step names.
            body: dict with "label" key.

        Returns:
            Updated pipeline state dict after executing the step.
        """
        from src.pipeline.step_runner import StepRunner
        from src.pipeline.state_manager import PipelineStateManager

        try:
            step_runner = StepRunner(PipelineStateManager())
            result = await step_runner.run_step(body["label"], step_name)
            return result
        except Exception as e:
            import logging
            logging.error("s1 step failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/s1/regenerate", dependencies=[Depends(verify_api_key)])
    async def regenerate_s1_step(body: dict):
        """Force re-execution of a specific step and invalidate all downstream.

        Request body:
            label: str — pipeline run label
            step: str — step name to regenerate

        Invalidates all downstream steps (marking them as pending) so they
        are re-executed with the updated input.

        Returns:
            Updated pipeline state dict with regenerated step done and
            downstream steps pending.
        """
        from src.pipeline.step_runner import StepRunner
        from src.pipeline.state_manager import PipelineStateManager
        from src.pipeline.step_editor import invalidate_downstream

        try:
            state_manager = PipelineStateManager()
            await invalidate_downstream(body["label"], body["step"], state_manager)
            step_runner = StepRunner(state_manager)
            result = await step_runner.regenerate_step(body["label"], body["step"])
            return result
        except Exception as e:
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/s1/resume", dependencies=[Depends(verify_api_key)])
    async def resume_s1_pipeline(body: dict):
        """Resume execution from current_step to completion.

        Request body:
            label: str — pipeline run label

        Returns:
            Final pipeline state dict.
        """
        from src.pipeline.step_runner import StepRunner
        from src.pipeline.state_manager import PipelineStateManager

        try:
            step_runner = StepRunner(PipelineStateManager())
            result = await step_runner.resume(body["label"])
            return result
        except Exception as e:
            import logging
            logging.error("s1 regenerate failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.get("/scenario/s1/state/{label}", dependencies=[Depends(verify_api_key)])
    async def get_s1_state(label: str):
        """Get the current pipeline state for a given label.

        Returns:
            Pipeline state dict, or 404 if not found.
        """
        from src.pipeline.state_manager import PipelineStateManager

        try:
            state_manager = PipelineStateManager()
            state = await state_manager.load(label)
            if state is None:
                raise HTTPException(status_code=404, detail=f"State not found for label: {label}")
            return state
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("s1 resume failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.put("/scenario/s1/state/{label}", dependencies=[Depends(verify_api_key)])
    async def update_s1_state(label: str, body: dict):
        """Update the pipeline state (used after user edits a step output).

        Request body:
            Partial or full state updates. Common use case:
            { "steps": { "scripts": { "edited_output": {...}, "edited": true } } }

        Logic:
            Loads existing state, deep-merges request body, saves back.

        Returns:
            Updated pipeline state dict.
        """
        from src.pipeline.state_manager import PipelineStateManager

        def deep_merge(base: dict, updates: dict) -> dict:
            for key, value in updates.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
            return base

        try:
            state_manager = PipelineStateManager()
            state = await state_manager.load(label)
            if state is None:
                raise HTTPException(status_code=404, detail=f"State not found for label: {label}")

            updated_state = deep_merge(state, body)
            await state_manager.save(label, updated_state)
            return updated_state
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("s1 state update failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    # ── Track 2: Step-by-Step Pipeline Control (all scenarios) ──
    # These endpoints provide fine-grained control over pipeline execution,
    # allowing users to run one step at a time, edit step outputs, and
    # regenerate specific steps with downstream invalidation.

    _SCENARIO_STEP_ORDER: dict[str, list[str]] = {
        "s1": [
            "strategy", "scripts", "compliance", "storyboards",
                "keyframe_images", "video_prompts", "thumbnail_prompts", "seedance_clips",
            "tts_audio", "thumbnail_images", "assemble_final", "audit",
        ],
    }

    def _validate_scenario(scenario: str) -> None:
        if scenario not in _SCENARIO_STEP_ORDER:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown scenario: {scenario}. Valid: {list(_SCENARIO_STEP_ORDER.keys())}",
            )

    def _get_step_deps(scenario: str, step_name: str) -> list[str]:
        """Return steps that must be completed before step_name."""
        order = _SCENARIO_STEP_ORDER[scenario]
        try:
            idx = order.index(step_name)
            return order[:idx]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown step: {step_name}")

    @app.get("/scenario/{scenario}/state/{label}/steps", dependencies=[Depends(verify_api_key)])
    async def list_steps(scenario: str, label: str):
        """List all pipeline steps with status and brief output preview.

        Args:
            scenario: Scenario identifier (e.g., "s1").
            label: Pipeline run label.

        Returns:
            Array of {step_name, status, preview, has_output, completed_at}.
        """
        from src.pipeline.state_manager import PipelineStateManager

        _validate_scenario(scenario)
        try:
            state_manager = PipelineStateManager()
            state = await state_manager.load(label)
            if state is None:
                raise HTTPException(status_code=404, detail=f"State not found for label: {label}")

            steps_data = state.get("steps", {})
            order = _SCENARIO_STEP_ORDER[scenario]
            result = []
            for step_name in order:
                sd = steps_data.get(step_name, {})
                status = sd.get("status", "pending")
                output = sd.get("output")
                edited_output = sd.get("edited_output") if sd.get("edited") else None

                # Generate a text preview from the output
                preview = ""
                display_output = edited_output if edited_output is not None else output
                if display_output:
                    if isinstance(display_output, list):
                        preview = f"[{len(display_output)} items]"
                    elif isinstance(display_output, dict):
                        if "overall_status" in display_output:
                            preview = str(display_output.get("overall_status", ""))
                        elif "summary" in display_output:
                            preview = str(display_output.get("summary", ""))[:80]
                        else:
                            preview = str(list(display_output.keys())[:3])
                    elif isinstance(display_output, str):
                        preview = display_output[:80]
                    else:
                        preview = str(display_output)[:80]

                result.append({
                    "step_name": step_name,
                    "status": status,
                    "preview": preview,
                    "has_output": output is not None,
                    "is_edited": sd.get("edited", False),
                    "completed_at": sd.get("completed_at", ""),
                })

            return {
                "label": label,
                "scenario": scenario,
                "current_step": state.get("current_step"),
                "steps": result,
            }
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("list_steps failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/{scenario}/step/{step_name}", dependencies=[Depends(verify_api_key)])
    async def execute_step(scenario: str, step_name: str, body: dict):
        """Execute a SINGLE step of the pipeline.

        If the step has already completed, returns cached result.
        If prior steps are not complete, returns 400 with listing of incomplete deps.

        Request body:
            label: str — pipeline run label

        Returns:
            { step, status, data } or error details.
        """
        from src.pipeline.state_manager import PipelineStateManager
        from src.pipeline.step_runner import StepRunner

        _validate_scenario(scenario)
        label = body.get("label", "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="Missing required field: label")

        try:
            state_manager = PipelineStateManager()
            state = await state_manager.load(label)
            if state is None:
                raise HTTPException(status_code=404, detail=f"State not found for label: {label}")

            steps_data = state.get("steps", {})
            deps = _get_step_deps(scenario, step_name)
            missing_deps: list[dict] = []
            for dep in deps:
                sd = steps_data.get(dep, {})
                if sd.get("status") != "done":
                    missing_deps.append({"step": dep, "status": sd.get("status", "pending")})

            if missing_deps:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "message": f"Cannot execute '{step_name}': prior steps not complete",
                        "missing_deps": missing_deps,
                    },
                )

            # If step already done, return cached result
            step_data = steps_data.get(step_name, {})
            if step_data.get("status") == "done":
                output = step_data.get("edited_output") if step_data.get("edited") else step_data.get("output")
                return {
                    "step": step_name,
                    "status": "completed",
                    "cached": True,
                    "data": output,
                }

            # For S1, use StepRunner; other scenarios can be extended
            if scenario == "s1":
                step_runner = StepRunner(state_manager)
                updated_state = await step_runner.run_step(label, step_name)
                updated_step = updated_state.get("steps", {}).get(step_name, {})
                output = updated_step.get("edited_output") if updated_step.get("edited") else updated_step.get("output")
                step_status = updated_step.get("status", "failed")
                return {
                    "step": step_name,
                    "status": "completed" if step_status == "done" else "failed",
                    "data": output,
                }

            raise HTTPException(status_code=501, detail=f"Step execution not implemented for scenario: {scenario}")

        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("execute_step failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.put("/scenario/{scenario}/state/{label}", dependencies=[Depends(verify_api_key)])
    async def edit_step_output(scenario: str, label: str, body: dict):
        """Update the state for a step's output (allows user editing).

        Request body:
            step_name: str — the step to update
            updates: any — the updated step output data

        Returns:
            { label, updated_step, state }.
        """
        from src.pipeline.step_editor import update_step_output

        _validate_scenario(scenario)
        step_name = body.get("step_name", "").strip()
        updates = body.get("updates")
        if not step_name:
            raise HTTPException(status_code=400, detail="Missing required field: step_name")
        if updates is None:
            raise HTTPException(status_code=400, detail="Missing required field: updates")

        try:
            result = await update_step_output(label, step_name, updates)
            return {
                "label": label,
                "updated_step": step_name,
                "state": result,
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            import logging
            logging.error("edit_step_output failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/{scenario}/regenerate/{label}/{step_name}", dependencies=[Depends(verify_api_key)])
    async def regenerate_step(scenario: str, label: str, step_name: str):
        """Re-run a specific step (e.g., after user edited its input).

        Invalidates all downstream steps by marking them as "pending"
        so they will be re-executed.

        Returns:
            { label, regenerated_step, invalidated: [...] }
        """
        from src.pipeline.state_manager import PipelineStateManager
        from src.pipeline.step_runner import StepRunner
        from src.pipeline.step_editor import invalidate_downstream

        _validate_scenario(scenario)
        try:
            state_manager = PipelineStateManager()
            state = await state_manager.load(label)
            if state is None:
                raise HTTPException(status_code=404, detail=f"State not found for label: {label}")

            order = _SCENARIO_STEP_ORDER[scenario]
            try:
                step_idx = order.index(step_name)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Unknown step: {step_name}")

            downstream = order[step_idx + 1:]

            # For S1, use StepRunner's regenerate_step
            if scenario == "s1":
                step_runner = StepRunner(state_manager)
                # invalidate_downstream marks steps as pending
                await invalidate_downstream(label, step_name, state_manager)
                # Then regenerate the specified step
                await step_runner.regenerate_step(label, step_name)
            else:
                raise HTTPException(status_code=501, detail=f"Regeneration not implemented for scenario: {scenario}")

            return {
                "label": label,
                "regenerated_step": step_name,
                "invalidated": downstream,
            }

        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("regenerate_step failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    # ── Expert Studio Gate Endpoints ──

    @app.get("/scenario/{scenario}/gate/{label}/{gate_id}", dependencies=[Depends(verify_api_key)])
    async def get_gate(scenario: str, label: str, gate_id: str):
        """Get gate state and candidates for Expert Studio approval.

        Args:
            scenario: Scenario identifier (e.g., "s1").
            label: Pipeline run label.
            gate_id: Gate identifier (e.g., "gate_1_script").

        Returns:
            Gate state dict with candidates, status, selections.
        """
        from src.pipeline.gate_manager import get_gate_state as _get_gate_state

        _validate_scenario(scenario)
        result = await _get_gate_state(label, gate_id)
        if "error" in result:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=result["error"])
        return result

    @app.post("/scenario/{scenario}/gate/{label}/{gate_id}/generate", dependencies=[Depends(verify_api_key)])
    async def generate_gate_candidates(scenario: str, label: str, gate_id: str):
        """Generate 3 candidates (standard/creative/conservative) for a gate.

        Each candidate is generated via the corresponding pipeline skill,
        scored by the AI evaluator, and ranked with a recommendation.

        Args:
            scenario: Scenario identifier (e.g., "s1").
            label: Pipeline run label.
            gate_id: Gate identifier (e.g., "gate_1_script").

        Returns:
            dict with candidates array, gate_id, label.
        """
        from src.pipeline.gate_manager import generate_candidates as _generate_candidates

        _validate_scenario(scenario)
        try:
            result = await _generate_candidates(label, gate_id)
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("generate_gate_candidates failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/{scenario}/gate/{label}/{gate_id}/approve", dependencies=[Depends(verify_api_key)])
    async def approve_gate_decision(scenario: str, label: str, gate_id: str, body: dict):
        """Approve a gate with selected candidate IDs.

        Request body:
            selected_ids: list[str] — candidate IDs the user selected.

        Records the approval, sets the selected candidate's output as the
        step output for downstream steps, and advances the pipeline.

        Args:
            scenario: Scenario identifier (e.g., "s1").
            label: Pipeline run label.
            gate_id: Gate identifier (e.g., "gate_1_script").

        Returns:
            Approval result with selected_ids and next_step.
        """
        from src.pipeline.gate_manager import approve_gate as _approve_gate

        _validate_scenario(scenario)
        selected_ids = body.get("selected_ids", [])
        if not selected_ids or not isinstance(selected_ids, list):
            raise HTTPException(status_code=400, detail="Missing or invalid required field: selected_ids (list[str])")

        try:
            result = await _approve_gate(label, gate_id, selected_ids)
            if "error" in result:
                status_code = 400
                if "already approved" in result.get("error", ""):
                    status_code = 409
                raise HTTPException(status_code=status_code, detail=result["error"])

            # Auto-resume pipeline after gate approval (step-by-step mode)
            # Resume runs from current_step until the next gate or completion.
            # Resume can take 5-30 minutes (keyframe generation + video synthesis).
            # Run in background to avoid HTTP 504 Gateway Timeout.
            async def _background_resume() -> None:
                import structlog

                log = structlog.get_logger()
                try:
                    from src.pipeline.step_runner import StepRunner
                    from src.pipeline.state_manager import PipelineStateManager

                    step_runner = StepRunner(PipelineStateManager())
                    await step_runner.resume(label)
                    log.info(
                        "background_resume_complete",
                        label=label,
                        gate_id=gate_id,
                    )
                except Exception as resume_err:
                    log.warning(
                        "background_resume_failed",
                        label=label,
                        gate_id=gate_id,
                        error=str(resume_err)[:200],
                    )
                    raise  # Re-raise so _register_background_task logs it

            task = asyncio.create_task(_background_resume())
            task_id = _register_background_task(task, label)
            result["resumed"] = True
            result["resuming"] = True
            result["background_task_id"] = task_id

            return result
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("approve_gate_decision failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/scenario/{scenario}/gate/{label}/{gate_id}/regenerate/{candidate_id}", dependencies=[Depends(verify_api_key)])
    async def regenerate_gate_candidate(scenario: str, label: str, gate_id: str, candidate_id: str):
        """Regenerate a single candidate for a gate.

        Re-executes the skill for the candidate's variant, re-scores it,
        and updates the candidate in place. Re-computes the recommendation.

        Args:
            scenario: Scenario identifier (e.g., "s1").
            label: Pipeline run label.
            gate_id: Gate identifier (e.g., "gate_1_script").
            candidate_id: The specific candidate ID to regenerate.

        Returns:
            Updated candidate dict with new data and score.
        """
        from src.pipeline.gate_manager import regenerate_candidate as _regenerate_candidate

        _validate_scenario(scenario)
        try:
            result = await _regenerate_candidate(label, gate_id, candidate_id)
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except Exception as e:
            import logging
            logging.error("regenerate_gate_candidate failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    # ── Distribution / Publish endpoints ──

    @app.post("/distribution/publish", dependencies=[Depends(verify_api_key)])
    async def distribution_publish(body: dict):
        """Publish content to a platform (TikTok or Shopify).

        Request body:
            platform: "tiktok" | "shopify"
            content: dict with platform-specific fields

        Returns:
            Publish result dict from the connector.
        """
        from src.connectors.registry import publish_to_platform

        try:
            result = await publish_to_platform(body["platform"], body["content"])
            if HAS_STORAGE:
                repo = PublishLogRepository()
                await repo.create({
                    "platform": body["platform"],
                    "post_id": result.get("post_id"),
                    "content": body["content"],
                    "status": "published" if result.get("success") else "failed",
                    "url": result.get("url"),
                    "error": result.get("error"),
                })
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=_safe_error(e))
        except Exception as e:
            import logging
            logging.error("distribution publish failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.get("/distribution/status/{platform}/{post_id}", dependencies=[Depends(verify_api_key)])
    async def distribution_status(platform: str, post_id: str):
        """Get publish status for a post on a platform.

        Returns:
            Status dict from the connector.
        """
        from src.connectors.registry import get_connector

        try:
            connector = get_connector(platform)
            result = await connector.get_status(post_id)
            return result
        except ValueError as e:
            raise HTTPException(status_code=400, detail=_safe_error(e))
        except Exception as e:
            import logging
            logging.error("distribution status failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.get("/distribution/platforms", dependencies=[Depends(verify_api_key)])
    async def distribution_platforms():
        """List available distribution platforms and their connection status.

        Returns:
            Array of platform metadata dicts.
        """
        return [
            {"id": "tiktok", "name": "TikTok", "connected": True},
            {"id": "shopify", "name": "Shopify", "connected": True},
        ]

    # ── Layer 5: Publish & Metrics endpoints ──

    @app.post("/publish/{video_id}", dependencies=[Depends(verify_api_key)])
    async def publish_video(video_id: str, body: dict):
        """Publish a video to selected platforms.

        Request body:
            platforms: ["tiktok", "shopify"]
            metadata: { hook, hashtags, product_name, ... }

        Returns:
            [{ platform, success, post_id, post_url, error }]
        """
        from src.connectors.publish_engine import PublishEngine

        platforms = body.get("platforms", [])
        metadata = body.get("metadata", {})

        if not platforms:
            raise HTTPException(status_code=400, detail="No platforms specified")

        from src.config import OUTPUT_DIR

        video_path = metadata.get("video_path", "")
        if not video_path:
            candidates = list(OUTPUT_DIR.rglob(f"{video_id}.*"))
            if candidates:
                video_path = str(candidates[0])
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Video file for '{video_id}' not found",
                )

        metadata["video_path"] = video_path

        engine = PublishEngine()
        results = await engine.publish(video_path, metadata, platforms)

        if HAS_STORAGE:
            try:
                repo = PublishLogRepository()
                for r in results:
                    await repo.create({
                        "platform": r.platform,
                        "post_id": r.post_id,
                        "content": {"video_id": video_id, "metadata": metadata},
                        "status": "published" if r.success else "failed",
                        "url": r.post_url,
                        "error": r.error,
                    })
            except Exception as exc:
                import logging
                logging.warning("Failed to log publish result: %s", exc)

        return [
            {
                "platform": r.platform,
                "success": r.success,
                "post_id": r.post_id,
                "post_url": r.post_url,
                "error": r.error,
            }
            for r in results
        ]

    @app.get("/metrics/{video_id}", dependencies=[Depends(verify_api_key)])
    async def get_video_metrics(video_id: str, platform: str = None):
        """Get metrics snapshots for a video. Optional platform filter."""
        if not HAS_STORAGE:
            raise HTTPException(status_code=503, detail="Metrics storage not available")

        try:
            repo = VideoMetricsRepository()
            rows = await repo.get_metrics(video_id, platform=platform)
            return {"video_id": video_id, "metrics": rows}
        except Exception as e:
            import logging
            logging.error("get_video_metrics failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.get("/dashboard/overview", dependencies=[Depends(verify_api_key)])
    async def get_dashboard_overview(scenario: str = None, platform: str = None, days: int = 7):
        """Get aggregated dashboard data.

        Query params:
            scenario (optional): "S1", "S2", or "S3"
            platform (optional): "tiktok" or "shopify"
            days     (optional): time window in days (default 7)
        """
        if not HAS_STORAGE:
            raise HTTPException(status_code=503, detail="Metrics storage not available")

        try:
            repo = VideoMetricsRepository()
            rows = await repo.get_dashboard_overview(
                scenario=scenario, platform=platform, days=days
            )
            return {
                "scenario": scenario,
                "platform": platform,
                "days": days,
                "data": rows,
            }
        except Exception as e:
            import logging
            logging.error("get_dashboard_overview failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    @app.post("/metrics/pull", dependencies=[Depends(verify_api_key)])
    async def trigger_metrics_pull():
        """Manually trigger metrics poll (debug endpoint)."""
        if not HAS_STORAGE:
            raise HTTPException(status_code=503, detail="Metrics storage not available")

        try:
            from src.tasks.metrics_poller import MetricsPoller
            poller = MetricsPoller()
            await poller.pull_all()
            return {"status": "ok", "message": "Metrics pull triggered successfully"}
        except ImportError:
            raise HTTPException(status_code=501, detail="MetricsPoller not yet implemented")
        except Exception as e:
            import logging
            logging.error("trigger_metrics_pull failed: %s", e)
            raise HTTPException(status_code=500, detail=_safe_error(e))

    # ── File upload ──

    try:
        from fastapi import UploadFile, File

        def _sanitize_filename(filename: str | None) -> str:
            """Sanitize and validate upload filename.

            Rejects path traversal attempts, enforces extension allowlist,
            and returns a UUID-based stored name.
            """
            if not filename:
                return "upload"
            safe = Path(filename).name
            if ".." in safe or "/" in safe or "\\" in safe or "\x00" in safe:
                raise HTTPException(status_code=400, detail="Invalid filename")
            ext = Path(safe).suffix.lower()
            allowed = {
                ".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg",
                ".webp", ".mp3", ".wav", ".m4a", ".pdf", ".txt", ".md",
            }
            if ext not in allowed:
                raise HTTPException(status_code=400, detail="File type not allowed")
            return f"{uuid.uuid4().hex}{ext}"

        MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB

        @app.post("/api/upload", dependencies=[Depends(verify_api_key)])
        async def upload_file(file: UploadFile = File(...)):
            """Upload an asset file (video, image, audio, document) to uploads dir."""
            from src.config import OUTPUT_DIR
            uploads_dir = OUTPUT_DIR / "uploads"
            uploads_dir.mkdir(parents=True, exist_ok=True)

            # Sanitize filename
            unique_name = _sanitize_filename(file.filename)
            original_name = Path(file.filename or "upload").name
            dest = uploads_dir / unique_name

            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE:
                raise HTTPException(status_code=413, detail=f"File too large. Max size: {MAX_UPLOAD_SIZE // (1024*1024)}MB")

            dest.write_bytes(content)

            rel_upload = (uploads_dir / unique_name).relative_to(OUTPUT_DIR.resolve())
            media_suffix = "/".join(quote(p, safe="") for p in rel_upload.parts)

            return {
                "filename": unique_name,
                "original_name": original_name,
                "path": f"/api/media/{media_suffix}",
                "size": len(content),
                "content_type": file.content_type,
            }
    except ImportError:
        pass  # python-multipart not installed

    # ── File listing ──

    @app.get("/api/files", dependencies=[Depends(verify_api_key)])
    async def list_files():
        """List media files under OUTPUT_DIR (recursive).

        Video/image: strictly larger than 1 MiB. Audio: any positive size (no floor).
        Documents (pdf, txt, etc.) are excluded — not treated as portfolio works.
        """
        from src.config import OUTPUT_DIR

        min_bytes = 1024 * 1024  # video / image only
        root = OUTPUT_DIR.resolve()
        files: list[dict[str, Any]] = []
        if not root.is_dir():
            return {"files": []}

        for f in root.rglob("*"):
            try:
                if not f.is_file():
                    continue
                rel = f.relative_to(root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in rel.parts):
                continue
            try:
                st = f.stat()
            except OSError:
                continue
            if st.st_size <= 0:
                continue
            ext = f.suffix.lower()
            file_type = "document"
            if ext in {".mp4", ".mov", ".webm", ".avi", ".mkv"}:
                file_type = "video"
            elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                file_type = "image"
            elif ext in {".mp3", ".wav", ".m4a", ".ogg", ".flac"}:
                file_type = "audio"
            if file_type == "document":
                continue
            if file_type != "audio" and st.st_size <= min_bytes:
                continue
            media_suffix = "/".join(quote(p, safe="") for p in rel.parts)
            path_tags = [str(p) for p in rel.parts[:-1]]
            files.append({
                "filename": f.name,
                "path": f"/api/media/{media_suffix}",
                "size": st.st_size,
                "type": file_type,
                "created": st.st_ctime,
                "tags": path_tags,
            })

        files.sort(key=lambda x: x["created"], reverse=True)
        return {"files": files}

    # ── Media serving ──

    @app.get("/api/media/{media_path:path}")
    async def serve_media(media_path: str):
        """Serve files from OUTPUT_DIR; media_path is relative to OUTPUT_DIR (posix subpaths allowed)."""
        from fastapi.responses import FileResponse
        from src.config import OUTPUT_DIR

        root = OUTPUT_DIR.resolve()
        if not media_path or media_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid path")

        rel = Path(media_path)
        if rel.is_absolute():
            raise HTTPException(status_code=400, detail="Invalid path")

        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid path")

        if not candidate.is_file():
            safe_name = rel.name
            search_roots = [
                OUTPUT_DIR,
                OUTPUT_DIR / "seedance",
                OUTPUT_DIR / "audio",
                OUTPUT_DIR / "gpt_images",
                OUTPUT_DIR / "renders",
                OUTPUT_DIR / "demo",
                OUTPUT_DIR / "uploads",
                OUTPUT_DIR / "fast_mode",
                OUTPUT_DIR / "fast_mode" / "audio",
            ]
            found: Path | None = None
            for sr in search_roots:
                cand2 = (sr / safe_name).resolve()
                try:
                    cand2.relative_to(root)
                except ValueError:
                    continue
                if cand2.is_file():
                    found = cand2
                    break
            if found is None:
                raise HTTPException(status_code=404, detail="File not found")
            candidate = found

        ext = candidate.suffix.lower()
        content_type = {
            ".mp4": "video/mp4",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".m4a": "audio/mp4",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".webm": "video/webm",
            ".pdf": "application/pdf",
        }.get(ext, "application/octet-stream")
        return FileResponse(
            str(candidate),
            media_type=content_type,
            filename=candidate.name,
        )

else:
    app = None  # type: ignore
