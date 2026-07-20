"""Task 7 PoYo GPT Image 2 / Seedance 2 durable async accounting contracts."""

from __future__ import annotations

import base64
import json
import sqlite3
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.models.provider_cost import ProviderCostContractError
from src.services.provider_cost import ProviderCostService
from src.services.provider_execution import (
    ProviderExecutionService,
    bind_provider_execution_context,
    reset_provider_execution_context,
)
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.storage.provider_cost_repository import ProviderCostRepository

CHECKED_AT = datetime(2026, 7, 18, 10, 0, 0, tzinfo=UTC)
POYO_KEY = "fixture-poyo-key-never-sent"
TENANT = "tenant-poyo-task7"
_FIXTURE_PNG = b"\x89PNG\r\n\x1a\nfixture-png"
_FIXTURE_MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"


class _Response:
    def __init__(self, payload: object, *, status_code: int = 200, raw: bytes | None = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = raw if raw is not None else json.dumps(payload, separators=(",", ":")).encode()
        self.text = self.content.decode("utf-8", errors="replace")

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "fixture HTTP error",
                request=httpx.Request("GET", "https://api.poyo.ai"),
                response=httpx.Response(self.status_code),
            )


class _Transport:
    def __init__(self, statuses: list[dict[str, Any]], *, submit_payload: object | None = None) -> None:
        self.statuses = list(statuses)
        self.submit_payload = submit_payload or {
            "code": 200,
            "data": {"task_id": "task_fixture_1", "status": "queued"},
        }
        self.posts: list[dict[str, Any]] = []
        self.gets: list[str] = []

    def response_for_get(self, path: str) -> _Response:
        self.gets.append(path)
        if "/api/generate/status/" in path:
            payload = self.statuses.pop(0) if self.statuses else {"code": 200, "data": {"status": "queued"}}
            return _Response(payload)
        return _Response({}, raw=_FIXTURE_MP4 if path.endswith(".mp4") else _FIXTURE_PNG)


class _FakeAsyncClient:
    def __init__(self, transport: _Transport, **kwargs: Any) -> None:
        self.transport = transport
        self.kwargs = kwargs

    async def post(self, path: str, **kwargs: Any) -> _Response:
        self.transport.posts.append({"path": path, **kwargs})
        return _Response(self.transport.submit_payload)

    async def get(self, path: str, **_: Any) -> _Response:
        return self.transport.response_for_get(path)

    async def aclose(self) -> None:
        return None

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None


def _rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM provider_cost_attempts ORDER BY logical_operation, ordinal, attempt_id"
    ).fetchall()


@asynccontextmanager
async def _async_bound_context(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
):
    del connection
    repository = ProviderCostRepository(require_postgres=False)
    catalog = ProviderPriceCatalog.load_default()
    execution = ProviderExecutionService(
        repository=repository,
        server_cap_usd_nanos=5_000_000_000,
        clock=lambda: CHECKED_AT,
    )
    context = await execution.initialize_context(
        tenant_id=TENANT,
        budget_job_kind="canonical",
        budget_job_id=f"job-{name}",
        scenario_or_resource_type="s1",
        generation_policy_version="generation-safety.v1",
    )

    def factory(registry: Any) -> ProviderCostService:
        return ProviderCostService(
            repository=repository,
            price_catalog=catalog,
            operation_registry=registry,
            clock=lambda: CHECKED_AT,
        )

    token = bind_provider_execution_context(context)
    try:
        yield repository, catalog, factory
    finally:
        reset_provider_execution_context(token)


async def _noop() -> None:
    return None


@pytest.mark.asyncio
async def test_gpt_image_paid_success_settles_before_download_and_is_not_poyo_video(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    transport = _Transport(
        [
            {
                "code": 200,
                "data": {
                    "status": "finished",
                    "credits_amount": 33_760_000,
                    "files": [{"file_url": "https://93.184.216.34/image.png"}],
                },
            }
        ]
    )
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "image") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        result = await client.generate(
            "a warm product scene",
            quality="high",
            size="1024x1792",
            image_id="image.primary",
        )
        await client.close()

    rows = _rows(isolated_provider_cost_db)
    assert len(rows) == 1
    assert rows[0]["state"] == "settled"
    assert rows[0]["catalog_operation"] == "image_generation"
    assert rows[0]["media_type"] == "image"
    assert rows[0]["provider_reported_credit_micro_units"] == 33_760_000
    local_path = result.get("local_path")
    assert isinstance(local_path, str) and Path(local_path).is_file()
    assert not any(row["logical_operation"].startswith("poyo_video") for row in rows)
    assert len(transport.posts) == 1


@pytest.mark.asyncio
async def test_gpt_image_download_failure_keeps_settled_cost(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    transport = _Transport(
        [
            {
                "code": 200,
                "data": {
                    "status": "finished",
                    "credits_amount": 2_000_000,
                    "files": [{"file_url": "https://93.184.216.34/image.png"}],
                },
            }
        ]
    )
    status_get = transport.response_for_get

    def failed_get(path: str) -> _Response:
        if "/api/generate/status/" in path:
            return status_get(path)
        raise httpx.ReadError("fixture download failure")

    transport.response_for_get = failed_get  # type: ignore[method-assign]
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "image-download") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.generate("download failure", quality="low", size="auto")
        await client.close()

    assert exc_info.value.code == "provider_cost_artifact_failed"
    assert _rows(isolated_provider_cost_db)[0]["state"] == "settled"


@pytest.mark.asyncio
async def test_poyo_poll_exhaustion_holds_submitted_without_resubmit(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    transport = _Transport([{"code": 200, "data": {"status": "queued"}}])
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(image_module, "_poyo_image_max_polls", lambda: 1)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "image-timeout") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        result = await client.generate("poll later", quality="low", size="auto")
        await client.close()

    assert result.get("_poyo_state") == "submitted"
    assert len(transport.posts) == 1
    assert _rows(isolated_provider_cost_db)[0]["state"] == "submitted"


@pytest.mark.asyncio
async def test_malformed_status_reads_retry_then_hold_submitted(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    transport = _Transport([])
    status_get = transport.response_for_get

    def malformed_status(path: str) -> _Response:
        if "/api/generate/status/" in path:
            return _Response({}, raw=b"not-json")
        return status_get(path)

    transport.response_for_get = malformed_status  # type: ignore[method-assign]
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(image_module, "_poyo_image_max_polls", lambda: 2)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "malformed-status") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        result = await client.generate("malformed status", quality="low", size="auto")
        await client.close()

    assert result["_poyo_state"] == "submitted"
    assert len(transport.posts) == 1
    assert _rows(isolated_provider_cost_db)[0]["state"] == "submitted"


@pytest.mark.asyncio
async def test_finished_noncanonical_credits_hold_accounting_error(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    raw = b'{"code":200,"data":{"status":"finished","credits_amount":2.0,"files":[{"file_url":"https://93.184.216.34/x"}]}}'
    transport = _Transport([{"code": 200, "data": {"status": "finished", "credits_amount": 2.0, "files": [{"file_url": "https://93.184.216.34/x"}]}}])
    status_get = transport.response_for_get

    def response(path: str) -> _Response:
        if "/api/generate/status/" in path:
            status_get(path)
            return _Response({}, raw=raw)
        return status_get(path)

    transport.response_for_get = response  # type: ignore[method-assign]
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "image-credit") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.generate("credit mismatch", quality="low", size="auto")
        await client.close()

    assert exc_info.value.code == "provider_cost_accounting_error"
    assert _rows(isolated_provider_cost_db)[0]["state"] == "accounting_error"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("credits", "expected_code", "expected_state"),
    [
        (0, "provider_cost_attempt_conflict", "released"),
        (1, "provider_cost_accounting_error", "accounting_error"),
        (None, "provider_cost_outcome_ambiguous", "ambiguous"),
    ],
)
async def test_failed_terminal_credit_classification_is_strict(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    credits: int | None,
    expected_code: str,
    expected_state: str,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    task = {
        "code": 200,
        "data": {
            "status": "failed",
            **({"credits_amount": credits} if credits is not None else {}),
        },
    }
    transport = _Transport([task])
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, f"failed-{expected_state}") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.generate("terminal failed", quality="low", size="auto")
        await client.close()

    assert exc_info.value.code == expected_code
    assert _rows(isolated_provider_cost_db)[0]["state"] == expected_state


@pytest.mark.asyncio
async def test_failed_noncanonical_credits_are_ambiguous_not_released(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    transport = _Transport([{"code": 200, "data": {"status": "failed", "credits_amount": 0.0}}])
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "failed-float") as (
        _repository,
        catalog,
        factory,
    ):
        client = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        with pytest.raises(ProviderCostContractError) as exc_info:
            await client.generate("failed float", quality="low", size="auto")
        await client.close()

    assert exc_info.value.code == "provider_cost_outcome_ambiguous"
    assert _rows(isolated_provider_cost_db)[0]["state"] == "ambiguous"


@pytest.mark.asyncio
async def test_submitted_restart_reuses_task_without_second_submit(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import poyo_client as poyo_module

    transport = _Transport([{"code": 200, "data": {"status": "queued"}}])
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())
    monkeypatch.setattr(image_module, "_poyo_image_max_polls", lambda: 1)

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "restart") as (
        _repository,
        catalog,
        factory,
    ):
        first = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        first_result = await first.generate("restart me", quality="low", size="auto", image_id="restart.primary")
        await first.close()
        assert first_result["_poyo_state"] == "submitted"

        transport.statuses.append(
            {
                "code": 200,
                "data": {
                    "status": "finished",
                    "credits_amount": 2_000_000,
                    "files": [{"file_url": "https://93.184.216.34/restarted.png"}],
                },
            }
        )
        second = image_module.GPTImageClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        second_result = await second.generate("restart me", quality="low", size="auto", image_id="restart.primary")
        await second.close()

    assert second_result["_poyo_state"] == "settled"
    assert len(transport.posts) == 1
    assert _rows(isolated_provider_cost_db)[0]["state"] == "settled"


@pytest.mark.asyncio
async def test_seedance_unsupported_references_and_resolution_block_before_submit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module
    from src.tools import seedance_client as seed_module

    transport = _Transport([])
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(seed_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    client = seed_module.SeedanceClient(output_dir=tmp_path)
    with pytest.raises(ProviderCostContractError):
        await client.text_to_video("bad 4k", duration=10, resolution="4K", model="seedance-2")
    with pytest.raises(ProviderCostContractError):
        await client.text_to_video(
            "bad reference",
            duration=10,
            resolution="720p",
            model="seedance-2",
            reference_video_urls=["https://cdn.invalid/reference.mp4"],
        )
    with pytest.raises(ProviderCostContractError):
        await client.text_to_video(
            "bad model",
            duration=10,
            resolution="720p",
            model="kling-3",
        )
    assert transport.posts == []
    await client.close()


@pytest.mark.asyncio
async def test_gpt_image_edit_model_is_zero_network_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module

    monkeypatch.setattr(image_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(image_module, "POYO_IMAGE_MODEL", "gpt-image-2-edit")
    client = image_module.GPTImageClient(output_dir=tmp_path)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client.generate("edit is unsupported", quality="low", size="auto")
    assert exc_info.value.code == "provider_cost_rule_unavailable"
    await client.close()


@pytest.mark.asyncio
async def test_seedance_paid_success_settles_exact_duration_without_stub(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module
    from src.tools import seedance_client as seed_module

    transport = _Transport(
        [
            {
                "code": 200,
                "data": {
                    "status": "finished",
                    "credits_amount": 400_000_000,
                    "duration": 10,
                    "files": [{"file_url": "https://93.184.216.34/video.mp4"}],
                },
            }
        ]
    )
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(seed_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "video") as (
        _repository,
        catalog,
        factory,
    ):
        client = seed_module.SeedanceClient(
            output_dir=tmp_path,
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        result = await client.text_to_video(
            "gentle product motion",
            duration=10,
            resolution="720p",
            model="seedance-2",
        )
        await client.close()

    assert result.get("_stub_mode") is None
    local_path = result.get("local_path")
    assert isinstance(local_path, str) and Path(local_path).is_file()
    row = _rows(isolated_provider_cost_db)[0]
    assert row["state"] == "settled"
    assert row["catalog_operation"] == "text_to_video"
    assert row["settlement_billing_facts"]
    assert row["provider_reported_credit_micro_units"] == 400_000_000
    assert len(transport.posts) == 1


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ("auto", "1K"),
        ("2048x2048", "2K"),
        ("3840x2160", "4K"),
        ("4000x2500", "2K"),
    ],
)
def test_gpt_image_resolution_freeze_matrix(size: str, expected: str) -> None:
    from src.tools.gpt_image_client import resolve_gpt_image_resolution

    assert resolve_gpt_image_resolution(size, quality="high").effective_resolution == expected


@pytest.mark.parametrize("size", ["1024x2000", "2048x5000", "99999x99999"])
def test_gpt_image_custom_resolution_outside_approved_envelope_is_blocked(size: str) -> None:
    from src.tools.gpt_image_client import resolve_gpt_image_resolution

    with pytest.raises(ProviderCostContractError):
        resolve_gpt_image_resolution(size, quality="high")


@pytest.mark.parametrize(
    ("size", "wire_size"),
    [("1024x1792", "9:16"), ("1536x1024", "3:2"), ("1024x1024", "1:1")],
)
def test_gpt_image_legacy_sizes_normalize_to_auto_ratio(size: str, wire_size: str) -> None:
    from src.tools.gpt_image_client import resolve_gpt_image_resolution

    resolved = resolve_gpt_image_resolution(size, quality="low")
    assert resolved.requested_resolution == "auto"
    assert resolved.effective_resolution == "1K"
    assert resolved.wire_size == wire_size


@pytest.mark.asyncio
async def test_unsupported_paid_paths_are_blocked_before_http_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import gpt_image_client as image_module
    from src.tools import seedance_client as seed_module

    constructions = 0

    def forbidden(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("unsupported paid path must not construct HTTP client")

    monkeypatch.setattr(image_module.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(image_module, "OPENAI_API_KEY", "legacy-openai-key")
    image_client = image_module.GPTImageClient(output_dir=tmp_path)
    with pytest.raises(ProviderCostContractError) as image_error:
        await image_client.generate("direct path")
    assert image_error.value.code == "provider_cost_legacy_path_blocked"
    monkeypatch.setattr(seed_module, "POYO_API_KEY", "")
    monkeypatch.setattr(seed_module, "SEEDANCE_API_KEY", "native-seedance-key")
    with pytest.raises(ProviderCostContractError) as seed_error:
        seed_module.SeedanceClient(output_dir=tmp_path)
    assert seed_error.value.code == "provider_cost_legacy_path_blocked"
    assert constructions == 0


@pytest.mark.asyncio
async def test_seedance_local_reference_is_artifact_scoped_and_hashes_exact_bytes(
    isolated_provider_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module
    from src.tools import seedance_client as seed_module

    raw_image = b"\x89PNG\r\n\x1a\n" + (b"fixture" * 40)
    image_path = tmp_path / "input.png"
    image_path.write_bytes(raw_image)
    transport = _Transport(
        [
            {
                "code": 200,
                "data": {
                    "status": "finished",
                    "credits_amount": 400_000_000,
                    "files": [{"file_url": "https://93.184.216.34/video.mp4"}],
                },
            }
        ]
    )
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **kw: _FakeAsyncClient(transport, **kw))
    monkeypatch.setattr(seed_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module.asyncio, "sleep", lambda *_: _noop())

    async with _async_bound_context(isolated_provider_cost_db, monkeypatch, "image-ref") as (
        _repository,
        catalog,
        factory,
    ):
        client = seed_module.SeedanceClient(
            output_dir=tmp_path / "clips",
            price_catalog=catalog,
            cost_service_factory=factory,
        )
        result = await client.text_to_video(
            "image reference motion",
            image_refs=[str(image_path)],
            duration=10,
            resolution="720p",
            model="seedance-2",
            operation_instance="ref.0",
        )
        await client.close()

    body = json.loads(transport.posts[0]["content"])
    encoded = body["input"]["image_urls"][0].split(",", 1)[1]
    assert base64.b64decode(encoded) == raw_image
    assert isinstance(result.get("local_path"), str)


@pytest.mark.asyncio
async def test_seedance_local_reference_outside_artifact_root_is_zero_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module
    from src.tools import seedance_client as seed_module

    constructions = 0

    def forbidden(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("blocked local reference must not construct HTTP")

    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(seed_module, "POYO_API_KEY", POYO_KEY)
    monkeypatch.setattr(poyo_module, "POYO_API_KEY", POYO_KEY)
    client = seed_module.SeedanceClient(output_dir=tmp_path)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client.image_to_video(
            "/etc/hosts",
            prompt="outside root",
            duration=10,
            resolution="720p",
            model="seedance-2",
        )
    await client.close()
    assert exc_info.value.code == "provider_cost_rule_unavailable"
    assert constructions == 0


@pytest.mark.asyncio
async def test_poyo_artifact_url_blocks_ssrf_before_http_construction(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module

    constructions = 0

    def forbidden(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("blocked artifact URL must not construct HTTP")

    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", forbidden)
    client = poyo_module.PoyoClient(api_key=POYO_KEY)
    with pytest.raises(ValueError, match="approved HTTPS"):
        await client.download(
            {"files": [{"file_url": "http://127.0.0.1/private"}]},
            tmp_path / "artifact.mp4",
        )
    await client.close()
    assert constructions == 0


@pytest.mark.asyncio
async def test_poyo_artifact_url_rejects_unresolved_hostname_before_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module

    constructions = 0

    def forbidden(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("unresolved artifact URL must not construct HTTP")

    def unresolved(*_: Any, **__: Any) -> list[Any]:
        raise OSError("fixture DNS failure")

    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(poyo_module.socket, "getaddrinfo", unresolved)
    client = poyo_module.PoyoClient(api_key=POYO_KEY)
    with pytest.raises(ValueError, match="could not be resolved"):
        await client.download(
            {"files": [{"file_url": "https://artifact.example/image.png"}]},
            tmp_path / "artifact.png",
        )
    await client.close()
    assert constructions == 0


@pytest.mark.asyncio
async def test_poyo_artifact_url_rejects_private_dns_before_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import socket

    from src.tools import poyo_client as poyo_module

    constructions = 0

    def forbidden(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("private DNS artifact URL must not construct HTTP")

    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(
        poyo_module.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))
        ],
    )
    client = poyo_module.PoyoClient(api_key=POYO_KEY)
    with pytest.raises(ValueError, match="globally routable"):
        await client.download(
            {"files": [{"file_url": "https://artifact.example/image.png"}]},
            tmp_path / "artifact.png",
        )
    await client.close()
    assert constructions == 0


@pytest.mark.asyncio
async def test_poyo_artifact_url_rejects_dns_rebinding_before_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module

    constructions = 0
    resolutions = iter([("93.184.216.34",), ("8.8.8.8",)])

    def forbidden(**_: Any) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("rebinding artifact URL must not construct HTTP")

    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", forbidden)
    monkeypatch.setattr(poyo_module, "_resolve_public_artifact_addresses", lambda _: next(resolutions))
    client = poyo_module.PoyoClient(api_key=POYO_KEY)
    with pytest.raises(RuntimeError, match="artifact download failed"):
        await client.download(
            {"files": [{"file_url": "https://artifact.example/image.png"}]},
            tmp_path / "artifact.png",
            max_retries=1,
        )
    await client.close()
    assert constructions == 0


@pytest.mark.asyncio
async def test_poyo_artifact_download_pins_verified_ip_and_preserves_tls_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module

    resolver_calls = 0
    requests: list[tuple[str, dict[str, Any]]] = []

    def stable_public_resolution(_: str) -> tuple[str, ...]:
        nonlocal resolver_calls
        resolver_calls += 1
        # A third independent DNS lookup would be a regression: after the
        # second validation the transport must connect to the frozen address.
        return ("93.184.216.34",)

    class CapturingClient:
        async def get(self, url: str, **kwargs: Any) -> _Response:
            requests.append((url, kwargs))
            return _Response({}, raw=_FIXTURE_PNG)

        async def __aenter__(self) -> CapturingClient:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr(poyo_module, "_resolve_public_artifact_addresses", stable_public_resolution)
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **_: CapturingClient())
    client = poyo_module.PoyoClient(api_key=POYO_KEY)
    output = await client.download(
        {"files": [{"file_url": "https://artifact.example/image.png"}]},
        tmp_path / "image.png",
        max_retries=1,
    )
    await client.close()

    assert output.read_bytes() == _FIXTURE_PNG
    assert resolver_calls == 2
    assert len(requests) == 1
    request_url, request_kwargs = requests[0]
    assert request_url == "https://93.184.216.34/image.png"
    assert request_kwargs["headers"] == {"Host": "artifact.example"}
    assert request_kwargs["extensions"] == {"sni_hostname": "artifact.example"}


@pytest.mark.asyncio
async def test_legacy_poyo_one_shot_is_zero_network_tombstone(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module

    monkeypatch.setattr(
        poyo_module.httpx,
        "AsyncClient",
        lambda **_: pytest.fail("legacy one-shot must not construct HTTP"),
    )
    client = poyo_module.PoyoClient(api_key=POYO_KEY)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await client.submit_poll_download(
            "seedance-2",
            {"prompt": "legacy"},
            tmp_path / "artifact.mp4",
        )
    with pytest.raises(ProviderCostContractError) as submit_exc:
        await client.submit("seedance-2", {"prompt": "legacy"})
    await client.close()
    assert exc_info.value.code == "provider_cost_legacy_path_blocked"
    assert submit_exc.value.code == "provider_cost_legacy_path_blocked"


@pytest.mark.asyncio
async def test_paid_seedance_verification_failure_cannot_fallback_to_stub(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.skills.seedance_video_generate import SeedanceVideoGenerateSkill

    class FakeSeedanceClient:
        def __init__(self, *, output_dir: Path | None = None, max_retries: int | None = None) -> None:
            del max_retries
            self.output_dir = output_dir or tmp_path

        async def text_to_video(self, **_: Any) -> dict[str, str]:
            path = self.output_dir / "invalid.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not-an-mp4")
            return {"local_path": str(path), "video_url": "https://cdn.invalid/video.mp4"}

        async def close(self) -> None:
            return None

    monkeypatch.setattr("src.tools.seedance_client.SeedanceClient", FakeSeedanceClient)
    result = await SeedanceVideoGenerateSkill().safe_execute(
        {"prompt": "paid artifact check", "output_dir": str(tmp_path), "provider_max_retries": 0}
    )
    assert result.success is False
    assert result.error == "provider_cost_artifact_failed"
    assert result.metadata.get("non_retryable") is True
    assert result.metadata.get("is_fallback") is not True


@pytest.mark.asyncio
async def test_paid_gpt_image_verification_failure_cannot_fallback_to_stub(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.skills.gpt_image_generate import GPTImageGenerateSkill

    class FakeGPTImageClient:
        def __init__(self, *, output_dir: Path | None = None, max_retries: int | None = None) -> None:
            del max_retries
            self.output_dir = output_dir or tmp_path

        async def generate(self, **_: Any) -> dict[str, str]:
            path = self.output_dir / "invalid.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"not-a-png")
            return {"local_path": str(path), "image_url": "https://cdn.invalid/image.png"}

        async def close(self) -> None:
            return None

    monkeypatch.setattr("src.tools.gpt_image_client.GPTImageClient", FakeGPTImageClient)
    monkeypatch.setattr("src.config.POYO_API_KEY", POYO_KEY)
    result = await GPTImageGenerateSkill().safe_execute(
        {"prompt": "paid image check", "output_dir": str(tmp_path), "provider_max_retries": 0}
    )
    assert result.success is False
    assert result.error == "provider_cost_artifact_failed"
    assert result.metadata.get("non_retryable") is True
    assert result.metadata.get("is_fallback") is not True


@pytest.mark.asyncio
async def test_download_retries_read_only_without_allocating_or_resubmitting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from src.tools import poyo_client as poyo_module

    transport = _Transport([])
    download_attempts = 0

    async def failing_get(path: str, **_: Any) -> _Response:
        nonlocal download_attempts
        download_attempts += 1
        raise httpx.ReadError("fixture download failure")

    client = _FakeAsyncClient(transport)
    client.get = failing_get  # type: ignore[method-assign]
    monkeypatch.setattr(poyo_module.httpx, "AsyncClient", lambda **_: client)
    poyo = poyo_module.PoyoClient(api_key=POYO_KEY)
    with pytest.raises(RuntimeError, match="artifact download failed"):
        await poyo.download(
            {"files": [{"file_url": "https://93.184.216.34/image.png"}]},
            tmp_path / "image.png",
            max_retries=3,
        )
    assert download_attempts == 3
    assert transport.posts == []
    await poyo.close()


@pytest.mark.asyncio
async def test_pending_skill_result_is_not_converted_to_stub_fallback() -> None:
    from src.skills.base import SkillCallable, SkillResult

    class PendingSkill(SkillCallable):
        max_retries = 3

        async def execute(self, params: dict[str, Any]) -> SkillResult:
            del params
            return SkillResult(
                success=False,
                error="provider_pending",
                metadata={"non_retryable": True, "poyo_state": "submitted"},
            )

        def validate_params(self, params: dict[str, Any]) -> list[str]:
            del params
            return []

        def validate_output(self, data: Any) -> list[str]:
            del data
            return []

        def fallback(self, params: dict[str, Any]) -> SkillResult:
            del params
            return SkillResult(success=True, data={"_stub_mode": "must-not-run"})

    result = await PendingSkill().safe_execute({"provider_max_retries": 2})
    assert result.success is False
    assert result.error == "provider_pending"
    assert result.metadata["poyo_state"] == "submitted"
    assert result.metadata["retries"] == 0
