#!/usr/bin/env python3
"""
Directly overwrite routing.py and pipeline.py with the latest fixes.

Usage:
    cd ~/project/hermes_evo/AI_vedio
    python3 scripts/overwrite_fix.py
    # Then restart uvicorn
"""
import os

BASE = os.path.dirname(os.path.dirname(__file__))

ROUTING_CONTENT = '''"""Conditional routing functions for the pipeline graph.

Each function inspects state and returns the next node name.
Handles both Pydantic models and dict forms (LangGraph serializes to dicts).

Retry limit: if a node has been re-executed >= MAX_RETRIES times,
CHANGES_REQUESTED is treated as APPROVED to prevent infinite loops.
"""

from __future__ import annotations

from src.models.state import VideoPipelineState

MAX_RETRIES = 3

# -- Audit-driven decision thresholds --
# Score > AUTO_APPROVE_THRESHOLD: skip human review, auto-approve
# Score < AUTO_REJECT_THRESHOLD: shut down pipeline, auto-reject
AUTO_APPROVE_THRESHOLD = 0.90
AUTO_REJECT_THRESHOLD = 0.60


def _get_approval_status(review) -> str | None:
    """Extract approval status from either dict or Pydantic model."""
    if review is None:
        return None
    if hasattr(review, "status"):
        return review.status.value if hasattr(review.status, "value") else str(review.status)
    if isinstance(review, dict):
        return review.get("status")
    return None


def _retry_guard(state: VideoPipelineState, node_key: str) -> str | None:
    """Check if a node has exhausted retries.

    Returns the overridden status ('approved') if retries exceeded,
    None otherwise so the caller falls through to normal routing.
    """
    retry_counts = state.get("retry_counts", {})
    count = retry_counts.get(node_key, 0)
    if count >= MAX_RETRIES:
        return "approved"
    return None


def _audit_guard(state: VideoPipelineState, checkpoint_key: str) -> str | None:
    """Check audit score for automatic decisions.

    If the audit report exists and has a score:
      - score > AUTO_APPROVE_THRESHOLD: return 'approved' (skip human review)
      - score < AUTO_REJECT_THRESHOLD: return 'rejected' (shut down pipeline)

    Otherwise returns None (fall through to normal human review).
    """
    reports = state.get("audit_reports", {})
    report = reports.get(checkpoint_key)
    if report is None:
        return None

    # Handle both Pydantic model and dict form
    if hasattr(report, "overall_score"):
        score = report.overall_score
    elif isinstance(report, dict):
        score = report.get("overall_score", 0.5)
    else:
        return None

    if score > AUTO_APPROVE_THRESHOLD:
        return "approved"
    if score < AUTO_REJECT_THRESHOLD:
        return "rejected"

    # Middle ground: needs human review
    return None


def _get_compliance_status(report) -> str | None:
    """Extract compliance status from either dict or Pydantic model."""
    if report is None:
        return None
    if hasattr(report, "status"):
        return report.status.value if hasattr(report.status, "value") else str(report.status)
    if isinstance(report, dict):
        return report.get("status")
    return None


def route_after_strategy(state: VideoPipelineState) -> str:
    """After strategy produces briefs: human review FIRST, then audit.

    Priority order:
      1. Human review: explicit rejection or changes-requested overrides auto-approve
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
      4. Default: re-loop to strategy_node
    """
    # Check human review FIRST -- explicit user action overrides auto decisions
    review = state.get("human_reviews", {}).get("strategy_review")
    override = _retry_guard(state, "strategy")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "script_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "strategy_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "strategy")
    if audit_verdict == "approved":
        return "script_node"
    if audit_verdict == "rejected":
        return "__end__"

    # Middle ground: needs human review
    return "strategy_node"


def route_after_script(state: VideoPipelineState) -> str:
    """After script: human review FIRST, then audit.

    Priority order:
      1. Human review: explicit user action overrides auto decisions
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
    """
    # Check human review FIRST
    review = state.get("human_reviews", {}).get("script_review")
    override = _retry_guard(state, "script")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "compliance_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "script_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "script")
    if audit_verdict == "approved":
        return "compliance_node"
    if audit_verdict == "rejected":
        return "__end__"

    return "script_node"


def route_after_compliance(state: VideoPipelineState) -> str:
    """Check compliance results: proceed or halt."""
    reports = state.get("compliance_reports", [])
    if not reports:
        return "storyboard_node"

    blocked = any(_get_compliance_status(r) == "BLOCKED" for r in reports)
    if blocked:
        return "__end__"

    return "storyboard_node"


def route_after_asset_sourcing(state: VideoPipelineState) -> str:
    """If gaps exist -> AI generation, else skip to editing."""
    asset_plans = state.get("asset_plans", [])
    has_gaps = False
    for plan in asset_plans:
        gaps = plan.gaps if hasattr(plan, "gaps") else plan.get("gaps", [])
        if gaps:
            has_gaps = True
            break
    if has_gaps:
        return "media_generation_node"
    return "editing_node"


def route_after_editing(state: VideoPipelineState) -> str:
    """After editing: human review FIRST, then audit.

    Priority order:
      1. Human review: explicit user action overrides auto decisions
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
    """
    # Check human review FIRST
    review = state.get("human_reviews", {}).get("edit_review")
    override = _retry_guard(state, "edit")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "audio_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "editing_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "edit")
    if audit_verdict == "approved":
        return "audio_node"
    if audit_verdict == "rejected":
        return "__end__"

    return "editing_node"


def route_after_thumbnail(state: VideoPipelineState) -> str:
    """After thumbnails: human review FIRST, then audit.

    Priority order:
      1. Human review: explicit user action overrides auto decisions
      2. Retry guard: exhausted retries -> force-approve
      3. Audit-driven: high score -> auto-approve, low score -> reject, middle -> re-loop
    """
    # Check human review FIRST
    review = state.get("human_reviews", {}).get("thumbnail_review")
    override = _retry_guard(state, "thumbnail")
    user_status = override or _get_approval_status(review)
    if user_status == "approved":
        return "distribution_node"
    if user_status == "rejected":
        return "__end__"
    if user_status == "changes_requested":
        return "thumbnail_node"

    # No human review yet -- fall through to audit-driven auto decisions
    audit_verdict = _audit_guard(state, "thumbnail")
    if audit_verdict == "approved":
        return "distribution_node"
    if audit_verdict == "rejected":
        return "__end__"

    return "thumbnail_node"
'''

PIPELINE_CONTENT = '''"""LangGraph pipeline assembly -- the master orchestrator.

Builds a StateGraph with 12 worker nodes + 4 self-audit nodes
+ 4 human-in-the-loop interrupt points.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.graph.nodes import (
    analytics_node,
    asset_sourcing_node,
    audio_node,
    caption_node,
    compliance_node,
    distribution_node,
    editing_audit_node,
    editing_node,
    media_generation_node,
    script_audit_node,
    script_node,
    storyboard_node,
    strategy_audit_node,
    strategy_node,
    thumbnail_audit_node,
    thumbnail_node,
)
from src.graph.routing import (
    route_after_asset_sourcing,
    route_after_compliance,
    route_after_editing,
    route_after_script,
    route_after_strategy,
    route_after_thumbnail,
)
from src.models.state import VideoPipelineState


def build_pipeline() -> StateGraph:
    """Construct the 16-node video creation pipeline with self-audit.

    Returns a compiled StateGraph ready for invocation.
    Human review checkpoints are set via interrupt_after on audit nodes.
    """
    graph = StateGraph(VideoPipelineState)

    # -- Add all 12 production nodes --
    graph.add_node("strategy_node", strategy_node)
    graph.add_node("script_node", script_node)
    graph.add_node("compliance_node", compliance_node)
    graph.add_node("storyboard_node", storyboard_node)
    graph.add_node("asset_sourcing_node", asset_sourcing_node)
    graph.add_node("media_generation_node", media_generation_node)
    graph.add_node("editing_node", editing_node)
    graph.add_node("audio_node", audio_node)
    graph.add_node("caption_node", caption_node)
    graph.add_node("thumbnail_node", thumbnail_node)
    graph.add_node("distribution_node", distribution_node)
    graph.add_node("analytics_node", analytics_node)

    # -- Add 4 self-audit nodes --
    graph.add_node("strategy_audit_node", strategy_audit_node)
    graph.add_node("script_audit_node", script_audit_node)
    graph.add_node("editing_audit_node", editing_audit_node)
    graph.add_node("thumbnail_audit_node", thumbnail_audit_node)

    # -- Entry point --
    graph.set_entry_point("strategy_node")

    # -- Edges: Generator -> Auditor -> [Human Review] -> Next --

    # Strategy -> Strategy Audit -> [Human Review #1] -> Script
    graph.add_edge("strategy_node", "strategy_audit_node")
    graph.add_conditional_edges(
        "strategy_audit_node",
        route_after_strategy,
        {"script_node": "script_node", "strategy_node": "strategy_node", "__end__": END},
    )

    # Script -> Script Audit -> [Human Review #2] -> Compliance
    graph.add_edge("script_node", "script_audit_node")
    graph.add_conditional_edges(
        "script_audit_node",
        route_after_script,
        {"compliance_node": "compliance_node", "script_node": "script_node", "__end__": END},
    )

    # Compliance -> Storyboard (or END if BLOCKED)
    graph.add_conditional_edges(
        "compliance_node",
        route_after_compliance,
        {"storyboard_node": "storyboard_node", "__end__": END},
    )

    # Storyboard -> Asset Sourcing
    graph.add_edge("storyboard_node", "asset_sourcing_node")

    # Asset Sourcing -> AI Generation (if gaps) or Editing
    graph.add_conditional_edges(
        "asset_sourcing_node",
        route_after_asset_sourcing,
        {
            "media_generation_node": "media_generation_node",
            "editing_node": "editing_node",
        },
    )

    # AI Generation -> Editing (always proceeds after generation)
    graph.add_edge("media_generation_node", "editing_node")

    # Editing -> Edit Audit -> [Human Review #3] -> Audio
    graph.add_edge("editing_node", "editing_audit_node")
    graph.add_conditional_edges(
        "editing_audit_node",
        route_after_editing,
        {"audio_node": "audio_node", "editing_node": "editing_node", "__end__": END},
    )

    # Audio -> Caption -> Thumbnail (linear chain)
    graph.add_edge("audio_node", "caption_node")
    graph.add_edge("caption_node", "thumbnail_node")

    # Thumbnail -> Thumbnail Audit -> [Human Review #4] -> Distribution
    graph.add_edge("thumbnail_node", "thumbnail_audit_node")
    graph.add_conditional_edges(
        "thumbnail_audit_node",
        route_after_thumbnail,
        {"distribution_node": "distribution_node", "thumbnail_node": "thumbnail_node", "__end__": END},
    )

    # Distribution -> Analytics -> END
    graph.add_edge("distribution_node", "analytics_node")
    graph.add_edge("analytics_node", END)

    return graph


def compile_pipeline(checkpointer=None, db_url: str | None = None) -> CompiledStateGraph:
    """Build and compile the pipeline with optional checkpointer or PostgresSaver.

    Supports three modes:
    1. No arguments -> MemorySaver (dev/test, in-memory)
    2. db_url + psycopg connection -> PostgresSaver (production, persistent)
    3. checkpointer passed -> uses provided checkpointer (highest priority)

    PostgresSaver lifecycle note: the caller is responsible for keeping the
    psycopg connection alive. For production use, create with:
        >>> with psycopg.connect(SUPABASE_DB_URL) as conn:
        ...     saver = PostgresSaver(conn)
        ...     pipeline = compile_pipeline(checkpointer=saver)

    Registers all src.models Pydantic types with LangGraph's msgpack serializer.

    Args:
        checkpointer: LangGraph BaseCheckpointSaver (overrides db_url if set).
        db_url: PostgreSQL connection string. When set without a checkpointer,
                tries to create a PostgresSaver internally. Falls back to
                MemorySaver on connection failure.
    """
    from enum import Enum

    import structlog
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from pydantic import BaseModel

    import src.models as _m

    log = structlog.get_logger()

    # -- Register all Pydantic + Enum classes --
    _model_classes = []
    for name in dir(_m):
        obj = getattr(_m, name, None)
        if not isinstance(obj, type):
            continue
        if obj is BaseModel:
            continue
        if issubclass(obj, BaseModel):
            _model_classes.append(obj)
        elif issubclass(obj, Enum):
            _model_classes.append(obj)
    serializer = JsonPlusSerializer(allowed_msgpack_modules=_model_classes)

    # -- Determine checkpointer (priority: explicit > db_url > MemorySaver) --
    if checkpointer is None:
        if db_url:
            try:
                import psycopg
                from langgraph.checkpoint.postgres import PostgresSaver

                conn = psycopg.connect(
                    db_url,
                    autocommit=True,
                    prepare_threshold=0,
                )
                checkpointer = PostgresSaver(conn)
                checkpointer.serde = serializer
                log.info(
                    "pipeline: using PostgresSaver",
                    db_url=db_url.split("@")[-1] if "@" in db_url else "local",
                )
            except Exception as e:
                log.warning(
                    "pipeline: PostgresSaver failed, falling back to MemorySaver",
                    error=str(e),
                )
                checkpointer = MemorySaver(serde=serializer)
        else:
            checkpointer = MemorySaver(serde=serializer)

    # -- Apply serializer to user-provided checkpointer that lacks our registration --
    if checkpointer is not None and hasattr(checkpointer, "serde"):
        if checkpointer.serde is None or not getattr(checkpointer.serde, "_allowed_msgpack_modules", None):
            try:
                if hasattr(checkpointer.serde, "with_msgpack_allowlist"):
                    checkpointer.serde = checkpointer.serde.with_msgpack_allowlist(_model_classes)
            except Exception:
                pass

    graph = build_pipeline()

    # Set interrupt points on AUDIT nodes -- human sees artifact + audit report
    compiled: CompiledStateGraph = graph.compile(
        checkpointer=checkpointer,
        interrupt_after=[
            "strategy_audit_node",  # Human Review #1: calendar + strategy audit
            "script_audit_node",    # Human Review #2: scripts + script audit
            "editing_audit_node",   # Human Review #3: first cut + edit audit
            "thumbnail_audit_node", # Human Review #4: thumbnails + thumbnail audit
        ],
    )
    return compiled


def get_pipeline_history(compiled_graph, thread_id: str) -> dict:
    """Get checkpoint history for a pipeline run.

    Args:
        compiled_graph: CompiledStateGraph instance.
        thread_id: Thread ID to fetch history for.

    Returns:
        Dict with thread_id, snapshots list, and status.
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = compiled_graph.get_state(config)
        if state is None or state.values is None:
            return {"thread_id": thread_id, "snapshots": [], "status": "not_found"}
        return {
            "thread_id": thread_id,
            "snapshots": [state.values],
            "status": "interrupted" if state.next else "complete",
        }
    except Exception as e:
        return {
            "thread_id": thread_id,
            "snapshots": [],
            "status": "error",
            "detail": str(e),
        }


# -- CLI convenience --
if __name__ == "__main__":
    import json

    compiled = compile_pipeline()
    config = {"configurable": {"thread_id": "demo-001"}}

    initial = {
        "product_catalog": {"product_name": "Wearable Breast Pump", "category": "baby"},
        "brand_guidelines": {"tone": "warm", "colors": ["pink", "white"]},
        "target_platforms": ["tiktok", "youtube_shorts"],
        "target_languages": ["en"],
        "content_calendar_week": "2026-W17",
        "current_step": "init",
        "errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    print("Running pipeline...")
    for event in compiled.stream(initial, config):
        print(json.dumps({k: str(v)[:80] for k, v in event.items()}, default=str))
        if compiled.get_state(config).next:
            print(f"Interrupted at: {compiled.get_state(config).next}")
            break
    print("Done.")
'''

if __name__ == "__main__":
    routing_path = os.path.join(BASE, "src", "graph", "routing.py")
    pipeline_path = os.path.join(BASE, "src", "graph", "pipeline.py")

    with open(routing_path, "w") as f:
        f.write(ROUTING_CONTENT)
    print(f"Overwritten: {routing_path}")

    with open(pipeline_path, "w") as f:
        f.write(PIPELINE_CONTENT)
    print(f"Overwritten: {pipeline_path}")

    print()
    print("Done. Restart uvicorn to pick up changes.")
    print("  cd ~/project/hermes_evo/AI_vedio")
    print("  source .venv/bin/activate")
    print("  python3 -m uvicorn src.api:app --reload --port 8001")
