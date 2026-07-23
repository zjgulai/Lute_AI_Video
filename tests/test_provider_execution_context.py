"""Task 4 immutable provider-execution authority contracts.

All persistence in this module is an isolated SQLite fixture.  No provider
client, credential, HTTP transport, or mutation retry is constructed.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.models.provider_cost import ProviderCostContractError
from src.services.provider_cost import (
    TrustedRegenerationEpoch,
    ValidatedPlanBudgetAuthorization,
    validate_provider_budget_authorization_json,
)
from src.storage import db as db_module
from src.storage.provider_cost_repository import ProviderCostRepository

TENANT_ID = "tenant-provider-execution"
OTHER_TENANT_ID = "tenant-provider-execution-other"
CANONICAL_JOB_ID = "fast_20260717_context_001"
GENERATION_POLICY_VERSION = "generation-safety.v2"
CHECKED_AT = datetime(2026, 7, 17, 8, 0, 0, tzinfo=UTC)


def _api() -> Any:
    try:
        return importlib.import_module("src.services.provider_execution")
    except ModuleNotFoundError:
        pytest.fail("ProviderExecutionContext is not implemented yet", pytrace=False)


def _install_sqlite_connection(
    connection: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_pg_available", False)
    monkeypatch.setattr(db_module, "_sqlite_conn", connection)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)


@pytest.fixture
def sqlite_execution_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        str(tmp_path / "provider-execution.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    _install_sqlite_connection(connection, monkeypatch)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


def _service(*, server_cap_usd_nanos: int = 100_000_000) -> Any:
    api = _api()
    return api.ProviderExecutionService(
        repository=ProviderCostRepository(require_postgres=False),
        server_cap_usd_nanos=server_cap_usd_nanos,
        clock=lambda: CHECKED_AT,
    )


async def _canonical_context(
    service: Any,
    *,
    job_id: str = CANONICAL_JOB_ID,
    authorization: object | None = None,
) -> Any:
    return await service.initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id=job_id,
        scenario_or_resource_type="fast",
        generation_policy_version=GENERATION_POLICY_VERSION,
        authorization=authorization,
    )


def _authorization_json() -> str:
    return (
        "{"
        '"approval_id":"approval-provider-execution-001",'
        '"approved_at":"2026-07-17T07:00:00Z",'
        '"expires_at":"2026-07-18T08:00:00Z",'
        '"provider":"poyo",'
        '"model":"gpt-image-2",'
        '"budget_limit":"0.080000000",'
        '"budget_limit_usd":0.080000000,'
        '"budget_stop_loss":{'
        '"max_total_cost_usd":0.060000000,'
        '"per_job_cost_ceiling_usd":0.050000000'
        "}"
        "}"
    )


@pytest.mark.asyncio
async def test_context_is_frozen_strict_server_owned_and_zero_retry(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    context = await _canonical_context(_service())

    assert context.version == "provider-execution.v1"
    assert context.tenant_id == TENANT_ID
    assert context.budget_job_kind == "canonical"
    assert context.budget_job_id == CANONICAL_JOB_ID
    assert context.scenario_or_resource_type == "fast"
    assert context.account_id
    assert context.effective_cap_usd_nanos == 100_000_000
    assert context.budget_source_kind == "server_config"
    assert context.trusted_authorization_ref is None
    assert context.budget_policy_version == "provider-budget.v1"
    assert context.generation_policy_version == GENERATION_POLICY_VERSION
    assert context.provider_max_retries == 0
    assert context.regeneration_epoch is None

    with pytest.raises((AttributeError, TypeError, ValidationError)):
        context.effective_cap_usd_nanos = 1

    raw = context.model_dump(mode="python")
    with pytest.raises(ValidationError):
        api.ProviderExecutionContext.model_validate(
            {**raw, "provider_max_retries": 1},
            strict=True,
        )
    with pytest.raises(ValidationError):
        api.ProviderExecutionContext.model_validate(
            {**raw, "client_budget": 1},
            strict=True,
        )


@pytest.mark.asyncio
async def test_safe_projection_contains_no_money_account_or_raw_authority(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    authorization = validate_provider_budget_authorization_json(
        _authorization_json(),
        expected_provider="poyo",
        expected_model="gpt-image-2",
        now=CHECKED_AT,
    )
    context = await _canonical_context(_service(), authorization=authorization)

    projection = api.project_provider_execution_context(context)

    assert projection == {
        "version": "provider-execution.v1",
        "budget_job_kind": "canonical",
        "budget_job_id": CANONICAL_JOB_ID,
        "scenario_or_resource_type": "fast",
        "budget_policy_version": "provider-budget.v1",
        "trusted_authorization_ref": "approval-provider-execution-001",
        "generation_policy_version": GENERATION_POLICY_VERSION,
        "provider_max_retries": 0,
        "regeneration_epoch": None,
    }
    serialized = repr(projection).lower()
    for forbidden in (
        "account_id",
        "effective_cap",
        "usd_nanos",
        "budget_limit",
        "approved_at",
        "expires_at",
        'provider":',
        "/tmp/",
    ):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_trusted_authorization_can_only_lower_the_server_cap(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    authorization = validate_provider_budget_authorization_json(
        _authorization_json(),
        expected_provider="poyo",
        expected_model="gpt-image-2",
        now=CHECKED_AT,
    )
    context = await _canonical_context(
        _service(server_cap_usd_nanos=70_000_000),
        authorization=authorization,
    )

    assert context.effective_cap_usd_nanos == 50_000_000
    assert context.budget_source_kind == "validated_authorization"
    assert context.trusted_authorization_ref == "approval-provider-execution-001"

    with pytest.raises(ProviderCostContractError) as raw_mapping:
        await _canonical_context(
            _service(),
            authorization={"approval_id": "client-forged"},
        )
    assert raw_mapping.value.code == "provider_budget_configuration_invalid"


@pytest.mark.asyncio
async def test_initialization_is_idempotent_and_reconstructs_from_private_account_truth(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    first = await _canonical_context(service)
    second = await _canonical_context(service)

    assert second == first
    projection = api.project_provider_execution_context(first)
    reconstructed = await service.reconstruct_context(
        projection,
        expected_tenant_id=TENANT_ID,
        expected_scenario_or_resource_type="fast",
        expected_generation_policy_version=GENERATION_POLICY_VERSION,
    )
    assert reconstructed == first

    row_count = sqlite_execution_db.execute(
        "SELECT COUNT(*) FROM job_budget_accounts WHERE tenant_id = ? AND job_id = ?",
        (TENANT_ID, CANONICAL_JOB_ID),
    ).fetchone()[0]
    assert row_count == 1


@pytest.mark.asyncio
async def test_same_job_concurrency_reuses_one_account_and_tenant_scope_is_independent(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    service = _service()

    contexts = await asyncio.gather(*[_canonical_context(service, job_id="fast_context_concurrent") for _ in range(20)])
    assert len({context.account_id for context in contexts}) == 1
    other = await service.initialize_context(
        tenant_id=OTHER_TENANT_ID,
        budget_job_kind="canonical",
        budget_job_id="fast_context_concurrent",
        scenario_or_resource_type="fast",
        generation_policy_version=GENERATION_POLICY_VERSION,
    )
    assert other.account_id != contexts[0].account_id

    rows = sqlite_execution_db.execute(
        "SELECT tenant_id, account_id FROM job_budget_accounts WHERE job_kind = ? AND job_id = ? ORDER BY tenant_id",
        ("canonical", "fast_context_concurrent"),
    ).fetchall()
    assert [(row["tenant_id"], row["account_id"]) for row in rows] == [
        (TENANT_ID, contexts[0].account_id),
        (OTHER_TENANT_ID, other.account_id),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("version"),
        lambda value: value.__setitem__("version", "provider-execution.v999"),
        lambda value: value.__setitem__("budget_job_id", "different-job"),
        lambda value: value.__setitem__("scenario_or_resource_type", "s1"),
        lambda value: value.__setitem__("generation_policy_version", "generation-safety.v999"),
        lambda value: value.__setitem__("provider_max_retries", 1),
        lambda value: value.__setitem__("effective_cap_usd_nanos", 1),
    ],
)
async def test_missing_corrupt_unknown_or_forged_projection_fails_closed(
    sqlite_execution_db: sqlite3.Connection,
    mutation: Any,
) -> None:
    api = _api()
    service = _service()
    context = await _canonical_context(service)
    projection = api.project_provider_execution_context(context)
    mutation(projection)

    with pytest.raises(ProviderCostContractError) as exc_info:
        await service.reconstruct_context(
            projection,
            expected_tenant_id=TENANT_ID,
            expected_scenario_or_resource_type="fast",
            expected_generation_policy_version=GENERATION_POLICY_VERSION,
        )
    assert exc_info.value.code == "provider_execution_context_missing"


@pytest.mark.asyncio
async def test_wrong_tenant_and_missing_account_fail_without_cross_tenant_disclosure(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    context = await _canonical_context(service)
    projection = api.project_provider_execution_context(context)

    with pytest.raises(ProviderCostContractError) as wrong_tenant:
        await service.reconstruct_context(
            projection,
            expected_tenant_id=OTHER_TENANT_ID,
            expected_scenario_or_resource_type="fast",
            expected_generation_policy_version=GENERATION_POLICY_VERSION,
        )
    assert wrong_tenant.value.code == "provider_execution_context_missing"

    sqlite_execution_db.execute(
        "DELETE FROM job_budget_accounts WHERE tenant_id = ? AND job_id = ?",
        (TENANT_ID, CANONICAL_JOB_ID),
    )
    sqlite_execution_db.commit()
    with pytest.raises(ProviderCostContractError) as missing:
        await service.reconstruct_context(
            projection,
            expected_tenant_id=TENANT_ID,
            expected_scenario_or_resource_type="fast",
            expected_generation_policy_version=GENERATION_POLICY_VERSION,
        )
    assert missing.value.code == "provider_execution_context_missing"


@pytest.mark.asyncio
async def test_repository_job_identity_lookup_is_tenant_bound_and_strict(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    service = _service()
    context = await _canonical_context(service)
    repository = ProviderCostRepository(require_postgres=False)

    account = await repository.get_account_by_job_identity(
        tenant_id=TENANT_ID,
        job_kind="canonical",
        job_id=CANONICAL_JOB_ID,
    )
    assert account is not None
    assert account["account_id"] == context.account_id
    assert (
        await repository.get_account_by_job_identity(
            tenant_id=OTHER_TENANT_ID,
            job_kind="canonical",
            job_id=CANONICAL_JOB_ID,
        )
        is None
    )

    invalid_kind: Any
    for invalid_kind in ("", "admin", 1, True):
        with pytest.raises(ProviderCostContractError):
            await repository.get_account_by_job_identity(
                tenant_id=TENANT_ID,
                job_kind=invalid_kind,
                job_id=CANONICAL_JOB_ID,
            )


@pytest.mark.asyncio
async def test_compatibility_identity_is_server_generated_and_ignores_output_label(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()

    first_job_id = api.new_compatibility_job_id()
    second_job_id = api.new_compatibility_job_id()
    assert first_job_id.startswith("compat_")
    assert second_job_id.startswith("compat_")
    assert first_job_id != second_job_id
    assert "output_label" not in inspect.signature(api.new_compatibility_job_id).parameters
    assert "output_label" not in inspect.signature(service.initialize_context).parameters

    context = await service.initialize_context(
        tenant_id=TENANT_ID,
        budget_job_kind="compatibility",
        budget_job_id=first_job_id,
        scenario_or_resource_type="s1",
        generation_policy_version=GENERATION_POLICY_VERSION,
    )
    assert context.budget_job_id == first_job_id
    assert context.budget_job_kind == "compatibility"


@pytest.mark.asyncio
async def test_contextvar_nested_reset_concurrency_and_background_copy(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    first = await _canonical_context(service, job_id="fast_context_first")
    second = await _canonical_context(service, job_id="fast_context_second")

    outer = api.bind_provider_execution_context(first)
    assert api.get_provider_execution_context() == first
    inner = api.bind_provider_execution_context(second)
    assert api.get_provider_execution_context() == second
    api.reset_provider_execution_context(inner)
    assert api.get_provider_execution_context() == first

    start = asyncio.Event()

    async def copied_context() -> Any:
        await start.wait()
        return api.get_provider_execution_context()

    task = asyncio.create_task(copied_context())
    api.reset_provider_execution_context(outer)
    assert api.get_provider_execution_context() is None
    start.set()
    assert await task == first

    barrier = asyncio.Event()

    async def isolated(value: Any) -> Any:
        token = api.bind_provider_execution_context(value)
        try:
            await barrier.wait()
            return api.get_provider_execution_context()
        finally:
            api.reset_provider_execution_context(token)

    tasks = [asyncio.create_task(isolated(first)), asyncio.create_task(isolated(second))]
    barrier.set()
    assert await asyncio.gather(*tasks) == [first, second]
    assert api.get_provider_execution_context() is None


@pytest.mark.asyncio
async def test_request_scope_restores_outer_context_and_background_keeps_copy(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    outer_context = await _canonical_context(service, job_id="fast_context_outer")
    request_context = await _canonical_context(service, job_id="fast_context_request")
    outer_token = api.bind_provider_execution_context(outer_context)
    guard = api.provider_execution_request_scope()
    await anext(guard)
    assert api.get_provider_execution_context() is None
    api.bind_provider_execution_context(request_context)
    release_background = asyncio.Event()

    async def copied_background() -> Any:
        await release_background.wait()
        return api.get_provider_execution_context()

    background = asyncio.create_task(copied_background())
    await guard.aclose()
    assert api.get_provider_execution_context() == outer_context
    release_background.set()
    assert await background == request_context
    api.reset_provider_execution_context(outer_token)
    assert api.get_provider_execution_context() is None


@pytest.mark.asyncio
async def test_persisted_scope_reconstructs_and_resets_explicitly(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    context = await _canonical_context(service)
    state = {
        "tenant_id": TENANT_ID,
        "scenario": "fast",
        "config": {
            "effective_generation_policy": {
                "version": GENERATION_POLICY_VERSION,
            },
            api.PROVIDER_EXECUTION_CONFIG_KEY: api.project_provider_execution_context(context),
        },
    }

    assert api.get_provider_execution_context() is None
    async with api.persisted_provider_execution_scope(state, service=service):
        assert api.get_provider_execution_context() == context
    assert api.get_provider_execution_context() is None


@pytest.mark.asyncio
async def test_trusted_regeneration_epoch_round_trips_only_after_safe_projection(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    context = await _canonical_context(service)
    epoch = TrustedRegenerationEpoch(
        operation_key="scenario.s1.scripts.primary",
        epoch_ref="regen_20260717_001",
    )

    regenerated = api.with_trusted_regeneration_epoch(context, epoch)
    assert regenerated is not context
    assert regenerated.regeneration_epoch == epoch
    projection = api.project_provider_execution_context(regenerated)
    reconstructed = await service.reconstruct_context(
        projection,
        expected_tenant_id=TENANT_ID,
        expected_scenario_or_resource_type="fast",
        expected_generation_policy_version=GENERATION_POLICY_VERSION,
    )
    assert reconstructed.regeneration_epoch == epoch

    for raw_epoch in ({"operation_key": "x", "epoch_ref": "y"}, 1, None):
        with pytest.raises(ProviderCostContractError):
            api.with_trusted_regeneration_epoch(context, raw_epoch)


@pytest.mark.asyncio
async def test_regeneration_epoch_is_persisted_before_future_ordinal_allocation(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    context = await _canonical_context(service)
    state = {
        "label": CANONICAL_JOB_ID,
        "tenant_id": TENANT_ID,
        "scenario": "fast",
        "config": {
            "effective_generation_policy": {
                "version": GENERATION_POLICY_VERSION,
            },
            api.PROVIDER_EXECUTION_CONFIG_KEY: api.project_provider_execution_context(context),
        },
    }
    events: list[str] = []

    class RecordingWriter:
        async def save(self, label: str, saved_state: dict[str, Any]) -> None:
            assert label == CANONICAL_JOB_ID
            projection = saved_state["config"][api.PROVIDER_EXECUTION_CONFIG_KEY]
            assert projection["regeneration_epoch"]["operation_key"] == ("scenario.fast.media.primary")
            events.append("epoch_persisted")

    regenerated = await api.persist_trusted_regeneration_epoch(
        state,
        state_writer=RecordingWriter(),
        operation_key="scenario.fast.media.primary",
        service=service,
    )
    events.append("ordinal_allocated")

    assert events == ["epoch_persisted", "ordinal_allocated"]
    assert regenerated.regeneration_epoch is not None
    assert regenerated.regeneration_epoch.epoch_ref.startswith("regen_")
    assert state["config"][api.PROVIDER_EXECUTION_CONFIG_KEY][
        "regeneration_epoch"
    ] == regenerated.regeneration_epoch.model_dump(mode="json")
    assert api.get_provider_execution_context() is None


@pytest.mark.asyncio
async def test_regeneration_epoch_corrupt_state_or_failed_save_never_mutates_projection(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    context = await _canonical_context(service)
    original_projection = api.project_provider_execution_context(context)
    state = {
        "label": CANONICAL_JOB_ID,
        "tenant_id": TENANT_ID,
        "scenario": "fast",
        "config": {
            "effective_generation_policy": {
                "version": GENERATION_POLICY_VERSION,
            },
            api.PROVIDER_EXECUTION_CONFIG_KEY: dict(original_projection),
        },
    }

    class FailingWriter:
        calls = 0

        async def save(self, label: str, saved_state: dict[str, Any]) -> None:
            self.calls += 1
            raise RuntimeError("fixture save failed")

    writer = FailingWriter()
    with pytest.raises(RuntimeError, match="fixture save failed"):
        await api.persist_trusted_regeneration_epoch(
            state,
            state_writer=writer,
            operation_key="scenario.fast.media.primary",
            service=service,
        )
    assert writer.calls == 1
    assert state["config"][api.PROVIDER_EXECUTION_CONFIG_KEY] == original_projection
    assert api.get_provider_execution_context() is None

    corrupted = {
        **state,
        "tenant_id": OTHER_TENANT_ID,
    }
    with pytest.raises(ProviderCostContractError) as exc_info:
        await api.persist_trusted_regeneration_epoch(
            corrupted,
            state_writer=writer,
            operation_key="scenario.fast.media.primary",
            service=service,
        )
    assert exc_info.value.code == "provider_execution_context_missing"
    assert writer.calls == 1


def test_source_contains_no_provider_client_http_retry_or_public_report_contract() -> None:
    api = _api()
    source = inspect.getsource(api).lower()
    for forbidden in (
        "import httpx",
        "import requests",
        "urllib.request",
        "openai(",
        "poyoclient(",
        "seedanceclient(",
        "@retry",
        "retry_with_backoff",
        "asyncio.sleep",
    ):
        assert forbidden not in source


@pytest.mark.asyncio
async def test_w5_plan_authorization_is_provider_neutral_and_only_lowers_cap(
    sqlite_execution_db: sqlite3.Connection,
) -> None:
    authorization = ValidatedPlanBudgetAuthorization(
        authorization_ref="w5fastact:fixture-001",
        authorization_scope="w5-fast",
        approved_at=datetime(2026, 7, 17, 7, 0, tzinfo=UTC),
        expires_at=datetime(2026, 7, 17, 9, 0, tzinfo=UTC),
        budget_limit_usd_nanos=3_150_000_000,
        max_total_cost_usd_nanos=3_150_000_000,
        per_job_cost_ceiling_usd_nanos=3_150_000_000,
        provider_job_caps=(("llm", 1), ("video", 1)),
    )
    context = await _canonical_context(
        _service(server_cap_usd_nanos=3_200_000_000),
        authorization=authorization,
    )

    assert context.effective_cap_usd_nanos == 3_150_000_000
    assert context.budget_source_kind == "validated_authorization"
    assert context.trusted_authorization_ref == "w5fastact:fixture-001"
