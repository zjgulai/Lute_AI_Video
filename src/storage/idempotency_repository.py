"""Atomic durable storage for tenant-scoped generation submissions.

This repository deliberately does not extend :class:`BaseRepository`: a
read-then-create abstraction cannot arbitrate concurrent paid submissions.
PostgreSQL uses its unique constraint with ``ON CONFLICT``; SQLite uses the
same constraint inside ``BEGIN IMMEDIATE`` under the existing connection lock.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from . import db

logger = logging.getLogger(__name__)

ClaimOutcome = Literal["owner", "replay", "conflict"]

NONTERMINAL_STATUSES = frozenset({"reserved", "initializing", "queued", "running"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "recovery_required"})
ALLOWED_STATUSES = NONTERMINAL_STATUSES | TERMINAL_STATUSES
ALLOWED_SCENARIOS = frozenset({"fast", "s1", "s2", "s3", "s4", "s5"})
ALLOWED_RESOURCE_TYPES = frozenset({"fast", "scenario"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_JSON_COLUMNS = frozenset({"response_body", "result_snapshot"})


class IdempotencyStoreUnavailableError(RuntimeError):
    """The required durable idempotency store cannot safely arbitrate work."""


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """Outcome of a single tenant/key claim attempt."""

    outcome: ClaimOutcome
    record: dict[str, Any]


class SubmissionIdempotencyRepository:
    """Persist and compare-and-set submission identities and lifecycle state."""

    _PG_CLAIM_SQL = """
        INSERT INTO idempotency_records (
            id,
            tenant_id,
            key_hash,
            fingerprint_version,
            request_hash,
            operation,
            scenario,
            resource_type,
            resource_id,
            record_status,
            stage,
            effective_policy_version,
            response_status,
            response_body,
            result_snapshot,
            safe_error_code,
            owner_instance_id,
            lease_expires_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            'reserved', 'reserved', $10, $11, $12::jsonb,
            NULL, NULL, $13,
            NOW() + make_interval(secs => $14::double precision)
        )
        ON CONFLICT (tenant_id, key_hash) DO NOTHING
        RETURNING *
    """

    def __init__(self, *, require_postgres: bool | None = None) -> None:
        if require_postgres is None:
            environment = os.getenv("ENVIRONMENT", "development").strip().lower()
            require_postgres = environment in {"prod", "production"}
        self.require_postgres = require_postgres

    async def claim(
        self,
        *,
        tenant_id: str,
        key_hash: str,
        fingerprint_version: str,
        request_hash: str,
        operation: str,
        scenario: str,
        resource_type: str,
        resource_id: str,
        effective_policy_version: str,
        response_status: int,
        response_body: Mapping[str, Any],
        owner_instance_id: str,
        lease_seconds: int = 120,
    ) -> ClaimResult:
        """Atomically own, replay, or conflict on a tenant-global key hash."""

        self._validate_claim(
            tenant_id=tenant_id,
            key_hash=key_hash,
            fingerprint_version=fingerprint_version,
            request_hash=request_hash,
            operation=operation,
            scenario=scenario,
            resource_type=resource_type,
            resource_id=resource_id,
            effective_policy_version=effective_policy_version,
            response_status=response_status,
            owner_instance_id=owner_instance_id,
            lease_seconds=lease_seconds,
        )
        response_json = self._encode_json(response_body)
        record_id = str(uuid.uuid4())

        pool, sqlite_conn = await self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(
                        self._PG_CLAIM_SQL,
                        record_id,
                        tenant_id,
                        key_hash,
                        fingerprint_version,
                        request_hash,
                        operation,
                        scenario,
                        resource_type,
                        resource_id,
                        effective_policy_version,
                        response_status,
                        response_json,
                        owner_instance_id,
                        lease_seconds,
                    )
                    inserted = row is not None
                    if row is None:
                        row = await connection.fetchrow(
                            "SELECT * FROM idempotency_records WHERE tenant_id = $1 AND key_hash = $2",
                            tenant_id,
                            key_hash,
                        )
                if row is None:
                    raise IdempotencyStoreUnavailableError
                record = self._normalize_record(row)
            else:
                if sqlite_conn is None:  # Defensive; _backend already rejects it.
                    raise IdempotencyStoreUnavailableError
                inserted, record = await asyncio.to_thread(
                    self._claim_sqlite,
                    sqlite_conn,
                    record_id,
                    tenant_id,
                    key_hash,
                    fingerprint_version,
                    request_hash,
                    operation,
                    scenario,
                    resource_type,
                    resource_id,
                    effective_policy_version,
                    response_status,
                    response_json,
                    owner_instance_id,
                    lease_seconds,
                )
        except IdempotencyStoreUnavailableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

        if inserted:
            return ClaimResult("owner", record)
        if self._fingerprint_matches(
            record,
            fingerprint_version=fingerprint_version,
            request_hash=request_hash,
            operation=operation,
            scenario=scenario,
        ):
            return ClaimResult("replay", record)
        return ClaimResult("conflict", record)

    async def get_by_key_hash(
        self,
        *,
        tenant_id: str,
        key_hash: str,
    ) -> dict[str, Any] | None:
        """Return a tenant-owned record without exposing cross-tenant rows."""

        self._require_text("tenant_id", tenant_id)
        self._require_digest("key_hash", key_hash)
        return await self._fetch_one(
            pg_query=("SELECT * FROM idempotency_records WHERE tenant_id = $1 AND key_hash = $2"),
            sqlite_query=("SELECT * FROM idempotency_records WHERE tenant_id = ? AND key_hash = ?"),
            args=(tenant_id, key_hash),
        )

    async def get_by_resource(
        self,
        *,
        tenant_id: str,
        resource_type: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        """Return the unique tenant-owned record for a Fast/scenario resource."""

        self._require_text("tenant_id", tenant_id)
        if resource_type not in ALLOWED_RESOURCE_TYPES:
            raise ValueError("resource_type is invalid")
        self._require_text("resource_id", resource_id)
        return await self._fetch_one(
            pg_query=(
                "SELECT * FROM idempotency_records WHERE tenant_id = $1 AND resource_type = $2 AND resource_id = $3"
            ),
            sqlite_query=(
                "SELECT * FROM idempotency_records WHERE tenant_id = ? AND resource_type = ? AND resource_id = ?"
            ),
            args=(tenant_id, resource_type, resource_id),
        )

    async def get_by_id(
        self,
        *,
        tenant_id: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        """Return one tenant-owned internal record for lifecycle arbitration."""

        self._require_text("tenant_id", tenant_id)
        self._require_text("record_id", record_id)
        return await self._fetch_one(
            pg_query=("SELECT * FROM idempotency_records WHERE tenant_id = $1 AND id = $2"),
            sqlite_query=("SELECT * FROM idempotency_records WHERE tenant_id = ? AND id = ?"),
            args=(tenant_id, record_id),
        )

    async def transition(
        self,
        *,
        tenant_id: str,
        record_id: str,
        expected_statuses: Collection[str],
        new_status: str,
        owner_instance_id: str,
        stage: str | None = None,
        response_status: int | None = None,
        response_body: Mapping[str, Any] | None = None,
        result_snapshot: Mapping[str, Any] | None = None,
        safe_error_code: str | None = None,
        lease_seconds: int | None = None,
        mark_completed: bool = False,
    ) -> dict[str, Any] | None:
        """Compare-and-set a lifecycle row; return ``None`` on a stale writer."""

        statuses = self._validate_transition(
            tenant_id=tenant_id,
            record_id=record_id,
            expected_statuses=expected_statuses,
            new_status=new_status,
            response_status=response_status,
            lease_seconds=lease_seconds,
        )
        self._require_text("owner_instance_id", owner_instance_id)
        response_json = self._encode_json(response_body) if response_body is not None else None
        result_json = self._encode_json(result_snapshot) if result_snapshot is not None else None
        complete = mark_completed or new_status in TERMINAL_STATUSES
        clear_lease = new_status in TERMINAL_STATUSES

        pool, sqlite_conn = await self._backend()
        try:
            if pool is not None:
                query = """
                    UPDATE idempotency_records
                    SET record_status = $4,
                        stage = COALESCE($5, stage),
                        response_status = COALESCE($6, response_status),
                        response_body = COALESCE($7::jsonb, response_body),
                        result_snapshot = COALESCE($8::jsonb, result_snapshot),
                        safe_error_code = COALESCE($9, safe_error_code),
                        lease_expires_at = CASE
                            WHEN $12::boolean THEN NULL
                            WHEN $11::integer IS NULL THEN lease_expires_at
                            ELSE NOW() + make_interval(secs => $11::double precision)
                        END,
                        completed_at = CASE
                            WHEN $13::boolean THEN COALESCE(completed_at, NOW())
                            ELSE completed_at
                        END,
                        updated_at = NOW()
                    WHERE tenant_id = $1
                      AND id = $2
                      AND record_status::text = ANY($3::text[])
                      AND owner_instance_id = $10
                    RETURNING *
                """
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(
                        query,
                        tenant_id,
                        record_id,
                        list(statuses),
                        new_status,
                        stage,
                        response_status,
                        response_json,
                        result_json,
                        safe_error_code,
                        owner_instance_id,
                        lease_seconds,
                        clear_lease,
                        complete,
                    )
                return self._normalize_record(row) if row is not None else None
            if sqlite_conn is None:
                raise IdempotencyStoreUnavailableError
            return await asyncio.to_thread(
                self._transition_sqlite,
                sqlite_conn,
                tenant_id,
                record_id,
                statuses,
                new_status,
                stage,
                response_status,
                response_json,
                result_json,
                safe_error_code,
                lease_seconds,
                owner_instance_id,
                complete,
                clear_lease,
            )
        except IdempotencyStoreUnavailableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def renew_lease(
        self,
        *,
        tenant_id: str,
        record_id: str,
        owner_instance_id: str,
        expected_statuses: Collection[str] = NONTERMINAL_STATUSES,
        lease_seconds: int = 120,
    ) -> dict[str, Any] | None:
        """Renew an owned nonterminal lease using database time."""

        statuses = self._validate_expected_statuses(expected_statuses)
        self._require_text("tenant_id", tenant_id)
        self._require_text("record_id", record_id)
        self._require_text("owner_instance_id", owner_instance_id)
        self._validate_lease_seconds(lease_seconds)

        pool, sqlite_conn = await self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(
                        """
                        UPDATE idempotency_records
                        SET lease_expires_at = NOW()
                                + make_interval(secs => $5::double precision),
                            updated_at = NOW()
                        WHERE tenant_id = $1
                          AND id = $2
                          AND owner_instance_id = $3
                          AND record_status::text = ANY($4::text[])
                        RETURNING *
                        """,
                        tenant_id,
                        record_id,
                        owner_instance_id,
                        list(statuses),
                        lease_seconds,
                    )
                return self._normalize_record(row) if row is not None else None
            if sqlite_conn is None:
                raise IdempotencyStoreUnavailableError
            return await asyncio.to_thread(
                self._renew_lease_sqlite,
                sqlite_conn,
                tenant_id,
                record_id,
                owner_instance_id,
                statuses,
                lease_seconds,
            )
        except IdempotencyStoreUnavailableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def reconcile_expired_lease(
        self,
        *,
        tenant_id: str,
        record_id: str,
        safe_error_code: str = "submission_owner_lost",
    ) -> dict[str, Any] | None:
        """CAS an expired nonterminal owner to ``recovery_required``."""

        self._require_text("tenant_id", tenant_id)
        self._require_text("record_id", record_id)
        self._require_text("safe_error_code", safe_error_code)
        recovery_projection = self._encode_json({"status": "recovery_required"})

        pool, sqlite_conn = await self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(
                        """
                        UPDATE idempotency_records
                        SET record_status = 'recovery_required',
                            stage = 'recovery_required',
                            response_body = response_body || $4::jsonb,
                            safe_error_code = $3,
                            lease_expires_at = NULL,
                            completed_at = COALESCE(completed_at, NOW()),
                            updated_at = NOW()
                        WHERE tenant_id = $1
                          AND id = $2
                          AND record_status::text = ANY($5::text[])
                          AND lease_expires_at IS NOT NULL
                          AND lease_expires_at <= NOW()
                        RETURNING *
                        """,
                        tenant_id,
                        record_id,
                        safe_error_code,
                        recovery_projection,
                        list(NONTERMINAL_STATUSES),
                    )
                if row is not None:
                    return self._normalize_record(row)
                return await self.get_by_id(
                    tenant_id=tenant_id,
                    record_id=record_id,
                )
            if sqlite_conn is None:
                raise IdempotencyStoreUnavailableError
            return await asyncio.to_thread(
                self._reconcile_expired_lease_sqlite,
                sqlite_conn,
                tenant_id,
                record_id,
                safe_error_code,
            )
        except IdempotencyStoreUnavailableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def _backend(self) -> tuple[Any | None, Any | None]:
        if self.require_postgres:
            pool = db.get_verified_pg_pool()
            if pool is None:
                raise IdempotencyStoreUnavailableError
            return pool, None

        pool = await db.get_pool()
        if pool is not None:
            return pool, None
        sqlite_conn = db.get_sqlite_conn()
        if sqlite_conn is None:
            raise IdempotencyStoreUnavailableError
        return None, sqlite_conn

    async def _fetch_one(
        self,
        *,
        pg_query: str,
        sqlite_query: str,
        args: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        pool, sqlite_conn = await self._backend()
        try:
            if pool is not None:
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(pg_query, *args)
            else:
                if sqlite_conn is None:
                    raise IdempotencyStoreUnavailableError
                row = await asyncio.to_thread(
                    self._fetch_one_sqlite,
                    sqlite_conn,
                    sqlite_query,
                    args,
                )
        except IdempotencyStoreUnavailableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)
        return self._normalize_record(row) if row is not None else None

    @staticmethod
    def _claim_sqlite(
        connection: Any,
        record_id: str,
        tenant_id: str,
        key_hash: str,
        fingerprint_version: str,
        request_hash: str,
        operation: str,
        scenario: str,
        resource_type: str,
        resource_id: str,
        effective_policy_version: str,
        response_status: int,
        response_json: str,
        owner_instance_id: str,
        lease_seconds: int,
    ) -> tuple[bool, dict[str, Any]]:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO idempotency_records (
                        id, tenant_id, key_hash, fingerprint_version,
                        request_hash, operation, scenario, resource_type,
                        resource_id, record_status, stage,
                        effective_policy_version, response_status,
                        response_body, owner_instance_id, lease_expires_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', 'reserved',
                        ?, ?, ?, ?, datetime('now', ?)
                    )
                    """,
                    (
                        record_id,
                        tenant_id,
                        key_hash,
                        fingerprint_version,
                        request_hash,
                        operation,
                        scenario,
                        resource_type,
                        resource_id,
                        effective_policy_version,
                        response_status,
                        response_json,
                        owner_instance_id,
                        f"+{lease_seconds} seconds",
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM idempotency_records WHERE tenant_id = ? AND key_hash = ?",
                    (tenant_id, key_hash),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        if row is None:
            raise IdempotencyStoreUnavailableError
        return cursor.rowcount == 1, SubmissionIdempotencyRepository._normalize_record(row)

    @staticmethod
    def _transition_sqlite(
        connection: Any,
        tenant_id: str,
        record_id: str,
        expected_statuses: tuple[str, ...],
        new_status: str,
        stage: str | None,
        response_status: int | None,
        response_json: str | None,
        result_json: str | None,
        safe_error_code: str | None,
        lease_seconds: int | None,
        owner_instance_id: str,
        complete: bool,
        clear_lease: bool,
    ) -> dict[str, Any] | None:
        placeholders = ", ".join("?" for _ in expected_statuses)
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    UPDATE idempotency_records
                    SET record_status = ?,
                        stage = COALESCE(?, stage),
                        response_status = COALESCE(?, response_status),
                        response_body = COALESCE(?, response_body),
                        result_snapshot = COALESCE(?, result_snapshot),
                        safe_error_code = COALESCE(?, safe_error_code),
                        lease_expires_at = CASE
                            WHEN ? THEN NULL
                            WHEN ? IS NULL THEN lease_expires_at
                            ELSE datetime('now', ?)
                        END,
                        completed_at = CASE
                            WHEN ? THEN COALESCE(completed_at, CURRENT_TIMESTAMP)
                            ELSE completed_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ?
                      AND id = ?
                      AND owner_instance_id = ?
                      AND record_status IN ({placeholders})
                    """,
                    (
                        new_status,
                        stage,
                        response_status,
                        response_json,
                        result_json,
                        safe_error_code,
                        int(clear_lease),
                        lease_seconds,
                        f"+{lease_seconds} seconds" if lease_seconds else None,
                        int(complete),
                        tenant_id,
                        record_id,
                        owner_instance_id,
                        *expected_statuses,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.commit()
                    return None
                row = connection.execute(
                    "SELECT * FROM idempotency_records WHERE tenant_id = ? AND id = ?",
                    (tenant_id, record_id),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return SubmissionIdempotencyRepository._normalize_record(row) if row is not None else None

    @staticmethod
    def _renew_lease_sqlite(
        connection: Any,
        tenant_id: str,
        record_id: str,
        owner_instance_id: str,
        expected_statuses: tuple[str, ...],
        lease_seconds: int,
    ) -> dict[str, Any] | None:
        placeholders = ", ".join("?" for _ in expected_statuses)
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    UPDATE idempotency_records
                    SET lease_expires_at = datetime('now', ?),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ?
                      AND id = ?
                      AND owner_instance_id = ?
                      AND record_status IN ({placeholders})
                    """,
                    (
                        f"+{lease_seconds} seconds",
                        tenant_id,
                        record_id,
                        owner_instance_id,
                        *expected_statuses,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.commit()
                    return None
                row = connection.execute(
                    "SELECT * FROM idempotency_records WHERE tenant_id = ? AND id = ?",
                    (tenant_id, record_id),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return SubmissionIdempotencyRepository._normalize_record(row) if row is not None else None

    @staticmethod
    def _reconcile_expired_lease_sqlite(
        connection: Any,
        tenant_id: str,
        record_id: str,
        safe_error_code: str,
    ) -> dict[str, Any] | None:
        placeholders = ", ".join("?" for _ in NONTERMINAL_STATUSES)
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT * FROM idempotency_records WHERE tenant_id = ? AND id = ?",
                    (tenant_id, record_id),
                ).fetchone()
                if existing is None:
                    connection.commit()
                    return None
                current = SubmissionIdempotencyRepository._normalize_record(existing)
                response_body = dict(current.get("response_body") or {})
                response_body["status"] = "recovery_required"
                connection.execute(
                    f"""
                    UPDATE idempotency_records
                    SET record_status = 'recovery_required',
                        stage = 'recovery_required',
                        response_body = ?,
                        safe_error_code = ?,
                        lease_expires_at = NULL,
                        completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ?
                      AND id = ?
                      AND record_status IN ({placeholders})
                      AND lease_expires_at IS NOT NULL
                      AND lease_expires_at <= CURRENT_TIMESTAMP
                    """,
                    (
                        SubmissionIdempotencyRepository._encode_json(response_body),
                        safe_error_code,
                        tenant_id,
                        record_id,
                        *NONTERMINAL_STATUSES,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM idempotency_records WHERE tenant_id = ? AND id = ?",
                    (tenant_id, record_id),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return SubmissionIdempotencyRepository._normalize_record(row) if row is not None else None

    @staticmethod
    def _fetch_one_sqlite(
        connection: Any,
        query: str,
        args: tuple[Any, ...],
    ) -> Any | None:
        with db.get_sqlite_lock():
            return connection.execute(query, args).fetchone()

    @staticmethod
    def _normalize_record(row: Any) -> dict[str, Any]:
        record = dict(row)
        for column in _JSON_COLUMNS:
            value = record.get(column)
            if not isinstance(value, str):
                continue
            try:
                record[column] = json.loads(value)
            except json.JSONDecodeError as exc:
                raise IdempotencyStoreUnavailableError from exc
        return record

    @staticmethod
    def _fingerprint_matches(
        record: Mapping[str, Any],
        *,
        fingerprint_version: str,
        request_hash: str,
        operation: str,
        scenario: str,
    ) -> bool:
        return (
            record.get("fingerprint_version") == fingerprint_version
            and record.get("request_hash") == request_hash
            and record.get("operation") == operation
            and record.get("scenario") == scenario
        )

    @classmethod
    def _validate_claim(cls, **values: Any) -> None:
        cls._require_text("tenant_id", values["tenant_id"])
        cls._require_digest("key_hash", values["key_hash"])
        cls._require_text("fingerprint_version", values["fingerprint_version"])
        cls._require_digest("request_hash", values["request_hash"])
        cls._require_text("operation", values["operation"])
        if values["scenario"] not in ALLOWED_SCENARIOS:
            raise ValueError("scenario is invalid")
        if values["resource_type"] not in ALLOWED_RESOURCE_TYPES:
            raise ValueError("resource_type is invalid")
        cls._require_text("resource_id", values["resource_id"])
        cls._require_text(
            "effective_policy_version",
            values["effective_policy_version"],
        )
        cls._validate_response_status(values["response_status"])
        cls._require_text("owner_instance_id", values["owner_instance_id"])
        cls._validate_lease_seconds(values["lease_seconds"])

    @classmethod
    def _validate_transition(
        cls,
        *,
        tenant_id: str,
        record_id: str,
        expected_statuses: Collection[str],
        new_status: str,
        response_status: int | None,
        lease_seconds: int | None,
    ) -> tuple[str, ...]:
        cls._require_text("tenant_id", tenant_id)
        cls._require_text("record_id", record_id)
        statuses = cls._validate_expected_statuses(expected_statuses)
        if new_status not in ALLOWED_STATUSES:
            raise ValueError("new_status is invalid")
        if response_status is not None:
            cls._validate_response_status(response_status)
        if lease_seconds is not None:
            cls._validate_lease_seconds(lease_seconds)
        return statuses

    @staticmethod
    def _validate_expected_statuses(statuses: Collection[str]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(statuses)))
        if not normalized or any(status not in ALLOWED_STATUSES for status in normalized):
            raise ValueError("expected_statuses are invalid")
        return normalized

    @staticmethod
    def _require_text(name: str, value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")

    @staticmethod
    def _require_digest(name: str, value: Any) -> None:
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")

    @staticmethod
    def _validate_response_status(value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or not 100 <= value <= 599:
            raise ValueError("response_status is invalid")

    @staticmethod
    def _validate_lease_seconds(value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 86_400:
            raise ValueError("lease_seconds is invalid")

    @staticmethod
    def _encode_json(value: Mapping[str, Any]) -> str:
        try:
            return json.dumps(
                dict(value),
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("safe projection must be canonical JSON") from exc

    @staticmethod
    def _raise_store_unavailable(exc: Exception) -> None:
        logger.warning(
            "Submission idempotency store operation failed (%s)",
            type(exc).__name__,
        )
        raise IdempotencyStoreUnavailableError from None


__all__ = [
    "ALLOWED_STATUSES",
    "ClaimResult",
    "IdempotencyStoreUnavailableError",
    "NONTERMINAL_STATUSES",
    "SubmissionIdempotencyRepository",
    "TERMINAL_STATUSES",
]
