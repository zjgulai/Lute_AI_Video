"""Leak guards for the shared background task registry."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.tasks import bg_registry

REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_FILE = REPO_ROOT / "configs" / "background-task-registry-contract.yaml"
RUNBOOK_FILE = REPO_ROOT / "docs" / "runbooks" / "background-task-registry-leak.md"
DOCS_LINK_SCOPE_FILE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"


@pytest.fixture(autouse=True)
async def clear_background_tasks():
    await bg_registry.cancel_background_tasks(timeout=1.0)
    yield
    await bg_registry.cancel_background_tasks(timeout=1.0)


async def _wait_for_registry_empty(timeout_sec: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout_sec
    while bg_registry.get_background_task_snapshot():
        if asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(0)
    assert bg_registry.get_background_task_snapshot() == {}


@pytest.mark.asyncio
async def test_completed_task_is_removed_without_shutdown() -> None:
    async def completed() -> str:
        await asyncio.sleep(0)
        return "ok"

    task = asyncio.create_task(completed())
    bg_registry.register_background_task(task, "leak_completed")

    assert await task == "ok"
    await _wait_for_registry_empty()


@pytest.mark.asyncio
async def test_failed_task_is_removed_without_shutdown() -> None:
    async def failed() -> None:
        await asyncio.sleep(0)
        raise RuntimeError("boom")

    task = asyncio.create_task(failed())
    bg_registry.register_background_task(task, "leak_failed")

    with pytest.raises(RuntimeError, match="boom"):
        await task
    await _wait_for_registry_empty()


@pytest.mark.asyncio
async def test_externally_cancelled_task_is_removed_without_shutdown() -> None:
    started = asyncio.Event()

    async def sleeper() -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            pass

    task = asyncio.create_task(sleeper())
    bg_registry.register_background_task(task, "leak_cancelled")
    await started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await _wait_for_registry_empty()


def test_background_task_registry_contract_is_documented_and_link_checked() -> None:
    assert CONTRACT_FILE.is_file()
    assert RUNBOOK_FILE.is_file()

    contract: dict[str, Any] = yaml.safe_load(CONTRACT_FILE.read_text())
    assert contract["registry_module"] == "src.tasks.bg_registry"
    assert contract["register_function"] == "register_background_task"
    assert contract["shutdown_function"] == "cancel_background_tasks"
    assert contract["auto_remove_on"] == ["completed", "failed", "cancelled"]
    assert contract["snapshot_excludes_task_objects"] is True
    assert contract["no_token_boundary"] is True

    runbook = RUNBOOK_FILE.read_text()
    for token in [
        "register_background_task",
        "cancel_background_tasks",
        "tests/test_bg_registry_leak_contract.py",
        "completed",
        "failed",
        "cancelled",
    ]:
        assert token in runbook

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE_FILE.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert "docs/runbooks/background-task-registry-leak.md" in scope_targets
