"""Opt-in disposable PostgreSQL 18 checks for the provider-cost ledger.

The lane accepts only an explicit passwordless localhost DSN for the dedicated
``provider_cost_w1_27`` database. It never contacts production or a provider.
"""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

_PG18_DSN = os.getenv("PROVIDER_COST_PG18_DSN")
_PG18_DATABASE = "provider_cost_w1_27"
_PG18_HOST = "127.0.0.1"
_PG18_PORT = 55440
_PG18_USERNAME = "postgres"
_LANE_ERROR = "disposable provider-cost PostgreSQL 18 lane is not authorized"


def _validate_pg18_dsn(dsn: str | None) -> None:
    if not isinstance(dsn, str) or not dsn or dsn != dsn.strip():
        raise ValueError(_LANE_ERROR)
    try:
        parsed = urlsplit(dsn)
        port = parsed.port
    except (TypeError, ValueError):
        raise ValueError(_LANE_ERROR) from None
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname != _PG18_HOST
        or port != _PG18_PORT
        or parsed.path != f"/{_PG18_DATABASE}"
        or parsed.username != _PG18_USERNAME
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(_LANE_ERROR)


async def _verified_pool(dsn: str | None) -> asyncpg.Pool:
    _validate_pg18_dsn(dsn)
    assert dsn is not None
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=24)
    try:
        async with pool.acquire() as connection:
            identity = await connection.fetchrow(
                "SELECT current_database() AS database_name, "
                "current_setting('server_version_num') AS server_version_num"
            )
        if (
            identity is None
            or identity["database_name"] != _PG18_DATABASE
            or int(identity["server_version_num"]) // 10_000 != 18
        ):
            raise ValueError(_LANE_ERROR)
    except Exception:
        await pool.close()
        raise RuntimeError(_LANE_ERROR) from None
    return pool


pytestmark = [
    pytest.mark.hermetic_slow,
    pytest.mark.skipif(
        not _PG18_DSN,
        reason="requires explicit disposable PROVIDER_COST_PG18_DSN",
    ),
]


from src.models.provider_cost import (
    LLMTokensBillingFacts,
    ProviderCostAccountIdentity,
)
from src.storage import db


@dataclass(frozen=True)
class PG18Harness:
    pool: asyncpg.Pool
    tenant_prefix: str


@pytest_asyncio.fixture
async def pg18_harness(monkeypatch: pytest.MonkeyPatch) -> PG18Harness:
    pool = await _verified_pool(_PG18_DSN)
    tenant_prefix = "provider-cost-pg18-" + uuid4().hex[:12]
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "_pg_available", True)
    try:
        yield PG18Harness(pool=pool, tenant_prefix=tenant_prefix)
    finally:
        try:
            async with pool.acquire() as connection:
                await connection.execute(
                    "DELETE FROM provider_cost_attempts WHERE tenant_id LIKE $1",
                    tenant_prefix + "%",
                )
                await connection.execute(
                    "DELETE FROM job_budget_accounts WHERE tenant_id LIKE $1",
                    tenant_prefix + "%",
                )
        finally:
            await pool.close()


def _reserve_kwargs(*, tenant_id: str, account_id: str) -> dict[str, object]:
    return {
        "tenant_id": tenant_id,
        "account_id": account_id,
        "logical_operation": "fast.script.primary",
        "attempt_fingerprint": "a" * 64,
        "start_new_epoch": False,
        "regeneration_epoch_ref": None,
        "provider": "deepseek",
        "canonical_model": "deepseek-v4-flash",
        "provider_billing_region": "deepseek_global_usd",
        "catalog_operation": "chat_completion",
        "media_type": "text",
        "billing_fact_kind": "llm_tokens.v1",
        "price_rule_id": "deepseek.deepseek-v4-flash.chat-completion.v1",
        "price_catalog_version": "provider-cost-catalog.2026-07-15.v1",
        "price_rule_version": "v1",
        "reservation_billing_facts": LLMTokensBillingFacts(
            schema_version="llm_tokens.v1",
            input_tokens=100,
            input_cache_hit_tokens=0,
            input_cache_miss_tokens=100,
            output_tokens=20,
            total_tokens=120,
        ),
        "reserved_usd_nanos": 100_000_000,
        "reservation_expires_at": datetime.now(UTC) + timedelta(minutes=5),
    }


@pytest.mark.asyncio
async def test_real_pg18_schema_and_twenty_way_reserve_are_exact(
    pg18_harness: PG18Harness,
) -> None:
    from src.storage.provider_cost_repository import ProviderCostRepository

    tenant_id = pg18_harness.tenant_prefix + "-reserve"
    repository = ProviderCostRepository(require_postgres=True)
    account = await repository.create_or_get_account(
        identity=ProviderCostAccountIdentity(
            tenant_id=tenant_id,
            job_kind="canonical",
            job_id="fast-pg18-001",
            scenario_or_resource_type="fast",
            budget_source_kind="server_config",
            budget_source_ref=None,
            budget_policy_version="provider-budget.v1",
        ),
        cap_usd_nanos=1_000_000_000,
    )
    results = await asyncio.gather(
        *(
            repository.reserve_or_replay(
                **_reserve_kwargs(
                    tenant_id=tenant_id,
                    account_id=account["account_id"],
                )
            )
            for _ in range(20)
        )
    )
    assert [result.outcome for result in results].count("owner") == 1
    assert [result.outcome for result in results].count("replay") == 19
    assert len({result.attempt["attempt_id"] for result in results}) == 1

    attempt_id = results[0].attempt["attempt_id"]
    started = await repository.transition_attempt(
        tenant_id=tenant_id,
        attempt_id=attempt_id,
        expected_state="reserved",
        new_state="submission_started",
    )
    assert started["attempt"]["state"] == "submission_started"
    settled = await repository.transition_attempt(
        tenant_id=tenant_id,
        attempt_id=attempt_id,
        expected_state="submission_started",
        new_state="settled",
        settlement_billing_facts=results[0].attempt["reservation_billing_facts"],
        settled_usd_nanos=80_000_000,
        provider_trace_id="trace_pg18_fixture_001",
    )
    assert settled["attempt"]["state"] == "settled"
    assert settled["account"]["reserved_usd_nanos"] == 0
    assert settled["account"]["settled_usd_nanos"] == 80_000_000
    assert (
        await repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state="submission_started",
            new_state="settled",
            settlement_billing_facts=results[0].attempt["reservation_billing_facts"],
            settled_usd_nanos=80_000_000,
            provider_trace_id="trace_pg18_fixture_001",
        )
        == settled
    )

    async with pg18_harness.pool.acquire() as connection:
        columns = {
            row["column_name"]
            for row in await connection.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = $1",
                "provider_cost_attempts",
            )
        }
        assert {
            "attempt_id",
            "account_id",
            "attempt_fingerprint",
            "regeneration_epoch_ref",
            "reservation_billing_facts",
            "state",
        } <= columns
        totals = await connection.fetchrow(
            "SELECT reserved_usd_nanos, settled_usd_nanos FROM job_budget_accounts WHERE account_id = $1::uuid",
            account["account_id"],
        )
        assert totals is not None
        assert totals["reserved_usd_nanos"] == 0
        assert totals["settled_usd_nanos"] == 80_000_000


def test_pg18_lane_rejects_any_non_disposable_dsn() -> None:
    for dsn in (
        None,
        "postgresql://postgres@localhost:55440/provider_cost_w1_27",
        "postgresql://postgres@127.0.0.1:5432/provider_cost_w1_27",
        "postgresql://postgres:secret@127.0.0.1:55440/provider_cost_w1_27",
        "postgresql://postgres@127.0.0.1:55440/production",
    ):
        with pytest.raises(ValueError, match="not authorized"):
            _validate_pg18_dsn(dsn)
