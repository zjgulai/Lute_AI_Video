import asyncio
import threading

import pytest

from src.tasks import bg_registry


@pytest.fixture(autouse=True)
async def clear_background_tasks():
    await bg_registry.cancel_background_tasks(timeout=1.0)
    yield
    await bg_registry.cancel_background_tasks(timeout=1.0)


@pytest.mark.asyncio
async def test_cancel_background_tasks_cancels_registered_task() -> None:
    started = asyncio.Event()

    async def sleeper() -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

    task = asyncio.create_task(sleeper())
    await started.wait()

    task_id = bg_registry.register_background_task(task, "test_sleeper")
    assert task_id in bg_registry.get_background_task_snapshot()

    await bg_registry.cancel_background_tasks(timeout=1.0)

    assert task.cancelled()
    assert bg_registry.get_background_task_snapshot() == {}


@pytest.mark.asyncio
async def test_cancel_background_tasks_removes_completed_task() -> None:
    async def completed() -> str:
        return "ok"

    task = asyncio.create_task(completed())
    bg_registry.register_background_task(task, "test_completed")
    await task

    await bg_registry.cancel_background_tasks(timeout=1.0)

    assert bg_registry.get_background_task_snapshot() == {}


@pytest.mark.asyncio
async def test_fastapi_lifespan_shutdown_cancels_registered_background_task(monkeypatch) -> None:
    import src.api as api

    started = threading.Event()
    cancelled = threading.Event()

    async def fake_startup() -> None:
        async def sleeper() -> None:
            started.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancelled.set()
                raise

        bg_registry.register_background_task(
            asyncio.create_task(sleeper()),
            label="lifespan_test_sleeper",
        )
        await asyncio.sleep(0)

    monkeypatch.setattr(api, "_run_startup", fake_startup)

    async with api.app.router.lifespan_context(api.app):
        snapshot = bg_registry.get_background_task_snapshot()
        assert any(record["label"] == "lifespan_test_sleeper" for record in snapshot.values())
        assert started.is_set()

    assert cancelled.wait(timeout=1.0)
    assert bg_registry.get_background_task_snapshot() == {}
