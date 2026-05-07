"""Cost tracking for all paid API calls.

Phase 1 (skeleton): in-memory accumulation + soft-budget warning.
Phase 2: PG persistence via alembic migration `add_api_costs_table`.

All unit costs are rough averages and will be refined with real billing data.
"""

import contextvars
import structlog
from datetime import datetime, timezone
from typing import Any

logger = structlog.get_logger()

# Per-request thread_id for pipeline-level cost aggregation.
# Set by the router on pipeline start; read automatically by track().
_thread_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "cost_thread_id", default=None
)

# Estimated unit cost (USD).  Tokens → per-token, units → per-unit.
_UNIT_COSTS: dict[str, float] = {
    "deepseek": 1.0 / 1_000_000,       # $1 per M tokens (V3)
    "deepseek_reasoning": 2.0 / 1_000_000,  # $2 per M tokens (V4-Pro)
    "poyo_image": 0.03,                # $0.03 per image
    "poyo_video": 0.3,                 # $0.30 per video
    "seedance_video": 0.3,             # $0.30 per video
    "cosyvoice": 0.02 / 60,            # $0.02 per minute of audio
}

SOFT_BUDGET_PER_PIPELINE = 5.0  # USD

_records: list[dict[str, Any]] = []


def set_thread_id(thread_id: str | None) -> None:
    """Bind a thread_id to the current request context for cost aggregation."""
    _thread_id_var.set(thread_id)


def get_thread_id() -> str | None:
    """Return the thread_id bound to the current request context."""
    return _thread_id_var.get()


def track(
    api: str,
    tokens: int | None = None,
    units: int = 1,
    thread_id: str | None = None,
) -> float:
    """Record a single API call and return estimated cost.

    Args:
        api: API identifier (must exist in _UNIT_COSTS).
        tokens: Token count for LLM calls.
        units: Unit count for media calls (images, videos, audio minutes).
        thread_id: Pipeline run identifier for aggregation.
    """
    effective_thread_id = thread_id or _thread_id_var.get()
    unit_cost = _UNIT_COSTS.get(api, 0.0)
    if tokens:
        cost = tokens * unit_cost
    else:
        cost = units * unit_cost

    record = {
        "thread_id": effective_thread_id,
        "api": api,
        "tokens": tokens,
        "units": units,
        "cost_usd": round(cost, 6),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _records.append(record)
    # P0: Prevent unbounded memory growth — cap at 10k records
    if len(_records) > 10_000:
        del _records[:-8_000]

    total = get_pipeline_cost(effective_thread_id)
    if total > SOFT_BUDGET_PER_PIPELINE:
        logger.warning(
            "cost_tracker: soft budget exceeded",
            thread_id=effective_thread_id,
            total_usd=round(total, 4),
            budget=SOFT_BUDGET_PER_PIPELINE,
            api=api,
        )
    return cost


def get_pipeline_cost(thread_id: str | None) -> float:
    """Return total estimated cost for a given pipeline run."""
    if not thread_id:
        return 0.0
    return sum(r["cost_usd"] for r in _records if r.get("thread_id") == thread_id)
