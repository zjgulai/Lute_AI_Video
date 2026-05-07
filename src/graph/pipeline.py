"""LangGraph pipeline assembly -- the master orchestrator.

Builds a StateGraph with 12 worker nodes + 4 self-audit nodes
+ 4 human-in-the-loop interrupt points.
"""

from __future__ import annotations

from typing import cast

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langchain_core.runnables import RunnableConfig

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
from src.telemetry import generate_trace_id, error_collector

import structlog
from src.config import DEFAULT_LANGUAGES


def _wrap_node_with_error_handling(node_func, node_name: str):
    """Wrap a LangGraph node with trace_id-aware error handling.

    P0-2: On exception, marks the pipeline as degraded via
    ``pipeline_degraded = True``. Routing functions check this flag
    and immediately terminate the pipeline (route to ``__end__``).

    Previously the wrapper returned ``_{node_name}_degraded = True``
    without terminating the pipeline, causing downstream nodes to
    execute on missing/empty data and produce meaningless output.
    """
    import functools

    @functools.wraps(node_func)
    async def wrapper(state: VideoPipelineState) -> dict:
        logger = structlog.get_logger()
        trace_id = state.get("trace_id", "unknown")

        # P0-2: If a prior node already degraded the pipeline, do not execute
        if state.get("pipeline_degraded"):
            logger.warning(
                "pipeline_node_skipped",
                trace_id=trace_id,
                node=node_name,
                reason="pipeline_already_degraded",
            )
            return {}

        try:
            return await node_func(state)
        except Exception as exc:
            error_msg = f"{node_name}: {exc}"
            logger.error(
                "pipeline_node_error",
                trace_id=trace_id,
                node=node_name,
                error=str(exc),
            )
            # T1.4: Structured error classification
            from src.tools.error_classifier import classify_error
            structured = classify_error(exc, context=node_name, node=node_name)
            structured_errors = list(state.get("structured_errors", []))
            structured_errors.append(structured.model_dump())
            # Collect structured error
            error_collector.collect(
                label=state.get("content_calendar_week", "unknown"),
                trace_id=trace_id,
                step=node_name,
                error=str(exc),
                context={"node": node_name, "trace_id": trace_id},
            )
            # P0-2: Mark pipeline degraded so routing functions terminate
            errors = list(state.get("errors", []))
            errors.append(error_msg)
            return {
                "errors": errors,
                "pipeline_degraded": True,
                "structured_errors": structured_errors,
            }

    return wrapper


def build_pipeline() -> StateGraph:
    """Construct the 16-node video creation pipeline with self-audit.

    Returns a compiled StateGraph ready for invocation.
    Human review checkpoints are set via interrupt_after on audit nodes.
    """
    graph = StateGraph(VideoPipelineState)

    # -- Wrap all nodes with trace_id-aware error handling --
    graph.add_node("strategy_node", _wrap_node_with_error_handling(strategy_node, "strategy_node"))
    graph.add_node("script_node", _wrap_node_with_error_handling(script_node, "script_node"))
    graph.add_node("compliance_node", _wrap_node_with_error_handling(compliance_node, "compliance_node"))
    graph.add_node("storyboard_node", _wrap_node_with_error_handling(storyboard_node, "storyboard_node"))
    graph.add_node("asset_sourcing_node", _wrap_node_with_error_handling(asset_sourcing_node, "asset_sourcing_node"))
    graph.add_node("media_generation_node", _wrap_node_with_error_handling(media_generation_node, "media_generation_node"))
    graph.add_node("editing_node", _wrap_node_with_error_handling(editing_node, "editing_node"))
    graph.add_node("audio_node", _wrap_node_with_error_handling(audio_node, "audio_node"))
    graph.add_node("caption_node", _wrap_node_with_error_handling(caption_node, "caption_node"))
    graph.add_node("thumbnail_node", _wrap_node_with_error_handling(thumbnail_node, "thumbnail_node"))
    graph.add_node("distribution_node", _wrap_node_with_error_handling(distribution_node, "distribution_node"))
    graph.add_node("analytics_node", _wrap_node_with_error_handling(analytics_node, "analytics_node"))

    # -- Add 4 self-audit nodes --
    graph.add_node("strategy_audit_node", _wrap_node_with_error_handling(strategy_audit_node, "strategy_audit_node"))
    graph.add_node("script_audit_node", _wrap_node_with_error_handling(script_audit_node, "script_audit_node"))
    graph.add_node("editing_audit_node", _wrap_node_with_error_handling(editing_audit_node, "editing_audit_node"))
    graph.add_node("thumbnail_audit_node", _wrap_node_with_error_handling(thumbnail_audit_node, "thumbnail_audit_node"))

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
    serializer = JsonPlusSerializer(allowed_msgpack_modules=_model_classes)  # type: ignore[call-arg]

    # -- Determine checkpointer (priority: explicit > db_url > MemorySaver) --
    if checkpointer is None:
        if db_url:
            try:
                import psycopg  # type: ignore[import-not-found]
                from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-not-found]

                from psycopg import Connection  # type: ignore[import-not-found]
                from psycopg.rows import DictRow, dict_row  # type: ignore[import-not-found]

                conn = cast(
                    Connection[DictRow],
                    psycopg.connect(
                        db_url,
                        autocommit=True,
                        prepare_threshold=0,
                        row_factory=dict_row,  # type: ignore[arg-type]
                    ),
                )
                checkpointer = PostgresSaver(conn)
                checkpointer.serde = serializer
                log.info(
                    "pipeline: using PostgresSaver",
                    db_url=db_url.split("@")[-1] if "@" in db_url else "local",
                )
            except Exception as e:  # type: ignore[misc]
                # P1-2: When db_url is explicitly provided, do NOT silently fall back
                # to MemorySaver. Production relies on persistence; a failed connection
                # means the deployment is misconfigured and should fail fast.
                log.error(
                    "pipeline: PostgresSaver connection failed and db_url was "
                    "explicitly set. Refusing to fall back to MemorySaver "
                    "(would lose all state on restart). Fix the connection or "
                    "omit db_url to use in-memory mode intentionally.",
                    error=str(e),
                )
                raise RuntimeError(
                    f"PostgreSQL connection failed ({e}). "
                    "Pipeline persistence is required in production. "
                    "Check SUPABASE_DB_URL / DATABASE_URL configuration."
                ) from e
        else:
            checkpointer = MemorySaver(serde=serializer)

    # -- Apply serializer to user-provided checkpointer that lacks our registration --
    if checkpointer is not None and hasattr(checkpointer, "serde"):
        _serde = checkpointer.serde
        if _serde is not None and not getattr(_serde, "_allowed_msgpack_modules", None):
            if isinstance(_serde, JsonPlusSerializer):
                try:
                    checkpointer.serde = _serde.with_msgpack_allowlist(_model_classes)  # type: ignore[union-attr]
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
    _history_config = cast(RunnableConfig, {"configurable": {"thread_id": thread_id}})
    try:
        state = compiled_graph.get_state(_history_config)
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
        "target_languages": DEFAULT_LANGUAGES,
        "content_calendar_week": "2026-W17",
        "current_step": "init",
        "trace_id": generate_trace_id(),
        "errors": [],
        "human_reviews": {},
        "pipeline_complete": False,
    }

    print("Running pipeline...")
    _run_config = cast(RunnableConfig, config)
    for event in compiled.stream(initial, _run_config):
        print(json.dumps({k: str(v)[:80] for k, v in event.items()}, default=str))
        if compiled.get_state(_run_config).next:
            print(f"Interrupted at: {compiled.get_state(_run_config).next}")
            break
    print("Done.")
