from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

_fast_tasks: dict[str, dict[str, Any]] = {}

_RETENTION_SEC = 600


def _gc_expired() -> None:
    now = time.time()
    expired = [
        tid
        for tid, entry in _fast_tasks.items()
        if entry.get("done_at") and (now - entry["done_at"]) > _RETENTION_SEC
    ]
    for tid in expired:
        _fast_tasks.pop(tid, None)


def register_fast_task(task: asyncio.Task[Any]) -> str:
    _gc_expired()
    task_id = f"fast_{int(time.time())}_{secrets.token_hex(4)}"
    started_at = time.time()
    _fast_tasks[task_id] = {
        "task": task,
        "started_at": started_at,
        "status": "running",
        "stage": "queued",
        "result": None,
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
            entry["error"] = str(exc)[:500]
        else:
            entry["status"] = "done"
            entry["result"] = t.result()
        entry["done_at"] = time.time()

    task.add_done_callback(_on_done)
    return task_id


def get_fast_task(task_id: str) -> dict[str, Any] | None:
    _gc_expired()
    entry = _fast_tasks.get(task_id)
    if entry is None:
        return None
    elapsed = time.time() - entry["started_at"]
    return {
        "task_id": task_id,
        "status": entry["status"],
        "stage": entry["stage"],
        "elapsed_sec": round(elapsed, 1),
        "result": entry["result"] if entry["status"] == "done" else None,
        "error": entry["error"] if entry["status"] == "failed" else None,
    }


def update_fast_task_stage(task_id: str, stage: str) -> None:
    entry = _fast_tasks.get(task_id)
    if entry is not None and entry["status"] == "running":
        entry["stage"] = stage
