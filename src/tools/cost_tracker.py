"""Cost tracking for all paid API calls.

Phase 1 (skeleton): in-memory accumulation + soft-budget warning.
Phase 2: PG persistence via alembic migration `add_api_costs_table`.

All unit costs are rough averages and will be refined with real billing data.
"""

import contextvars
from datetime import UTC, datetime
from typing import Any

import structlog

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

# Sprint 3 P3-4: hard budget for Expert mode (closes diagnostic R-COST-EXP).
# Expert mode generates 3 candidates per gate × 3 gates with regenerate
# allowed, so worst-case cost can hit $11.98/condition (per diagnostic).
# This hard cap stops runaway spend by raising BudgetExceededError before
# the next expensive step. Auto mode uses the soft warning above.
HARD_BUDGET_EXPERT_MODE = 5.0  # USD

_records: list[dict[str, Any]] = []


class BudgetExceededError(RuntimeError):
    """Raised when a pipeline thread exceeds its hard budget cap.

    Carries `thread_id`, `total_usd`, `cap_usd`, `mode` so callers (StepRunner)
    can record degraded_reason and surface the failure cleanly without
    swallowing the actionable context.
    """

    def __init__(self, thread_id: str | None, total_usd: float, cap_usd: float, mode: str):
        self.thread_id = thread_id
        self.total_usd = total_usd
        self.cap_usd = cap_usd
        self.mode = mode
        super().__init__(
            f"Budget exceeded: thread={thread_id} mode={mode} "
            f"total=${total_usd:.4f} cap=${cap_usd:.2f}"
        )


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
        "created_at": datetime.now(UTC).isoformat(),
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


def check_budget(thread_id: str | None, mode: str) -> None:
    """Sprint 3 P3-4: raise BudgetExceededError if Expert mode is over the
    hard cap.

    Auto mode and unknown modes only emit the soft-warning path (which
    already lives inside ``track``). Expert mode requires hard enforcement
    because diagnostic R-COST-EXP showed worst-case 18 Seedance calls
    reaching $11.98/condition with the soft warning being merely advisory.

    Call this BEFORE invoking the next expensive step (e.g., from
    StepRunner._execute_step right before pipeline.run_step).
    """
    if mode != "expert":
        return
    total = get_pipeline_cost(thread_id)
    if total >= HARD_BUDGET_EXPERT_MODE:
        raise BudgetExceededError(
            thread_id=thread_id,
            total_usd=total,
            cap_usd=HARD_BUDGET_EXPERT_MODE,
            mode=mode,
        )
