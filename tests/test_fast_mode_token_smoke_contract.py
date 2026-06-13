from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def test_fast_mode_pending_review_output_dir_is_tenant_scoped(tmp_path, monkeypatch):
    import src.services.fast_mode as fast_mode

    monkeypatch.setattr(fast_mode, "OUTPUT_DIR", tmp_path)

    output_dir = fast_mode._artifact_output_dir(
        "pending_review",
        tenant_id="momcozy-marketing",
        run_id="fast_123_abcd",
    )

    assert output_dir == tmp_path / "tenants" / "momcozy-marketing" / "pending_review" / "fast_mode" / "fast_123_abcd"


def test_seedance_provider_retry_zero_means_single_attempt():
    from src.tools.seedance_client import SeedanceClient

    client = SeedanceClient(api_key="", max_retries=0)

    assert client.max_attempts == 1


def test_seedance_default_attempts_preserve_existing_retry_budget():
    from src.tools import seedance_client
    from src.tools.seedance_client import SeedanceClient

    client = SeedanceClient(api_key="")

    assert client.max_attempts == seedance_client.MAX_RETRIES


@pytest.mark.asyncio
async def test_fast_mode_submit_passes_l4c1r_artifact_and_retry_controls(monkeypatch):
    from src.routers import _deps, scenario
    from src.routers._deps import ApiKeyType, AuthContext

    token = _deps._auth_context_var.set(
        AuthContext(
            tenant_id="momcozy-marketing",
            permissions=frozenset({"all"}),
            key_type=ApiKeyType.TENANT,
            key_id="test-key",
        )
    )
    try:
        async_generate = AsyncMock(
            return_value={
                "success": True,
                "video_path": "/tmp/x.mp4",
                "video_url": "/api/media/x.mp4",
                "filename": "x.mp4",
                "llm_prompt": "prompt",
                "scene_description": "scene",
                "user_prompt": "prompt",
                "duration_seconds": 10,
                "file_size_bytes": 2_000_000,
                "generation_time_ms": 100,
                "timing": {"llm_ms": 1, "video_ms": 99, "tts_ms": 0},
                "model_info": {"llm": "deepseek", "llm_model": "deepseek-chat", "video": "poyo-seedance-2", "tts": None},
                "is_stub": False,
                "tts_path": None,
                "artifact_disposition": "pending_review",
                "artifact_review_status": "pending_review",
                "artifact_storage_scope": "tenant_pending_review",
                "artifact_run_id": "fast_123_abcd",
            }
        )

        class FakeService:
            async def generate(self, **kwargs):
                return await async_generate(**kwargs)

        with patch("src.services.fast_mode.get_fast_mode_service", return_value=FakeService()):
            response = await scenario.fast_submit(
                scenario.FastModeRequest(
                    user_prompt="safe object shot",
                    duration=10,
                    enable_tts=False,
                    artifact_disposition="pending_review",
                    provider_max_retries=0,
                )
            )

        assert response["status"] == "queued"
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert async_generate.await_count == 1
        kwargs = async_generate.await_args.kwargs
        assert kwargs["artifact_disposition"] == "pending_review"
        assert kwargs["tenant_id"] == "momcozy-marketing"
        assert kwargs["provider_max_retries"] == 0
        assert kwargs["artifact_run_id"].startswith("fast_")
    finally:
        _deps._auth_context_var.reset(token)
