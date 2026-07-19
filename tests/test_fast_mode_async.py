from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import httpx
import pytest

TENANT_ID = "tenant-fast-tests"
POLICY_VERSION = "generation-safety.v1"


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
    async def test_task_lookup_is_tenant_bound_and_persists_policy_status(self):
        from src.tasks.fast_task_registry import (
            get_fast_task,
            register_fast_task,
        )

        async def _bounded() -> dict:
            return {
                "status": "completed_bounded",
                "success": False,
                "full_media_success": False,
            }

        task = asyncio.create_task(_bounded())
        tid = register_fast_task(
            task,
            tenant_id="tenant-a",
            effective_policy_version="generation-safety.v1",
        )

        assert get_fast_task(tid, tenant_id="tenant-b") is None
        running = get_fast_task(tid, tenant_id="tenant-a")
        assert running is not None
        assert running["effective_policy_version"] == "generation-safety.v1"
        assert running["result_status"] == "pending"

        await task
        await asyncio.sleep(0)

        done = get_fast_task(tid, tenant_id="tenant-a")
        assert done is not None
        assert done["result_status"] == "completed_bounded"

    @pytest.mark.asyncio
    async def test_expired_task_remains_indistinguishable_from_unknown(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ):
        from src.tasks import fast_task_registry

        async def _done() -> dict:
            return {"status": "completed_full", "success": True}

        task = asyncio.create_task(_done())
        tid = fast_task_registry.register_fast_task(
            task,
            tenant_id="tenant-a",
            effective_policy_version="generation-safety.v1",
        )
        await task
        await asyncio.sleep(0)
        done_at = fast_task_registry._fast_tasks[tid]["done_at"]
        monkeypatch.setattr(
            fast_task_registry.time,
            "time",
            lambda: done_at + fast_task_registry._RETENTION_SEC + 1,
        )

        assert fast_task_registry.get_fast_task(tid, tenant_id="tenant-a") is None
        assert fast_task_registry.get_fast_task("unknown", tenant_id="tenant-a") is None

    @pytest.mark.asyncio
    async def test_register_returns_unique_task_ids(self):
        from src.tasks.fast_task_registry import register_fast_task

        async def _noop() -> dict:
            return {"ok": True}

        t1 = asyncio.create_task(_noop())
        t2 = asyncio.create_task(_noop())
        id1 = register_fast_task(
            t1,
            tenant_id=TENANT_ID,
            effective_policy_version=POLICY_VERSION,
        )
        id2 = register_fast_task(
            t2,
            tenant_id=TENANT_ID,
            effective_policy_version=POLICY_VERSION,
        )
        assert id1 != id2
        assert id1.startswith("fast_")
        await t1
        await t2

    @pytest.mark.asyncio
    async def test_register_accepts_preallocated_task_id_and_refuses_overwrite(self):
        from src.tasks.fast_task_registry import register_fast_task

        release = asyncio.Event()

        async def _wait() -> dict:
            await release.wait()
            return {"ok": True}

        first = asyncio.create_task(_wait())
        second = asyncio.create_task(_wait())
        task_id = "fast_preallocated_fixture"

        assert (
            register_fast_task(
                first,
                task_id=task_id,
                tenant_id=TENANT_ID,
                effective_policy_version=POLICY_VERSION,
            )
            == task_id
        )
        with pytest.raises(ValueError, match="already registered"):
            register_fast_task(
                second,
                task_id=task_id,
                tenant_id=TENANT_ID,
                effective_policy_version=POLICY_VERSION,
            )

        second.cancel()
        release.set()
        await first
        with pytest.raises(asyncio.CancelledError):
            await second

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
        tid = register_fast_task(
            task,
            tenant_id=TENANT_ID,
            effective_policy_version=POLICY_VERSION,
        )

        snapshot = get_fast_task(tid, tenant_id=TENANT_ID)
        assert snapshot is not None
        assert snapshot["status"] == "running"
        assert snapshot["result"] is None

        await task
        await asyncio.sleep(0)

        snapshot = get_fast_task(tid, tenant_id=TENANT_ID)
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
        tid = register_fast_task(
            task,
            tenant_id=TENANT_ID,
            effective_policy_version=POLICY_VERSION,
        )
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)

        snapshot = get_fast_task(tid, tenant_id=TENANT_ID)
        assert snapshot["status"] == "failed"
        assert "seedance rejected" in snapshot["error"]
        assert snapshot["result"] is None

    def test_get_unknown_task_returns_none(self):
        from src.tasks.fast_task_registry import get_fast_task

        assert get_fast_task("nope_does_not_exist", tenant_id=TENANT_ID) is None

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
        tid = register_fast_task(
            task,
            tenant_id=TENANT_ID,
            effective_policy_version=POLICY_VERSION,
        )
        update_fast_task_stage(tid, "video", tenant_id=TENANT_ID)

        snapshot = get_fast_task(tid, tenant_id=TENANT_ID)
        assert snapshot["stage"] == "video"
        await task


class TestFastSubmitEndpoint:
    @pytest.mark.asyncio
    async def test_status_hides_cross_tenant_task_as_not_found(self):
        from fastapi import HTTPException

        from src.routers import _deps, scenario
        from src.routers._deps import ApiKeyType, AuthContext
        from src.tasks.fast_task_registry import register_fast_task

        async def _wait() -> dict:
            await asyncio.sleep(0.05)
            return {"status": "completed_bounded", "success": False}

        task = asyncio.create_task(_wait())
        tid = register_fast_task(
            task,
            tenant_id="tenant-a",
            effective_policy_version="generation-safety.v1",
        )
        token = _deps._auth_context_var.set(
            AuthContext(
                tenant_id="tenant-b",
                permissions=frozenset({"provider:submit"}),
                key_type=ApiKeyType.TENANT,
                key_id="tenant-b-key",
            )
        )
        try:
            with pytest.raises(HTTPException) as cross_tenant:
                await scenario.fast_status(tid)
            with pytest.raises(HTTPException) as unknown:
                await scenario.fast_status("unknown-task")

            assert cross_tenant.value.status_code == 404
            assert unknown.value.status_code == 404
            assert cross_tenant.value.detail == unknown.value.detail
        finally:
            _deps._auth_context_var.reset(token)
            await task

    @pytest.mark.asyncio
    async def test_submit_requires_api_key(self, client):
        r = await client.post(
            "/fast/submit",
            headers={"Idempotency-Key": "fast-auth-contract-0001"},
            json={"user_prompt": "test"},
        )
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
                headers={
                    **auth,
                    "Idempotency-Key": f"fast-submit-contract-{uuid.uuid4()}",
                },
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
            tid = register_fast_task(
                task,
                tenant_id=TENANT_ID,
                effective_policy_version=POLICY_VERSION,
            )
            assert get_fast_task(tid, tenant_id=TENANT_ID)["status"] == "running"
            await task
            await asyncio.sleep(0)
            return tid

        tid = asyncio.run(_drive())
        snapshot = get_fast_task(tid, tenant_id=TENANT_ID)
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
            tid = register_fast_task(
                task,
                tenant_id=TENANT_ID,
                effective_policy_version=POLICY_VERSION,
            )
            try:
                await task
            except RuntimeError:
                pass
            await asyncio.sleep(0)
            return tid

        tid = asyncio.run(_drive())
        snapshot = get_fast_task(tid, tenant_id=TENANT_ID)
        assert snapshot["status"] == "failed", f"got: {snapshot}"
        assert "seedance API timeout" in snapshot["error"]
