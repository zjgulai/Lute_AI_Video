from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.fixture
async def client():
    from src.api import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest.fixture
def auth():
    return {"X-API-Key": os.environ["API_KEY"]}


class TestFastTaskRegistry:

    @pytest.mark.asyncio
    async def test_register_returns_unique_task_ids(self):
        from src.tasks.fast_task_registry import register_fast_task

        async def _noop() -> dict:
            return {"ok": True}

        t1 = asyncio.create_task(_noop())
        t2 = asyncio.create_task(_noop())
        id1 = register_fast_task(t1)
        id2 = register_fast_task(t2)
        assert id1 != id2
        assert id1.startswith("fast_")
        await t1
        await t2

    @pytest.mark.asyncio
    async def test_running_to_done_lifecycle(self):
        from src.tasks.fast_task_registry import (
            get_fast_task,
            register_fast_task,
        )

        async def _slow() -> dict:
            await asyncio.sleep(0.05)
            return {"video_url": "/media/foo.mp4"}

        task = asyncio.create_task(_slow())
        tid = register_fast_task(task)

        snapshot = get_fast_task(tid)
        assert snapshot is not None
        assert snapshot["status"] == "running"
        assert snapshot["result"] is None

        await task
        await asyncio.sleep(0)

        snapshot = get_fast_task(tid)
        assert snapshot["status"] == "done"
        assert snapshot["result"] == {"video_url": "/media/foo.mp4"}
        assert snapshot["error"] is None

    @pytest.mark.asyncio
    async def test_failed_task_records_error(self):
        from src.tasks.fast_task_registry import (
            get_fast_task,
            register_fast_task,
        )

        async def _crash() -> dict:
            raise RuntimeError("seedance rejected")

        task = asyncio.create_task(_crash())
        tid = register_fast_task(task)
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)

        snapshot = get_fast_task(tid)
        assert snapshot["status"] == "failed"
        assert "seedance rejected" in snapshot["error"]
        assert snapshot["result"] is None

    def test_get_unknown_task_returns_none(self):
        from src.tasks.fast_task_registry import get_fast_task

        assert get_fast_task("nope_does_not_exist") is None

    @pytest.mark.asyncio
    async def test_update_stage_visible_in_snapshot(self):
        from src.tasks.fast_task_registry import (
            get_fast_task,
            register_fast_task,
            update_fast_task_stage,
        )

        async def _wait() -> dict:
            await asyncio.sleep(0.1)
            return {}

        task = asyncio.create_task(_wait())
        tid = register_fast_task(task)
        update_fast_task_stage(tid, "video")

        snapshot = get_fast_task(tid)
        assert snapshot["stage"] == "video"
        await task


class TestFastSubmitEndpoint:

    @pytest.mark.asyncio
    async def test_submit_requires_api_key(self, client):
        r = await client.post("/fast/submit", json={"user_prompt": "test"})
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_status_404_for_unknown_task(self, client, auth):
        r = await client.get("/fast/status/unknown_task_id_xyz", headers=auth)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_submit_returns_task_id_immediately(self, client, auth):
        async def _fake_generate(*a, **kw):
            await asyncio.sleep(0.5)
            return {
                "success": True,
                "video_path": "/tmp/fake.mp4",
                "video_url": "/media/fake.mp4",
            }

        with patch("src.services.fast_mode.FastModeService.generate", new=AsyncMock(side_effect=_fake_generate)):
            r = await client.post(
                "/fast/submit",
                headers=auth,
                json={"user_prompt": "a red apple", "duration": 10, "enable_tts": False},
            )

        assert r.status_code == 200
        data = r.json()
        assert "task_id" in data
        assert data["task_id"].startswith("fast_")
        assert data["status"] == "queued"
        assert "started_at_unix" in data

    def test_status_returns_running_then_done(self):
        """Verify submit + status round-trip via direct registry manipulation.

        Note: TestClient closes its event loop after each request, which
        cancels in-flight asyncio tasks. We test the registry behavior
        directly here instead of going through the request lifecycle.
        Production uvicorn keeps the loop alive across requests.
        """
        import asyncio

        from src.tasks.fast_task_registry import (
            get_fast_task,
            register_fast_task,
        )

        async def _fake() -> dict:
            await asyncio.sleep(0.05)
            return {"success": True, "video_path": "/tmp/x.mp4"}

        async def _drive() -> str:
            task = asyncio.create_task(_fake())
            tid = register_fast_task(task)
            assert get_fast_task(tid)["status"] == "running"
            await task
            await asyncio.sleep(0)
            return tid

        tid = asyncio.run(_drive())
        snapshot = get_fast_task(tid)
        assert snapshot["status"] == "done", f"got: {snapshot}"
        assert snapshot["result"] == {"success": True, "video_path": "/tmp/x.mp4"}

    def test_status_failed_records_error(self):
        """Verify failed task records error via direct registry call.

        Same TestClient limitation as above — test registry directly.
        """
        import asyncio

        from src.tasks.fast_task_registry import (
            get_fast_task,
            register_fast_task,
        )

        async def _crash() -> dict:
            raise RuntimeError("seedance API timeout")

        async def _drive() -> str:
            task = asyncio.create_task(_crash())
            tid = register_fast_task(task)
            try:
                await task
            except RuntimeError:
                pass
            await asyncio.sleep(0)
            return tid

        tid = asyncio.run(_drive())
        snapshot = get_fast_task(tid)
        assert snapshot["status"] == "failed", f"got: {snapshot}"
        assert "seedance API timeout" in snapshot["error"]
