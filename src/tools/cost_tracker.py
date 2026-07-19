"""Retired compatibility tombstone for the pre-ledger cost tracker.

Provider spend is authoritative only in ``ProviderCostService`` and its durable
attempt ledger.  The former process-local tracker is intentionally absent; old
imports fail closed with the same stable contract error instead of creating a
second accounting authority.
"""

from __future__ import annotations

from typing import NoReturn

from src.models.provider_cost import ProviderCostContractError

_RETIRED_SYMBOLS = frozenset(
    {
        "track",
        "check_budget",
        "set_thread_id",
        "get_thread_id",
        "get_pipeline_cost",
        "BudgetExceededError",
        "SOFT_BUDGET_PER_PIPELINE",
        "HARD_BUDGET_EXPERT_MODE",
    }
)

__all__: tuple[str, ...] = ()


def __getattr__(name: str) -> NoReturn:
    if name in _RETIRED_SYMBOLS:
        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "the process-local cost tracker was retired; use ProviderCostService",
        )
    raise AttributeError(name)
