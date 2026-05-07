"""Background task registry — isolated module to break circular imports.

Previously lived in src/routers/_state.py, which created a cycle:
    nodes.py → _state.py → pipeline.py → nodes.py

By moving the registry here, both nodes.py and _state.py can import it
without depending on each other.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

# Global background task registry — keyed by task_id
_background_tasks: dict[str, dict[str, Any]] = {}


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
        except (asyncio.CancelledError, Exception):
            pass
        finally:
            _background_tasks.pop(task_id, None)

    task.add_done_callback(_on_done)
    return task_id
