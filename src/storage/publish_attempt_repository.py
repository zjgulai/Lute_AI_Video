"""Fail-closed, tenant-bound persistence for W1-23 publish attempts."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

import asyncpg
from pydantic import ValidationError

from src.models.publish_attempt import PublishMetadata, PublishReceiptV1

from . import db

logger = logging.getLogger(__name__)

ALLOWED_PLATFORMS = frozenset({"tiktok", "shopify"})
ALLOWED_ROUTE_KINDS = frozenset({"canonical", "legacy_adapter"})
ALLOWED_STATUSES = frozenset(
    {
        "prepared",
        "authorization_failed",
        "preflight_failed",
        "acceptance_consumed",
        "published",
        "failed",
        "ambiguous",
    }
)
ALLOWED_ERROR_CODES = frozenset(
    {
        "publish_connector_not_ready",
        "publish_connector_not_ready_after_consume",
        "publish_connector_simulated",
        "publish_attempt_store_unavailable",
        "acceptance_not_found",
        "acceptance_expired",
        "acceptance_not_available",
        "acceptance_artifact_integrity_mismatch",
        "acceptance_store_unavailable",
        "publish_artifact_unavailable_after_consume",
        "publish_attempt_state_unknown",
        "publish_connector_failed",
        "publish_outcome_ambiguous",
        "publish_preflight_rejected",
        "publish_preflight_unavailable",
    }
)
ERROR_CODES_BY_STATUS = {
    "authorization_failed": frozenset(
        {
            "acceptance_not_found",
            "acceptance_expired",
            "acceptance_not_available",
            "acceptance_artifact_integrity_mismatch",
            "acceptance_store_unavailable",
        }
    ),
    "failed": frozenset(
        {
            "publish_artifact_unavailable_after_consume",
            "publish_connector_not_ready_after_consume",
            "publish_connector_simulated",
            "publish_connector_failed",
        }
    ),
    "preflight_failed": frozenset(
        {
            "publish_preflight_rejected",
            "publish_preflight_unavailable",
        }
    ),
    "ambiguous": frozenset({"publish_outcome_ambiguous"}),
}
LEGAL_TRANSITIONS = frozenset(
    {
        ("prepared", "authorization_failed"),
        ("prepared", "preflight_failed"),
        ("prepared", "acceptance_consumed"),
        ("acceptance_consumed", "published"),
        ("acceptance_consumed", "failed"),
        ("acceptance_consumed", "ambiguous"),
    }
)
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


class PublishAttemptStoreUnavailable(RuntimeError):
    """The attempt store or its required W1-23 schema is unavailable."""


_STORE_DRIVER_ERRORS = (
    sqlite3.Error,
    asyncpg.PostgresError,
    asyncpg.InterfaceError,
    asyncpg.InternalClientError,
    OSError,
    ConnectionError,
    TimeoutError,
)


class PublishAttemptRepository:
    """Persist one-way publish-attempt state using PG or local SQLite."""

    def __init__(self, *, require_postgres: bool | None = None) -> None:
        if require_postgres is None:
            environment = os.getenv("ENVIRONMENT", "development").strip().lower()
            require_postgres = environment in {"prod", "production"}
        self.require_postgres = require_postgres

    async def create_prepared(
        self,
        *,
        tenant_id: str,
        acceptance_id: str,
        platform: str,
        route_kind: str,
        metadata: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._require_text("tenant_id", tenant_id, max_length=64)
        self._validate_uuid4("acceptance_id", acceptance_id)
        self._validate_platform(platform)
        self._validate_route_kind(route_kind)
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata is invalid")
        attempt_id = str(uuid.uuid4())
        content = {
            "schema_version": "publish-attempt.v1",
            "route_kind": route_kind,
            "metadata": dict(metadata),
        }
        return await self._insert_prepared(
            attempt_id=attempt_id,
            tenant_id=tenant_id,
            acceptance_id=acceptance_id,
            platform=platform,
            content_json=self._encode_content(content, tenant_id=tenant_id),
        )

    async def get_by_id(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        self._require_text("tenant_id", tenant_id, max_length=64)
        self._validate_uuid4("attempt_id", attempt_id)
        return await self._fetch_one(
            pg_query=(
                "SELECT * FROM publish_logs "
                "WHERE tenant_id = $1 AND id = $2::uuid"
            ),
            sqlite_query=(
                "SELECT * FROM publish_logs "
                "WHERE tenant_id = ? AND id = ?"
            ),
            args=(tenant_id, attempt_id),
        )

    async def get_published_receipt_by_post_id(
        self,
        *,
        tenant_id: str,
        platform: str,
        post_id: str,
    ) -> PublishReceiptV1 | None:
        self._require_text("tenant_id", tenant_id, max_length=64)
        self._validate_platform(platform)
        self._require_text("post_id", post_id, max_length=256)
        records = await self._fetch_many(
            pg_query=(
                "SELECT * FROM publish_logs "
                "WHERE tenant_id = $1 AND platform = $2 AND post_id = $3 "
                "AND status = 'published' AND receipt IS NOT NULL"
            ),
            sqlite_query=(
                "SELECT * FROM publish_logs "
                "WHERE tenant_id = ? AND platform = ? AND post_id = ? "
                "AND status = 'published' AND receipt IS NOT NULL"
            ),
            args=(tenant_id, platform, post_id),
        )
        receipts: dict[str, PublishReceiptV1] = {}
        for record in records:
            try:
                receipt = self._normalize_receipt(record.get("receipt"))
            except (TypeError, ValueError, ValidationError):
                raise PublishAttemptStoreUnavailable from None
            if (
                receipt is None
                or receipt.platform != platform
                or receipt.post_id != post_id
            ):
                raise PublishAttemptStoreUnavailable
            receipts[receipt.canonical_json()] = receipt
        if len(receipts) > 1:
            logger.warning(
                "Contradictory durable publish receipts found for exact lookup"
            )
            raise PublishAttemptStoreUnavailable
        return next(iter(receipts.values()), None)

    async def transition(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_status: str,
        new_status: str,
        content: Mapping[str, Any] | None = None,
        post_id: str | None = None,
        url: str | None = None,
        error_code: str | None = None,
        receipt: PublishReceiptV1 | Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        self._require_text("tenant_id", tenant_id, max_length=64)
        self._validate_uuid4("attempt_id", attempt_id)
        if (
            not isinstance(expected_status, str)
            or not isinstance(new_status, str)
            or (expected_status, new_status) not in LEGAL_TRANSITIONS
        ):
            raise ValueError("attempt transition is invalid")
        if new_status == "acceptance_consumed":
            if content is None:
                raise ValueError("acceptance-consumed content is required")
            content_json = self._encode_content(content, tenant_id=tenant_id)
            normalized_content = json.loads(content_json)
            if "source" not in normalized_content or "artifact" not in normalized_content:
                raise ValueError("acceptance-consumed content is invalid")
        else:
            if content is not None:
                raise ValueError("attempt transition content is invalid")
            content_json = None
        receipt_model = self._normalize_receipt(receipt)
        self._validate_transition_projection(
            new_status=new_status,
            post_id=post_id,
            url=url,
            error_code=error_code,
            receipt=receipt_model,
            allow_legacy_published=False,
        )
        return await self._transition_backend(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_status=expected_status,
            new_status=new_status,
            content_json=content_json,
            post_id=post_id,
            url=url,
            error_code=error_code,
            receipt_json=(
                receipt_model.canonical_json()
                if receipt_model is not None
                else None
            ),
        )

    async def _backend(self) -> tuple[Any | None, sqlite3.Connection | None]:
        try:
            if self.require_postgres:
                pool = db.get_verified_pg_pool()
                if pool is None:
                    raise PublishAttemptStoreUnavailable
                return pool, None
            pool = await db.get_pool()
            if pool is not None and db.is_pg_available():
                return pool, None
            if db._sqlite_conn is None:
                db._init_sqlite()
            return None, db._sqlite_conn
        except PublishAttemptStoreUnavailable:
            raise
        except _STORE_DRIVER_ERRORS as exc:
            self._raise_store_unavailable(exc)

    async def _insert_prepared(
        self,
        *,
        attempt_id: str,
        tenant_id: str,
        acceptance_id: str,
        platform: str,
        content_json: str,
    ) -> dict[str, Any]:
        pool, sqlite_connection = await self._backend()
        if pool is not None:
            try:
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        row = await connection.fetchrow(
                            """
                            INSERT INTO publish_logs (
                                id, tenant_id, acceptance_id, platform, content,
                                status, created_at, updated_at
                            ) VALUES (
                                $1::uuid, $2, $3, $4, $5::jsonb,
                                'prepared', NOW(), NOW()
                            )
                            RETURNING *
                            """,
                            attempt_id,
                            tenant_id,
                            acceptance_id,
                            platform,
                            content_json,
                        )
                        if row is None:
                            raise PublishAttemptStoreUnavailable
                        record = self._normalize_record(row)
                return record
            except PublishAttemptStoreUnavailable:
                raise
            except _STORE_DRIVER_ERRORS as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise PublishAttemptStoreUnavailable
        try:
            row = await asyncio.to_thread(
                self._insert_prepared_sqlite,
                sqlite_connection,
                attempt_id,
                tenant_id,
                acceptance_id,
                platform,
                content_json,
            )
            return row
        except PublishAttemptStoreUnavailable:
            raise
        except _STORE_DRIVER_ERRORS as exc:
            self._raise_store_unavailable(exc)

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
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        row = await connection.fetchrow(pg_query, *args)
                        record = self._normalize_record(row) if row is not None else None
                return record
            except PublishAttemptStoreUnavailable:
                raise
            except _STORE_DRIVER_ERRORS as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise PublishAttemptStoreUnavailable
        try:
            row = await asyncio.to_thread(
                self._fetch_one_sqlite,
                sqlite_connection,
                sqlite_query,
                args,
            )
            return (
                self._normalize_record(row, require_canonical_json_text=True)
                if row is not None
                else None
            )
        except PublishAttemptStoreUnavailable:
            raise
        except _STORE_DRIVER_ERRORS as exc:
            self._raise_store_unavailable(exc)

    async def _fetch_many(
        self,
        *,
        pg_query: str,
        sqlite_query: str,
        args: tuple[Any, ...],
    ) -> list[dict[str, Any]]:
        pool, sqlite_connection = await self._backend()
        if pool is not None:
            try:
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        rows = await connection.fetch(pg_query, *args)
                        return [self._normalize_record(row) for row in rows]
            except PublishAttemptStoreUnavailable:
                raise
            except _STORE_DRIVER_ERRORS as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise PublishAttemptStoreUnavailable
        try:
            rows = await asyncio.to_thread(
                self._fetch_many_sqlite,
                sqlite_connection,
                sqlite_query,
                args,
            )
            return [
                self._normalize_record(row, require_canonical_json_text=True)
                for row in rows
            ]
        except PublishAttemptStoreUnavailable:
            raise
        except _STORE_DRIVER_ERRORS as exc:
            self._raise_store_unavailable(exc)

    async def _transition_backend(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_status: str,
        new_status: str,
        content_json: str | None,
        post_id: str | None,
        url: str | None,
        error_code: str | None,
        receipt_json: str | None,
    ) -> dict[str, Any] | None:
        pool, sqlite_connection = await self._backend()
        args = (
            tenant_id,
            attempt_id,
            expected_status,
            new_status,
            content_json,
            post_id,
            url,
            error_code,
            receipt_json,
        )
        if pool is not None:
            try:
                async with pool.acquire() as connection:
                    async with connection.transaction():
                        current_row = await connection.fetchrow(
                            """
                            SELECT * FROM publish_logs
                            WHERE tenant_id = $1
                              AND id = $2::uuid
                              AND status = $3
                            FOR UPDATE
                            """,
                            tenant_id,
                            attempt_id,
                            expected_status,
                        )
                        if current_row is None:
                            return None
                        current = self._normalize_record(current_row)
                        if receipt_json is not None:
                            receipt_model = self._normalize_receipt(receipt_json)
                            if (
                                receipt_model is None
                                or receipt_model.platform != current["platform"]
                            ):
                                raise ValueError("receipt platform is contradictory")
                        effective_content_json = self._content_for_transition(
                            current=current,
                            new_status=new_status,
                            requested_content_json=content_json,
                        )
                        row = await connection.fetchrow(
                            """
                            UPDATE publish_logs
                            SET status = $4,
                                content = COALESCE($5::jsonb, content),
                                post_id = COALESCE($6, post_id),
                                url = COALESCE($7, url),
                                error = COALESCE($8, error),
                                receipt = $9::jsonb,
                                updated_at = NOW()
                            WHERE tenant_id = $1
                              AND id = $2::uuid
                              AND status = $3
                            RETURNING *
                            """,
                            tenant_id,
                            attempt_id,
                            expected_status,
                            new_status,
                            effective_content_json,
                            post_id,
                            url,
                            error_code,
                            receipt_json,
                        )
                        record = self._normalize_record(row) if row is not None else None
                return record
            except PublishAttemptStoreUnavailable:
                raise
            except _STORE_DRIVER_ERRORS as exc:
                self._raise_store_unavailable(exc)
        if sqlite_connection is None:
            raise PublishAttemptStoreUnavailable
        try:
            row = await asyncio.to_thread(
                self._transition_sqlite,
                sqlite_connection,
                args,
            )
            return row
        except PublishAttemptStoreUnavailable:
            raise
        except _STORE_DRIVER_ERRORS as exc:
            self._raise_store_unavailable(exc)

    @classmethod
    def _insert_prepared_sqlite(
        cls,
        connection: sqlite3.Connection,
        attempt_id: str,
        tenant_id: str,
        acceptance_id: str,
        platform: str,
        content_json: str,
    ) -> Mapping[str, Any]:
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO publish_logs (
                        id, tenant_id, acceptance_id, platform, content,
                        status, created_at, updated_at
                    ) VALUES (
                        ?, ?, ?, ?, ?, 'prepared',
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    """,
                    (
                        attempt_id,
                        tenant_id,
                        acceptance_id,
                        platform,
                        content_json,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM publish_logs WHERE tenant_id = ? AND id = ?",
                    (tenant_id, attempt_id),
                ).fetchone()
                if row is None:
                    raise PublishAttemptStoreUnavailable
                record = cls._normalize_record(
                    row,
                    require_canonical_json_text=True,
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return record

    @classmethod
    def _transition_sqlite(
        cls,
        connection: sqlite3.Connection,
        args: tuple[Any, ...],
    ) -> Mapping[str, Any] | None:
        (
            tenant_id,
            attempt_id,
            expected_status,
            new_status,
            content_json,
            post_id,
            url,
            error_code,
            receipt_json,
        ) = args
        with db.get_sqlite_lock():
            try:
                connection.execute("BEGIN IMMEDIATE")
                current_row = connection.execute(
                    """
                    SELECT * FROM publish_logs
                    WHERE tenant_id = ?
                      AND id = ?
                      AND status = ?
                    """,
                    (tenant_id, attempt_id, expected_status),
                ).fetchone()
                if current_row is None:
                    connection.commit()
                    return None
                current = cls._normalize_record(
                    current_row,
                    require_canonical_json_text=True,
                )
                if receipt_json is not None:
                    receipt_model = cls._normalize_receipt(
                        receipt_json,
                        require_canonical_json_text=True,
                    )
                    if (
                        receipt_model is None
                        or receipt_model.platform != current["platform"]
                    ):
                        raise ValueError("receipt platform is contradictory")
                effective_content_json = cls._content_for_transition(
                    current=current,
                    new_status=new_status,
                    requested_content_json=content_json,
                )
                cursor = connection.execute(
                    """
                    UPDATE publish_logs
                    SET status = ?,
                        content = COALESCE(?, content),
                        post_id = COALESCE(?, post_id),
                        url = COALESCE(?, url),
                        error = COALESCE(?, error),
                        receipt = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tenant_id = ?
                      AND id = ?
                      AND status = ?
                    """,
                    (
                        new_status,
                        effective_content_json,
                        post_id,
                        url,
                        error_code,
                        receipt_json,
                        tenant_id,
                        attempt_id,
                        expected_status,
                    ),
                )
                row = (
                    connection.execute(
                        "SELECT * FROM publish_logs WHERE tenant_id = ? AND id = ?",
                        (tenant_id, attempt_id),
                    ).fetchone()
                    if cursor.rowcount == 1
                    else None
                )
                record = (
                    cls._normalize_record(
                        row,
                        require_canonical_json_text=True,
                    )
                    if row is not None
                    else None
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return record

    @staticmethod
    def _fetch_one_sqlite(
        connection: sqlite3.Connection,
        query: str,
        args: tuple[Any, ...],
    ) -> Mapping[str, Any] | None:
        with db.get_sqlite_lock():
            row = connection.execute(query, args).fetchone()
        return row

    @staticmethod
    def _fetch_many_sqlite(
        connection: sqlite3.Connection,
        query: str,
        args: tuple[Any, ...],
    ) -> list[Mapping[str, Any]]:
        with db.get_sqlite_lock():
            rows = connection.execute(query, args).fetchall()
        return list(rows)

    @classmethod
    def _content_for_transition(
        cls,
        *,
        current: Mapping[str, Any],
        new_status: str,
        requested_content_json: str | None,
    ) -> str | None:
        if new_status != "acceptance_consumed":
            if requested_content_json is not None:
                raise ValueError("attempt transition content is invalid")
            return None
        if requested_content_json is None:
            raise ValueError("acceptance-consumed content is required")
        stored_content = current.get("content")
        tenant_id = current.get("tenant_id")
        if not isinstance(stored_content, Mapping) or not isinstance(tenant_id, str):
            raise PublishAttemptStoreUnavailable
        requested_content = json.loads(requested_content_json)
        for field in ("schema_version", "route_kind", "metadata"):
            if requested_content.get(field) != stored_content.get(field):
                raise ValueError("prepared content authority is immutable")
        source = requested_content.get("source")
        artifact = requested_content.get("artifact")
        if source is None or artifact is None:
            raise ValueError("acceptance-consumed content is invalid")
        merged = dict(stored_content)
        merged["source"] = source
        merged["artifact"] = artifact
        return cls._encode_content(merged, tenant_id=tenant_id)

    @classmethod
    def _encode_content(
        cls,
        content: Mapping[str, Any],
        *,
        tenant_id: str,
    ) -> str:
        try:
            normalized = cls._normalize_content_projection(
                content,
                tenant_id=tenant_id,
            )
            encoded = json.dumps(
                normalized,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError, ValidationError):
            raise ValueError("attempt content is invalid") from None
        if len(encoded.encode("utf-8")) > 32 * 1024:
            raise ValueError("attempt content exceeds 32 KiB")
        return encoded

    @staticmethod
    def _normalize_receipt(
        value: PublishReceiptV1 | Mapping[str, Any] | str | None,
        *,
        require_canonical_json_text: bool = False,
    ) -> PublishReceiptV1 | None:
        if value is None:
            return None
        raw_receipt: str | None = None
        if isinstance(value, PublishReceiptV1):
            receipt = value
        else:
            if isinstance(value, str):
                raw_receipt = value
                payload = json.loads(value)
            elif isinstance(value, Mapping):
                payload = dict(value)
            else:
                raise ValueError("receipt is invalid")
            if not isinstance(payload, Mapping):
                raise ValueError("receipt is invalid")
            receipt = PublishReceiptV1.model_validate(payload)
        if (
            require_canonical_json_text
            and raw_receipt != receipt.canonical_json()
        ):
            raise ValueError("receipt is not canonical JSON")
        return receipt

    @staticmethod
    def _normalize_content_projection(
        content: Mapping[str, Any],
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        payload = dict(content)
        allowed_top = {
            "schema_version",
            "route_kind",
            "metadata",
            "source",
            "artifact",
        }
        if set(payload) - allowed_top:
            raise ValueError("attempt content has unknown fields")
        if payload.get("schema_version") != "publish-attempt.v1":
            raise ValueError("attempt schema version is invalid")
        route_kind = payload.get("route_kind")
        if not isinstance(route_kind, str) or route_kind not in ALLOWED_ROUTE_KINDS:
            raise ValueError("attempt route kind is invalid")
        metadata = PublishMetadata.model_validate(payload.get("metadata", {}))
        normalized: dict[str, Any] = {
            "schema_version": "publish-attempt.v1",
            "route_kind": route_kind,
            "metadata": metadata.model_dump(mode="json", exclude_none=True),
        }

        source = payload.get("source")
        artifact = payload.get("artifact")
        if (source is None) != (artifact is None):
            raise ValueError("source and artifact must be stored together")
        if source is None:
            return normalized
        if not isinstance(source, Mapping) or set(source) != {
            "resource_type",
            "resource_id",
            "scenario",
        }:
            raise ValueError("attempt source is invalid")
        resource_type = source.get("resource_type")
        resource_id = source.get("resource_id")
        scenario = source.get("scenario")
        if (
            resource_type not in {"fast", "scenario"}
            or not isinstance(resource_id, str)
            or _RESOURCE_ID_RE.fullmatch(resource_id) is None
            or not isinstance(scenario, str)
            or scenario not in {"fast", "s1", "s2", "s3", "s4", "s5"}
            or (resource_type == "fast") != (scenario == "fast")
        ):
            raise ValueError("attempt source is invalid")
        if not isinstance(artifact, Mapping) or set(artifact) != {
            "path",
            "sha256",
            "size_bytes",
            "kind",
        }:
            raise ValueError("attempt artifact is invalid")
        artifact_path = artifact.get("path")
        artifact_sha256 = artifact.get("sha256")
        artifact_size = artifact.get("size_bytes")
        if not isinstance(artifact_path, str):
            raise ValueError("attempt artifact path is invalid")
        canonical_path = str(PurePosixPath(artifact_path))
        expected_prefix = (
            f"tenants/{tenant_id}/pending_review/fast_mode/{resource_id}/"
            if resource_type == "fast"
            else f"tenants/{tenant_id}/pending_review/{resource_id}/"
        )
        if (
            artifact_path != canonical_path
            or artifact_path.startswith("/")
            or "\\" in artifact_path
            or ".." in PurePosixPath(artifact_path).parts
            or not artifact_path.startswith(expected_prefix)
            or not artifact_path.endswith((".mp4", ".webm"))
            or not isinstance(artifact_sha256, str)
            or _SHA256_RE.fullmatch(artifact_sha256) is None
            or not isinstance(artifact_size, int)
            or isinstance(artifact_size, bool)
            or artifact_size <= 0
            or artifact.get("kind") != "video"
        ):
            raise ValueError("attempt artifact is invalid")
        normalized["source"] = dict(source)
        normalized["artifact"] = dict(artifact)
        return normalized

    @classmethod
    def _normalize_record(
        cls,
        row: Mapping[str, Any],
        *,
        require_canonical_json_text: bool = False,
    ) -> dict[str, Any]:
        record = dict(row)
        tenant_id = record.get("tenant_id")
        attempt_id = str(record.get("id") or "")
        acceptance_id = record.get("acceptance_id")
        platform = record.get("platform")
        status = record.get("status")
        if (
            not isinstance(tenant_id, str)
            or not tenant_id
            or len(tenant_id) > 64
            or _UUID4_RE.fullmatch(attempt_id) is None
            or not isinstance(acceptance_id, str)
            or _UUID4_RE.fullmatch(acceptance_id) is None
            or not isinstance(platform, str)
            or platform not in ALLOWED_PLATFORMS
            or not isinstance(status, str)
            or status not in ALLOWED_STATUSES
        ):
            raise PublishAttemptStoreUnavailable
        record["id"] = attempt_id
        try:
            cls._validate_timestamp(record.get("created_at"))
            cls._validate_timestamp(record.get("updated_at"))
            content = record.get("content")
            if isinstance(content, str):
                raw_content = content
                content = json.loads(raw_content)
            elif isinstance(content, Mapping):
                raw_content = None
                content = dict(content)
            else:
                raise ValueError("attempt content is missing")
            content_json = cls._encode_content(content, tenant_id=tenant_id)
            if require_canonical_json_text and raw_content != content_json:
                raise ValueError("attempt content is not canonical JSON")
            normalized_content = json.loads(content_json)
            has_authority = "source" in normalized_content
            if status in {
                "prepared",
                "authorization_failed",
                "preflight_failed",
            } and has_authority:
                raise ValueError("pre-consume attempt has artifact authority")
            if status in {"acceptance_consumed", "published", "failed", "ambiguous"} and (
                not has_authority
            ):
                raise ValueError("post-consume attempt lacks artifact authority")
            record["content"] = normalized_content
            receipt = cls._normalize_receipt(
                record.get("receipt"),
                require_canonical_json_text=require_canonical_json_text,
            )
            if receipt is not None and receipt.platform != platform:
                raise ValueError("receipt platform is contradictory")
            record["receipt"] = (
                receipt.model_dump(mode="json") if receipt is not None else None
            )
        except (TypeError, ValueError, ValidationError):
            raise PublishAttemptStoreUnavailable from None
        try:
            cls._validate_transition_projection(
                new_status=status,
                post_id=record.get("post_id"),
                url=record.get("url"),
                error_code=record.get("error"),
                receipt=receipt,
                allow_legacy_published=True,
            )
        except ValueError:
            raise PublishAttemptStoreUnavailable from None
        return record

    @staticmethod
    def _validate_timestamp(value: Any) -> None:
        if isinstance(value, datetime):
            return
        if not isinstance(value, str) or not value:
            raise ValueError("attempt timestamp is invalid")
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("attempt timestamp is invalid") from None

    @staticmethod
    def _validate_transition_projection(
        *,
        new_status: str,
        post_id: str | None,
        url: str | None,
        error_code: str | None,
        receipt: PublishReceiptV1 | None,
        allow_legacy_published: bool,
    ) -> None:
        if new_status in {"prepared", "acceptance_consumed"}:
            if (
                post_id is not None
                or url is not None
                or error_code is not None
                or receipt is not None
            ):
                raise ValueError("active attempt projection is invalid")
            return
        if new_status == "published":
            if error_code is not None:
                raise ValueError("published attempt cannot carry an error")
            if receipt is None:
                if not allow_legacy_published:
                    raise ValueError("published attempt requires a receipt")
            else:
                receipt.validate_published()
                if post_id != receipt.post_id or url != receipt.post_url:
                    raise ValueError("published receipt projection is contradictory")
        else:
            if post_id is not None or url is not None:
                raise ValueError("failed attempt cannot carry connector success")
            allowed_error_codes = ERROR_CODES_BY_STATUS.get(new_status, frozenset())
            if not isinstance(error_code, str) or error_code not in allowed_error_codes:
                raise ValueError("attempt error code is invalid")
            if new_status in {"authorization_failed", "preflight_failed"}:
                if receipt is not None:
                    raise ValueError("pre-consume failure cannot carry a receipt")
            elif receipt is not None:
                if (
                    receipt.post_id is not None
                    or receipt.post_url is not None
                    or receipt.public_visibility_verified
                ):
                    raise ValueError("terminal failure receipt is not partial")
                try:
                    receipt.validate_published()
                except ValueError:
                    receipt_claims_completion = False
                else:
                    receipt_claims_completion = True
                if receipt_claims_completion:
                    raise ValueError("terminal failure receipt claims completion")
            return
        if post_id is not None and (
            not isinstance(post_id, str)
            or not post_id
            or len(post_id) > 256
            or _CONTROL_RE.search(post_id)
        ):
            raise ValueError("post_id is invalid")
        if url is not None:
            if (
                not isinstance(url, str)
                or len(url) > 2048
                or _CONTROL_RE.search(url)
                or any(character.isspace() for character in url)
            ):
                raise ValueError("post URL is invalid")
            try:
                parsed = urlsplit(url)
                parsed.port
            except ValueError:
                raise ValueError("post URL is invalid") from None
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("post URL is invalid")

    @staticmethod
    def _validate_uuid4(name: str, value: Any) -> None:
        if not isinstance(value, str) or _UUID4_RE.fullmatch(value) is None:
            raise ValueError(f"{name} is invalid")

    @staticmethod
    def _require_text(name: str, value: Any, *, max_length: int) -> None:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > max_length
            or _CONTROL_RE.search(value)
        ):
            raise ValueError(f"{name} is invalid")

    @staticmethod
    def _validate_platform(platform: Any) -> None:
        if not isinstance(platform, str) or platform not in ALLOWED_PLATFORMS:
            raise ValueError("platform is invalid")

    @staticmethod
    def _validate_route_kind(route_kind: Any) -> None:
        if not isinstance(route_kind, str) or route_kind not in ALLOWED_ROUTE_KINDS:
            raise ValueError("route_kind is invalid")

    @staticmethod
    def _raise_store_unavailable(exc: Exception) -> None:
        logger.warning(
            "Publish attempt store operation failed (%s)",
            type(exc).__name__,
        )
        raise PublishAttemptStoreUnavailable from None


__all__ = [
    "ALLOWED_ERROR_CODES",
    "ALLOWED_PLATFORMS",
    "ALLOWED_ROUTE_KINDS",
    "ALLOWED_STATUSES",
    "LEGAL_TRANSITIONS",
    "PublishAttemptRepository",
    "PublishAttemptStoreUnavailable",
]
