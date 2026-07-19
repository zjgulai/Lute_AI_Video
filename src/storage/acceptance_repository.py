"""Atomic durable storage for single-use human acceptance records."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from asyncpg.exceptions import UniqueViolationError

from . import db

logger = logging.getLogger(__name__)

_ALLOWED_ARTIFACT_KINDS = frozenset({"text", "image", "audio", "video"})
_ALLOWED_DECISIONS = frozenset({"accepted", "rejected"})
_ALLOWED_REVIEWER_KEY_TYPES = frozenset({"tenant", "test_bundle", "env_fallback"})
_ALLOWED_SCENARIOS = frozenset({"fast", "s1", "s2", "s3", "s4", "s5"})
_ALLOWED_SOURCE_RESOURCE_TYPES = frozenset({"fast", "scenario"})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class AcceptanceStoreUnavailableError(RuntimeError):
    pass


class AcceptancePayloadConflictError(ValueError):
    pass


class AcceptanceAlreadyAvailableError(ValueError):
    pass


class AcceptanceSourceNotFoundError(LookupError):
    pass


class AcceptanceNotRevocableError(ValueError):
    pass


class AcceptanceNotAvailableError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CreateAcceptanceResult:
    outcome: Literal["owner", "replay"]
    record: dict[str, Any]


class AcceptanceRecordRepository:
    """Persist tenant-owned acceptance decisions with SQLite arbitration."""

    def __init__(self, *, require_postgres: bool | None = None) -> None:
        if require_postgres is None:
            environment = os.getenv("ENVIRONMENT", "development").strip().lower()
            require_postgres = environment in {"prod", "production"}
        self.require_postgres = require_postgres

    async def get_by_creation_key_hash(
        self,
        *,
        tenant_id: str,
        creation_key_hash: str,
    ) -> dict[str, Any] | None:
        """Read a creation-key record without exposing another tenant's row."""

        self._require_text("tenant_id", tenant_id)
        self._require_digest("creation_key_hash", creation_key_hash)
        return await self._fetch_one(
            pg_query=(
                "SELECT * FROM acceptance_records "
                "WHERE tenant_id = $1 AND creation_key_hash = $2"
            ),
            sqlite_query=(
                "SELECT * FROM acceptance_records "
                "WHERE tenant_id = ? AND creation_key_hash = ?"
            ),
            args=(tenant_id, creation_key_hash),
        )

    async def get_by_id(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
    ) -> dict[str, Any] | None:
        """Read one tenant-owned acceptance record by public identifier."""

        self._require_text("tenant_id", tenant_id)
        self._require_text("acceptance_id", acceptance_id)
        return await self._fetch_one(
            pg_query=(
                "SELECT * FROM acceptance_records WHERE tenant_id = $1 AND id = $2"
            ),
            sqlite_query=(
                "SELECT * FROM acceptance_records WHERE tenant_id = ? AND id = ?"
            ),
            args=(tenant_id, acceptance_id),
        )

    async def create_or_replay(
        self,
        *,
        tenant_id: str,
        creation_key_hash: str,
        fingerprint_version: str,
        request_hash: str,
        source_resource_type: str,
        source_resource_id: str,
        scenario: str,
        artifact_path: str,
        artifact_sha256: str,
        artifact_size_bytes: int,
        artifact_kind: str,
        decision: str,
        reviewer_key_id: str,
        reviewer_key_type: str,
        review_notes: str,
        expires_in_seconds: int,
    ) -> CreateAcceptanceResult:
        """Create one decision or replay its tenant-scoped creation key."""

        values = {
            "tenant_id": tenant_id,
            "creation_key_hash": creation_key_hash,
            "fingerprint_version": fingerprint_version,
            "request_hash": request_hash,
            "source_resource_type": source_resource_type,
            "source_resource_id": source_resource_id,
            "scenario": scenario,
            "artifact_path": artifact_path,
            "artifact_sha256": artifact_sha256,
            "artifact_size_bytes": artifact_size_bytes,
            "artifact_kind": artifact_kind,
            "decision": decision,
            "reviewer_key_id": reviewer_key_id,
            "reviewer_key_type": reviewer_key_type,
            "review_notes": review_notes,
            "expires_in_seconds": expires_in_seconds,
        }
        self._validate_create(values)

        record_id = str(uuid.uuid4())
        pool, sqlite_connection = await self._backend()
        if pool is not None:
            try:
                return await self._create_or_replay_postgres(
                    pool,
                    record_id,
                    values,
                )
            except (
                AcceptanceAlreadyAvailableError,
                AcceptancePayloadConflictError,
                AcceptanceSourceNotFoundError,
            ):
                raise
            except Exception as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise AcceptanceStoreUnavailableError

        try:
            return await asyncio.to_thread(
                self._create_or_replay_sqlite,
                sqlite_connection,
                record_id,
                values,
            )
        except (
            AcceptanceAlreadyAvailableError,
            AcceptancePayloadConflictError,
            AcceptanceSourceNotFoundError,
        ):
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def reconcile_expired(
        self,
        *,
        tenant_id: str,
        acceptance_id: str | None = None,
        artifact_path: str | None = None,
    ) -> int:
        """CAS database-expired available rows to ``expired``."""

        self._require_text("tenant_id", tenant_id)
        if acceptance_id is not None:
            self._require_text("acceptance_id", acceptance_id)
        if artifact_path is not None:
            self._require_text("artifact_path", artifact_path)

        pool, sqlite_connection = await self._backend()
        if pool is not None:
            clauses = [
                "tenant_id = $1",
                "record_status = 'available'",
                "expires_at <= NOW()",
            ]
            args: list[Any] = [tenant_id]
            if acceptance_id is not None:
                args.append(acceptance_id)
                clauses.append(f"id = ${len(args)}")
            if artifact_path is not None:
                args.append(artifact_path)
                clauses.append(f"artifact_path = ${len(args)}")
            query = f"""
                UPDATE acceptance_records
                SET record_status = 'expired', updated_at = NOW()
                WHERE {' AND '.join(clauses)}
                RETURNING id
            """
            try:
                async with pool.acquire() as connection:
                    rows = await connection.fetch(query, *args)
                return len(rows)
            except Exception as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise AcceptanceStoreUnavailableError
        try:
            return await asyncio.to_thread(
                self._reconcile_expired_sqlite,
                sqlite_connection,
                tenant_id,
                acceptance_id,
                artifact_path,
            )
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def revoke(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        reviewer_key_id: str,
    ) -> dict[str, Any]:
        """Revoke one live accepted record; replay an existing revocation."""

        self._require_text("tenant_id", tenant_id)
        self._require_text("acceptance_id", acceptance_id)
        self._require_text("reviewer_key_id", reviewer_key_id)

        pool, sqlite_connection = await self._backend()
        if pool is not None:
            try:
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(
                        """
                        UPDATE acceptance_records
                        SET record_status = 'revoked',
                            revoked_at = NOW(),
                            revoked_by_key_id = $3,
                            updated_at = NOW()
                        WHERE tenant_id = $1 AND id = $2
                          AND decision = 'accepted'
                          AND record_status = 'available'
                          AND expires_at > NOW()
                        RETURNING *
                        """,
                        tenant_id,
                        acceptance_id,
                        reviewer_key_id,
                    )
                    if row is None:
                        row = await connection.fetchrow(
                            """
                            SELECT * FROM acceptance_records
                            WHERE tenant_id = $1 AND id = $2
                            """,
                            tenant_id,
                            acceptance_id,
                        )
                if row is not None and row["record_status"] == "revoked":
                    return dict(row)
                raise AcceptanceNotRevocableError
            except AcceptanceNotRevocableError:
                raise
            except Exception as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise AcceptanceStoreUnavailableError
        try:
            return await asyncio.to_thread(
                self._revoke_sqlite,
                sqlite_connection,
                tenant_id,
                acceptance_id,
                reviewer_key_id,
            )
        except AcceptanceNotRevocableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def consume(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        artifact_path: str,
        artifact_sha256: str,
        consumer_operation: str,
        consumer_resource_id: str,
    ) -> dict[str, Any]:
        """Atomically consume an exact, live accepted artifact once."""

        for name, value in (
            ("tenant_id", tenant_id),
            ("acceptance_id", acceptance_id),
            ("artifact_path", artifact_path),
            ("consumer_operation", consumer_operation),
            ("consumer_resource_id", consumer_resource_id),
        ):
            self._require_text(name, value)
        self._require_digest("artifact_sha256", artifact_sha256)

        pool, sqlite_connection = await self._backend()
        if pool is not None:
            try:
                async with pool.acquire() as connection:
                    row = await connection.fetchrow(
                        """
                        UPDATE acceptance_records
                        SET record_status = 'consumed',
                            consumed_at = NOW(),
                            consumed_by_operation = $5,
                            consumed_by_resource_id = $6,
                            updated_at = NOW()
                        WHERE tenant_id = $1 AND id = $2
                          AND decision = 'accepted'
                          AND record_status = 'available'
                          AND expires_at > NOW()
                          AND artifact_path = $3
                          AND artifact_sha256 = $4
                        RETURNING *
                        """,
                        tenant_id,
                        acceptance_id,
                        artifact_path,
                        artifact_sha256,
                        consumer_operation,
                        consumer_resource_id,
                    )
                    if row is not None:
                        return dict(row)
                    await connection.fetchrow(
                        """
                        SELECT * FROM acceptance_records
                        WHERE tenant_id = $1 AND id = $2
                        """,
                        tenant_id,
                        acceptance_id,
                    )
                raise AcceptanceNotAvailableError
            except AcceptanceNotAvailableError:
                raise
            except Exception as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise AcceptanceStoreUnavailableError
        try:
            return await asyncio.to_thread(
                self._consume_sqlite,
                sqlite_connection,
                tenant_id,
                acceptance_id,
                artifact_path,
                artifact_sha256,
                consumer_operation,
                consumer_resource_id,
            )
        except AcceptanceNotAvailableError:
            raise
        except Exception as exc:
            self._raise_store_unavailable(exc)

    async def _backend(self) -> tuple[Any | None, sqlite3.Connection | None]:
        if self.require_postgres:
            pool = db.get_verified_pg_pool()
            if pool is None:
                raise AcceptanceStoreUnavailableError
            return pool, None

        pool = await db.get_pool()
        if pool is not None:
            return pool, None
        sqlite_connection = db.get_sqlite_conn()
        if sqlite_connection is None:
            raise AcceptanceStoreUnavailableError
        return None, sqlite_connection

    async def _create_or_replay_postgres(
        self,
        pool: Any,
        record_id: str,
        values: Mapping[str, Any],
    ) -> CreateAcceptanceResult:
        try:
            async with pool.acquire() as connection:
                async with connection.transaction():
                    source = await connection.fetchrow(
                        """
                        SELECT id FROM idempotency_records
                        WHERE tenant_id = $1
                          AND resource_type = $2
                          AND resource_id = $3
                        FOR UPDATE
                        """,
                        values["tenant_id"],
                        values["source_resource_type"],
                        values["source_resource_id"],
                    )
                    if source is None:
                        raise AcceptanceSourceNotFoundError

                    existing = await connection.fetchrow(
                        """
                        SELECT * FROM acceptance_records
                        WHERE tenant_id = $1 AND creation_key_hash = $2
                        """,
                        values["tenant_id"],
                        values["creation_key_hash"],
                    )
                    if existing is not None:
                        record = dict(existing)
                        if self._fingerprint_matches(record, values):
                            return CreateAcceptanceResult("replay", record)
                        raise AcceptancePayloadConflictError

                    await connection.execute(
                        """
                        UPDATE acceptance_records
                        SET record_status = 'expired', updated_at = NOW()
                        WHERE tenant_id = $1 AND artifact_path = $2
                          AND record_status = 'available'
                          AND expires_at <= NOW()
                        """,
                        values["tenant_id"],
                        values["artifact_path"],
                    )
                    if values["decision"] == "rejected":
                        await connection.execute(
                            """
                            UPDATE acceptance_records
                            SET record_status = 'revoked',
                                revoked_at = NOW(),
                                revoked_by_key_id = $1,
                                revoked_by_record_id = $2,
                                updated_at = NOW()
                            WHERE tenant_id = $3 AND artifact_path = $4
                              AND record_status = 'available'
                            """,
                            values["reviewer_key_id"],
                            record_id,
                            values["tenant_id"],
                            values["artifact_path"],
                        )
                    row = await connection.fetchrow(
                        """
                        INSERT INTO acceptance_records (
                            id, tenant_id, creation_key_hash,
                            fingerprint_version, request_hash,
                            source_resource_type, source_resource_id, scenario,
                            artifact_path, artifact_sha256, artifact_size_bytes,
                            artifact_kind, decision, record_status,
                            reviewer_key_id, reviewer_key_type, review_notes,
                            expires_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9,
                            $10, $11, $12, $13::varchar,
                            CASE WHEN $13::varchar = 'accepted'
                                THEN 'available' ELSE 'rejected' END,
                            $14, $15, $16,
                            NOW() + make_interval(secs => $17::double precision)
                        )
                        RETURNING *
                        """,
                        record_id,
                        values["tenant_id"],
                        values["creation_key_hash"],
                        values["fingerprint_version"],
                        values["request_hash"],
                        values["source_resource_type"],
                        values["source_resource_id"],
                        values["scenario"],
                        values["artifact_path"],
                        values["artifact_sha256"],
                        values["artifact_size_bytes"],
                        values["artifact_kind"],
                        values["decision"],
                        values["reviewer_key_id"],
                        values["reviewer_key_type"],
                        values["review_notes"],
                        values["expires_in_seconds"],
                    )
            if row is None:
                raise AcceptanceStoreUnavailableError
            return CreateAcceptanceResult("owner", dict(row))
        except UniqueViolationError as exc:
            constraint_name = getattr(exc, "constraint_name", None)
            existing = await self._fetch_one_postgres(
                pool,
                """
                SELECT * FROM acceptance_records
                WHERE tenant_id = $1 AND creation_key_hash = $2
                """,
                (values["tenant_id"], values["creation_key_hash"]),
            )
            if existing is not None:
                if self._fingerprint_matches(existing, values):
                    return CreateAcceptanceResult("replay", existing)
                raise AcceptancePayloadConflictError
            if constraint_name == "uq_acceptance_records_tenant_available_path":
                raise AcceptanceAlreadyAvailableError from None
            raise

    @staticmethod
    async def _fetch_one_postgres(
        pool: Any,
        query: str,
        args: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        async with pool.acquire() as connection:
            row = await connection.fetchrow(query, *args)
        return dict(row) if row is not None else None

    async def _fetch_one(
        self,
        *,
        pg_query: str,
        sqlite_query: str,
        args: tuple[Any, ...],
    ) -> dict[str, Any] | None:
        pool, sqlite_connection = await self._backend()
        if pool is not None:
            try:
                return await self._fetch_one_postgres(pool, pg_query, args)
            except Exception as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise AcceptanceStoreUnavailableError
        try:
            row = await asyncio.to_thread(
                self._fetch_one_sqlite,
                sqlite_connection,
                sqlite_query,
                args,
            )
        except Exception as exc:
            self._raise_store_unavailable(exc)
        return dict(row) if row is not None else None

    @staticmethod
    def _create_or_replay_sqlite(
        connection: sqlite3.Connection,
        record_id: str,
        values: Mapping[str, Any],
    ) -> CreateAcceptanceResult:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                source = connection.execute(
                    """
                    SELECT id FROM idempotency_records
                    WHERE tenant_id = ? AND resource_type = ? AND resource_id = ?
                    """,
                    (
                        values["tenant_id"],
                        values["source_resource_type"],
                        values["source_resource_id"],
                    ),
                ).fetchone()
                if source is None:
                    raise AcceptanceSourceNotFoundError

                existing = connection.execute(
                    """
                    SELECT * FROM acceptance_records
                    WHERE tenant_id = ? AND creation_key_hash = ?
                    """,
                    (values["tenant_id"], values["creation_key_hash"]),
                ).fetchone()
                if existing is not None:
                    record = dict(existing)
                    if AcceptanceRecordRepository._fingerprint_matches(record, values):
                        connection.commit()
                        return CreateAcceptanceResult("replay", record)
                    raise AcceptancePayloadConflictError

                connection.execute(
                    """
                    UPDATE acceptance_records
                    SET record_status = 'expired', updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ? AND artifact_path = ?
                      AND record_status = 'available'
                      AND expires_at <= CURRENT_TIMESTAMP
                    """,
                    (values["tenant_id"], values["artifact_path"]),
                )
                if values["decision"] == "rejected":
                    connection.execute(
                        """
                        UPDATE acceptance_records
                        SET record_status = 'revoked',
                            revoked_at = CURRENT_TIMESTAMP,
                            revoked_by_key_id = ?,
                            revoked_by_record_id = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tenant_id = ? AND artifact_path = ?
                          AND record_status = 'available'
                        """,
                        (
                            values["reviewer_key_id"],
                            record_id,
                            values["tenant_id"],
                            values["artifact_path"],
                        ),
                    )
                record_status = (
                    "available" if values["decision"] == "accepted" else "rejected"
                )
                connection.execute(
                    """
                    INSERT INTO acceptance_records (
                        id, tenant_id, creation_key_hash, fingerprint_version,
                        request_hash, source_resource_type, source_resource_id,
                        scenario, artifact_path, artifact_sha256,
                        artifact_size_bytes, artifact_kind, decision,
                        record_status, reviewer_key_id, reviewer_key_type,
                        review_notes, expires_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        datetime('now', ?)
                    )
                    """,
                    (
                        record_id,
                        values["tenant_id"],
                        values["creation_key_hash"],
                        values["fingerprint_version"],
                        values["request_hash"],
                        values["source_resource_type"],
                        values["source_resource_id"],
                        values["scenario"],
                        values["artifact_path"],
                        values["artifact_sha256"],
                        values["artifact_size_bytes"],
                        values["artifact_kind"],
                        values["decision"],
                        record_status,
                        values["reviewer_key_id"],
                        values["reviewer_key_type"],
                        values["review_notes"],
                        f"+{values['expires_in_seconds']} seconds",
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM acceptance_records WHERE tenant_id = ? AND id = ?",
                    (values["tenant_id"], record_id),
                ).fetchone()
                connection.commit()
            except sqlite3.IntegrityError as exc:
                connection.rollback()
                if "acceptance_records.tenant_id, acceptance_records.artifact_path" in str(exc):
                    raise AcceptanceAlreadyAvailableError from None
                raise
            except Exception:
                connection.rollback()
                raise

        if row is None:
            raise AcceptanceStoreUnavailableError
        return CreateAcceptanceResult("owner", dict(row))

    @staticmethod
    def _reconcile_expired_sqlite(
        connection: sqlite3.Connection,
        tenant_id: str,
        acceptance_id: str | None,
        artifact_path: str | None,
    ) -> int:
        clauses = [
            "tenant_id = ?",
            "record_status = 'available'",
            "expires_at <= CURRENT_TIMESTAMP",
        ]
        args: list[Any] = [tenant_id]
        if acceptance_id is not None:
            clauses.append("id = ?")
            args.append(acceptance_id)
        if artifact_path is not None:
            clauses.append("artifact_path = ?")
            args.append(artifact_path)

        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    f"""
                    UPDATE acceptance_records
                    SET record_status = 'expired', updated_at = CURRENT_TIMESTAMP
                    WHERE {' AND '.join(clauses)}
                    """,
                    args,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return cursor.rowcount

    @staticmethod
    def _revoke_sqlite(
        connection: sqlite3.Connection,
        tenant_id: str,
        acceptance_id: str,
        reviewer_key_id: str,
    ) -> dict[str, Any]:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE acceptance_records
                    SET record_status = 'revoked',
                        revoked_at = CURRENT_TIMESTAMP,
                        revoked_by_key_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ? AND id = ?
                      AND decision = 'accepted'
                      AND record_status = 'available'
                      AND expires_at > CURRENT_TIMESTAMP
                    """,
                    (reviewer_key_id, tenant_id, acceptance_id),
                )
                row = connection.execute(
                    "SELECT * FROM acceptance_records WHERE tenant_id = ? AND id = ?",
                    (tenant_id, acceptance_id),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        if cursor.rowcount == 1 and row is not None:
            return dict(row)
        if row is not None and row["record_status"] == "revoked":
            return dict(row)
        raise AcceptanceNotRevocableError

    @staticmethod
    def _consume_sqlite(
        connection: sqlite3.Connection,
        tenant_id: str,
        acceptance_id: str,
        artifact_path: str,
        artifact_sha256: str,
        consumer_operation: str,
        consumer_resource_id: str,
    ) -> dict[str, Any]:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                cursor = connection.execute(
                    """
                    UPDATE acceptance_records
                    SET record_status = 'consumed',
                        consumed_at = CURRENT_TIMESTAMP,
                        consumed_by_operation = ?,
                        consumed_by_resource_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ? AND id = ?
                      AND decision = 'accepted'
                      AND record_status = 'available'
                      AND expires_at > CURRENT_TIMESTAMP
                      AND artifact_path = ?
                      AND artifact_sha256 = ?
                    """,
                    (
                        consumer_operation,
                        consumer_resource_id,
                        tenant_id,
                        acceptance_id,
                        artifact_path,
                        artifact_sha256,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM acceptance_records WHERE tenant_id = ? AND id = ?",
                    (tenant_id, acceptance_id),
                ).fetchone()
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        if cursor.rowcount == 1 and row is not None:
            return dict(row)
        raise AcceptanceNotAvailableError

    @staticmethod
    def _fetch_one_sqlite(
        connection: sqlite3.Connection,
        query: str,
        args: tuple[Any, ...],
    ) -> sqlite3.Row | None:
        with db.get_sqlite_lock():
            return connection.execute(query, args).fetchone()

    @staticmethod
    def _fingerprint_matches(
        record: Mapping[str, Any],
        values: Mapping[str, Any],
    ) -> bool:
        return (
            record.get("fingerprint_version") == values["fingerprint_version"]
            and record.get("request_hash") == values["request_hash"]
        )

    @classmethod
    def _validate_create(cls, values: Mapping[str, Any]) -> None:
        for name in (
            "tenant_id",
            "fingerprint_version",
            "source_resource_id",
            "artifact_path",
            "reviewer_key_id",
        ):
            cls._require_text(name, values[name])
        cls._require_digest("creation_key_hash", values["creation_key_hash"])
        cls._require_digest("request_hash", values["request_hash"])
        cls._require_digest("artifact_sha256", values["artifact_sha256"])
        if values["source_resource_type"] not in _ALLOWED_SOURCE_RESOURCE_TYPES:
            raise ValueError("source_resource_type is invalid")
        if values["scenario"] not in _ALLOWED_SCENARIOS:
            raise ValueError("scenario is invalid")
        if values["artifact_kind"] not in _ALLOWED_ARTIFACT_KINDS:
            raise ValueError("artifact_kind is invalid")
        if values["decision"] not in _ALLOWED_DECISIONS:
            raise ValueError("decision is invalid")
        if values["reviewer_key_type"] not in _ALLOWED_REVIEWER_KEY_TYPES:
            raise ValueError("reviewer_key_type is invalid")
        if not isinstance(values["review_notes"], str):
            raise ValueError("review_notes is invalid")
        cls._require_positive_integer(
            "artifact_size_bytes",
            values["artifact_size_bytes"],
        )
        cls._require_positive_integer(
            "expires_in_seconds",
            values["expires_in_seconds"],
        )

    @staticmethod
    def _require_text(name: str, value: Any) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} is required")

    @staticmethod
    def _require_digest(name: str, value: Any) -> None:
        if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
            raise ValueError(f"{name} must be a lowercase SHA-256 digest")

    @staticmethod
    def _require_positive_integer(name: str, value: Any) -> None:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive integer")

    @staticmethod
    def _raise_store_unavailable(exc: Exception) -> None:
        logger.warning(
            "Acceptance record store operation failed (%s)",
            type(exc).__name__,
        )
        raise AcceptanceStoreUnavailableError from None


__all__ = [
    "AcceptanceAlreadyAvailableError",
    "AcceptanceNotAvailableError",
    "AcceptanceNotRevocableError",
    "AcceptancePayloadConflictError",
    "AcceptanceRecordRepository",
    "AcceptanceSourceNotFoundError",
    "AcceptanceStoreUnavailableError",
    "CreateAcceptanceResult",
]
