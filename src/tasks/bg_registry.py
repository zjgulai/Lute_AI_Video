"""Background task registry — isolated module to break circular imports.

Previously lived in src/routers/_state.py, which created a cycle:
    nodes.py → _state.py → pipeline.py → nodes.py

By moving the registry here, both nodes.py and _state.py can import it
without depending on each other.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

# Global background task registry — keyed by task_id
_background_tasks: dict[str, dict[str, Any]] = {}


def _project_active_task_count() -> None:
    from src.telemetry_prometheus import update_active_background_tasks

    update_active_background_tasks(len(_background_tasks))


def get_background_task_snapshot() -> dict[str, dict[str, Any]]:
    """Return a read-only snapshot of registered task metadata."""
    snapshot: dict[str, dict[str, Any]] = {}
    for task_id, record in _background_tasks.items():
        task = record.get("task")
        snapshot[task_id] = {
            "label": record.get("label", "unknown"),
            "started_at": record.get("started_at"),
            "done": isinstance(task, asyncio.Task) and task.done(),
            "cancelled": isinstance(task, asyncio.Task) and task.cancelled(),
        }
    return snapshot


def register_background_task(task: asyncio.Task[Any], label: str) -> str:
    """Register a background task and attach completion callback.

    Args:
        task: The asyncio.Task to register.
        label: Human-readable label for the task.

    Returns:
        A unique task_id.
    """
    import structlog

    log = structlog.get_logger()
    task_id = f"{label}_{id(task)}"
    started_at = time.time()
    _background_tasks[task_id] = {"task": task, "label": label, "started_at": started_at}
    _project_active_task_count()

    def _on_done(t: asyncio.Task[Any]) -> None:
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
        except asyncio.CancelledError:
            logging.getLogger("tasks.bg_registry").debug(
                "background task callback cancelled",
                extra={"task_id": task_id, "label": label},
            )
        except Exception as exc:
            logging.getLogger("tasks.bg_registry").warning(
                "background task callback failed: %s", exc,
                extra={"task_id": task_id, "label": label},
            )
        finally:
            _background_tasks.pop(task_id, None)
            _project_active_task_count()

    task.add_done_callback(_on_done)
    return task_id


async def cancel_background_tasks(timeout: float = 5.0) -> None:
    """Cancel registered background tasks during application shutdown."""
    if not _background_tasks:
        _project_active_task_count()
        return

    log = logging.getLogger("tasks.bg_registry")
    records = list(_background_tasks.items())
    pending_tasks: list[asyncio.Task[Any]] = []

    for task_id, record in records:
        task = record.get("task")
        label = record.get("label", "unknown")
        if not isinstance(task, asyncio.Task):
            _background_tasks.pop(task_id, None)
            continue
        if task.done():
            continue
        log.info("cancelling background task", extra={"task_id": task_id, "label": label})
        task.cancel()
        pending_tasks.append(task)

    if pending_tasks:
        try:
            await asyncio.wait_for(
                asyncio.gather(*pending_tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            log.warning(
                "background task cancellation timed out",
                extra={"task_count": len(pending_tasks), "timeout": timeout},
            )

    for task_id, record in records:
        task = record.get("task")
        if not isinstance(task, asyncio.Task) or task.done():
            _background_tasks.pop(task_id, None)
    _project_active_task_count()
