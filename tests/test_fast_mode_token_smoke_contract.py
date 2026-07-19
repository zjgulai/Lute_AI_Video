from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


def _fast_policy(
    *,
    tenant_id: str = "momcozy-marketing",
    enable_media_synthesis: bool,
    disposition: str = "pending_review",
) -> dict[str, Any]:
    return {
        "version": "generation-safety.v1",
        "tenant_id": tenant_id,
        "scenario": "fast",
        "provider_submit_allowed": True,
        "enable_media_synthesis": enable_media_synthesis,
        "artifact_disposition": disposition,
        "provider_max_retries": 0,
    }


class _FakeLLM:
    def __init__(self) -> None:
        self.attempts = 0

    def _get_client(self) -> object:
        return type("Model", (), {"model_name": "fake-llm"})()

    async def invoke_json(self, **_kwargs: Any) -> dict[str, str]:
        from src.pipeline.generation_policy import get_effective_provider_max_retries

        self.attempts += 1
        assert get_effective_provider_max_retries(3) == 0
        return {
            "video_prompt": "A safe cinematic object shot with warm studio light.",
            "scene_description": "A safe object rotates in warm light.",
        }


class _NeverMediaClient:
    _is_poyo = True

    def __init__(self) -> None:
        self.attempts = 0

    async def text_to_video(self, **_kwargs: Any) -> dict[str, str]:
        self.attempts += 1
        raise AssertionError("media provider must not run")


class _NeverTTSClient:
    def __init__(self) -> None:
        self.attempts = 0

    async def synthesize(self, **_kwargs: Any) -> Path:
        self.attempts += 1
        raise AssertionError("TTS provider must not run")


@pytest.mark.asyncio
async def test_fast_mode_no_media_does_not_construct_media_clients() -> None:
    from src.services.fast_mode import FastModeService

    factory_calls = {"seedance": 0, "cosyvoice": 0}

    def seedance_factory(**_kwargs: Any) -> None:
        factory_calls["seedance"] += 1
        raise AssertionError("Seedance factory must not run for no-media")

    def cosyvoice_factory(**_kwargs: Any) -> None:
        factory_calls["cosyvoice"] += 1
        raise AssertionError("CosyVoice factory must not run for no-media")

    service = FastModeService(
        llm_client=_FakeLLM(),
        seedance_client_factory=seedance_factory,
        cosyvoice_client_factory=cosyvoice_factory,
    )
    assert not hasattr(service, "seedance")
    assert not hasattr(service, "cosyvoice")

    result = await service.generate(
        user_prompt="safe object shot",
        duration=10,
        enable_tts=True,
        artifact_disposition="pending_review",
        tenant_id="momcozy-marketing",
        provider_max_retries=0,
        enable_media_synthesis=False,
        effective_generation_policy=_fast_policy(enable_media_synthesis=False),
    )

    assert factory_calls == {"seedance": 0, "cosyvoice": 0}
    assert result["status"] == "completed_bounded"


@pytest.mark.asyncio
async def test_fast_mode_no_media_stops_before_seedance_and_tts() -> None:
    from src.services.fast_mode import FastModeService

    llm = _FakeLLM()
    seedance = _NeverMediaClient()
    cosyvoice = _NeverTTSClient()
    service = FastModeService(
        llm_client=llm,
        seedance_client=seedance,
        cosyvoice_client=cosyvoice,
    )

    result = await service.generate(
        user_prompt="safe object shot",
        duration=10,
        enable_tts=True,
        artifact_disposition="pending_review",
        tenant_id="momcozy-marketing",
        provider_max_retries=0,
        enable_media_synthesis=False,
        effective_generation_policy=_fast_policy(enable_media_synthesis=False),
    )

    assert llm.attempts == 1
    assert seedance.attempts == 0
    assert cosyvoice.attempts == 0
    assert result["status"] == "completed_bounded"
    assert result["lifecycle_status"] == "completed_bounded"
    assert result["completion_kind"] == "no_media"
    assert result["request_succeeded"] is True
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert result["pipeline_complete"] is False
    assert result["publish_allowed"] is False
    assert result["delivery_accepted"] is False
    assert result["video_path"] == ""
    assert result["video_url"] == ""
    assert result["tts_path"] is None


@pytest.mark.asyncio
async def test_fast_mode_tts_client_init_failure_stops_before_video_coroutine() -> None:
    """A companion-client init failure must not leave an unawaited video submit."""
    from src.services.fast_mode import FastModeService

    created: dict[str, Any] = {}

    class DeferredSeedance:
        _is_poyo = True

        def __init__(self, **_kwargs: Any) -> None:
            self.starts = 0
            self.closed = False
            created["seedance"] = self

        def text_to_video(self, **_kwargs: Any):
            self.starts += 1

            async def result() -> dict[str, str]:
                raise AssertionError("video provider coroutine must not be awaited")

            return result()

        async def close(self) -> None:
            self.closed = True

    def failing_tts_factory(**_kwargs: Any) -> None:
        raise RuntimeError("TTS client init failed")

    service = FastModeService(
        llm_client=_FakeLLM(),
        seedance_client_factory=DeferredSeedance,
        cosyvoice_client_factory=failing_tts_factory,
    )

    with pytest.raises(RuntimeError, match="TTS client init failed"):
        await service.generate(
            user_prompt="safe object shot",
            duration=10,
            enable_tts=True,
            artifact_disposition="pending_review",
            tenant_id="momcozy-marketing",
            artifact_run_id="fast_tts_init_failure",
            provider_max_retries=0,
            enable_media_synthesis=True,
            effective_generation_policy=_fast_policy(enable_media_synthesis=True),
        )

    assert created["seedance"].starts == 0
    assert created["seedance"].closed is True


@pytest.mark.asyncio
async def test_fast_mode_rejects_missing_effective_policy_before_any_provider() -> None:
    from src.services.fast_mode import FastModeService

    llm = _FakeLLM()
    seedance = _NeverMediaClient()
    cosyvoice = _NeverTTSClient()
    service = FastModeService(
        llm_client=llm,
        seedance_client=seedance,
        cosyvoice_client=cosyvoice,
    )

    with pytest.raises(ValueError, match="effective generation policy"):
        await service.generate(user_prompt="safe object shot")

    assert llm.attempts == 0
    assert seedance.attempts == 0
    assert cosyvoice.attempts == 0


@pytest.mark.asyncio
async def test_fast_mode_media_and_tts_paths_are_tenant_run_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.services.fast_mode as fast_mode

    monkeypatch.setattr(fast_mode, "OUTPUT_DIR", tmp_path)
    created: dict[str, Any] = {}

    class FakeSeedance:
        _is_poyo = True

        def __init__(self, *, output_dir: Path, max_retries: int) -> None:
            self.output_dir = output_dir
            self.max_retries = max_retries
            self.attempts = 0
            self.closed = False
            created["seedance"] = self

        async def text_to_video(self, **_kwargs: Any) -> dict[str, str]:
            self.attempts += 1
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / "generated.mp4"
            path.write_bytes(b"video")
            return {"local_path": str(path), "video_url": "https://provider.example/video.mp4"}

        async def close(self) -> None:
            self.closed = True

    class FakeCosyVoice:
        def __init__(self, *, output_dir: Path) -> None:
            self.output_dir = output_dir
            self.attempts = 0
            self.closed = False
            created["cosyvoice"] = self

        async def synthesize(self, **_kwargs: Any) -> Path:
            self.attempts += 1
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / "voice.mp3"
            path.write_bytes(b"audio")
            return path

        async def close(self) -> None:
            self.closed = True

    service = fast_mode.FastModeService(
        llm_client=_FakeLLM(),
        seedance_client=_NeverMediaClient(),
        cosyvoice_client=_NeverTTSClient(),
        seedance_client_factory=FakeSeedance,
        cosyvoice_client_factory=FakeCosyVoice,
    )
    result = await service.generate(
        user_prompt="safe object shot",
        duration=10,
        enable_tts=True,
        artifact_disposition="pending_review",
        tenant_id="momcozy-marketing",
        artifact_run_id="fast_123_abcd",
        provider_max_retries=0,
        enable_media_synthesis=True,
        effective_generation_policy=_fast_policy(enable_media_synthesis=True),
    )

    expected_root = tmp_path / "tenants" / "momcozy-marketing" / "pending_review" / "fast_mode" / "fast_123_abcd"
    assert created["seedance"].output_dir == expected_root
    assert created["seedance"].max_retries == 0
    assert created["cosyvoice"].output_dir == expected_root / "audio"
    assert created["seedance"].attempts == 1
    assert created["cosyvoice"].attempts == 1
    assert created["seedance"].closed is True
    assert created["cosyvoice"].closed is True
    assert (tmp_path / result["video_path"]).resolve().is_relative_to(expected_root.resolve())
    assert result["video_url"] == result["video_path"]
    assert result["tts_path"] is not None
    assert (tmp_path / result["tts_path"]).resolve().is_relative_to(expected_root.resolve())
    assert result["status"] == "completed_full"
    assert result["full_media_success"] is True


@pytest.mark.asyncio
async def test_fast_mode_cosyvoice_fallback_audio_stays_in_tenant_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.services.fast_mode as fast_mode
    from src.tools.cosyvoice_client import CosyVoiceClient

    monkeypatch.setattr(fast_mode, "OUTPUT_DIR", tmp_path)

    class FakeSeedance:
        _is_poyo = True

        def __init__(self, *, output_dir: Path, max_retries: int) -> None:
            self.output_dir = output_dir
            self.max_retries = max_retries

        async def text_to_video(self, **_kwargs: Any) -> dict[str, str]:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / "generated.mp4"
            path.write_bytes(b"video")
            return {"local_path": str(path), "video_url": "https://provider.example/video.mp4"}

        async def close(self) -> None:
            return None

    def fallback_cosyvoice_factory(*, output_dir: Path) -> CosyVoiceClient:
        client = CosyVoiceClient(api_key="", output_dir=output_dir)
        client.api_key = ""
        client._client = None

        def fake_silent_mp3(output_label: str = "tts") -> Path:
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{output_label}.mp3"
            path.write_bytes(b"fallback-audio")
            return path

        client._build_silent_mp3 = fake_silent_mp3  # type: ignore[method-assign]
        return client

    service = fast_mode.FastModeService(
        llm_client=_FakeLLM(),
        seedance_client=_NeverMediaClient(),
        cosyvoice_client=_NeverTTSClient(),
        seedance_client_factory=FakeSeedance,
        cosyvoice_client_factory=fallback_cosyvoice_factory,
    )
    result = await service.generate(
        user_prompt="safe object shot",
        duration=10,
        enable_tts=True,
        artifact_disposition="pending_review",
        tenant_id="momcozy-marketing",
        artifact_run_id="fast_fallback",
        provider_max_retries=0,
        enable_media_synthesis=True,
        effective_generation_policy=_fast_policy(enable_media_synthesis=True),
    )

    expected_audio_root = (
        tmp_path / "tenants" / "momcozy-marketing" / "pending_review" / "fast_mode" / "fast_fallback" / "audio"
    )
    assert result["tts_path"] is not None
    fallback_path = (tmp_path / result["tts_path"]).resolve()
    assert fallback_path.is_relative_to(expected_audio_root.resolve())
    assert fallback_path.name == "tts_en_fallback.mp3"
    assert result["tts_is_fallback"] is True
    assert result["tts_fallback_reason"] == "missing_api_key"
    assert result["status"] == "completed_bounded"
    assert result["completion_kind"] == "bounded_media"
    assert result["request_succeeded"] is True
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert result["pipeline_complete"] is False


@pytest.mark.asyncio
async def test_cosyvoice_metadata_marks_fallback_and_keeps_path_api_compatible(
    tmp_path: Path,
) -> None:
    from src.tools.cosyvoice_client import CosyVoiceClient

    client = CosyVoiceClient(api_key="", output_dir=tmp_path)
    client.api_key = ""
    client._client = None

    metadata = await client.synthesize_with_metadata("fallback", language="en")
    legacy_path = await client.synthesize("fallback", language="en")

    assert metadata.path == tmp_path / "tts_en_fallback.mp3"
    assert metadata.is_fallback is True
    assert metadata.reason == "missing_api_key"
    assert legacy_path == metadata.path


@pytest.mark.asyncio
async def test_fast_mode_requested_tts_failure_is_bounded_not_full_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.services.fast_mode as fast_mode

    monkeypatch.setattr(fast_mode, "OUTPUT_DIR", tmp_path)

    class FakeSeedance:
        _is_poyo = True

        def __init__(self, *, output_dir: Path, max_retries: int) -> None:
            self.output_dir = output_dir
            self.max_retries = max_retries

        async def text_to_video(self, **_kwargs: Any) -> dict[str, str]:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / "generated.mp4"
            path.write_bytes(b"video")
            return {"local_path": str(path), "video_url": "https://provider.example/video.mp4"}

        async def close(self) -> None:
            return None

    class FailingCosyVoice:
        def __init__(self, *, output_dir: Path) -> None:
            self.output_dir = output_dir

        async def synthesize(self, **_kwargs: Any) -> Path:
            raise RuntimeError("fake tts failure")

        async def close(self) -> None:
            return None

    service = fast_mode.FastModeService(
        llm_client=_FakeLLM(),
        seedance_client=_NeverMediaClient(),
        cosyvoice_client=_NeverTTSClient(),
        seedance_client_factory=FakeSeedance,
        cosyvoice_client_factory=FailingCosyVoice,
    )
    result = await service.generate(
        user_prompt="safe object shot",
        duration=10,
        enable_tts=True,
        artifact_disposition="pending_review",
        tenant_id="momcozy-marketing",
        artifact_run_id="fast_tts_failure",
        provider_max_retries=0,
        enable_media_synthesis=True,
        effective_generation_policy=_fast_policy(enable_media_synthesis=True),
    )

    assert result["status"] == "completed_bounded"
    assert result["completion_kind"] == "bounded_media"
    assert result["request_succeeded"] is True
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert result["pipeline_complete"] is False
    assert result["video_path"]
    assert result["tts_path"] is None


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
async def test_fast_mode_submit_passes_l4c1r_artifact_and_retry_controls(
    monkeypatch,
    isolated_provider_cost_db,
):
    from src.routers import _deps, scenario
    from src.routers._deps import ApiKeyType, AuthContext
    from src.services import submission_idempotency
    from src.services.submission_idempotency import SubmissionClaim

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
                "model_info": {
                    "llm": "deepseek",
                    "llm_model": "deepseek-v4-flash",
                    "video": "poyo-seedance-2",
                    "tts": None,
                },
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

        class FakeSubmissionIdempotency:
            async def claim_submission(self, **_kwargs: Any) -> SubmissionClaim:
                return SubmissionClaim(outcome="owner", record={"id": "submission-fixture"})

            async def transition(self, **kwargs: Any) -> dict[str, Any]:
                return {"id": kwargs["record_id"], "record_status": kwargs["new_status"]}

            def start_heartbeat(self, **_kwargs: Any) -> None:
                return None

            async def mark_terminal(self, **kwargs: Any) -> dict[str, Any]:
                return {"id": kwargs["record_id"], "record_status": kwargs["status"]}

            async def stop_heartbeat(self, **_kwargs: Any) -> None:
                return None

        monkeypatch.setattr(
            submission_idempotency,
            "get_submission_idempotency_service",
            lambda: FakeSubmissionIdempotency(),
        )
        with patch("src.services.fast_mode.get_fast_mode_service", return_value=FakeService()):
            response = await scenario._fast_submit_validated(
                scenario.FastModeRequest(
                    user_prompt="safe object shot",
                    duration=10,
                    enable_tts=False,
                    artifact_disposition="pending_review",
                    provider_max_retries=0,
                ),
                "fast-token-smoke-contract-0001",
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


@pytest.mark.asyncio
async def test_fast_mode_sync_generate_uses_unique_tenant_run_ids(
    isolated_provider_cost_db,
) -> None:
    from src.routers import _deps, scenario
    from src.routers._deps import ApiKeyType, AuthContext

    captured: list[str] = []

    class FakeService:
        async def generate(self, **kwargs: Any) -> dict[str, Any]:
            captured.append(kwargs["artifact_run_id"])
            return {
                "status": "completed_bounded",
                "lifecycle_status": "completed_bounded",
                "completion_kind": "no_media",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
            }

    token = _deps._auth_context_var.set(
        AuthContext(
            tenant_id="momcozy-marketing",
            permissions=frozenset({"provider:submit"}),
            key_type=ApiKeyType.TENANT,
            key_id="test-key",
        )
    )
    try:
        request = scenario.FastModeRequest(
            user_prompt="safe object shot",
            duration=10,
            enable_tts=False,
        )
        with patch("src.services.fast_mode.get_fast_mode_service", return_value=FakeService()):
            await scenario.fast_generate(request)
            await scenario.fast_generate(request)

        assert len(captured) == 2
        assert captured[0] != captured[1]
        assert all(run_id.startswith("fast_generate_") for run_id in captured)
    finally:
        _deps._auth_context_var.reset(token)
