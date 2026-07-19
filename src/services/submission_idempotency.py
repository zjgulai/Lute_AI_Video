"""Tenant-scoped durable idempotency for canonical async submissions.

This module owns header validation, secret-free request fingerprinting, the
repository-facing claim contract, safe readback projections, and lease
heartbeat orchestration.  It deliberately does not execute a scenario, inject
provider credentials, or retry a mutation.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel
from starlette.requests import Request

FINGERPRINT_VERSION = "submit-fingerprint.v1"
DEFAULT_LEASE_SECONDS = 120
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30
NONTERMINAL_STATUSES = (
    "reserved",
    "initializing",
    "queued",
    "running",
)
COMPLETED_OWNER_STATUSES = frozenset({"completed", "failed"})

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
_EXACT_CREDENTIAL_FIELDS = frozenset(
    {
        "api_key",
        "api_keys",
        "authorization",
        "credentials",
        "idempotency_key",
        "password",
        "private_key",
        "provider_api_key",
        "provider_api_keys",
        "refresh_token",
        "secret",
        "token",
        "x_api_key",
    }
)
_CREDENTIAL_FIELD_SUFFIXES = (
    "_api_key",
    "_api_keys",
    "_access_token",
    "_auth_token",
    "_password",
    "_private_key",
    "_refresh_token",
    "_secret",
)


class SubmissionIdempotencyError(Exception):
    """Stable, non-secret error exposed by the HTTP adapter."""

    status_code = 500
    code = "submission_idempotency_error"

    def __init__(self) -> None:
        super().__init__(self.code)

    @property
    def detail(self) -> dict[str, str]:
        return {"code": self.code}


class IdempotencyKeyRequired(SubmissionIdempotencyError):
    status_code = 400
    code = "idempotency_key_required"


class IdempotencyKeyInvalid(SubmissionIdempotencyError):
    status_code = 400
    code = "idempotency_key_invalid"


class IdempotencyPayloadConflict(SubmissionIdempotencyError):
    status_code = 409
    code = "idempotency_payload_conflict"


class SubmissionNotFound(SubmissionIdempotencyError):
    status_code = 404
    code = "submission_not_found"


class IdempotencyStoreUnavailable(SubmissionIdempotencyError):
    status_code = 503
    code = "idempotency_store_unavailable"


def validate_idempotency_key_headers(values: Sequence[str]) -> str:
    """Validate an exact single opaque header without echoing its value."""

    if not values:
        raise IdempotencyKeyRequired()
    if len(values) != 1:
        raise IdempotencyKeyInvalid()
    value = values[0]
    if not isinstance(value, str) or _IDEMPOTENCY_KEY_RE.fullmatch(value) is None:
        raise IdempotencyKeyInvalid()
    return value


def extract_idempotency_key(request: Request) -> str:
    """Read all raw header occurrences so duplicates cannot be collapsed."""

    return validate_idempotency_key_headers(request.headers.getlist("idempotency-key"))


def hash_idempotency_key(raw_key: str) -> str:
    """Return the only server-side representation allowed for a raw key."""

    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _is_credential_field(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "_")
    return normalized in _EXACT_CREDENTIAL_FIELDS or normalized.endswith(_CREDENTIAL_FIELD_SUFFIXES)


def _strip_credentials(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip_credentials(item)
            for key, item in value.items()
            if isinstance(key, str) and not _is_credential_field(key)
        }
    if isinstance(value, (list, tuple)):
        return [_strip_credentials(item) for item in value]
    return value


def _validated_json_projection(value: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        dumped = value.model_dump(
            mode="json",
            exclude_none=False,
            exclude_defaults=False,
            exclude_unset=False,
        )
    elif isinstance(value, Mapping):
        dumped = dict(value)
    else:
        raise TypeError("fingerprint input must be a validated model or mapping")
    return cast(dict[str, Any], _strip_credentials(dumped))


@dataclass(frozen=True)
class RequestFingerprint:
    version: str
    request_hash: str


def build_request_fingerprint(
    validated_request: BaseModel | Mapping[str, Any],
    *,
    operation: str,
    scenario: str,
    effective_policy: BaseModel | Mapping[str, Any],
) -> RequestFingerprint:
    """Build the versioned canonical business-request fingerprint.

    Pydantic defaults and explicit ``None`` values are included.  Mapping key
    order is normalized by JSON encoding while list order and JSON scalar types
    remain significant.  Credential-bearing fields are removed recursively
    before serialization.
    """

    envelope = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "operation": operation,
        "scenario": scenario,
        "payload": _validated_json_projection(validated_request),
        "effective_policy": _validated_json_projection(effective_policy),
    }
    canonical = json.dumps(
        envelope,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return RequestFingerprint(
        version=FINGERPRINT_VERSION,
        request_hash=hashlib.sha256(canonical).hexdigest(),
    )


def preallocate_resource_id(
    *,
    resource_type: Literal["fast", "scenario"],
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"],
    clock: Callable[[], float] = time.time,
    token_factory: Callable[[], str] | None = None,
) -> str:
    """Allocate the stable job identity persisted by the initial claim."""

    if resource_type == "fast" and scenario != "fast":
        raise ValueError("fast resource requires fast scenario")
    if resource_type == "scenario" and scenario == "fast":
        raise ValueError("scenario resource requires s1-s5 scenario")
    token = (token_factory or (lambda: uuid.uuid4().hex[:8]))()
    return f"{scenario}_{int(clock())}_{token}"


class RepositoryClaimResult(Protocol):
    outcome: str
    record: Mapping[str, Any]


class SubmissionRepository(Protocol):
    async def claim(self, **kwargs: Any) -> RepositoryClaimResult: ...

    async def get_by_key_hash(self, *, tenant_id: str, key_hash: str) -> Mapping[str, Any] | None: ...

    async def get_by_resource(
        self, *, tenant_id: str, resource_type: str, resource_id: str
    ) -> Mapping[str, Any] | None: ...

    async def get_by_id(
        self, *, tenant_id: str, record_id: str
    ) -> Mapping[str, Any] | None: ...

    async def transition(self, **kwargs: Any) -> Mapping[str, Any] | None: ...

    async def renew_lease(self, **kwargs: Any) -> Mapping[str, Any] | None: ...

    async def reconcile_expired_lease(self, **kwargs: Any) -> Mapping[str, Any] | None: ...


def _default_repository() -> SubmissionRepository:
    # Delayed import keeps pure fingerprint/header tests independent of storage
    # initialization and breaks the router/service/storage import cycle.
    from src.storage.idempotency_repository import SubmissionIdempotencyRepository

    return SubmissionIdempotencyRepository()


def _is_store_unavailable_error(exc: Exception) -> bool:
    # Import lazily for the same reason as _default_repository.  The class-name
    # fallback keeps an injected repository implementation interoperable.
    if exc.__class__.__name__ == "IdempotencyStoreUnavailableError":
        return True
    try:
        from src.storage.idempotency_repository import (
            IdempotencyStoreUnavailableError,
        )
    except ImportError:
        return False
    return isinstance(exc, IdempotencyStoreUnavailableError)


async def _call_repository(method: Callable[..., Awaitable[Any]], **kwargs: Any) -> Any:
    try:
        return await method(**kwargs)
    except SubmissionIdempotencyError:
        raise
    except Exception as exc:
        if _is_store_unavailable_error(exc):
            raise IdempotencyStoreUnavailable() from None
        raise


@dataclass(frozen=True)
class SubmissionClaim:
    outcome: Literal["owner", "replay"]
    record: dict[str, Any]

    @property
    def is_owner(self) -> bool:
        return self.outcome == "owner"


FailureCallback = Callable[[], Awaitable[None] | None]
SleepFunction = Callable[[float], Awaitable[None]]


class SubmissionHeartbeat:
    """Independent renewable lease handle for one claimed submission."""

    def __init__(
        self,
        *,
        repository: SubmissionRepository,
        tenant_id: str,
        record_id: str,
        owner_instance_id: str,
        lease_seconds: int,
        interval_seconds: int,
        sleep: SleepFunction,
        on_failure: FailureCallback | None,
    ) -> None:
        self.repository = repository
        self.tenant_id = tenant_id
        self.record_id = record_id
        self.owner_instance_id = owner_instance_id
        self.lease_seconds = lease_seconds
        self.interval_seconds = interval_seconds
        self._sleep = sleep
        self._on_failure = on_failure
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._failure_signaled = False
        self.last_error: Exception | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _signal_failure(self) -> None:
        if self._failure_signaled:
            return
        self._failure_signaled = True
        if self._on_failure is None:
            return
        result = self._on_failure()
        if inspect.isawaitable(result):
            await result

    async def renew_once(self) -> bool:
        """Renew via repository DB time and owner/status compare-and-set."""

        try:
            renewed = await _call_repository(
                self.repository.renew_lease,
                tenant_id=self.tenant_id,
                record_id=self.record_id,
                owner_instance_id=self.owner_instance_id,
                expected_statuses=NONTERMINAL_STATUSES,
                lease_seconds=self.lease_seconds,
            )
        except Exception as exc:
            self.last_error = exc
            await self._signal_failure()
            return False

        if renewed is not None:
            return True

        # A lost renew is not permission to rerun.  Only a successful CAS to
        # recovery_required proves this caller still owned nonterminal work.
        try:
            recovered = await _call_repository(
                self.repository.transition,
                tenant_id=self.tenant_id,
                record_id=self.record_id,
                expected_statuses=NONTERMINAL_STATUSES,
                new_status="recovery_required",
                safe_error_code="submission_owner_lost",
                owner_instance_id=self.owner_instance_id,
                mark_completed=True,
            )
        except Exception as exc:
            self.last_error = exc
            await self._signal_failure()
            return False
        if recovered is not None:
            await self._signal_failure()
            return False

        # A normal completed/failed CAS may have won between the renew miss
        # and recovery CAS.  Do not cancel that already-terminal owner.  Every
        # other state means this worker no longer has authority to continue.
        try:
            current = await _call_repository(
                self.repository.get_by_id,
                tenant_id=self.tenant_id,
                record_id=self.record_id,
            )
        except Exception as exc:
            self.last_error = exc
            await self._signal_failure()
            return False
        if current is None or current.get("record_status") not in COMPLETED_OWNER_STATUSES:
            await self._signal_failure()
        return False

    def start(self) -> SubmissionHeartbeat:
        if self.running:
            return self
        self._stopping = False
        self._task = asyncio.create_task(self._run())
        return self

    async def _run(self) -> None:
        try:
            while not self._stopping:
                await self._sleep(self.interval_seconds)
                if self._stopping or not await self.renew_once():
                    return
        except asyncio.CancelledError:
            return
        except Exception as exc:  # fail closed; never authorize replay
            self.last_error = exc
            await self._signal_failure()

    async def stop(self) -> None:
        self._stopping = True
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task


class SubmissionIdempotencyService:
    """Shared service boundary used by Fast, Scenario, and readback routers."""

    def __init__(
        self,
        repository: SubmissionRepository | None = None,
        *,
        instance_id: str | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        heartbeat_interval_seconds: int = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        sleep: SleepFunction = asyncio.sleep,
    ) -> None:
        self.repository = repository or _default_repository()
        self.instance_id = instance_id or f"instance-{uuid.uuid4().hex}"
        self.lease_seconds = lease_seconds
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self._sleep = sleep
        self._heartbeats: dict[tuple[str, str], SubmissionHeartbeat] = {}

    async def claim_submission(
        self,
        *,
        tenant_id: str,
        raw_key: str,
        validated_request: BaseModel | Mapping[str, Any],
        effective_policy: BaseModel | Mapping[str, Any],
        operation: str,
        scenario: str,
        resource_type: Literal["fast", "scenario"],
        resource_id: str,
        response_body: Mapping[str, Any],
        response_status: int = 200,
    ) -> SubmissionClaim:
        raw_key = validate_idempotency_key_headers([raw_key])
        fingerprint = build_request_fingerprint(
            validated_request,
            operation=operation,
            scenario=scenario,
            effective_policy=effective_policy,
        )
        policy_projection = _validated_json_projection(effective_policy)
        effective_policy_version = str(policy_projection.get("version") or "")
        safe_response = cast(dict[str, Any], _strip_credentials(dict(response_body)))

        result = await _call_repository(
            self.repository.claim,
            tenant_id=tenant_id,
            key_hash=hash_idempotency_key(raw_key),
            fingerprint_version=fingerprint.version,
            request_hash=fingerprint.request_hash,
            operation=operation,
            scenario=scenario,
            resource_type=resource_type,
            resource_id=resource_id,
            effective_policy_version=effective_policy_version,
            response_status=response_status,
            response_body=safe_response,
            owner_instance_id=self.instance_id,
            lease_seconds=self.lease_seconds,
        )
        outcome = str(result.outcome)
        if outcome == "conflict":
            raise IdempotencyPayloadConflict()
        if outcome not in {"owner", "replay"}:
            raise RuntimeError("invalid idempotency claim outcome")
        record = dict(result.record)
        if outcome == "replay":
            record = await self._reconcile_record(
                tenant_id=tenant_id,
                record=record,
            )
        return SubmissionClaim(
            outcome=cast(Literal["owner", "replay"], outcome),
            record=record,
        )

    async def _reconcile_record(self, *, tenant_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
        current = dict(record)
        if current.get("record_status") in NONTERMINAL_STATUSES:
            reconciled = await _call_repository(
                self.repository.reconcile_expired_lease,
                tenant_id=tenant_id,
                record_id=str(current["id"]),
                safe_error_code="submission_owner_lost",
            )
            if reconciled is not None:
                current = dict(reconciled)
        return current

    @staticmethod
    def _safe_readback_projection(record: Mapping[str, Any]) -> dict[str, Any]:
        projection: dict[str, Any] = {
            "resource_type": record.get("resource_type"),
            "resource_id": record.get("resource_id"),
            "scenario": record.get("scenario"),
            "status": record.get("record_status"),
            "submit_response": _strip_credentials(record.get("response_body") or {}),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
        }
        for key in (
            "stage",
            "result_snapshot",
            "safe_error_code",
            "effective_policy_version",
        ):
            value = record.get(key)
            if value is not None:
                projection[key] = _strip_credentials(value)
        return projection

    async def readback(self, *, tenant_id: str, raw_key: str) -> dict[str, Any]:
        raw_key = validate_idempotency_key_headers([raw_key])
        record = await _call_repository(
            self.repository.get_by_key_hash,
            tenant_id=tenant_id,
            key_hash=hash_idempotency_key(raw_key),
        )
        if record is None:
            raise SubmissionNotFound()
        current = await self._reconcile_record(tenant_id=tenant_id, record=record)
        return self._safe_readback_projection(current)

    async def readback_by_resource(
        self,
        *,
        tenant_id: str,
        resource_type: Literal["fast", "scenario"],
        resource_id: str,
    ) -> dict[str, Any]:
        """Return tenant-bound durable status without exposing repository data."""

        record = await _call_repository(
            self.repository.get_by_resource,
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if record is None:
            raise SubmissionNotFound()
        current = await self._reconcile_record(tenant_id=tenant_id, record=record)
        return self._safe_readback_projection(current)

    async def transition(
        self,
        *,
        tenant_id: str,
        record_id: str,
        expected_statuses: Sequence[str],
        new_status: str,
        stage: str | None = None,
        response_status: int | None = None,
        response_body: Mapping[str, Any] | None = None,
        result_snapshot: Mapping[str, Any] | None = None,
        safe_error_code: str | None = None,
        lease_seconds: int | None = None,
        mark_completed: bool = False,
    ) -> dict[str, Any] | None:
        kwargs: dict[str, Any] = {
            "tenant_id": tenant_id,
            "record_id": record_id,
            "expected_statuses": tuple(expected_statuses),
            "new_status": new_status,
            "stage": stage,
            "response_status": response_status,
            "response_body": (_strip_credentials(dict(response_body)) if response_body is not None else None),
            "result_snapshot": (_strip_credentials(dict(result_snapshot)) if result_snapshot is not None else None),
            "safe_error_code": safe_error_code,
            "lease_seconds": lease_seconds,
            "owner_instance_id": self.instance_id,
            "mark_completed": mark_completed,
        }
        record = await _call_repository(self.repository.transition, **kwargs)
        return dict(record) if record is not None else None

    def create_heartbeat(
        self,
        *,
        tenant_id: str,
        record_id: str,
        on_failure: FailureCallback | None = None,
    ) -> SubmissionHeartbeat:
        return SubmissionHeartbeat(
            repository=self.repository,
            tenant_id=tenant_id,
            record_id=record_id,
            owner_instance_id=self.instance_id,
            lease_seconds=self.lease_seconds,
            interval_seconds=self.heartbeat_interval_seconds,
            sleep=self._sleep,
            on_failure=on_failure,
        )

    def start_heartbeat(
        self,
        *,
        tenant_id: str,
        record_id: str,
        on_failure: FailureCallback | None = None,
    ) -> SubmissionHeartbeat:
        key = (tenant_id, record_id)
        existing = self._heartbeats.get(key)
        if existing is not None and existing.running:
            return existing
        heartbeat = self.create_heartbeat(
            tenant_id=tenant_id,
            record_id=record_id,
            on_failure=on_failure,
        ).start()
        self._heartbeats[key] = heartbeat
        return heartbeat

    async def stop_heartbeat(self, *, tenant_id: str, record_id: str) -> None:
        heartbeat = self._heartbeats.pop((tenant_id, record_id), None)
        if heartbeat is not None:
            await heartbeat.stop()

    async def mark_terminal(
        self,
        *,
        tenant_id: str,
        record_id: str,
        status: Literal["completed", "failed", "recovery_required"],
        stage: str | None = None,
        response_status: int | None = None,
        response_body: Mapping[str, Any] | None = None,
        result_snapshot: Mapping[str, Any] | None = None,
        safe_error_code: str | None = None,
    ) -> dict[str, Any] | None:
        """Persist terminal CAS first, then stop the independent heartbeat."""

        try:
            return await self.transition(
                tenant_id=tenant_id,
                record_id=record_id,
                expected_statuses=NONTERMINAL_STATUSES,
                new_status=status,
                stage=stage,
                response_status=response_status,
                response_body=response_body,
                result_snapshot=result_snapshot,
                safe_error_code=safe_error_code,
                mark_completed=True,
            )
        finally:
            await self.stop_heartbeat(tenant_id=tenant_id, record_id=record_id)

    async def shutdown(self) -> None:
        """Mark locally owned work unrecoverable before stopping heartbeats."""

        shutdown_error: SubmissionIdempotencyError | None = None
        for (tenant_id, record_id), heartbeat in list(self._heartbeats.items()):
            try:
                await self.transition(
                    tenant_id=tenant_id,
                    record_id=record_id,
                    expected_statuses=NONTERMINAL_STATUSES,
                    new_status="recovery_required",
                    safe_error_code="submission_shutdown",
                    mark_completed=True,
                )
            except SubmissionIdempotencyError as exc:
                shutdown_error = shutdown_error or exc
            except Exception:
                shutdown_error = shutdown_error or IdempotencyStoreUnavailable()
            finally:
                try:
                    await heartbeat.stop()
                except Exception:
                    shutdown_error = shutdown_error or IdempotencyStoreUnavailable()
                self._heartbeats.pop((tenant_id, record_id), None)
        if shutdown_error is not None:
            raise shutdown_error


_service: SubmissionIdempotencyService | None = None


def get_submission_idempotency_service() -> SubmissionIdempotencyService:
    """Return the process-local orchestrator backed by the durable authority."""

    global _service
    if _service is None:
        _service = SubmissionIdempotencyService()
    return _service


async def shutdown_submission_idempotency_service_if_initialized() -> None:
    """Gracefully stop active owners without constructing an unused service."""

    global _service
    if _service is None:
        return
    service = _service
    _service = None
    await service.shutdown()
