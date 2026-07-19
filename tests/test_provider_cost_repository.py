"""W1-27/W1-30 durable provider-cost schema and repository contracts.

All executed database mutations in this module use an isolated SQLite file or
an injected failing PostgreSQL boundary. No production database or provider is
contacted.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.models.provider_cost import (
    LLMTokensBillingFacts,
    ProviderCostAccountIdentity,
    ProviderCostContractError,
)
from src.storage import db as db_module

TENANT_ID = "tenant-cost-alpha"
CHECKED_AT = datetime(2026, 7, 15, 17, 1, 24, tzinfo=UTC)
FINGERPRINT = "a" * 64


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
        str(tmp_path / "provider-cost.db"),
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    _install_sqlite_connection(connection, monkeypatch)
    db_module._create_sqlite_tables()
    yield connection
    connection.close()


def _account_identity(
    *,
    tenant_id: str = TENANT_ID,
    job_id: str = "fast-task-001",
) -> ProviderCostAccountIdentity:
    return ProviderCostAccountIdentity(
        tenant_id=tenant_id,
        job_kind="canonical",
        job_id=job_id,
        scenario_or_resource_type="fast",
        budget_source_kind="server_config",
        budget_source_ref=None,
        budget_policy_version="provider-budget.v1",
    )


def _reservation_facts() -> LLMTokensBillingFacts:
    return LLMTokensBillingFacts(
        schema_version="llm_tokens.v1",
        input_tokens=100,
        input_cache_hit_tokens=0,
        input_cache_miss_tokens=100,
        output_tokens=20,
        total_tokens=120,
    )


def _reserve_kwargs(
    *,
    account_id: str,
    tenant_id: str = TENANT_ID,
    fingerprint: str = FINGERPRINT,
    start_new_epoch: bool = False,
    regeneration_epoch_ref: str | None = None,
    reserved_usd_nanos: int = 100_000_000,
) -> dict[str, object]:
    return {
        "tenant_id": tenant_id,
        "account_id": account_id,
        "logical_operation": "fast.script.primary",
        "attempt_fingerprint": fingerprint,
        "start_new_epoch": start_new_epoch,
        "regeneration_epoch_ref": regeneration_epoch_ref,
        "provider": "deepseek",
        "canonical_model": "deepseek-v4-flash",
        "provider_billing_region": "deepseek_global_usd",
        "catalog_operation": "chat_completion",
        "media_type": "text",
        "billing_fact_kind": "llm_tokens.v1",
        "price_rule_id": "deepseek.deepseek-v4-flash.chat-completion.v1",
        "price_catalog_version": "provider-cost-catalog.2026-07-15.v1",
        "price_rule_version": "v1",
        "reservation_billing_facts": _reservation_facts(),
        "reserved_usd_nanos": reserved_usd_nanos,
        "reservation_expires_at": CHECKED_AT + timedelta(minutes=5),
    }


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _table_indexes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA index_list({table})").fetchall()}


def test_sqlite_schema_has_exact_account_and_attempt_surfaces(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    account_columns = {
        "account_id",
        "tenant_id",
        "job_kind",
        "job_id",
        "scenario_or_resource_type",
        "cap_usd_nanos",
        "reserved_usd_nanos",
        "settled_usd_nanos",
        "budget_source_kind",
        "budget_source_ref",
        "budget_policy_version",
        "created_at",
        "updated_at",
    }
    attempt_columns = {
        "attempt_id",
        "account_id",
        "tenant_id",
        "job_kind",
        "job_id",
        "scenario_or_resource_type",
        "logical_operation",
        "ordinal",
        "attempt_fingerprint",
        "regeneration_epoch_ref",
        "provider",
        "canonical_model",
        "provider_billing_region",
        "catalog_operation",
        "media_type",
        "billing_fact_kind",
        "price_rule_id",
        "price_catalog_version",
        "price_rule_version",
        "reservation_billing_facts",
        "settlement_billing_facts",
        "reserved_usd_nanos",
        "settled_usd_nanos",
        "provider_reported_cost_usd_nanos",
        "provider_reported_credit_micro_units",
        "provider_reported_currency",
        "state",
        "external_task_id",
        "provider_trace_id",
        "safe_error_code",
        "reservation_expires_at",
        "submission_started_at",
        "submitted_at",
        "terminal_at",
        "created_at",
        "updated_at",
    }
    assert _table_columns(sqlite_cost_db, "job_budget_accounts") == account_columns
    assert _table_columns(sqlite_cost_db, "provider_cost_attempts") == attempt_columns
    assert {
        "sqlite_autoindex_job_budget_accounts_1",
        "sqlite_autoindex_job_budget_accounts_2",
    } <= _table_indexes(sqlite_cost_db, "job_budget_accounts")
    assert {
        "sqlite_autoindex_provider_cost_attempts_1",
        "sqlite_autoindex_provider_cost_attempts_2",
        "idx_provider_cost_attempts_account_state",
        "idx_provider_cost_attempts_reservation_expiry",
    } <= _table_indexes(sqlite_cost_db, "provider_cost_attempts")


def test_migration_and_fresh_postgres_schema_are_exactly_additive() -> None:
    migration_path = Path("migrations/alembic/versions/b7c8d9e0f1a2_add_provider_cost_ledger.py")
    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert 'revision: str = "b7c8d9e0f1a2"' in migration
    assert 'down_revision: str | None = "a6b7c8d9e0f1"' in migration
    assert migration.index('op.create_table(\n        "job_budget_accounts"') < migration.index(
        'op.create_table(\n        "provider_cost_attempts"'
    )
    assert migration.index('op.drop_table("provider_cost_attempts")') < migration.index(
        'op.drop_table("job_budget_accounts")'
    )
    for constraint in (
        "uq_job_budget_accounts_tenant_job",
        "ck_job_budget_accounts_conservation",
        "uq_provider_cost_attempts_operation_ordinal",
        "ck_provider_cost_attempts_state",
        "ck_provider_cost_attempts_state_fields",
        "fk_provider_cost_attempts_account",
    ):
        assert constraint in migration

    fresh = Path("src/storage/migrations/001_init.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS job_budget_accounts" in fresh
    assert "CREATE TABLE IF NOT EXISTS provider_cost_attempts" in fresh
    assert fresh.index("CREATE TABLE IF NOT EXISTS job_budget_accounts") < fresh.index(
        "CREATE TABLE IF NOT EXISTS provider_cost_attempts"
    )
    assert "REFERENCES job_budget_accounts(account_id) ON DELETE RESTRICT" in fresh


def test_db_readiness_requires_both_cost_tables_and_critical_columns() -> None:
    assert {"job_budget_accounts", "provider_cost_attempts"} <= set(db_module._REQUIRED_TABLES)
    assert {
        "account_id",
        "cap_usd_nanos",
        "reserved_usd_nanos",
        "settled_usd_nanos",
    } <= db_module._REQUIRED_TABLE_COLUMNS["job_budget_accounts"]
    assert {
        "attempt_id",
        "account_id",
        "attempt_fingerprint",
        "regeneration_epoch_ref",
        "reservation_billing_facts",
        "state",
    } <= db_module._REQUIRED_TABLE_COLUMNS["provider_cost_attempts"]


class _FakeInformationSchemaConnection:
    def __init__(self, columns: dict[str, set[str]]) -> None:
        self._columns = columns

    async def fetch(self, _query: str, table: str) -> list[dict[str, str]]:
        return [{"column_name": column} for column in self._columns.get(table, set())]


@pytest.mark.asyncio
async def test_pg_readiness_rejects_legacy_attempt_schema_until_epoch_column_exists() -> None:
    columns = {table: set(required) for table, required in db_module._REQUIRED_TABLE_COLUMNS.items()}
    columns["provider_cost_attempts"].remove("regeneration_epoch_ref")
    legacy_connection = _FakeInformationSchemaConnection(columns)

    assert await db_module._verify_required_columns(legacy_connection) is False

    columns["provider_cost_attempts"].add("regeneration_epoch_ref")
    upgraded_connection = _FakeInformationSchemaConnection(columns)
    assert await db_module._verify_required_columns(upgraded_connection) is True


@pytest.mark.asyncio
async def test_account_create_is_idempotent_and_conflicting_authority_fails(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    replay = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    assert replay == account
    assert account["reserved_usd_nanos"] == 0
    assert account["settled_usd_nanos"] == 0

    with pytest.raises(ProviderCostContractError) as exc_info:
        await repository.create_or_get_account(
            identity=_account_identity(),
            cap_usd_nanos=2_000_000_000,
        )
    assert exc_info.value.code == "provider_cost_attempt_conflict"


@pytest.mark.asyncio
async def test_reserve_replay_conflict_new_epoch_and_conservation_are_atomic(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=300_000_000,
    )
    owner = await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    assert owner.outcome == "owner"
    assert owner.attempt["ordinal"] == 0
    assert owner.attempt["state"] == "reserved"
    assert owner.account["reserved_usd_nanos"] == 100_000_000

    replay = await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    assert replay.outcome == "replay"
    assert replay.attempt["attempt_id"] == owner.attempt["attempt_id"]
    assert replay.account["reserved_usd_nanos"] == 100_000_000

    with pytest.raises(ProviderCostContractError) as conflict:
        await repository.reserve_or_replay(
            **_reserve_kwargs(
                account_id=account["account_id"],
                fingerprint="b" * 64,
            )
        )
    assert conflict.value.code == "provider_cost_attempt_conflict"

    regenerated = await repository.reserve_or_replay(
        **_reserve_kwargs(
            account_id=account["account_id"],
            fingerprint="b" * 64,
            start_new_epoch=True,
            regeneration_epoch_ref="regen-repository-001",
        )
    )
    assert regenerated.outcome == "owner"
    assert regenerated.attempt["ordinal"] == 1
    assert regenerated.account["reserved_usd_nanos"] == 200_000_000

    with pytest.raises(ProviderCostContractError) as exhausted:
        await repository.reserve_or_replay(
            **_reserve_kwargs(
                account_id=account["account_id"],
                fingerprint="c" * 64,
                start_new_epoch=True,
                regeneration_epoch_ref="regen-repository-002",
                reserved_usd_nanos=100_000_001,
            )
        )
    assert exhausted.value.code == "provider_budget_exhausted"
    durable = await repository.get_account(
        tenant_id=TENANT_ID,
        account_id=account["account_id"],
    )
    assert durable is not None
    assert durable["reserved_usd_nanos"] == 200_000_000
    assert sqlite_cost_db.execute("SELECT COUNT(*) FROM provider_cost_attempts").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_regeneration_epoch_is_single_use_per_logical_operation(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=300_000_000,
    )
    epoch_ref = "regen-repository-single-use"

    first = await repository.reserve_or_replay(
        **_reserve_kwargs(
            account_id=account["account_id"],
            fingerprint="a" * 64,
            start_new_epoch=True,
            regeneration_epoch_ref=epoch_ref,
        )
    )
    assert first.outcome == "owner"
    assert first.attempt["ordinal"] == 0
    assert first.attempt["regeneration_epoch_ref"] == epoch_ref

    with pytest.raises(ProviderCostContractError) as immutable_conflict:
        await repository.reserve_or_replay(
            **_reserve_kwargs(
                account_id=account["account_id"],
                fingerprint="a" * 64,
                start_new_epoch=True,
                regeneration_epoch_ref="regen-repository-conflicting-ref",
            )
        )
    assert immutable_conflict.value.code == "provider_cost_attempt_conflict"

    with pytest.raises(ProviderCostContractError) as reused:
        await repository.reserve_or_replay(
            **_reserve_kwargs(
                account_id=account["account_id"],
                fingerprint="b" * 64,
                start_new_epoch=True,
                regeneration_epoch_ref=epoch_ref,
            )
        )
    assert reused.value.code == "provider_cost_attempt_conflict"

    second = await repository.reserve_or_replay(
        **_reserve_kwargs(
            account_id=account["account_id"],
            fingerprint="b" * 64,
            start_new_epoch=True,
            regeneration_epoch_ref="regen-repository-single-use-002",
        )
    )
    assert second.outcome == "owner"
    assert second.attempt["ordinal"] == 1
    assert sqlite_cost_db.execute("SELECT COUNT(*) FROM provider_cost_attempts").fetchone()[0] == 2


@pytest.mark.asyncio
async def test_twenty_way_same_fingerprint_has_one_owner_and_nineteen_replays(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    results = await asyncio.gather(
        *(repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"])) for _ in range(20))
    )
    assert [result.outcome for result in results].count("owner") == 1
    assert [result.outcome for result in results].count("replay") == 19
    assert len({result.attempt["attempt_id"] for result in results}) == 1
    durable = await repository.get_account(
        tenant_id=TENANT_ID,
        account_id=account["account_id"],
    )
    assert durable is not None
    assert durable["reserved_usd_nanos"] == 100_000_000


@pytest.mark.asyncio
async def test_terminal_transition_is_idempotent_and_conflict_rolls_back(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    reserved = await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    started = await repository.transition_attempt(
        tenant_id=TENANT_ID,
        attempt_id=reserved.attempt["attempt_id"],
        expected_state="reserved",
        new_state="submission_started",
    )
    assert started["attempt"]["state"] == "submission_started"

    settled = await repository.transition_attempt(
        tenant_id=TENANT_ID,
        attempt_id=reserved.attempt["attempt_id"],
        expected_state="submission_started",
        new_state="settled",
        settlement_billing_facts=_reservation_facts(),
        settled_usd_nanos=80_000_000,
        provider_trace_id="trace_fixture_001",
    )
    assert settled["attempt"]["state"] == "settled"
    assert settled["attempt"]["settled_usd_nanos"] == 80_000_000
    assert settled["account"]["reserved_usd_nanos"] == 0
    assert settled["account"]["settled_usd_nanos"] == 80_000_000

    replay = await repository.transition_attempt(
        tenant_id=TENANT_ID,
        attempt_id=reserved.attempt["attempt_id"],
        expected_state="submission_started",
        new_state="settled",
        settlement_billing_facts=_reservation_facts(),
        settled_usd_nanos=80_000_000,
        provider_trace_id="trace_fixture_001",
    )
    assert replay == settled

    with pytest.raises(ProviderCostContractError) as conflict:
        await repository.transition_attempt(
            tenant_id=TENANT_ID,
            attempt_id=reserved.attempt["attempt_id"],
            expected_state="submission_started",
            new_state="settled",
            settlement_billing_facts=_reservation_facts(),
            settled_usd_nanos=80_000_001,
            provider_trace_id="trace_fixture_001",
        )
    assert conflict.value.code == "provider_cost_attempt_conflict"
    durable = await repository.get_account(
        tenant_id=TENANT_ID,
        account_id=account["account_id"],
    )
    assert durable == settled["account"]


@pytest.mark.asyncio
async def test_tenant_isolation_malformed_json_and_parent_delete_fail_closed(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    reserved = await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    assert (
        await repository.get_attempt(
            tenant_id="tenant-cost-other",
            attempt_id=reserved.attempt["attempt_id"],
        )
        is None
    )
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_cost_db.execute(
            "DELETE FROM job_budget_accounts WHERE account_id = ?",
            (account["account_id"],),
        )
    sqlite_cost_db.rollback()

    sqlite_cost_db.execute(
        "UPDATE provider_cost_attempts SET reservation_billing_facts = ? WHERE attempt_id = ?",
        ("{", reserved.attempt["attempt_id"]),
    )
    sqlite_cost_db.commit()
    with pytest.raises(ProviderCostContractError) as malformed:
        await repository.get_attempt(
            tenant_id=TENANT_ID,
            attempt_id=reserved.attempt["attempt_id"],
        )
    assert malformed.value.code == "provider_cost_store_unavailable"


@pytest.mark.asyncio
async def test_repository_rejects_naive_expiry_and_unknown_safe_error_code(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    invalid_expiry = _reserve_kwargs(account_id=account["account_id"])
    invalid_expiry["reservation_expires_at"] = datetime(2026, 7, 16, 1, 0, 0)
    with pytest.raises(ProviderCostContractError) as expiry_error:
        await repository.reserve_or_replay(**invalid_expiry)
    assert expiry_error.value.code == "provider_cost_usage_invalid"

    invalid_epoch = _reserve_kwargs(
        account_id=account["account_id"],
        start_new_epoch=True,
    )
    with pytest.raises(ProviderCostContractError) as epoch_error:
        await repository.reserve_or_replay(**invalid_epoch)
    assert epoch_error.value.code == "provider_cost_usage_invalid"

    reserved = await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    await repository.transition_attempt(
        tenant_id=TENANT_ID,
        attempt_id=reserved.attempt["attempt_id"],
        expected_state="reserved",
        new_state="submission_started",
    )
    with pytest.raises(ProviderCostContractError) as safe_error:
        await repository.transition_attempt(
            tenant_id=TENANT_ID,
            attempt_id=reserved.attempt["attempt_id"],
            expected_state="submission_started",
            new_state="ambiguous",
            safe_error_code="fixture_unknown_error",
        )
    assert safe_error.value.code == "provider_cost_usage_invalid"


@pytest.mark.asyncio
async def test_malformed_stored_identity_is_store_unavailable(
    sqlite_cost_db: sqlite3.Connection,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    reserved = await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    sqlite_cost_db.execute(
        "UPDATE provider_cost_attempts SET job_id = ? WHERE attempt_id = ?",
        ("invalid stored job id", reserved.attempt["attempt_id"]),
    )
    sqlite_cost_db.commit()
    with pytest.raises(ProviderCostContractError) as exc_info:
        await repository.get_attempt(
            tenant_id=TENANT_ID,
            attempt_id=reserved.attempt["attempt_id"],
        )
    assert exc_info.value.code == "provider_cost_store_unavailable"


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        (
            "UPDATE job_budget_accounts SET cap_usd_nanos = 0 WHERE tenant_id = ?",
            (TENANT_ID,),
        ),
        (
            "UPDATE job_budget_accounts SET reserved_usd_nanos = cap_usd_nanos + 1 WHERE tenant_id = ?",
            (TENANT_ID,),
        ),
        (
            "UPDATE provider_cost_attempts SET state = 'unknown' WHERE tenant_id = ?",
            (TENANT_ID,),
        ),
        (
            "UPDATE provider_cost_attempts SET state = 'settled' WHERE tenant_id = ?",
            (TENANT_ID,),
        ),
        (
            "UPDATE provider_cost_attempts SET settled_usd_nanos = reserved_usd_nanos + 1 WHERE tenant_id = ?",
            (TENANT_ID,),
        ),
    ],
)
@pytest.mark.asyncio
async def test_sqlite_constraints_reject_invalid_money_state_and_projection(
    sqlite_cost_db: sqlite3.Connection,
    statement: str,
    parameters: tuple[object, ...],
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    repository = ProviderCostRepository(require_postgres=False)
    account = await repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    await repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_cost_db.execute(statement, parameters)
    sqlite_cost_db.rollback()


@pytest.mark.asyncio
async def test_existing_sqlite_restart_preserves_replay_and_conservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    path = tmp_path / "provider-cost-restart.db"
    first_connection = sqlite3.connect(str(path), check_same_thread=False)
    first_connection.row_factory = sqlite3.Row
    _install_sqlite_connection(first_connection, monkeypatch)
    db_module._create_sqlite_tables()
    first_repository = ProviderCostRepository(require_postgres=False)
    account = await first_repository.create_or_get_account(
        identity=_account_identity(),
        cap_usd_nanos=1_000_000_000,
    )
    owner = await first_repository.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    first_connection.close()

    second_connection = sqlite3.connect(str(path), check_same_thread=False)
    second_connection.row_factory = sqlite3.Row
    _install_sqlite_connection(second_connection, monkeypatch)
    db_module._create_sqlite_tables()
    restarted = ProviderCostRepository(require_postgres=False)
    replay = await restarted.reserve_or_replay(**_reserve_kwargs(account_id=account["account_id"]))
    assert replay.outcome == "replay"
    assert replay.attempt["attempt_id"] == owner.attempt["attempt_id"]
    assert replay.account["reserved_usd_nanos"] == 100_000_000
    second_connection.close()


@pytest.mark.asyncio
async def test_required_postgres_failure_never_falls_back_to_sqlite(
    sqlite_cost_db: sqlite3.Connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    def unavailable_pool() -> None:
        raise RuntimeError("fixture unavailable")

    monkeypatch.setattr(db_module, "get_verified_pg_pool", unavailable_pool)
    repository = ProviderCostRepository(require_postgres=True)
    with pytest.raises(ProviderCostContractError) as exc_info:
        await repository.create_or_get_account(
            identity=_account_identity(),
            cap_usd_nanos=1_000_000_000,
        )
    assert exc_info.value.code == "provider_cost_store_unavailable"
    assert sqlite_cost_db.execute("SELECT COUNT(*) FROM job_budget_accounts").fetchone()[0] == 0


def test_repository_source_freezes_lock_order_and_no_fallback_contract() -> None:
    source_path = Path("src/storage/provider_cost_repository.py")
    assert source_path.exists()
    source = source_path.read_text(encoding="utf-8")
    assert "BEGIN IMMEDIATE" in source
    assert "FOR UPDATE" in source
    assert source.index("job_budget_accounts") < source.index("provider_cost_attempts")
    assert "BaseRepository" not in source
    assert "cost_tracker" not in source
    assert "fallback" not in source.lower()
