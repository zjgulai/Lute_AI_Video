"""Task 6 SiliconFlow TTS exact UTF-8 billing and artifact-boundary contracts."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from src.models.provider_cost import ProviderCostContractError
from src.services.provider_cost import ProviderCostService
from src.services.provider_execution import (
    ProviderExecutionContext,
    ProviderExecutionService,
    _provider_execution_context_var,
    bind_provider_execution_context,
    new_trusted_regeneration_epoch,
    reset_provider_execution_context,
    with_trusted_regeneration_epoch,
)
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.storage.provider_cost_repository import ProviderCostRepository
from src.tools import cosyvoice_client as cosy_module
from src.tools.cosyvoice_client import (
    COSYVOICE_GLOBAL_ENDPOINT,
    COSYVOICE_MODEL,
    TTS_MAX_INPUT_CHARS,
    CosyVoiceClient,
    freeze_tts_input,
)

CHECKED_AT = datetime(2026, 7, 17, 9, 0, 0, tzinfo=UTC)
TENANT_ID = "tenant-provider-cost-tts"
FIXTURE_KEY = "fixture-siliconflow-key-never-sent"
CAP_USD_NANOS = 2_000_000_000


class _FakeResponse:
    def __init__(self, *, content: bytes = b"fixture-audio", error: BaseException | None = None) -> None:
        self.content = content
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error


class _FakeAsyncClient:
    instances: list[_FakeAsyncClient] = []
    next_error: BaseException | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.posts: list[dict[str, Any]] = []
        self.response = _FakeResponse(error=type(self).next_error)
        _FakeAsyncClient.instances.append(self)

    async def post(self, path: str, *, json: dict[str, Any]) -> _FakeResponse:
        self.posts.append({"path": path, "json": json})
        return self.response

    async def aclose(self) -> None:
        return None


@asynccontextmanager
async def _paid_tts_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    isolated_provider_cost_db: sqlite3.Connection,
    *,
    text: str = "Hello 界🙂e\u0301",
    voice: str = "speech:custom:voice:opaque",
) -> AsyncIterator[
    tuple[CosyVoiceClient, ProviderCostRepository, ProviderExecutionContext, str, str]
]:
    del isolated_provider_cost_db
    repository = ProviderCostRepository(require_postgres=False)
    catalog = ProviderPriceCatalog.load_default()
    execution_service = ProviderExecutionService(
        repository=repository,
        server_cap_usd_nanos=CAP_USD_NANOS,
        clock=lambda: CHECKED_AT,
    )
    context = await execution_service.initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id="tts-job-1",
        scenario_or_resource_type="fast",
        generation_policy_version="generation-safety.v2",
    )

    _FakeAsyncClient.instances.clear()
    monkeypatch.setattr(cosy_module.httpx, "AsyncClient", _FakeAsyncClient)

    def cost_service_factory(registry: Any) -> ProviderCostService:
        return ProviderCostService(
            repository=repository,
            price_catalog=catalog,
            operation_registry=registry,
            clock=lambda: CHECKED_AT,
        )

    client = CosyVoiceClient(
        api_key=FIXTURE_KEY,
        base_url=COSYVOICE_GLOBAL_ENDPOINT,
        model=COSYVOICE_MODEL,
        output_dir=tmp_path,
        price_catalog=catalog,
        cost_service_factory=cost_service_factory,
    )
    context_token = bind_provider_execution_context(context)
    try:
        yield client, repository, context, text, voice
    finally:
        await client.close()
        reset_provider_execution_context(context_token)


def _attempt_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM provider_cost_attempts ORDER BY logical_operation, ordinal, attempt_id"
    ).fetchall()


@pytest.mark.asyncio
async def test_tts_skill_uses_request_scoped_siliconflow_key_and_operation_slot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.skills import elevenlabs_tts as skill_module

    captured: dict[str, Any] = {}

    class FakeCosyVoice:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def synthesize(self, **kwargs: Any) -> Path:
            captured["synthesize"] = kwargs
            path = tmp_path / "speech.mp3"
            path.write_bytes(b"ID3" + b"0" * 300)
            return path

        async def close(self) -> None:
            captured["closed"] = True

    monkeypatch.setattr(
        skill_module,
        "get_request_api_key",
        lambda name: "request-siliconflow-key" if name == "SILICONFLOW_API_KEY" else "",
    )
    monkeypatch.setattr(cosy_module, "CosyVoiceClient", FakeCosyVoice)
    monkeypatch.setattr(skill_module.ElevenLabsTTSSkill, "_measure_duration", staticmethod(lambda _: 0.0))

    result = await skill_module.ElevenLabsTTSSkill().execute(
        {
            "text": "request scoped voice",
            "language": "en",
            "output_dir": str(tmp_path),
            "operation_instance": "script.2",
        }
    )

    assert result.success is True
    assert result.data["simulated"] is False
    assert captured["api_key"] == "request-siliconflow-key"
    assert captured["synthesize"]["operation_instance"] == "script.2"
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_tts_skill_blocks_legacy_paid_provider_before_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.skills import elevenlabs_tts as skill_module

    monkeypatch.setattr(
        skill_module,
        "get_request_api_key",
        lambda name: "legacy-key" if name == "ELEVENLABS_API_KEY" else "",
    )

    with pytest.raises(ProviderCostContractError) as exc_info:
        await skill_module.ElevenLabsTTSSkill().execute(
            {"text": "legacy must stop", "language": "en", "output_dir": str(tmp_path)}
        )

    assert exc_info.value.code == "provider_cost_legacy_path_blocked"
    assert list(tmp_path.iterdir()) == []


def test_legacy_tts_client_blocks_request_key_before_http_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import httpx

    from src.tools import elevenlabs_client as legacy_module

    constructions = 0

    def forbidden_constructor(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("legacy HTTP client must not be constructed")

    monkeypatch.setattr(
        legacy_module,
        "get_request_api_key",
        lambda name: "legacy-key" if name == "ELEVENLABS_API_KEY" else "",
    )
    monkeypatch.setattr(httpx, "AsyncClient", forbidden_constructor)

    with pytest.raises(ProviderCostContractError) as exc_info:
        legacy_module.ElevenLabsClient(output_dir=tmp_path)

    assert exc_info.value.code == "provider_cost_legacy_path_blocked"
    assert constructions == 0


@pytest.mark.asyncio
async def test_tts_skill_does_not_convert_ambiguous_cost_error_to_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.skills import elevenlabs_tts as skill_module

    class AmbiguousCosyVoice:
        def __init__(self, **_: Any) -> None:
            return None

        async def synthesize(self, **_: Any) -> Path:
            raise ProviderCostContractError(
                "provider_cost_outcome_ambiguous",
                "fixture acknowledgement is uncertain",
            )

        async def close(self) -> None:
            raise RuntimeError("fixture close failure")

    monkeypatch.setattr(
        skill_module,
        "get_request_api_key",
        lambda name: "request-siliconflow-key" if name == "SILICONFLOW_API_KEY" else "",
    )
    monkeypatch.setattr(cosy_module, "CosyVoiceClient", AmbiguousCosyVoice)

    with pytest.raises(ProviderCostContractError) as exc_info:
        await skill_module.ElevenLabsTTSSkill().safe_execute(
            {"text": "ambiguous provider", "language": "en", "output_dir": str(tmp_path)}
        )

    assert exc_info.value.code == "provider_cost_outcome_ambiguous"
    assert not list(tmp_path.glob("fallback_tts_*.mp3"))


@pytest.mark.asyncio
async def test_tts_skill_success_survives_client_close_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.skills import elevenlabs_tts as skill_module

    class SuccessfulCosyVoice:
        def __init__(self, **_: Any) -> None:
            return None

        async def synthesize(self, **_: Any) -> Path:
            path = tmp_path / "success.mp3"
            path.write_bytes(b"ID3" + b"0" * 300)
            return path

        async def close(self) -> None:
            raise RuntimeError("fixture close failure")

    monkeypatch.setattr(
        skill_module,
        "get_request_api_key",
        lambda name: "request-siliconflow-key" if name == "SILICONFLOW_API_KEY" else "",
    )
    monkeypatch.setattr(cosy_module, "CosyVoiceClient", SuccessfulCosyVoice)
    monkeypatch.setattr(skill_module.ElevenLabsTTSSkill, "_measure_duration", staticmethod(lambda _: 0.0))

    result = await skill_module.ElevenLabsTTSSkill().safe_execute(
        {"text": "close failure must not erase success", "language": "en", "output_dir": str(tmp_path)}
    )

    assert result.success is True
    assert result.data["audio_path"] == str(tmp_path / "success.mp3")
    assert result.data["simulated"] is False


def test_s1_s3_s4_tts_callers_use_server_owned_operation_slots() -> None:
    expected = {
        "src/pipeline/s1_product_pipeline.py": '"operation_instance": f"script.{script_index}"',
        "src/pipeline/s3_remix_pipeline.py": '"operation_instance": f"segment.{i}"',
        "src/pipeline/s4_live_shoot_pipeline.py": '"operation_instance": f"script.{script_index}"',
    }
    for relative_path, marker in expected.items():
        source = Path(relative_path).read_text(encoding="utf-8")
        assert marker in source
        assert '"operation_instance": script.get' not in source


def test_paid_tts_logs_use_stable_facts_only() -> None:
    fast_source = Path("src/services/fast_mode.py").read_text(encoding="utf-8")
    skill_source = Path("src/skills/elevenlabs_tts.py").read_text(encoding="utf-8")
    s1_source = Path("src/pipeline/s1_product_pipeline.py").read_text(encoding="utf-8")

    assert "error=str(" not in fast_source
    assert "path=str(" not in fast_source
    assert "error=str(" not in skill_source
    assert "text_preview=" not in s1_source


@pytest.mark.asyncio
async def test_s5_tts_consumes_skill_singular_audio_path(
    tmp_path: Path,
) -> None:
    from src.pipeline.s5_brand_vlog_pipeline import S5BrandVlogPipeline

    captured: dict[str, Any] = {}

    class FakeRegistry:
        async def execute(self, skill_name: str, params: dict[str, Any]) -> SimpleNamespace:
            captured["skill_name"] = skill_name
            captured["params"] = params
            return SimpleNamespace(
                success=True,
                data={
                    "audio_path": str(tmp_path / "vlog.mp3"),
                    "simulated": False,
                },
                error=None,
            )

    errors: list[str] = []
    result = await S5BrandVlogPipeline()._step_tts_audio(
        FakeRegistry(),
        [{"segments": [{"voiceover": "vlog voiceover"}]}],
        errors,
    )

    assert result == {
        "audio_paths": [str(tmp_path / "vlog.mp3")],
        "simulated": False,
    }
    assert captured["params"]["operation_instance"] == "vlog.primary"
    assert errors == []


def test_freeze_tts_input_uses_exact_utf8_bytes_and_digest_without_text_storage() -> None:
    cases = {
        "ASCII": ("abc", 3),
        "CJK": ("界", 3),
        "emoji": ("🙂", 4),
        "combining": ("e\u0301", 3),
    }
    for _, (text, expected_bytes) in cases.items():
        frozen = freeze_tts_input(text)
        assert frozen.text == text
        assert frozen.input_utf8_bytes == expected_bytes
        assert len(frozen.input_sha256) == 64
        assert text not in frozen.input_sha256

    with pytest.raises(ProviderCostContractError) as empty:
        freeze_tts_input("")
    assert empty.value.code == "provider_cost_usage_invalid"

    with pytest.raises(ProviderCostContractError) as surrogate:
        freeze_tts_input("bad\ud800")
    assert surrogate.value.code == "provider_cost_usage_invalid"

    with pytest.raises(ProviderCostContractError) as oversize:
        freeze_tts_input("x" * (TTS_MAX_INPUT_CHARS + 1))
    assert oversize.value.code == "provider_cost_usage_invalid"


@pytest.mark.parametrize(
    ("base_url", "model", "region"),
    [
        ("https://api.siliconflow.cn/v1", COSYVOICE_MODEL, "siliconflow_global_usd"),
        ("https://fixture.invalid/v1", COSYVOICE_MODEL, "siliconflow_global_usd"),
        (COSYVOICE_GLOBAL_ENDPOINT, "FunAudioLLM/other", "siliconflow_global_usd"),
        (COSYVOICE_GLOBAL_ENDPOINT, COSYVOICE_MODEL, "siliconflow_unknown"),
    ],
)
def test_exact_model_endpoint_region_fail_before_http_client_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    base_url: str,
    model: str,
    region: str,
) -> None:
    constructions = 0

    def forbidden_constructor(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("HTTP client must be lazy and exact-config guarded")

    monkeypatch.setattr(cosy_module.httpx, "AsyncClient", forbidden_constructor)
    with pytest.raises(ProviderCostContractError) as exc_info:
        CosyVoiceClient(
            api_key=FIXTURE_KEY,
            base_url=base_url,
            model=model,
            provider_billing_region=region,
            output_dir=tmp_path,
        )
    assert exc_info.value.code == "provider_cost_rule_unavailable"
    assert constructions == 0


@pytest.mark.asyncio
async def test_missing_key_is_explicit_zero_attempt_fallback(
    isolated_provider_cost_db: sqlite3.Connection,
    tmp_path: Path,
) -> None:
    client = CosyVoiceClient(
        api_key="",
        base_url=COSYVOICE_GLOBAL_ENDPOINT,
        model=COSYVOICE_MODEL,
        output_dir=tmp_path,
    )
    result = await client.synthesize_with_metadata("local fallback")
    assert result.is_fallback is True
    assert result.reason == "missing_api_key"
    assert _attempt_rows(isolated_provider_cost_db) == []
    await client.close()


@pytest.mark.asyncio
async def test_exact_bytes_reserve_start_one_post_settle_before_artifact_probe(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _paid_tts_scope(monkeypatch, tmp_path, isolated_provider_cost_db) as (
        client,
        repository,
        context,
        text,
        voice,
    ):
        probe_states: list[str] = []

        def probe(path: Path, response_format: str) -> dict[str, Any]:
            del response_format
            row = _attempt_rows(isolated_provider_cost_db)[0]
            probe_states.append(str(row["state"]))
            assert path.is_file()
            assert path.stat().st_size == len(b"fixture-audio")
            return {"format": "mp3", "duration_ms": 1_000, "size_bytes": path.stat().st_size}

        monkeypatch.setattr(client, "_probe_audio_artifact", probe)
        result = await client.synthesize_with_metadata(
            text,
            voice=voice,
            response_format="mp3",
            speed=1.0,
        )

        frozen = freeze_tts_input(text)
        assert result.is_fallback is False
        assert result.input_utf8_bytes == frozen.input_utf8_bytes
        assert result.attempt_id
        assert probe_states == ["settled"]
        assert len(_FakeAsyncClient.instances) == 1
        posts = _FakeAsyncClient.instances[0].posts
        assert len(posts) == 1
        assert posts[0]["path"] == "/audio/speech"
        assert posts[0]["json"] == {
            "model": COSYVOICE_MODEL,
            "input": text,
            "voice": voice,
            "response_format": "mp3",
            "speed": 1.0,
        }

        row = _attempt_rows(isolated_provider_cost_db)[0]
        assert row["state"] == "settled"
        assert row["settled_usd_nanos"] == frozen.input_utf8_bytes * 7_150
        assert row["settlement_billing_facts"]
        assert str(frozen.text) not in str(row["attempt_fingerprint"])
        assert str(frozen.text) not in str(row["reservation_billing_facts"])
        assert str(frozen.text) not in str(row["settlement_billing_facts"])
        assert context.account_id == row["account_id"]
        assert result.path.exists()
        del repository


@pytest.mark.asyncio
async def test_artifact_failure_after_provider_success_keeps_cost_settled(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _paid_tts_scope(monkeypatch, tmp_path, isolated_provider_cost_db) as (client, *_):
        def failing_probe(_: Path, __: str) -> dict[str, Any]:
            raise RuntimeError("fixture probe failure")

        monkeypatch.setattr(client, "_probe_audio_artifact", failing_probe)
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.synthesize_with_metadata("artifact failure")

    assert exc_info.value.code == "provider_cost_artifact_failed"
    assert _attempt_rows(isolated_provider_cost_db)[0]["state"] == "settled"
    assert not list(tmp_path.glob("*fallback*"))


@pytest.mark.asyncio
async def test_timeout_is_ambiguous_and_never_silent_fallback(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _FakeAsyncClient.next_error = httpx.ReadTimeout("fixture timeout")
    try:
        async with _paid_tts_scope(monkeypatch, tmp_path, isolated_provider_cost_db) as (client, *_):
            with pytest.raises(ProviderCostContractError) as exc_info:
                await client.synthesize_with_metadata("provider timeout")
            with pytest.raises(ProviderCostContractError) as replay_exc:
                await client.synthesize_with_metadata("provider timeout")
    finally:
        _FakeAsyncClient.next_error = None

    assert exc_info.value.code == "provider_cost_outcome_ambiguous"
    assert replay_exc.value.code == "provider_cost_outcome_ambiguous"
    assert _attempt_rows(isolated_provider_cost_db)[0]["state"] == "ambiguous"
    assert len(_FakeAsyncClient.instances[0].posts) == 1
    assert not list(tmp_path.glob("*fallback*"))


@pytest.mark.asyncio
async def test_provider_rejection_after_post_is_ambiguous_and_single_attempt(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = httpx.Request("POST", f"{COSYVOICE_GLOBAL_ENDPOINT}/audio/speech")
    response = httpx.Response(400, request=request)
    _FakeAsyncClient.next_error = httpx.HTTPStatusError(
        "fixture provider rejection",
        request=request,
        response=response,
    )
    try:
        async with _paid_tts_scope(
            monkeypatch, tmp_path, isolated_provider_cost_db
        ) as (client, *_):
            with pytest.raises(ProviderCostContractError) as exc_info:
                await client.synthesize_with_metadata("provider rejection")
            with pytest.raises(ProviderCostContractError) as replay_exc:
                await client.synthesize_with_metadata("provider rejection")
    finally:
        _FakeAsyncClient.next_error = None

    assert exc_info.value.code == "provider_cost_outcome_ambiguous"
    assert replay_exc.value.code == "provider_cost_outcome_ambiguous"
    assert _attempt_rows(isolated_provider_cost_db)[0]["state"] == "ambiguous"
    assert len(_FakeAsyncClient.instances[0].posts) == 1
    assert not list(tmp_path.glob("*fallback*"))


@pytest.mark.asyncio
async def test_missing_context_with_key_blocks_before_http_client_and_attempt(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    constructions = 0

    def forbidden_constructor(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("HTTP client must not be constructed")

    monkeypatch.setattr(cosy_module.httpx, "AsyncClient", forbidden_constructor)
    client = CosyVoiceClient(
        api_key=FIXTURE_KEY,
        base_url=COSYVOICE_GLOBAL_ENDPOINT,
        model=COSYVOICE_MODEL,
        output_dir=tmp_path,
    )
    context_token = _provider_execution_context_var.set(None)
    try:
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.synthesize_with_metadata("missing context")
    finally:
        _provider_execution_context_var.reset(context_token)
        await client.close()

    assert exc_info.value.code == "provider_execution_context_missing"
    assert constructions == 0
    assert _attempt_rows(isolated_provider_cost_db) == []


@pytest.mark.asyncio
async def test_valid_voice_is_not_a_catalog_dimension(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _paid_tts_scope(monkeypatch, tmp_path, isolated_provider_cost_db) as (client, *_):
        monkeypatch.setattr(
            client,
            "_probe_audio_artifact",
            lambda path, response_format: {
                "format": response_format,
                "duration_ms": 1,
                "size_bytes": path.stat().st_size,
            },
        )
        await client.synthesize_with_metadata(
            "voice compatibility",
            voice="speech:owner:custom-voice:opaque",
        )

    assert _FakeAsyncClient.instances[0].posts[0]["json"]["voice"].startswith("speech:")
    assert _attempt_rows(isolated_provider_cost_db)[0]["state"] == "settled"


@pytest.mark.asyncio
async def test_language_is_bounded_and_paid_operation_instance_is_ledger_scoped(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _paid_tts_scope(monkeypatch, tmp_path, isolated_provider_cost_db) as (client, *_):
        monkeypatch.setattr(
            client,
            "_probe_audio_artifact",
            lambda path, response_format: {
                "format": response_format,
                "duration_ms": 1,
                "size_bytes": path.stat().st_size,
            },
        )
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.synthesize_with_metadata("unsafe language", language="../audio")
        assert exc_info.value.code == "provider_cost_usage_invalid"
        assert _attempt_rows(isolated_provider_cost_db) == []

        await client.synthesize_script(
            [
                {"text": "segment one", "start_time": 0.0, "end_time": 1.0},
                {"text": "segment two", "start_time": 1.0, "end_time": 2.0},
            ]
        )

    rows = _attempt_rows(isolated_provider_cost_db)
    assert len(rows) == 2
    assert {row["logical_operation"] for row in rows} == {
        "tts.cosyvoice.speech.segment.0",
        "tts.cosyvoice.speech.segment.1",
    }


@pytest.mark.asyncio
async def test_regeneration_epoch_changes_fingerprint_and_allocates_one_new_attempt(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    async with _paid_tts_scope(monkeypatch, tmp_path, isolated_provider_cost_db) as (
        client,
        _repository,
        context,
        _text,
        _voice,
    ):
        monkeypatch.setattr(
            client,
            "_probe_audio_artifact",
            lambda path, response_format: {
                "format": response_format,
                "duration_ms": 1,
                "size_bytes": path.stat().st_size,
            },
        )
        await client.synthesize_with_metadata("same input")
        regenerated = with_trusted_regeneration_epoch(
            context,
            new_trusted_regeneration_epoch("tts.regenerate"),
        )
        token = bind_provider_execution_context(regenerated)
        try:
            await client.synthesize_with_metadata("same input")
        finally:
            reset_provider_execution_context(token)

    rows = _attempt_rows(isolated_provider_cost_db)
    assert len(rows) == 2
    assert rows[0]["attempt_fingerprint"] != rows[1]["attempt_fingerprint"]
    assert rows[0]["regeneration_epoch_ref"] is None
    assert rows[1]["regeneration_epoch_ref"]
