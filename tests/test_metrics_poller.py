from __future__ import annotations

import asyncio

import pytest


class _Repo:
    async def get_active_posts(self) -> list[dict]:
        return [{"id": str(i)} for i in range(6)]


@pytest.mark.asyncio
async def test_pull_all_uses_bounded_concurrency() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    poller = MetricsPoller(max_concurrency=2)
    poller.repo = _Repo()  # type: ignore[assignment]

    active = 0
    max_active = 0

    async def fake_pull_single(post: dict) -> bool:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return True

    poller.pull_single = fake_pull_single  # type: ignore[method-assign]

    await poller.pull_all()

    assert max_active == 2


@pytest.mark.asyncio
async def test_pull_all_isolates_single_task_failure() -> None:
    from src.tasks.metrics_poller import MetricsPoller

    poller = MetricsPoller(max_concurrency=3)
    poller.repo = _Repo()  # type: ignore[assignment]
    seen: list[str] = []

    async def fake_pull_single(post: dict) -> bool:
        seen.append(post["id"])
        if post["id"] == "2":
            raise RuntimeError("platform error")
        return post["id"] != "3"

    poller.pull_single = fake_pull_single  # type: ignore[method-assign]

    await poller.pull_all()

    assert sorted(seen) == ["0", "1", "2", "3", "4", "5"]
