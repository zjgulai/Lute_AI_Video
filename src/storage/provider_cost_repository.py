"""Atomic tenant-bound persistence for provider cost authority."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, NoReturn, get_args

import asyncpg
from pydantic import BaseModel, ValidationError

from src.models.provider_cost import (
    MAX_SIGNED_BIGINT,
    AttemptState,
    ProviderBillingFacts,
    ProviderCostAccountIdentity,
    ProviderCostAttemptIdentity,
    ProviderCostContractError,
    ProviderCostErrorCode,
    parse_billing_facts,
)

from . import db

logger = logging.getLogger(__name__)

ReserveOutcome = Literal["owner", "replay"]

_ATTEMPT_STATES = frozenset(
    {
        "reserved",
        "submission_started",
        "submitted",
        "settled",
        "released",
        "ambiguous",
        "accounting_error",
    }
)
_LEGAL_TRANSITIONS = frozenset(
    {
        ("reserved", "submission_started"),
        ("reserved", "released"),
        ("submission_started", "submitted"),
        ("submission_started", "settled"),
        ("submission_started", "released"),
        ("submission_started", "ambiguous"),
        ("submission_started", "accounting_error"),
        ("submitted", "settled"),
        ("submitted", "released"),
        ("submitted", "ambiguous"),
        ("submitted", "accounting_error"),
    }
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,159}$")
_SAFE_ERROR_CODES = frozenset(get_args(ProviderCostErrorCode))


@dataclass(frozen=True, slots=True)
class ProviderCostReserveResult:
    """Atomic result of owning or replaying one durable reservation."""

    outcome: ReserveOutcome
    account: dict[str, Any]
    attempt: dict[str, Any]


class ProviderCostRepository:
    """Persist account-first budget transitions with strict row normalization."""

    def __init__(self, *, require_postgres: bool | None = None) -> None:
        if require_postgres is None:
            environment = os.getenv("ENVIRONMENT", "development").strip().lower()
            require_postgres = environment in {"prod", "production"}
        self.require_postgres = require_postgres

    async def create_or_get_account(
        self,
        *,
        identity: ProviderCostAccountIdentity,
        cap_usd_nanos: int,
    ) -> dict[str, Any]:
        if not isinstance(identity, ProviderCostAccountIdentity):
            self._usage_error("account identity must be a strict model")
        self._require_positive_money(cap_usd_nanos, "account cap")
        account_id = str(uuid.uuid4())
        pool, connection = self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as pg_connection:
                    async with pg_connection.transaction():
                        row = await pg_connection.fetchrow(
                            """
                            INSERT INTO job_budget_accounts (
                                account_id, tenant_id, job_kind, job_id,
                                scenario_or_resource_type, cap_usd_nanos,
                                reserved_usd_nanos, settled_usd_nanos,
                                budget_source_kind, budget_source_ref,
                                budget_policy_version
                            ) VALUES (
                                $1::uuid, $2, $3, $4, $5, $6, 0, 0,
                                $7, $8, $9
                            )
                            ON CONFLICT (tenant_id, job_kind, job_id) DO NOTHING
                            RETURNING *
                            """,
                            account_id,
                            identity.tenant_id,
                            identity.job_kind,
                            identity.job_id,
                            identity.scenario_or_resource_type,
                            cap_usd_nanos,
                            identity.budget_source_kind,
                            identity.budget_source_ref,
                            identity.budget_policy_version,
                        )
                        if row is None:
                            row = await pg_connection.fetchrow(
                                """
                                SELECT * FROM job_budget_accounts
                                WHERE tenant_id = $1 AND job_kind = $2
                                  AND job_id = $3
                                FOR UPDATE
                                """,
                                identity.tenant_id,
                                identity.job_kind,
                                identity.job_id,
                            )
                        account = self._normalize_account(row)
                        self._require_same_account_authority(
                            account,
                            identity=identity,
                            cap_usd_nanos=cap_usd_nanos,
                        )
                        return account
            if connection is None:
                self._store_error("SQLite connection is unavailable")
            return await asyncio.to_thread(
                self._create_or_get_account_sqlite,
                connection,
                account_id,
                identity,
                cap_usd_nanos,
            )
        except ProviderCostContractError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def reserve_or_replay(
        self,
        *,
        tenant_id: str,
        account_id: str,
        logical_operation: str,
        attempt_fingerprint: str,
        start_new_epoch: bool,
        regeneration_epoch_ref: str | None,
        provider: str,
        canonical_model: str,
        provider_billing_region: str,
        catalog_operation: str,
        media_type: str,
        billing_fact_kind: str,
        price_rule_id: str,
        price_catalog_version: str,
        price_rule_version: str,
        reservation_billing_facts: object,
        reserved_usd_nanos: int,
        reservation_expires_at: datetime,
    ) -> ProviderCostReserveResult:
        normalized = self._validate_reservation_input(
            tenant_id=tenant_id,
            account_id=account_id,
            logical_operation=logical_operation,
            attempt_fingerprint=attempt_fingerprint,
            start_new_epoch=start_new_epoch,
            regeneration_epoch_ref=regeneration_epoch_ref,
            provider=provider,
            canonical_model=canonical_model,
            provider_billing_region=provider_billing_region,
            catalog_operation=catalog_operation,
            media_type=media_type,
            billing_fact_kind=billing_fact_kind,
            price_rule_id=price_rule_id,
            price_catalog_version=price_catalog_version,
            price_rule_version=price_rule_version,
            reservation_billing_facts=reservation_billing_facts,
            reserved_usd_nanos=reserved_usd_nanos,
            reservation_expires_at=reservation_expires_at,
        )
        attempt_id = str(uuid.uuid4())
        pool, connection = self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as pg_connection:
                    async with pg_connection.transaction():
                        return await self._reserve_postgres(
                            pg_connection,
                            attempt_id=attempt_id,
                            normalized=normalized,
                        )
            if connection is None:
                self._store_error("SQLite connection is unavailable")
            return await asyncio.to_thread(
                self._reserve_sqlite,
                connection,
                attempt_id,
                normalized,
            )
        except ProviderCostContractError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def transition_attempt(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_state: AttemptState,
        new_state: AttemptState,
        settlement_billing_facts: object | None = None,
        settled_usd_nanos: int = 0,
        provider_reported_cost_usd_nanos: int | None = None,
        provider_reported_credit_micro_units: int | None = None,
        provider_reported_currency: str | None = None,
        external_task_id: str | None = None,
        provider_trace_id: str | None = None,
        safe_error_code: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        transition = self._validate_transition_input(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state=expected_state,
            new_state=new_state,
            settlement_billing_facts=settlement_billing_facts,
            settled_usd_nanos=settled_usd_nanos,
            provider_reported_cost_usd_nanos=provider_reported_cost_usd_nanos,
            provider_reported_credit_micro_units=provider_reported_credit_micro_units,
            provider_reported_currency=provider_reported_currency,
            external_task_id=external_task_id,
            provider_trace_id=provider_trace_id,
            safe_error_code=safe_error_code,
        )
        pool, connection = self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as pg_connection:
                    async with pg_connection.transaction():
                        return await self._transition_postgres(
                            pg_connection,
                            transition,
                        )
            if connection is None:
                self._store_error("SQLite connection is unavailable")
            return await asyncio.to_thread(
                self._transition_sqlite,
                connection,
                transition,
            )
        except ProviderCostContractError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def get_account(
        self,
        *,
        tenant_id: str,
        account_id: str,
    ) -> dict[str, Any] | None:
        self._require_safe_id(tenant_id, "tenant ID")
        self._require_uuid4(account_id, "account ID")
        pool, connection = self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as pg_connection:
                    row = await pg_connection.fetchrow(
                        "SELECT * FROM job_budget_accounts WHERE tenant_id = $1 AND account_id = $2::uuid",
                        tenant_id,
                        account_id,
                    )
            else:
                if connection is None:
                    self._store_error("SQLite connection is unavailable")
                row = await asyncio.to_thread(
                    self._fetch_one_sqlite,
                    connection,
                    "SELECT * FROM job_budget_accounts WHERE tenant_id = ? AND account_id = ?",
                    (tenant_id, account_id),
                )
            return self._normalize_account(row) if row is not None else None
        except ProviderCostContractError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def get_account_by_job_identity(
        self,
        *,
        tenant_id: str,
        job_kind: str,
        job_id: str,
    ) -> dict[str, Any] | None:
        """Return one tenant-bound account by its immutable composite identity."""

        self._require_safe_id(tenant_id, "tenant ID")
        if type(job_kind) is not str or job_kind not in {"canonical", "compatibility"}:
            self._usage_error("budget job kind is invalid")
        self._require_safe_id(job_id, "budget job ID")
        pool, connection = self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as pg_connection:
                    row = await pg_connection.fetchrow(
                        "SELECT * FROM job_budget_accounts WHERE tenant_id = $1 AND job_kind = $2 AND job_id = $3",
                        tenant_id,
                        job_kind,
                        job_id,
                    )
            else:
                if connection is None:
                    self._store_error("SQLite connection is unavailable")
                row = await asyncio.to_thread(
                    self._fetch_one_sqlite,
                    connection,
                    "SELECT * FROM job_budget_accounts WHERE tenant_id = ? AND job_kind = ? AND job_id = ?",
                    (tenant_id, job_kind, job_id),
                )
            return self._normalize_account(row) if row is not None else None
        except ProviderCostContractError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def get_attempt(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        self._require_safe_id(tenant_id, "tenant ID")
        self._require_uuid4(attempt_id, "attempt ID")
        pool, connection = self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as pg_connection:
                    row = await pg_connection.fetchrow(
                        "SELECT * FROM provider_cost_attempts WHERE tenant_id = $1 AND attempt_id = $2::uuid",
                        tenant_id,
                        attempt_id,
                    )
            else:
                if connection is None:
                    self._store_error("SQLite connection is unavailable")
                row = await asyncio.to_thread(
                    self._fetch_one_sqlite,
                    connection,
                    "SELECT * FROM provider_cost_attempts WHERE tenant_id = ? AND attempt_id = ?",
                    (tenant_id, attempt_id),
                )
            return self._normalize_attempt(row) if row is not None else None
        except ProviderCostContractError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    def _backend(self) -> tuple[asyncpg.Pool | None, sqlite3.Connection | None]:
        if self.require_postgres:
            try:
                pool = db.get_verified_pg_pool()
            except Exception as exc:
                self._raise_store_unavailable(exc)
            if pool is None:
                self._store_error("verified PostgreSQL pool is unavailable")
            return pool, None
        connection = db.get_sqlite_conn()
        if connection is None:
            self._store_error("SQLite connection is unavailable")
        return None, connection

    @staticmethod
    def _create_or_get_account_sqlite(
        connection: sqlite3.Connection,
        account_id: str,
        identity: ProviderCostAccountIdentity,
        cap_usd_nanos: int,
    ) -> dict[str, Any]:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT OR IGNORE INTO job_budget_accounts (
                        account_id, tenant_id, job_kind, job_id,
                        scenario_or_resource_type, cap_usd_nanos,
                        reserved_usd_nanos, settled_usd_nanos,
                        budget_source_kind, budget_source_ref,
                        budget_policy_version
                    ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)
                    """,
                    (
                        account_id,
                        identity.tenant_id,
                        identity.job_kind,
                        identity.job_id,
                        identity.scenario_or_resource_type,
                        cap_usd_nanos,
                        identity.budget_source_kind,
                        identity.budget_source_ref,
                        identity.budget_policy_version,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM job_budget_accounts WHERE tenant_id = ? AND job_kind = ? AND job_id = ?",
                    (identity.tenant_id, identity.job_kind, identity.job_id),
                ).fetchone()
                account = ProviderCostRepository._normalize_account(row)
                ProviderCostRepository._require_same_account_authority(
                    account,
                    identity=identity,
                    cap_usd_nanos=cap_usd_nanos,
                )
                connection.commit()
                return account
            except Exception:
                connection.rollback()
                raise

    async def _reserve_postgres(
        self,
        connection: Any,
        *,
        attempt_id: str,
        normalized: dict[str, Any],
    ) -> ProviderCostReserveResult:
        account_row = await connection.fetchrow(
            """
            SELECT * FROM job_budget_accounts
            WHERE tenant_id = $1 AND account_id = $2::uuid
            FOR UPDATE
            """,
            normalized["tenant_id"],
            normalized["account_id"],
        )
        account = self._normalize_account(account_row)
        attempt_rows = await connection.fetch(
            """
            SELECT * FROM provider_cost_attempts
            WHERE account_id = $1::uuid AND logical_operation = $2
            ORDER BY ordinal
            FOR UPDATE
            """,
            normalized["account_id"],
            normalized["logical_operation"],
        )
        attempts = [self._normalize_attempt(row) for row in attempt_rows]
        replay = self._resolve_reservation_replay(
            account,
            attempts=attempts,
            normalized=normalized,
        )
        if replay is not None:
            return ProviderCostReserveResult("replay", account, replay)
        ordinal = self._next_ordinal(
            attempts,
            normalized["start_new_epoch"],
            normalized["regeneration_epoch_ref"],
        )
        self._require_budget_available(
            account,
            reserved_usd_nanos=normalized["reserved_usd_nanos"],
        )
        await connection.execute(
            """
            UPDATE job_budget_accounts
            SET reserved_usd_nanos = reserved_usd_nanos + $1,
                updated_at = CURRENT_TIMESTAMP
            WHERE account_id = $2::uuid AND tenant_id = $3
            """,
            normalized["reserved_usd_nanos"],
            normalized["account_id"],
            normalized["tenant_id"],
        )
        attempt_row = await connection.fetchrow(
            """
            INSERT INTO provider_cost_attempts (
                attempt_id, account_id, tenant_id, job_kind, job_id,
                scenario_or_resource_type, logical_operation, ordinal,
                attempt_fingerprint, regeneration_epoch_ref, provider, canonical_model,
                provider_billing_region, catalog_operation, media_type,
                billing_fact_kind, price_rule_id, price_catalog_version,
                price_rule_version, reservation_billing_facts,
                reserved_usd_nanos, settled_usd_nanos, state,
                reservation_expires_at
            ) VALUES (
                $1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20::jsonb,
                $21, 0, 'reserved', $22
            )
            RETURNING *
            """,
            attempt_id,
            normalized["account_id"],
            normalized["tenant_id"],
            account["job_kind"],
            account["job_id"],
            account["scenario_or_resource_type"],
            normalized["logical_operation"],
            ordinal,
            normalized["attempt_fingerprint"],
            normalized["regeneration_epoch_ref"],
            normalized["provider"],
            normalized["canonical_model"],
            normalized["provider_billing_region"],
            normalized["catalog_operation"],
            normalized["media_type"],
            normalized["billing_fact_kind"],
            normalized["price_rule_id"],
            normalized["price_catalog_version"],
            normalized["price_rule_version"],
            normalized["reservation_json"],
            normalized["reserved_usd_nanos"],
            normalized["reservation_expires_at"],
        )
        updated_account_row = await connection.fetchrow(
            "SELECT * FROM job_budget_accounts WHERE account_id = $1::uuid",
            normalized["account_id"],
        )
        updated_account = self._normalize_account(updated_account_row)
        attempt = self._normalize_attempt(attempt_row)
        self._require_attempt_account_match(updated_account, attempt)
        return ProviderCostReserveResult("owner", updated_account, attempt)

    @staticmethod
    def _reserve_sqlite(
        connection: sqlite3.Connection,
        attempt_id: str,
        normalized: dict[str, Any],
    ) -> ProviderCostReserveResult:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                account_row = connection.execute(
                    "SELECT * FROM job_budget_accounts WHERE tenant_id = ? AND account_id = ?",
                    (normalized["tenant_id"], normalized["account_id"]),
                ).fetchone()
                account = ProviderCostRepository._normalize_account(account_row)
                attempt_rows = connection.execute(
                    "SELECT * FROM provider_cost_attempts "
                    "WHERE account_id = ? AND logical_operation = ? "
                    "ORDER BY ordinal",
                    (normalized["account_id"], normalized["logical_operation"]),
                ).fetchall()
                attempts = [ProviderCostRepository._normalize_attempt(row) for row in attempt_rows]
                replay = ProviderCostRepository._resolve_reservation_replay(
                    account,
                    attempts=attempts,
                    normalized=normalized,
                )
                if replay is not None:
                    connection.commit()
                    return ProviderCostReserveResult("replay", account, replay)
                ordinal = ProviderCostRepository._next_ordinal(
                    attempts,
                    normalized["start_new_epoch"],
                    normalized["regeneration_epoch_ref"],
                )
                ProviderCostRepository._require_budget_available(
                    account,
                    reserved_usd_nanos=normalized["reserved_usd_nanos"],
                )
                connection.execute(
                    """
                    UPDATE job_budget_accounts
                    SET reserved_usd_nanos = reserved_usd_nanos + ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE account_id = ? AND tenant_id = ?
                    """,
                    (
                        normalized["reserved_usd_nanos"],
                        normalized["account_id"],
                        normalized["tenant_id"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO provider_cost_attempts (
                        attempt_id, account_id, tenant_id, job_kind, job_id,
                        scenario_or_resource_type, logical_operation, ordinal,
                        attempt_fingerprint, regeneration_epoch_ref, provider, canonical_model,
                        provider_billing_region, catalog_operation, media_type,
                        billing_fact_kind, price_rule_id, price_catalog_version,
                        price_rule_version, reservation_billing_facts,
                        reserved_usd_nanos, settled_usd_nanos, state,
                        reservation_expires_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, 0, 'reserved', ?
                    )
                    """,
                    (
                        attempt_id,
                        normalized["account_id"],
                        normalized["tenant_id"],
                        account["job_kind"],
                        account["job_id"],
                        account["scenario_or_resource_type"],
                        normalized["logical_operation"],
                        ordinal,
                        normalized["attempt_fingerprint"],
                        normalized["regeneration_epoch_ref"],
                        normalized["provider"],
                        normalized["canonical_model"],
                        normalized["provider_billing_region"],
                        normalized["catalog_operation"],
                        normalized["media_type"],
                        normalized["billing_fact_kind"],
                        normalized["price_rule_id"],
                        normalized["price_catalog_version"],
                        normalized["price_rule_version"],
                        normalized["reservation_json"],
                        normalized["reserved_usd_nanos"],
                        normalized["reservation_expires_at"].isoformat(),
                    ),
                )
                updated_account = ProviderCostRepository._normalize_account(
                    connection.execute(
                        "SELECT * FROM job_budget_accounts WHERE account_id = ?",
                        (normalized["account_id"],),
                    ).fetchone()
                )
                attempt = ProviderCostRepository._normalize_attempt(
                    connection.execute(
                        "SELECT * FROM provider_cost_attempts WHERE attempt_id = ?",
                        (attempt_id,),
                    ).fetchone()
                )
                ProviderCostRepository._require_attempt_account_match(
                    updated_account,
                    attempt,
                )
                connection.commit()
                return ProviderCostReserveResult("owner", updated_account, attempt)
            except Exception:
                connection.rollback()
                raise

    async def _transition_postgres(
        self,
        connection: Any,
        transition: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        account_row = await connection.fetchrow(
            """
            SELECT account.*
            FROM job_budget_accounts AS account
            JOIN provider_cost_attempts AS attempt
              ON attempt.account_id = account.account_id
            WHERE attempt.tenant_id = $1 AND attempt.attempt_id = $2::uuid
            FOR UPDATE OF account
            """,
            transition["tenant_id"],
            transition["attempt_id"],
        )
        account = self._normalize_account(account_row)
        attempt_row = await connection.fetchrow(
            """
            SELECT * FROM provider_cost_attempts
            WHERE tenant_id = $1 AND attempt_id = $2::uuid
            FOR UPDATE
            """,
            transition["tenant_id"],
            transition["attempt_id"],
        )
        attempt = self._normalize_attempt(attempt_row)
        self._require_attempt_account_match(account, attempt)
        replay = self._resolve_transition_replay(
            account,
            attempt=attempt,
            transition=transition,
        )
        if replay is not None:
            return replay
        self._require_expected_transition(attempt, transition=transition)
        await self._update_account_for_transition_postgres(
            connection,
            account=account,
            attempt=attempt,
            transition=transition,
        )
        updated_attempt_row = await connection.fetchrow(
            """
            UPDATE provider_cost_attempts
            SET state = $1::varchar,
                settlement_billing_facts = $2::jsonb,
                settled_usd_nanos = $3,
                provider_reported_cost_usd_nanos = COALESCE($4, provider_reported_cost_usd_nanos),
                provider_reported_credit_micro_units = COALESCE($5, provider_reported_credit_micro_units),
                provider_reported_currency = COALESCE($6, provider_reported_currency),
                external_task_id = COALESCE($7, external_task_id),
                provider_trace_id = COALESCE($8, provider_trace_id),
                safe_error_code = COALESCE($9, safe_error_code),
                submission_started_at = CASE
                    WHEN $1 = 'submission_started'
                        THEN COALESCE(submission_started_at, CURRENT_TIMESTAMP)
                    ELSE submission_started_at
                END,
                submitted_at = CASE
                    WHEN $1 = 'submitted'
                        THEN COALESCE(submitted_at, CURRENT_TIMESTAMP)
                    ELSE submitted_at
                END,
                terminal_at = CASE
                    WHEN $1 IN ('settled', 'released', 'ambiguous', 'accounting_error')
                        THEN COALESCE(terminal_at, CURRENT_TIMESTAMP)
                    ELSE terminal_at
                END,
                updated_at = CURRENT_TIMESTAMP
            WHERE tenant_id = $10 AND attempt_id = $11::uuid AND state = $12
            RETURNING *
            """,
            transition["new_state"],
            transition["settlement_json"],
            transition["settled_usd_nanos"],
            transition["provider_reported_cost_usd_nanos"],
            transition["provider_reported_credit_micro_units"],
            transition["provider_reported_currency"],
            transition["external_task_id"],
            transition["provider_trace_id"],
            transition["safe_error_code"],
            transition["tenant_id"],
            transition["attempt_id"],
            transition["expected_state"],
        )
        if updated_attempt_row is None:
            self._conflict("attempt compare-and-set failed")
        updated_account_row = await connection.fetchrow(
            "SELECT * FROM job_budget_accounts WHERE account_id = $1::uuid",
            attempt["account_id"],
        )
        result = {
            "account": self._normalize_account(updated_account_row),
            "attempt": self._normalize_attempt(updated_attempt_row),
        }
        self._require_attempt_account_match(result["account"], result["attempt"])
        return result

    @staticmethod
    def _transition_sqlite(
        connection: sqlite3.Connection,
        transition: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                account_row = connection.execute(
                    """
                    SELECT account.*
                    FROM job_budget_accounts AS account
                    JOIN provider_cost_attempts AS attempt
                      ON attempt.account_id = account.account_id
                    WHERE attempt.tenant_id = ? AND attempt.attempt_id = ?
                    """,
                    (transition["tenant_id"], transition["attempt_id"]),
                ).fetchone()
                account = ProviderCostRepository._normalize_account(account_row)
                attempt = ProviderCostRepository._normalize_attempt(
                    connection.execute(
                        "SELECT * FROM provider_cost_attempts WHERE tenant_id = ? AND attempt_id = ?",
                        (transition["tenant_id"], transition["attempt_id"]),
                    ).fetchone()
                )
                ProviderCostRepository._require_attempt_account_match(account, attempt)
                replay = ProviderCostRepository._resolve_transition_replay(
                    account,
                    attempt=attempt,
                    transition=transition,
                )
                if replay is not None:
                    connection.commit()
                    return replay
                ProviderCostRepository._require_expected_transition(
                    attempt,
                    transition=transition,
                )
                ProviderCostRepository._update_account_for_transition_sqlite(
                    connection,
                    account=account,
                    attempt=attempt,
                    transition=transition,
                )
                cursor = connection.execute(
                    """
                    UPDATE provider_cost_attempts
                    SET state = ?,
                        settlement_billing_facts = ?,
                        settled_usd_nanos = ?,
                        provider_reported_cost_usd_nanos = COALESCE(?, provider_reported_cost_usd_nanos),
                        provider_reported_credit_micro_units = COALESCE(?, provider_reported_credit_micro_units),
                        provider_reported_currency = COALESCE(?, provider_reported_currency),
                        external_task_id = COALESCE(?, external_task_id),
                        provider_trace_id = COALESCE(?, provider_trace_id),
                        safe_error_code = COALESCE(?, safe_error_code),
                        submission_started_at = CASE
                            WHEN ? = 'submission_started'
                                THEN COALESCE(submission_started_at, CURRENT_TIMESTAMP)
                            ELSE submission_started_at
                        END,
                        submitted_at = CASE
                            WHEN ? = 'submitted'
                                THEN COALESCE(submitted_at, CURRENT_TIMESTAMP)
                            ELSE submitted_at
                        END,
                        terminal_at = CASE
                            WHEN ? IN ('settled', 'released', 'ambiguous', 'accounting_error')
                                THEN COALESCE(terminal_at, CURRENT_TIMESTAMP)
                            ELSE terminal_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ? AND attempt_id = ? AND state = ?
                    """,
                    (
                        transition["new_state"],
                        transition["settlement_json"],
                        transition["settled_usd_nanos"],
                        transition["provider_reported_cost_usd_nanos"],
                        transition["provider_reported_credit_micro_units"],
                        transition["provider_reported_currency"],
                        transition["external_task_id"],
                        transition["provider_trace_id"],
                        transition["safe_error_code"],
                        transition["new_state"],
                        transition["new_state"],
                        transition["new_state"],
                        transition["tenant_id"],
                        transition["attempt_id"],
                        transition["expected_state"],
                    ),
                )
                if cursor.rowcount != 1:
                    ProviderCostRepository._conflict("attempt compare-and-set failed")
                result = {
                    "account": ProviderCostRepository._normalize_account(
                        connection.execute(
                            "SELECT * FROM job_budget_accounts WHERE account_id = ?",
                            (attempt["account_id"],),
                        ).fetchone()
                    ),
                    "attempt": ProviderCostRepository._normalize_attempt(
                        connection.execute(
                            "SELECT * FROM provider_cost_attempts WHERE attempt_id = ?",
                            (transition["attempt_id"],),
                        ).fetchone()
                    ),
                }
                ProviderCostRepository._require_attempt_account_match(
                    result["account"],
                    result["attempt"],
                )
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    @staticmethod
    async def _update_account_for_transition_postgres(
        connection: Any,
        *,
        account: dict[str, Any],
        attempt: dict[str, Any],
        transition: dict[str, Any],
    ) -> None:
        reserved_delta, settled_delta = ProviderCostRepository._money_deltas(
            attempt,
            transition=transition,
        )
        if reserved_delta == 0 and settled_delta == 0:
            return
        status = await connection.execute(
            """
            UPDATE job_budget_accounts
            SET reserved_usd_nanos = reserved_usd_nanos + $1,
                settled_usd_nanos = settled_usd_nanos + $2,
                updated_at = CURRENT_TIMESTAMP
            WHERE account_id = $3::uuid AND tenant_id = $4
              AND reserved_usd_nanos + $1 >= 0
              AND settled_usd_nanos + $2 >= 0
              AND reserved_usd_nanos + $1 + settled_usd_nanos + $2
                    <= cap_usd_nanos
            """,
            reserved_delta,
            settled_delta,
            account["account_id"],
            account["tenant_id"],
        )
        if status != "UPDATE 1":
            ProviderCostRepository._store_error("account conservation update failed")

    @staticmethod
    def _update_account_for_transition_sqlite(
        connection: sqlite3.Connection,
        *,
        account: dict[str, Any],
        attempt: dict[str, Any],
        transition: dict[str, Any],
    ) -> None:
        reserved_delta, settled_delta = ProviderCostRepository._money_deltas(
            attempt,
            transition=transition,
        )
        if reserved_delta == 0 and settled_delta == 0:
            return
        cursor = connection.execute(
            """
            UPDATE job_budget_accounts
            SET reserved_usd_nanos = reserved_usd_nanos + ?,
                settled_usd_nanos = settled_usd_nanos + ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE account_id = ? AND tenant_id = ?
              AND reserved_usd_nanos + ? >= 0
              AND settled_usd_nanos + ? >= 0
              AND reserved_usd_nanos + ? + settled_usd_nanos + ?
                    <= cap_usd_nanos
            """,
            (
                reserved_delta,
                settled_delta,
                account["account_id"],
                account["tenant_id"],
                reserved_delta,
                settled_delta,
                reserved_delta,
                settled_delta,
            ),
        )
        if cursor.rowcount != 1:
            ProviderCostRepository._store_error("account conservation update failed")

    @staticmethod
    def _money_deltas(
        attempt: dict[str, Any],
        *,
        transition: dict[str, Any],
    ) -> tuple[int, int]:
        if transition["new_state"] == "settled":
            return -attempt["reserved_usd_nanos"], transition["settled_usd_nanos"]
        if transition["new_state"] == "released":
            return -attempt["reserved_usd_nanos"], 0
        return 0, 0

    @staticmethod
    def _resolve_reservation_replay(
        account: dict[str, Any],
        *,
        attempts: list[dict[str, Any]],
        normalized: dict[str, Any],
    ) -> dict[str, Any] | None:
        for attempt in attempts:
            ProviderCostRepository._require_attempt_account_match(account, attempt)
            if attempt["attempt_fingerprint"] != normalized["attempt_fingerprint"]:
                continue
            expected = {
                "tenant_id": normalized["tenant_id"],
                "account_id": normalized["account_id"],
                "logical_operation": normalized["logical_operation"],
                "regeneration_epoch_ref": normalized["regeneration_epoch_ref"],
                "provider": normalized["provider"],
                "canonical_model": normalized["canonical_model"],
                "provider_billing_region": normalized["provider_billing_region"],
                "catalog_operation": normalized["catalog_operation"],
                "media_type": normalized["media_type"],
                "billing_fact_kind": normalized["billing_fact_kind"],
                "price_rule_id": normalized["price_rule_id"],
                "price_catalog_version": normalized["price_catalog_version"],
                "price_rule_version": normalized["price_rule_version"],
                "reservation_billing_facts": normalized["reservation_facts"],
                "reserved_usd_nanos": normalized["reserved_usd_nanos"],
            }
            if any(attempt[key] != value for key, value in expected.items()):
                ProviderCostRepository._conflict("same fingerprint has conflicting immutable authority")
            return attempt
        return None

    @staticmethod
    def _next_ordinal(
        attempts: list[dict[str, Any]],
        start_new_epoch: bool,
        regeneration_epoch_ref: str | None,
    ) -> int:
        if attempts and not start_new_epoch:
            ProviderCostRepository._conflict("logical operation already has a different fingerprint")
        if start_new_epoch:
            if regeneration_epoch_ref is None:
                ProviderCostRepository._usage_error("regeneration epoch reference is required")
            if any(attempt.get("regeneration_epoch_ref") == regeneration_epoch_ref for attempt in attempts):
                ProviderCostRepository._conflict("regeneration epoch was already consumed")
        if not attempts:
            return 0
        ordinal = max(attempt["ordinal"] for attempt in attempts) + 1
        if ordinal > MAX_SIGNED_BIGINT:
            ProviderCostRepository._store_error("attempt ordinal overflow")
        return ordinal

    @staticmethod
    def _resolve_transition_replay(
        account: dict[str, Any],
        *,
        attempt: dict[str, Any],
        transition: dict[str, Any],
    ) -> dict[str, dict[str, Any]] | None:
        if attempt["state"] == transition["expected_state"]:
            return None
        if attempt["state"] != transition["new_state"]:
            ProviderCostRepository._conflict("attempt state is stale")
        if attempt["settled_usd_nanos"] != transition["settled_usd_nanos"]:
            ProviderCostRepository._conflict("terminal amount conflicts")
        if attempt["settlement_billing_facts"] != transition["settlement_facts"]:
            ProviderCostRepository._conflict("terminal billing facts conflict")
        for field in (
            "provider_reported_cost_usd_nanos",
            "provider_reported_credit_micro_units",
            "provider_reported_currency",
            "external_task_id",
            "provider_trace_id",
            "safe_error_code",
        ):
            requested = transition[field]
            if requested is not None and attempt[field] != requested:
                ProviderCostRepository._conflict("terminal projection conflicts")
        return {"account": account, "attempt": attempt}

    @staticmethod
    def _require_expected_transition(
        attempt: dict[str, Any],
        *,
        transition: dict[str, Any],
    ) -> None:
        if attempt["state"] != transition["expected_state"]:
            ProviderCostRepository._conflict("attempt state is stale")
        if (transition["expected_state"], transition["new_state"]) not in _LEGAL_TRANSITIONS:
            ProviderCostRepository._conflict("attempt transition is not legal")
        if transition["new_state"] == "settled" and transition["settled_usd_nanos"] > attempt["reserved_usd_nanos"]:
            ProviderCostRepository._conflict("settlement exceeds reservation")
        if (
            transition["settlement_facts"] is not None
            and transition["settlement_facts"]["schema_version"] != attempt["billing_fact_kind"]
        ):
            ProviderCostRepository._conflict("settlement fact kind conflicts")

    @staticmethod
    def _validate_reservation_input(**values: Any) -> dict[str, Any]:
        ProviderCostRepository._require_safe_id(values["tenant_id"], "tenant ID")
        ProviderCostRepository._require_uuid4(values["account_id"], "account ID")
        if (
            not isinstance(values["logical_operation"], str)
            or _SAFE_OPERATION_RE.fullmatch(values["logical_operation"]) is None
        ):
            ProviderCostRepository._usage_error("logical operation is invalid")
        if (
            not isinstance(values["attempt_fingerprint"], str)
            or _SHA256_RE.fullmatch(values["attempt_fingerprint"]) is None
        ):
            ProviderCostRepository._usage_error("attempt fingerprint is invalid")
        if type(values["start_new_epoch"]) is not bool:
            ProviderCostRepository._usage_error("new epoch flag is invalid")
        regeneration_epoch_ref = values.get("regeneration_epoch_ref")
        if values["start_new_epoch"]:
            ProviderCostRepository._require_safe_id(
                regeneration_epoch_ref,
                "regeneration epoch reference",
            )
        elif regeneration_epoch_ref is not None:
            ProviderCostRepository._usage_error("regeneration epoch reference is unexpected")
        ProviderCostRepository._require_positive_money(
            values["reserved_usd_nanos"],
            "attempt reservation",
        )
        expires_at = ProviderCostRepository._require_utc_datetime(
            values["reservation_expires_at"],
            "reservation expiry",
        )
        for name in ("price_rule_id", "price_catalog_version", "price_rule_version"):
            ProviderCostRepository._require_safe_id(values[name], name)
        try:
            ProviderCostAttemptIdentity(
                logical_operation=values["logical_operation"],
                catalog_operation=values["catalog_operation"],
                ordinal=0,
                provider=values["provider"],
                canonical_model=values["canonical_model"],
                provider_billing_region=values["provider_billing_region"],
                media_type=values["media_type"],
                billing_fact_kind=values["billing_fact_kind"],
                state="reserved",
            )
            facts = ProviderCostRepository._normalize_facts_input(values["reservation_billing_facts"])
        except (TypeError, ValueError, ValidationError) as exc:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "reservation authority is invalid",
            ) from exc
        if facts.schema_version != values["billing_fact_kind"]:
            ProviderCostRepository._usage_error("reservation fact kind conflicts")
        facts_dict = facts.model_dump(mode="json")
        return {
            **values,
            "reservation_expires_at": expires_at,
            "reservation_facts": facts_dict,
            "reservation_json": ProviderCostRepository._encode_json(facts_dict),
        }

    @staticmethod
    def _validate_transition_input(**values: Any) -> dict[str, Any]:
        ProviderCostRepository._require_safe_id(values["tenant_id"], "tenant ID")
        ProviderCostRepository._require_uuid4(values["attempt_id"], "attempt ID")
        if values["expected_state"] not in _ATTEMPT_STATES or values["new_state"] not in _ATTEMPT_STATES:
            ProviderCostRepository._usage_error("attempt state is invalid")
        ProviderCostRepository._require_nonnegative_money(
            values["settled_usd_nanos"],
            "settled amount",
        )
        for field in (
            "provider_reported_cost_usd_nanos",
            "provider_reported_credit_micro_units",
        ):
            value = values[field]
            if value is not None:
                ProviderCostRepository._require_nonnegative_money(value, field)
        if values["provider_reported_currency"] not in {None, "USD"}:
            ProviderCostRepository._usage_error("provider currency is invalid")
        for field in ("external_task_id", "provider_trace_id", "safe_error_code"):
            value = values[field]
            if value is not None:
                ProviderCostRepository._require_safe_id(value, field)
        if values["safe_error_code"] is not None and values["safe_error_code"] not in _SAFE_ERROR_CODES:
            ProviderCostRepository._usage_error("safe error code is invalid")
        facts: ProviderBillingFacts | None = None
        if values["settlement_billing_facts"] is not None:
            try:
                facts = ProviderCostRepository._normalize_facts_input(values["settlement_billing_facts"])
            except (TypeError, ValueError, ValidationError) as exc:
                raise ProviderCostContractError(
                    "provider_cost_usage_invalid",
                    "settlement billing facts are invalid",
                ) from exc
        if values["new_state"] == "settled":
            if facts is None or values["settled_usd_nanos"] <= 0:
                ProviderCostRepository._usage_error("settled transition requires positive exact facts")
        elif values["new_state"] == "accounting_error":
            if values["settled_usd_nanos"] != 0:
                ProviderCostRepository._usage_error("accounting error cannot move settled money")
        elif facts is not None or values["settled_usd_nanos"] != 0:
            ProviderCostRepository._usage_error("non-settled transition cannot carry settlement authority")
        if values["new_state"] in {"ambiguous", "accounting_error"}:
            if values["safe_error_code"] is None:
                ProviderCostRepository._usage_error("held terminal transition requires a safe error code")
        facts_dict = facts.model_dump(mode="json") if facts is not None else None
        return {
            **values,
            "settlement_facts": facts_dict,
            "settlement_json": (ProviderCostRepository._encode_json(facts_dict) if facts_dict is not None else None),
        }

    @staticmethod
    def _normalize_account(
        row: asyncpg.Record | sqlite3.Row | None,
    ) -> dict[str, Any]:
        if row is None:
            ProviderCostRepository._conflict("budget account was not found")
        try:
            record: dict[str, Any] = {key: row[key] for key in row.keys()}
            record["account_id"] = ProviderCostRepository._normalize_stored_uuid4(
                record.get("account_id"),
                "account ID",
            )
            identity = ProviderCostAccountIdentity.model_validate(
                {
                    field: record.get(field)
                    for field in ProviderCostAccountIdentity.model_fields
                },
                strict=True,
            )
            for field in (
                "cap_usd_nanos",
                "reserved_usd_nanos",
                "settled_usd_nanos",
            ):
                ProviderCostRepository._require_nonnegative_money(record.get(field), field)
            if record["cap_usd_nanos"] <= 0:
                raise ValueError("account cap is not positive")
            if record["reserved_usd_nanos"] + record["settled_usd_nanos"] > record["cap_usd_nanos"]:
                raise ValueError("account conservation is invalid")
            record.update(identity.model_dump(mode="python"))
            record["created_at"] = ProviderCostRepository._normalize_stored_datetime(
                record.get("created_at"),
                "account created_at",
            )
            record["updated_at"] = ProviderCostRepository._normalize_stored_datetime(
                record.get("updated_at"),
                "account updated_at",
            )
            return record
        except (
            ProviderCostContractError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            ProviderCostRepository._raise_store_unavailable(exc)

    @staticmethod
    def _normalize_attempt(
        row: asyncpg.Record | sqlite3.Row | None,
    ) -> dict[str, Any]:
        if row is None:
            ProviderCostRepository._conflict("provider attempt was not found")
        try:
            record: dict[str, Any] = {key: row[key] for key in row.keys()}
            record["attempt_id"] = ProviderCostRepository._normalize_stored_uuid4(
                record.get("attempt_id"),
                "attempt ID",
            )
            record["account_id"] = ProviderCostRepository._normalize_stored_uuid4(
                record.get("account_id"),
                "account ID",
            )
            identity = ProviderCostAttemptIdentity.model_validate(
                {
                    field: record.get(field)
                    for field in ProviderCostAttemptIdentity.model_fields
                },
                strict=True,
            )
            ProviderCostRepository._require_safe_id(record.get("tenant_id"), "tenant ID")
            ProviderCostRepository._require_safe_id(record.get("job_id"), "job ID")
            ProviderCostRepository._require_safe_id(
                record.get("scenario_or_resource_type"),
                "scenario or resource type",
            )
            if record.get("job_kind") not in {"canonical", "compatibility"}:
                raise ValueError("attempt job kind is invalid")
            fingerprint = record.get("attempt_fingerprint")
            if not isinstance(fingerprint, str) or _SHA256_RE.fullmatch(fingerprint) is None:
                raise ValueError("attempt fingerprint is invalid")
            regeneration_epoch_ref = record.get("regeneration_epoch_ref")
            if regeneration_epoch_ref is not None:
                ProviderCostRepository._require_safe_id(
                    regeneration_epoch_ref,
                    "regeneration epoch reference",
                )
            for field in (
                "price_rule_id",
                "price_catalog_version",
                "price_rule_version",
            ):
                ProviderCostRepository._require_safe_id(record.get(field), field)
            reservation_facts = ProviderCostRepository._decode_facts(record.get("reservation_billing_facts"))
            if reservation_facts.schema_version != identity.billing_fact_kind:
                raise ValueError("reservation fact kind is invalid")
            settlement_value = record.get("settlement_billing_facts")
            settlement_facts = (
                ProviderCostRepository._decode_facts(settlement_value) if settlement_value is not None else None
            )
            if settlement_facts is not None and settlement_facts.schema_version != identity.billing_fact_kind:
                raise ValueError("settlement fact kind is invalid")
            ProviderCostRepository._require_positive_money(
                record.get("reserved_usd_nanos"),
                "attempt reservation",
            )
            ProviderCostRepository._require_nonnegative_money(
                record.get("settled_usd_nanos"),
                "attempt settlement",
            )
            if record["settled_usd_nanos"] > record["reserved_usd_nanos"]:
                raise ValueError("attempt settlement exceeds reservation")
            for field in (
                "provider_reported_cost_usd_nanos",
                "provider_reported_credit_micro_units",
            ):
                value = record.get(field)
                if value is not None:
                    ProviderCostRepository._require_nonnegative_money(value, field)
            if record.get("provider_reported_currency") not in {None, "USD"}:
                raise ValueError("provider reported currency is invalid")
            for field in ("external_task_id", "provider_trace_id", "safe_error_code"):
                value = record.get(field)
                if value is not None:
                    ProviderCostRepository._require_safe_id(value, field)
            if record.get("safe_error_code") is not None and record["safe_error_code"] not in _SAFE_ERROR_CODES:
                raise ValueError("stored safe error code is invalid")
            record.update(identity.model_dump(mode="python"))
            record["reservation_billing_facts"] = reservation_facts.model_dump(mode="json")
            record["settlement_billing_facts"] = (
                settlement_facts.model_dump(mode="json") if settlement_facts is not None else None
            )
            for field in (
                "reservation_expires_at",
                "created_at",
                "updated_at",
            ):
                record[field] = ProviderCostRepository._normalize_stored_datetime(
                    record.get(field),
                    field,
                )
            for field in ("submission_started_at", "submitted_at", "terminal_at"):
                value = record.get(field)
                record[field] = (
                    ProviderCostRepository._normalize_stored_datetime(value, field) if value is not None else None
                )
            ProviderCostRepository._validate_state_projection(record)
            return record
        except (
            ProviderCostContractError,
            KeyError,
            TypeError,
            ValueError,
            ValidationError,
        ) as exc:
            ProviderCostRepository._raise_store_unavailable(exc)

    @staticmethod
    def _validate_state_projection(record: dict[str, Any]) -> None:
        state = record["state"]
        started = record["submission_started_at"] is not None
        submitted = record["submitted_at"] is not None
        terminal = record["terminal_at"] is not None
        settlement = record["settlement_billing_facts"] is not None
        settled = record["settled_usd_nanos"]
        valid = {
            "reserved": not started and not submitted and not terminal and not settlement and settled == 0,
            "submission_started": started and not submitted and not terminal and not settlement and settled == 0,
            "submitted": started and submitted and not terminal and not settlement and settled == 0,
            "settled": started and terminal and settlement and settled > 0,
            "released": terminal and not settlement and settled == 0,
            "ambiguous": terminal and settled == 0 and record["safe_error_code"] is not None,
            "accounting_error": terminal and settled == 0 and record["safe_error_code"] is not None,
        }[state]
        if not valid:
            raise ValueError("attempt state projection is invalid")

    @staticmethod
    def _require_same_account_authority(
        account: dict[str, Any],
        *,
        identity: ProviderCostAccountIdentity,
        cap_usd_nanos: int,
    ) -> None:
        expected = {
            **identity.model_dump(mode="python"),
            "cap_usd_nanos": cap_usd_nanos,
        }
        if any(account.get(key) != value for key, value in expected.items()):
            ProviderCostRepository._conflict("budget account authority conflicts")

    @staticmethod
    def _require_attempt_account_match(
        account: dict[str, Any],
        attempt: dict[str, Any],
    ) -> None:
        for field in (
            "account_id",
            "tenant_id",
            "job_kind",
            "job_id",
            "scenario_or_resource_type",
        ):
            if account.get(field) != attempt.get(field):
                ProviderCostRepository._store_error("account and attempt identity are inconsistent")

    @staticmethod
    def _require_budget_available(
        account: dict[str, Any],
        *,
        reserved_usd_nanos: int,
    ) -> None:
        projected = account["reserved_usd_nanos"] + account["settled_usd_nanos"] + reserved_usd_nanos
        if projected > account["cap_usd_nanos"]:
            raise ProviderCostContractError(
                "provider_budget_exhausted",
                "provider job budget is exhausted",
            )

    @staticmethod
    def _normalize_facts_input(value: object) -> ProviderBillingFacts:
        if isinstance(value, BaseModel):
            value = value.model_dump(mode="python")
        return parse_billing_facts(value)

    @staticmethod
    def _decode_facts(value: object) -> ProviderBillingFacts:
        if isinstance(value, str):
            value = json.loads(
                value,
                parse_float=ProviderCostRepository._reject_non_integer_json,
                parse_constant=ProviderCostRepository._reject_non_integer_json,
            )
        if not isinstance(value, dict):
            raise ValueError("stored billing facts are invalid")
        return parse_billing_facts(value)

    @staticmethod
    def _encode_json(value: dict[str, Any]) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @staticmethod
    def _reject_non_integer_json(value: str) -> int:
        raise ValueError(f"non-integer stored JSON number is forbidden: {value}")

    @staticmethod
    def _require_uuid4(value: object, name: str) -> None:
        if not isinstance(value, str):
            ProviderCostRepository._usage_error(f"{name} is invalid")
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError, TypeError):
            ProviderCostRepository._usage_error(f"{name} is invalid")
        if parsed.version != 4 or str(parsed) != value:
            ProviderCostRepository._usage_error(f"{name} is invalid")

    @staticmethod
    def _normalize_stored_uuid4(value: object, name: str) -> str:
        if isinstance(value, uuid.UUID):
            value = str(value)
        ProviderCostRepository._require_uuid4(value, name)
        assert isinstance(value, str)
        return value

    @staticmethod
    def _require_safe_id(value: object, name: str) -> None:
        if not isinstance(value, str) or _SAFE_ID_RE.fullmatch(value) is None:
            ProviderCostRepository._usage_error(f"{name} is invalid")

    @staticmethod
    def _require_positive_money(value: object, name: str) -> None:
        if type(value) is not int or value <= 0 or value > MAX_SIGNED_BIGINT:
            ProviderCostRepository._usage_error(f"{name} is invalid")

    @staticmethod
    def _require_nonnegative_money(value: object, name: str) -> None:
        if type(value) is not int or value < 0 or value > MAX_SIGNED_BIGINT:
            ProviderCostRepository._usage_error(f"{name} is invalid")

    @staticmethod
    def _require_utc_datetime(value: object, name: str) -> datetime:
        if not isinstance(value, datetime):
            ProviderCostRepository._usage_error(f"{name} is invalid")
        if value.tzinfo is None or value.utcoffset() is None:
            ProviderCostRepository._usage_error(f"{name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _normalize_stored_datetime(value: object, name: str) -> datetime:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                ProviderCostRepository._store_error(f"stored {name} is invalid")
        if not isinstance(value, datetime):
            ProviderCostRepository._store_error(f"stored {name} is invalid")
        if value.tzinfo is None or value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _fetch_one_sqlite(
        connection: sqlite3.Connection,
        query: str,
        args: tuple[Any, ...],
    ) -> sqlite3.Row | None:
        with db.get_sqlite_lock():
            return connection.execute(query, args).fetchone()

    @staticmethod
    def _usage_error(detail: str) -> NoReturn:
        raise ProviderCostContractError("provider_cost_usage_invalid", detail)

    @staticmethod
    def _conflict(detail: str) -> NoReturn:
        raise ProviderCostContractError("provider_cost_attempt_conflict", detail)

    @staticmethod
    def _store_error(detail: str) -> NoReturn:
        raise ProviderCostContractError("provider_cost_store_unavailable", detail)

    @staticmethod
    def _raise_store_unavailable(exc: Exception) -> NoReturn:
        logger.warning(
            "Provider cost store operation failed (%s)",
            type(exc).__name__,
        )
        raise ProviderCostContractError("provider_cost_store_unavailable") from None


__all__ = ["ProviderCostRepository", "ProviderCostReserveResult", "ReserveOutcome"]
