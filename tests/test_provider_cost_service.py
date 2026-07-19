"""W1-27/W1-30 provider-cost service authority and lifecycle contracts.

Every database mutation in this module uses an isolated SQLite file. The
service under test must not contain provider clients, HTTP transports, or
mutation retry behavior.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from src.models.provider_cost import (
    ImageCountBillingFacts,
    ProviderCostAccountIdentity,
    ProviderCostContractError,
)
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.storage import db as db_module
from src.storage.provider_cost_repository import ProviderCostRepository

TENANT_ID = "tenant-cost-service"
CHECKED_AT = datetime(2026, 7, 15, 17, 1, 25, tzinfo=UTC)
FINGERPRINT_A = "a" * 64
FINGERPRINT_B = "b" * 64
OPERATION_KEY = "fast.image.primary"


def _api() -> Any:
    try:
        return importlib.import_module("src.services.provider_cost")
    except ModuleNotFoundError:
        pytest.fail(
            "ProviderCostService is not implemented yet",
            pytrace=False,
        )


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
def sqlite_cost_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        str(tmp_path / "provider-cost-service.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    _install_sqlite_connection(connection, monkeypatch)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


class _Clock:
    def __init__(self, current: datetime = CHECKED_AT) -> None:
        self.current = current

    def __call__(self) -> datetime:
        return self.current


def _operation_definition(*, image_count: int = 1) -> Any:
    api = _api()
    return api.ProviderCostOperationDefinition(
        registry_key=OPERATION_KEY,
        logical_operation="fast.image.primary",
        provider="poyo",
        canonical_model="gpt-image-2",
        provider_billing_region="poyo_global_usd",
        catalog_operation="image_generation",
        media_type="image",
        billing_fact_kind="image_count.v1",
        dimensions=(("effective_resolution", "1K"), ("quality", "low")),
        reservation_billing_facts=ImageCountBillingFacts(
            schema_version="image_count.v1",
            image_count=image_count,
        ),
        reservation_ttl_seconds=300,
    )


def _service(
    *,
    image_count: int = 1,
    clock: _Clock | None = None,
) -> Any:
    api = _api()
    definition = _operation_definition(image_count=image_count)
    return api.ProviderCostService(
        repository=ProviderCostRepository(require_postgres=False),
        price_catalog=ProviderPriceCatalog.load_default(),
        operation_registry={OPERATION_KEY: definition},
        clock=clock or _Clock(),
    )


def _identity(
    *,
    job_id: str = "fast-task-service-001",
    source_kind: str = "server_config",
    source_ref: str | None = None,
    scenario_or_resource_type: str = "fast",
    budget_policy_version: str = "provider-budget.v1",
) -> ProviderCostAccountIdentity:
    return ProviderCostAccountIdentity(
        tenant_id=TENANT_ID,
        job_kind="canonical",
        job_id=job_id,
        scenario_or_resource_type=scenario_or_resource_type,
        budget_source_kind=source_kind,
        budget_source_ref=source_ref,
        budget_policy_version=budget_policy_version,
    )


def _authorization_json(
    *,
    provider: str = "poyo",
    model: str = "gpt-image-2",
    approved_at: str = "2026-07-15T17:00:00Z",
    expires_at: str = "2026-07-16T17:01:25Z",
    budget_display: str = "0.100000000",
    budget_numeric: str = "0.100000000",
    max_total: str = "0.080000000",
    per_job: str = "0.050000000",
) -> str:
    return (
        "{"
        '"approval_id":"approval-cost-service-001",'
        f'"approved_at":"{approved_at}",'
        f'"expires_at":"{expires_at}",'
        f'"provider":"{provider}",'
        f'"model":"{model}",'
        f'"budget_limit":"{budget_display}",'
        f'"budget_limit_usd":{budget_numeric},'
        '"budget_stop_loss":{'
        f'"max_total_cost_usd":{max_total},'
        f'"per_job_cost_ceiling_usd":{per_job}'
        "}"
        "}"
    )


def _validated_authorization() -> Any:
    api = _api()
    return api.validate_provider_budget_authorization_json(
        _authorization_json(),
        expected_provider="poyo",
        expected_model="gpt-image-2",
        now=CHECKED_AT,
    )


async def _account(
    service: Any,
    *,
    identity: ProviderCostAccountIdentity | None = None,
    server_cap_usd_nanos: int = 100_000_000,
    authorization: object | None = None,
) -> dict[str, Any]:
    return await service.initialize_account(
        identity=identity or _identity(),
        server_cap_usd_nanos=server_cap_usd_nanos,
        authorization=authorization,
    )


async def _reserve(
    service: Any,
    account_id: str,
    *,
    fingerprint: str = FINGERPRINT_A,
    regeneration_epoch: object | None = None,
) -> Any:
    return await service.reserve_or_replay(
        tenant_id=TENANT_ID,
        account_id=account_id,
        operation_key=OPERATION_KEY,
        attempt_fingerprint=fingerprint,
        regeneration_epoch=regeneration_epoch,
    )


def test_trusted_authorization_uses_raw_decimal_json_and_is_frozen() -> None:
    api = _api()
    authorization = _validated_authorization()

    assert authorization.authorization_ref == "approval-cost-service-001"
    assert authorization.provider == "poyo"
    assert authorization.canonical_model == "gpt-image-2"
    assert authorization.budget_limit_usd_nanos == 100_000_000
    assert authorization.max_total_cost_usd_nanos == 80_000_000
    assert authorization.per_job_cost_ceiling_usd_nanos == 50_000_000
    assert authorization.expires_at == datetime(
        2026,
        7,
        16,
        17,
        1,
        25,
        tzinfo=UTC,
    )
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        authorization.budget_limit_usd_nanos = 1
    assert "float(" not in inspect.getsource(api.validate_provider_budget_authorization_json)


@pytest.mark.parametrize(
    "raw",
    [
        {"budget_limit_usd": 0.1},
        0.1,
        "/tmp/private-approval.json",
        _authorization_json().replace(
            '"provider":"poyo",',
            '"provider":"poyo","provider":"poyo",',
        ),
        _authorization_json(budget_numeric="1e-1"),
        _authorization_json(budget_numeric="NaN"),
        _authorization_json(budget_display="0.100000001"),
        _authorization_json(max_total="0.100000001"),
        _authorization_json(max_total="0.040000000", per_job="0.050000000"),
        _authorization_json(approved_at="2026-07-15T18:00:00Z"),
        _authorization_json(expires_at="2026-07-15T17:01:25Z"),
    ],
)
def test_trusted_authorization_rejects_untrusted_or_inexact_authority(raw: object) -> None:
    api = _api()

    with pytest.raises(ProviderCostContractError) as exc_info:
        api.validate_provider_budget_authorization_json(
            raw,
            expected_provider="poyo",
            expected_model="gpt-image-2",
            now=CHECKED_AT,
        )

    assert exc_info.value.code == "provider_budget_configuration_invalid"


@pytest.mark.parametrize(
    ("provider", "model"),
    [("deepseek", "gpt-image-2"), ("poyo", "seedance-2")],
)
def test_trusted_authorization_requires_exact_provider_model_binding(
    provider: str,
    model: str,
) -> None:
    api = _api()

    with pytest.raises(ProviderCostContractError) as exc_info:
        api.validate_provider_budget_authorization_json(
            _authorization_json(provider=provider, model=model),
            expected_provider="poyo",
            expected_model="gpt-image-2",
            now=CHECKED_AT,
        )

    assert exc_info.value.code == "provider_budget_configuration_invalid"


@pytest.mark.asyncio
async def test_account_initialization_is_idempotent_and_authorization_only_lowers_cap(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    authorization = _validated_authorization()
    identity = _identity(
        source_kind="validated_authorization",
        source_ref=authorization.authorization_ref,
    )

    account = await _account(
        service,
        identity=identity,
        server_cap_usd_nanos=100_000_000,
        authorization=authorization,
    )
    replay = await _account(
        service,
        identity=identity,
        server_cap_usd_nanos=100_000_000,
        authorization=authorization,
    )
    assert replay == account
    assert account["cap_usd_nanos"] == 50_000_000
    assert account["budget_source_kind"] == "validated_authorization"

    lower_server_cap = await _account(
        service,
        identity=_identity(
            job_id="fast-task-service-002",
            source_kind="validated_authorization",
            source_ref=authorization.authorization_ref,
        ),
        server_cap_usd_nanos=40_000_000,
        authorization=authorization,
    )
    assert lower_server_cap["cap_usd_nanos"] == 40_000_000

    with pytest.raises(ProviderCostContractError) as raw_authority:
        await _account(
            service,
            identity=_identity(job_id="fast-task-service-003"),
            authorization={"budget_limit_usd": 0.01},
        )
    assert raw_authority.value.code == "provider_budget_configuration_invalid"

    with pytest.raises(ProviderCostContractError) as conflict:
        await _account(
            service,
            identity=identity,
            server_cap_usd_nanos=40_000_000,
            authorization=authorization,
        )
    assert conflict.value.code == "provider_cost_attempt_conflict"


@pytest.mark.asyncio
async def test_server_config_account_rejects_authorization_source_confusion(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()

    account = await _account(service)
    assert account["cap_usd_nanos"] == 100_000_000
    assert account["budget_source_kind"] == "server_config"
    assert account["budget_source_ref"] is None

    authorization = _validated_authorization()
    with pytest.raises(ProviderCostContractError) as source_conflict:
        await _account(service, authorization=authorization)
    assert source_conflict.value.code == "provider_budget_configuration_invalid"


@pytest.mark.asyncio
async def test_account_replay_conflicts_on_scenario_policy_and_budget_source(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    await _account(service)

    for conflicting_identity in (
        _identity(scenario_or_resource_type="s1"),
        _identity(budget_policy_version="provider-budget.v2"),
    ):
        with pytest.raises(ProviderCostContractError) as conflict:
            await _account(service, identity=conflicting_identity)
        assert conflict.value.code == "provider_cost_attempt_conflict"

    api = _api()
    authorization = api.validate_provider_budget_authorization_json(
        _authorization_json(
            max_total="0.100000000",
            per_job="0.100000000",
        ),
        expected_provider="poyo",
        expected_model="gpt-image-2",
        now=CHECKED_AT,
    )
    with pytest.raises(ProviderCostContractError) as source_conflict:
        await _account(
            service,
            identity=_identity(
                source_kind="validated_authorization",
                source_ref=authorization.authorization_ref,
            ),
            authorization=authorization,
        )
    assert source_conflict.value.code == "provider_cost_attempt_conflict"


@pytest.mark.asyncio
async def test_reserve_uses_registry_catalog_and_repository_owned_ordinal(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    account = await _account(service)

    owner = await _reserve(service, account["account_id"])
    replay = await _reserve(service, account["account_id"])
    assert owner.outcome == "owner"
    assert replay.outcome == "replay"
    assert replay.attempt == owner.attempt
    assert owner.attempt["ordinal"] == 0
    assert owner.attempt["reserved_usd_nanos"] == 10_000_000
    assert owner.attempt["price_rule_id"] == "poyo.gpt-image-2.low.1k.v1"

    assert "ordinal" not in inspect.signature(service.reserve_or_replay).parameters
    assert "reserved_usd_nanos" not in inspect.signature(service.reserve_or_replay).parameters
    with pytest.raises(ProviderCostContractError) as unknown_operation:
        await service.reserve_or_replay(
            tenant_id=TENANT_ID,
            account_id=account["account_id"],
            operation_key="fast.image.unknown",
            attempt_fingerprint=FINGERPRINT_B,
        )
    assert unknown_operation.value.code == "provider_cost_rule_unavailable"

    definition = _operation_definition()
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        definition.provider = "deepseek"
    with pytest.raises(ProviderCostContractError):
        api.ProviderCostService(
            repository=ProviderCostRepository(require_postgres=False),
            price_catalog=ProviderPriceCatalog.load_default(),
            operation_registry={OPERATION_KEY: {"provider": "poyo"}},
        )


def test_factory_keeps_repository_catalog_registry_and_clock_injectable() -> None:
    api = _api()
    repository = ProviderCostRepository(require_postgres=False)
    catalog = ProviderPriceCatalog.load_default()
    clock = _Clock()
    definition = _operation_definition()

    service = api.build_provider_cost_service(
        operation_registry={OPERATION_KEY: definition},
        repository=repository,
        price_catalog=catalog,
        clock=clock,
    )

    assert service._repository is repository
    assert service._price_catalog is catalog
    assert service._clock is clock


@pytest.mark.asyncio
async def test_new_ordinal_requires_frozen_trusted_regeneration_epoch(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    api = _api()
    service = _service()
    account = await _account(service)
    await _reserve(service, account["account_id"])

    with pytest.raises(ProviderCostContractError) as no_epoch:
        await _reserve(
            service,
            account["account_id"],
            fingerprint=FINGERPRINT_B,
        )
    assert no_epoch.value.code == "provider_cost_attempt_conflict"

    for raw_epoch in (1, {"epoch_ref": "regen-001"}):
        with pytest.raises(ProviderCostContractError) as invalid_epoch:
            await _reserve(
                service,
                account["account_id"],
                fingerprint=FINGERPRINT_B,
                regeneration_epoch=raw_epoch,
            )
        assert invalid_epoch.value.code == "provider_cost_attempt_conflict"

    epoch = api.TrustedRegenerationEpoch(
        operation_key=OPERATION_KEY,
        epoch_ref="regen-001",
    )
    regenerated = await _reserve(
        service,
        account["account_id"],
        fingerprint=FINGERPRINT_B,
        regeneration_epoch=epoch,
    )
    assert regenerated.outcome == "owner"
    assert regenerated.attempt["ordinal"] == 1
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        epoch.epoch_ref = "regen-002"


@pytest.mark.asyncio
async def test_twenty_concurrent_reserves_have_one_owner_and_nineteen_replays(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    account = await _account(service)

    results = await asyncio.gather(*[_reserve(service, account["account_id"]) for _ in range(20)])

    assert [result.outcome for result in results].count("owner") == 1
    assert [result.outcome for result in results].count("replay") == 19
    assert len({result.attempt["attempt_id"] for result in results}) == 1


@pytest.mark.asyncio
async def test_exact_state_machine_settles_and_terminal_replay_is_read_only(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]

    started = await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )
    assert started["attempt"]["state"] == "submission_started"
    submitted = await service.mark_submitted(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        external_task_id="task-safe-001",
        provider_trace_id="trace-safe-001",
    )
    assert submitted["attempt"]["state"] == "submitted"

    facts = ImageCountBillingFacts(schema_version="image_count.v1", image_count=1)
    settled = await service.settle(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        expected_state="submitted",
        settlement_billing_facts=facts,
    )
    replay = await service.settle(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        expected_state="submitted",
        settlement_billing_facts=facts,
    )
    assert replay == settled
    assert settled["attempt"]["state"] == "settled"
    assert settled["account"]["reserved_usd_nanos"] == 0
    assert settled["account"]["settled_usd_nanos"] == 10_000_000

    before = sqlite_cost_db.total_changes
    with pytest.raises(ProviderCostContractError) as stale:
        await service.release(
            tenant_id=TENANT_ID,
            attempt_id=attempt_id,
            expected_state="submission_started",
        )
    assert stale.value.code == "provider_cost_attempt_conflict"
    assert sqlite_cost_db.total_changes == before


@pytest.mark.asyncio
async def test_submitted_state_requires_a_runtime_valid_external_task_id(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]
    await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )

    with pytest.raises(ProviderCostContractError) as exc_info:
        await service.mark_submitted(
            tenant_id=TENANT_ID,
            attempt_id=attempt_id,
            external_task_id=None,  # type: ignore[arg-type]
        )
    assert exc_info.value.code == "provider_cost_usage_invalid"
    stored = await service.get_attempt(tenant_id=TENANT_ID, attempt_id=attempt_id)
    assert stored is not None
    assert stored["state"] == "submission_started"


@pytest.mark.asyncio
async def test_settlement_below_reservation_refunds_exact_difference(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service(image_count=2)
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]
    await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )

    settled = await service.settle(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        expected_state="submission_started",
        settlement_billing_facts=ImageCountBillingFacts(
            schema_version="image_count.v1",
            image_count=1,
        ),
    )

    assert settled["attempt"]["reserved_usd_nanos"] == 20_000_000
    assert settled["attempt"]["settled_usd_nanos"] == 10_000_000
    assert settled["account"]["reserved_usd_nanos"] == 0
    assert settled["account"]["settled_usd_nanos"] == 10_000_000


@pytest.mark.asyncio
async def test_settlement_over_reservation_holds_full_amount_as_accounting_error(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service(image_count=1)
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]
    await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )

    held = await service.settle(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
        expected_state="submission_started",
        settlement_billing_facts=ImageCountBillingFacts(
            schema_version="image_count.v1",
            image_count=2,
        ),
    )

    assert held["attempt"]["state"] == "accounting_error"
    assert held["attempt"]["settled_usd_nanos"] == 0
    assert held["attempt"]["settlement_billing_facts"]["image_count"] == 2
    assert held["attempt"]["safe_error_code"] == "provider_cost_accounting_error"
    assert held["account"]["reserved_usd_nanos"] == 10_000_000
    assert held["account"]["settled_usd_nanos"] == 0


@pytest.mark.asyncio
async def test_only_expired_pre_submit_reserved_attempt_is_auto_released(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    clock = _Clock()
    service = _service(clock=clock)
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]

    clock.current += timedelta(minutes=6)
    released = await service.release_expired_reserved(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )
    assert released["attempt"]["state"] == "released"
    assert released["account"]["reserved_usd_nanos"] == 0

    for held_state in (
        "submission_started",
        "submitted",
        "ambiguous",
        "accounting_error",
    ):
        held_clock = _Clock(CHECKED_AT)
        held_service = _service(clock=held_clock)
        held_account = await _account(
            held_service,
            identity=_identity(job_id=f"fast-task-held-{held_state}"),
        )
        held_reserved = await _reserve(held_service, held_account["account_id"])
        held_attempt_id = held_reserved.attempt["attempt_id"]
        await held_service.mark_submission_started(
            tenant_id=TENANT_ID,
            attempt_id=held_attempt_id,
        )
        if held_state == "submitted":
            await held_service.mark_submitted(
                tenant_id=TENANT_ID,
                attempt_id=held_attempt_id,
                external_task_id="task-safe-held",
            )
        elif held_state == "ambiguous":
            await held_service.mark_ambiguous(
                tenant_id=TENANT_ID,
                attempt_id=held_attempt_id,
                expected_state="submission_started",
            )
        elif held_state == "accounting_error":
            await held_service.mark_accounting_error(
                tenant_id=TENANT_ID,
                attempt_id=held_attempt_id,
                expected_state="submission_started",
            )
        held_clock.current += timedelta(minutes=6)
        held = await held_service.release_expired_reserved(
            tenant_id=TENANT_ID,
            attempt_id=held_attempt_id,
        )
        assert held["attempt"]["state"] == held_state
        assert held["account"]["reserved_usd_nanos"] == 10_000_000


@pytest.mark.asyncio
async def test_release_ambiguous_and_accounting_error_keep_exact_conservation(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()

    released_account = await _account(
        service,
        identity=_identity(job_id="fast-task-release"),
    )
    released_reservation = await _reserve(service, released_account["account_id"])
    released_id = released_reservation.attempt["attempt_id"]
    await service.mark_submission_started(tenant_id=TENANT_ID, attempt_id=released_id)
    released = await service.release(
        tenant_id=TENANT_ID,
        attempt_id=released_id,
        expected_state="submission_started",
    )
    assert released["attempt"]["state"] == "released"
    assert released["account"]["reserved_usd_nanos"] == 0

    ambiguous_account = await _account(
        service,
        identity=_identity(job_id="fast-task-ambiguous"),
    )
    ambiguous_reservation = await _reserve(service, ambiguous_account["account_id"])
    ambiguous_id = ambiguous_reservation.attempt["attempt_id"]
    await service.mark_submission_started(tenant_id=TENANT_ID, attempt_id=ambiguous_id)
    ambiguous = await service.mark_ambiguous(
        tenant_id=TENANT_ID,
        attempt_id=ambiguous_id,
        expected_state="submission_started",
        provider_trace_id="trace-safe-ambiguous",
    )
    assert ambiguous["attempt"]["state"] == "ambiguous"
    assert ambiguous["account"]["reserved_usd_nanos"] == 10_000_000

    error_account = await _account(
        service,
        identity=_identity(job_id="fast-task-accounting-error"),
    )
    error_reservation = await _reserve(service, error_account["account_id"])
    error_id = error_reservation.attempt["attempt_id"]
    await service.mark_submission_started(tenant_id=TENANT_ID, attempt_id=error_id)
    accounting_error = await service.mark_accounting_error(
        tenant_id=TENANT_ID,
        attempt_id=error_id,
        expected_state="submission_started",
    )
    assert accounting_error["attempt"]["state"] == "accounting_error"
    assert accounting_error["account"]["reserved_usd_nanos"] == 10_000_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_id",
    [
        "https://provider.example/tasks/123",
        "/tmp/provider-response.json",
        '{"task_id":"123"}',
        "provider said request body was invalid",
    ],
)
async def test_external_task_and_trace_ids_reject_urls_paths_bodies_and_messages(
    sqlite_cost_db: sqlite3.Connection,
    unsafe_id: str,
) -> None:
    service = _service()
    account = await _account(
        service,
        identity=_identity(job_id=f"fast-task-unsafe-{abs(hash(unsafe_id))}"),
    )
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]
    await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )

    with pytest.raises(ProviderCostContractError) as exc_info:
        await service.mark_submitted(
            tenant_id=TENANT_ID,
            attempt_id=attempt_id,
            external_task_id=unsafe_id,
            provider_trace_id="trace-safe-001",
        )
    assert exc_info.value.code == "provider_cost_usage_invalid"
    stored = await service.get_attempt(tenant_id=TENANT_ID, attempt_id=attempt_id)
    assert stored is not None
    assert stored["state"] == "submission_started"
    assert stored["external_task_id"] is None


@pytest.mark.asyncio
async def test_provider_trace_id_uses_the_same_bounded_identifier_allowlist(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]
    await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )

    with pytest.raises(ProviderCostContractError) as exc_info:
        await service.mark_submitted(
            tenant_id=TENANT_ID,
            attempt_id=attempt_id,
            external_task_id="task-safe-001",
            provider_trace_id="https://provider.example/traces/123",
        )
    assert exc_info.value.code == "provider_cost_usage_invalid"
    stored = await service.get_attempt(tenant_id=TENANT_ID, attempt_id=attempt_id)
    assert stored is not None
    assert stored["state"] == "submission_started"
    assert stored["provider_trace_id"] is None


@pytest.mark.asyncio
async def test_restart_replays_durable_attempt_without_new_ordinal(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    first = _service()
    account = await _account(first)
    reserved = await _reserve(first, account["account_id"])
    await first.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=reserved.attempt["attempt_id"],
    )

    restarted = _service()
    replay = await _reserve(restarted, account["account_id"])
    stored = await restarted.get_attempt(
        tenant_id=TENANT_ID,
        attempt_id=reserved.attempt["attempt_id"],
    )
    assert replay.outcome == "replay"
    assert replay.attempt["attempt_id"] == reserved.attempt["attempt_id"]
    assert replay.attempt["ordinal"] == 0
    assert stored is not None
    assert stored["state"] == "submission_started"
    assert sqlite_cost_db.execute("SELECT COUNT(*) FROM provider_cost_attempts").fetchone()[0] == 1


@pytest.mark.asyncio
async def test_transition_failure_rolls_back_account_and_attempt_atomically(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    service = _service()
    account = await _account(service)
    reserved = await _reserve(service, account["account_id"])
    attempt_id = reserved.attempt["attempt_id"]
    await service.mark_submission_started(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )
    sqlite_cost_db.execute(
        """
        CREATE TRIGGER fail_provider_cost_settle
        BEFORE UPDATE ON provider_cost_attempts
        WHEN NEW.state = 'settled'
        BEGIN
            SELECT RAISE(ABORT, 'injected attempt update failure');
        END
        """
    )
    sqlite_cost_db.commit()

    with pytest.raises(ProviderCostContractError) as exc_info:
        await service.settle(
            tenant_id=TENANT_ID,
            attempt_id=attempt_id,
            expected_state="submission_started",
            settlement_billing_facts=ImageCountBillingFacts(
                schema_version="image_count.v1",
                image_count=1,
            ),
        )
    assert exc_info.value.code == "provider_cost_store_unavailable"

    stored_account = await service.get_account(
        tenant_id=TENANT_ID,
        account_id=account["account_id"],
    )
    stored_attempt = await service.get_attempt(
        tenant_id=TENANT_ID,
        attempt_id=attempt_id,
    )
    assert stored_account is not None
    assert stored_attempt is not None
    assert stored_account["reserved_usd_nanos"] == 10_000_000
    assert stored_account["settled_usd_nanos"] == 0
    assert stored_attempt["state"] == "submission_started"
    assert stored_attempt["settled_usd_nanos"] == 0


def test_service_source_contains_no_provider_mutation_http_or_retry() -> None:
    _api()
    source = Path("src/services/provider_cost.py").read_text(encoding="utf-8")

    for forbidden in (
        "httpx",
        "requests.",
        "PoyoClient",
        "SeedanceClient",
        "LLMClient",
        "CosyVoice",
        "@retry",
        "retry(",
    ):
        assert forbidden not in source
