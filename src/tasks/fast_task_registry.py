from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from src.services.provider_execution import PersistedProviderExecutionProjection

_fast_tasks: dict[str, dict[str, Any]] = {}

_RETENTION_SEC = 600


def _gc_expired() -> None:
    now = time.time()
    expired = [
        tid for tid, entry in _fast_tasks.items() if entry.get("done_at") and (now - entry["done_at"]) > _RETENTION_SEC
    ]
    for tid in expired:
        _fast_tasks.pop(tid, None)


def _completed_result_status(result: Any) -> str:
    if isinstance(result, dict):
        status = result.get("status")
        if isinstance(status, str) and status:
            return status
        if result.get("success") is True:
            return "completed_full"
        if result.get("success") is False:
            return "error"
    return "unknown"


def register_fast_task(
    task: asyncio.Task[Any],
    *,
    task_id: str | None = None,
    tenant_id: str,
    effective_policy_version: str,
    provider_execution_projection: Mapping[str, Any] | None = None,
) -> str:
    _gc_expired()
    if not tenant_id or not effective_policy_version:
        raise ValueError("Fast task ownership and policy version are required")
    normalized_execution_projection = None
    if provider_execution_projection is not None:
        try:
            normalized_execution_projection = PersistedProviderExecutionProjection.model_validate(
                provider_execution_projection,
                strict=True,
            ).model_dump(mode="json")
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValueError("Fast task provider execution projection is invalid") from exc
    task_id = task_id or f"fast_{int(time.time())}_{secrets.token_hex(4)}"
    if task_id in _fast_tasks:
        raise ValueError(f"Fast task already registered: {task_id}")
    started_at = time.time()
    _fast_tasks[task_id] = {
        "task": task,
        "started_at": started_at,
        "status": "running",
        "stage": "queued",
        "result": None,
        "tenant_id": tenant_id,
        "effective_policy_version": effective_policy_version,
        "provider_execution_projection": normalized_execution_projection,
        "result_status": "pending",
        "error": None,
        "done_at": None,
    }

    def _on_done(t: asyncio.Task[Any]) -> None:
        entry = _fast_tasks.get(task_id)
        if entry is None:
            return
        try:
            exc = t.exception()
        except (asyncio.CancelledError, Exception) as e:
            exc = e
        if exc is not None:
            entry["status"] = "failed"
            entry["result_status"] = "failed"
            entry["error"] = str(exc)[:500]
        else:
            entry["status"] = "done"
            entry["result"] = t.result()
            entry["result_status"] = _completed_result_status(entry["result"])
        entry["done_at"] = time.time()

    task.add_done_callback(_on_done)
    return task_id


def get_fast_task_execution_projection(
    task_id: str,
    *,
    tenant_id: str,
) -> dict[str, Any] | None:
    """Return the internal safe execution reference without widening status."""

    _gc_expired()
    entry = _fast_tasks.get(task_id)
    if entry is None or entry["tenant_id"] != tenant_id:
        return None
    projection = entry.get("provider_execution_projection")
    return dict(projection) if isinstance(projection, dict) else None


def get_fast_task(task_id: str, *, tenant_id: str) -> dict[str, Any] | None:
    _gc_expired()
    entry = _fast_tasks.get(task_id)
    if entry is None or entry["tenant_id"] != tenant_id:
        return None
    elapsed = time.time() - entry["started_at"]
    return {
        "task_id": task_id,
        "status": entry["status"],
        "stage": entry["stage"],
        "elapsed_sec": round(elapsed, 1),
        "effective_policy_version": entry["effective_policy_version"],
        "result_status": entry["result_status"],
        "result": entry["result"] if entry["status"] == "done" else None,
        "error": entry["error"] if entry["status"] == "failed" else None,
    }


def update_fast_task_stage(task_id: str, stage: str, *, tenant_id: str) -> None:
    entry = _fast_tasks.get(task_id)
    if entry is not None and entry["tenant_id"] == tenant_id and entry["status"] == "running":
        entry["stage"] = stage
