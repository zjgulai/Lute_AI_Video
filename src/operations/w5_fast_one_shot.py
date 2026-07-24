"""Fail-closed primitives for one explicitly authorized W5 Fast submission.

The module is deliberately transport-neutral.  It owns the durable local
one-shot marker, safe evidence projections, finite GET-only polling, and the
provider-off restoration guarantee.  Real HTTP and database access belong in
the thin operator CLI so this safety boundary remains hermetically testable.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

_MAX_EVIDENCE_BYTES = 64 * 1024
_SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SAFE_PROVIDER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_SAFE_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+/@-]{0,127}\Z")
_SAFE_EXTERNAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}\Z")
_MAX_SIGNED_INT = 9_223_372_036_854_775_807
_TERMINAL_STATUSES = frozenset(
    {
        "cancelled",
        "completed",
        "done",
        "error",
        "failed",
        "pending_review",
        "recovery_required",
        "rejected",
    }
)
_TERMINAL_LIFECYCLES = frozenset(
    {
        "completed_bounded",
        "completed_no_media",
        "failed",
        "pending_review",
        "recovery_required",
    }
)


class OperatorBlocked(RuntimeError):
    """Stable, secret-free operator failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TransportAmbiguous(RuntimeError):
    """The backend request may have been accepted; retry is forbidden."""


@dataclass(frozen=True, slots=True)
class BackendResponse:
    """Minimal backend response used by the dependency-injected core."""

    status_code: int
    payload: Mapping[str, Any]


class BackendGateway(Protocol):
    """Exactly the two backend-direct operations allowed by this workflow."""

    def submit(self, *, payload: bytes, raw_key: str, api_key: str) -> BackendResponse:
        """Perform the sole POST after the durable marker exists."""

        ...

    def status(self, *, task_id: str, api_key: str) -> BackendResponse:
        """Perform one read-only status GET."""

        ...


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _parse_json_object(raw: str, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_constant,
        )
    except (RecursionError, TypeError, ValueError, json.JSONDecodeError):
        raise OperatorBlocked(code) from None
    if type(value) is not dict:
        raise OperatorBlocked(code)
    return value


class EvidenceStore:
    """Create-only, bounded, no-follow JSON evidence directory."""

    def __init__(self, root: str | Path) -> None:
        candidate = Path(root)
        try:
            candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
            metadata = candidate.lstat()
        except OSError:
            raise OperatorBlocked("operator_evidence_unavailable") from None
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise OperatorBlocked("operator_evidence_unavailable")
        if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise OperatorBlocked("operator_evidence_permissions_invalid")
        self._root = candidate
        self._root_identity = (metadata.st_dev, metadata.st_ino)

    @staticmethod
    def _validate_name(name: str) -> str:
        if not isinstance(name, str) or _SAFE_NAME.fullmatch(name) is None:
            raise OperatorBlocked("operator_evidence_name_invalid")
        return name

    def path(self, name: str) -> Path:
        return self._root / self._validate_name(name)

    def _open_directory(self) -> int:
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            descriptor = os.open(self._root, flags)
        except OSError:
            raise OperatorBlocked("operator_evidence_unavailable") from None
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or (metadata.st_dev, metadata.st_ino) != self._root_identity
            ):
                raise OperatorBlocked("operator_evidence_permissions_invalid")
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    def create_json(self, name: str, payload: Mapping[str, Any]) -> Path:
        """Atomically claim one evidence name and write private JSON once."""

        safe_name = self._validate_name(name)
        try:
            encoded = (
                json.dumps(
                    dict(payload),
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError):
            raise OperatorBlocked("operator_evidence_invalid") from None
        if len(encoded) > _MAX_EVIDENCE_BYTES:
            raise OperatorBlocked("operator_evidence_too_large")

        directory = self._open_directory()
        descriptor: int | None = None
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            try:
                descriptor = os.open(safe_name, flags, 0o600, dir_fd=directory)
            except FileExistsError:
                raise OperatorBlocked("operator_evidence_exists") from None
            except OSError:
                raise OperatorBlocked("operator_evidence_unavailable") from None
            os.fchmod(descriptor, 0o600)
            view = memoryview(encoded)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("short evidence write")
                view = view[written:]
            os.fsync(descriptor)
            os.fsync(directory)
        except OperatorBlocked:
            raise
        except OSError:
            raise OperatorBlocked("operator_evidence_unavailable") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)
        return self.path(safe_name)

    def read_json(self, name: str) -> str:
        """Read and validate one bounded regular JSON object without following links."""

        safe_name = self._validate_name(name)
        directory = self._open_directory()
        descriptor: int | None = None
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            try:
                descriptor = os.open(safe_name, flags, dir_fd=directory)
            except OSError:
                raise OperatorBlocked("operator_evidence_unavailable") from None
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise OperatorBlocked("operator_evidence_unavailable")
            if metadata.st_size > _MAX_EVIDENCE_BYTES:
                raise OperatorBlocked("operator_evidence_too_large")
            chunks: list[bytes] = []
            remaining = _MAX_EVIDENCE_BYTES + 1
            while remaining:
                chunk = os.read(descriptor, min(remaining, 8192))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) > _MAX_EVIDENCE_BYTES:
                raise OperatorBlocked("operator_evidence_too_large")
        except OperatorBlocked:
            raise
        except OSError:
            raise OperatorBlocked("operator_evidence_unavailable") from None
        finally:
            if descriptor is not None:
                os.close(descriptor)
            os.close(directory)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise OperatorBlocked("operator_evidence_invalid") from None
        _parse_json_object(decoded, code="operator_evidence_invalid")
        return decoded

    def load_object(self, name: str) -> dict[str, Any]:
        return _parse_json_object(
            self.read_json(name),
            code="operator_evidence_invalid",
        )


def assert_backend_route_contract(paths: Mapping[str, Any]) -> None:
    """Require canonical backend-direct submit and status methods."""

    submit = paths.get("/fast/submit")
    if type(submit) is not dict or type(submit.get("post")) is not dict:
        raise OperatorBlocked("backend_submit_route_contract_mismatch")
    status_route = paths.get("/fast/status/{task_id}")
    if type(status_route) is not dict or type(status_route.get("get")) is not dict:
        raise OperatorBlocked("backend_status_route_contract_mismatch")


def _canonical_request(payload: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise OperatorBlocked("w5_fast_request_invalid") from None


def _safe_identifier(value: object) -> str | None:
    if isinstance(value, str) and _SAFE_IDENTIFIER.fullmatch(value):
        return value
    return None


def _validate_authority(authority: Mapping[str, Any]) -> dict[str, Any]:
    activation_id = _safe_identifier(authority.get("activation_id"))
    binding_id = _safe_identifier(authority.get("binding_id"))
    tenant_id = _safe_identifier(authority.get("tenant_id"))
    if not activation_id or not binding_id or not tenant_id:
        raise OperatorBlocked("w5_fast_authority_invalid")
    exact = {
        "submission_cap": 1,
        "automatic_retry_cap": 0,
        "provider_max_retries": 0,
        "artifact_disposition": "pending_review",
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    if any(authority.get(key) != expected for key, expected in exact.items()):
        raise OperatorBlocked("w5_fast_authority_invalid")
    return {
        "activation_id": activation_id,
        "binding_id": binding_id,
        "tenant_id": tenant_id,
        **exact,
    }


def _safe_detail_code(payload: Mapping[str, Any]) -> str | None:
    detail = payload.get("detail")
    if type(detail) is dict:
        return _safe_identifier(detail.get("code"))
    return _safe_identifier(detail)


def _write_submit_outcome(store: EvidenceStore, outcome: dict[str, Any]) -> dict[str, Any]:
    store.create_json("submit-outcome.json", outcome)
    return outcome


def execute_submit_once(
    *,
    store: EvidenceStore,
    gateway: BackendGateway,
    raw_key: str,
    api_key: str,
    request_payload: Mapping[str, Any],
    authority: Mapping[str, Any],
    invoked_at_unix: int,
) -> dict[str, Any]:
    """Create the marker first, then perform at most one backend POST."""

    if _SHA256.fullmatch(raw_key) is None or not api_key:
        raise OperatorBlocked("w5_fast_submit_credentials_invalid")
    if type(invoked_at_unix) is not int or invoked_at_unix < 0:
        raise OperatorBlocked("w5_fast_invocation_time_invalid")
    safe_authority = _validate_authority(authority)
    payload = _canonical_request(request_payload)
    request_sha256 = hashlib.sha256(payload).hexdigest()
    marker = {
        "version": "w5-fast-submit-marker.v1",
        "state": "consumed_before_submit",
        "invoked_at_unix": invoked_at_unix,
        "request_sha256": request_sha256,
        "idempotency_key_sha256": hashlib.sha256(raw_key.encode("ascii")).hexdigest(),
        **safe_authority,
    }
    try:
        store.create_json("submit-invoked.json", marker)
    except OperatorBlocked as exc:
        if exc.code == "operator_evidence_exists":
            raise OperatorBlocked("w5_fast_submit_marker_exists") from None
        raise

    try:
        response = gateway.submit(payload=payload, raw_key=raw_key, api_key=api_key)
    except TransportAmbiguous:
        return _write_submit_outcome(
            store,
            {
                "submit_state": "transport_ambiguous",
                "submit_count": 1,
                "provider_retry_count": 0,
                "safe_error_code": "backend_submit_transport_ambiguous",
            },
        )

    if 200 <= response.status_code < 300:
        task_id = _safe_identifier(response.payload.get("task_id"))
        status_value = _safe_identifier(response.payload.get("status"))
        if task_id is None or status_value is None:
            return _write_submit_outcome(
                store,
                {
                    "submit_state": "response_ambiguous",
                    "submit_count": 1,
                    "provider_retry_count": 0,
                    "safe_error_code": "backend_submit_response_invalid",
                },
            )
        outcome: dict[str, Any] = {
            "submit_state": "accepted",
            "task_id": task_id,
            "status": status_value,
            "submit_count": 1,
            "provider_retry_count": 0,
        }
        started = response.payload.get("started_at_unix")
        if type(started) is int and started >= 0:
            outcome["started_at_unix"] = started
        replay = response.payload.get("idempotent_replay")
        if type(replay) is bool:
            outcome["idempotent_replay"] = replay
        return _write_submit_outcome(store, outcome)

    rejected: dict[str, Any] = {
        "submit_state": "rejected",
        "http_status": response.status_code,
        "submit_count": 1,
        "provider_retry_count": 0,
    }
    detail_code = _safe_detail_code(response.payload)
    if detail_code is not None:
        rejected["detail_code"] = detail_code
    return _write_submit_outcome(store, rejected)


def _safe_status_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    projected: dict[str, Any] = {}
    for key in ("task_id", "status", "stage", "lifecycle_status", "safe_error_code"):
        value = _safe_identifier(payload.get(key))
        if value is not None:
            projected[key] = value
    progress = payload.get("progress")
    if type(progress) is int and 0 <= progress <= 100:
        projected["progress"] = progress
    elif type(progress) is float and 0 <= progress <= 100:
        projected["progress"] = progress
    return projected


def poll_status(
    *,
    store: EvidenceStore,
    gateway: BackendGateway,
    api_key: str,
    max_polls: int,
    sleep: Callable[[float], None],
    poll_interval_seconds: float,
) -> dict[str, Any]:
    """Read durable submit truth and perform only a finite number of GETs."""

    submit = store.load_object("submit-outcome.json")
    task_id = _safe_identifier(submit.get("task_id"))
    if submit.get("submit_state") != "accepted" or task_id is None:
        raise OperatorBlocked("w5_fast_poll_unavailable")
    if not api_key:
        raise OperatorBlocked("w5_fast_poll_credentials_invalid")
    if type(max_polls) is not int or not 1 <= max_polls <= 10_000:
        raise OperatorBlocked("w5_fast_poll_limit_invalid")
    if (
        isinstance(poll_interval_seconds, bool)
        or not isinstance(poll_interval_seconds, (int, float))
        or not 0 <= float(poll_interval_seconds) <= 3600
    ):
        raise OperatorBlocked("w5_fast_poll_interval_invalid")

    latest: dict[str, Any] = {"task_id": task_id, "status": "unknown"}
    poll_count = 0
    for index in range(max_polls):
        poll_count = index + 1
        try:
            response = gateway.status(task_id=task_id, api_key=api_key)
        except TransportAmbiguous:
            latest = {
                "task_id": task_id,
                "status": "poll_transport_unavailable",
                "safe_error_code": "backend_status_transport_unavailable",
            }
            break
        if response.status_code != 200:
            latest = {
                "task_id": task_id,
                "status": "poll_rejected",
                "http_status": response.status_code,
            }
            detail_code = _safe_detail_code(response.payload)
            if detail_code is not None:
                latest["detail_code"] = detail_code
            break
        latest = _safe_status_projection(response.payload)
        latest.setdefault("task_id", task_id)
        if latest.get("task_id") != task_id:
            latest = {
                "task_id": task_id,
                "status": "poll_invalid",
                "safe_error_code": "backend_status_task_mismatch",
            }
            break
        status_value = latest.get("status")
        lifecycle = latest.get("lifecycle_status")
        if status_value in _TERMINAL_STATUSES or lifecycle in _TERMINAL_LIFECYCLES:
            break
        if index + 1 < max_polls:
            sleep(float(poll_interval_seconds))
    else:
        latest["poll_exhausted"] = True
        latest["safe_error_code"] = "backend_status_poll_exhausted"

    latest["poll_count"] = poll_count
    store.create_json("terminal-outcome.json", latest)
    return latest


def _safe_ledger_string(field: str, value: object) -> str | None:
    if isinstance(value, UUID):
        candidate = str(value)
    elif isinstance(value, str):
        candidate = value
    else:
        return None
    pattern = {
        "provider": _SAFE_PROVIDER,
        "canonical_model": _SAFE_MODEL,
        "external_task_id": _SAFE_EXTERNAL_ID,
    }.get(field, _SAFE_IDENTIFIER)
    return candidate if pattern.fullmatch(candidate) is not None else None


def _safe_ledger_integer(field: str, value: object) -> int | None:
    if type(value) is not int:
        return None
    if field == "ordinal":
        return value if 1 <= value <= 10_000 else None
    if field.endswith("_usd_nanos"):
        return value if 0 <= value <= _MAX_SIGNED_INT else None
    return value if 0 <= value <= _MAX_SIGNED_INT else None


def _allowlisted_mapping(
    value: object,
    *,
    string_fields: Sequence[str],
    integer_fields: Sequence[str] = (),
) -> dict[str, Any] | None:
    if type(value) is not dict:
        return None
    projected: dict[str, Any] = {}
    for field in string_fields:
        item = value.get(field)
        if item is None:
            projected[field] = item
            continue
        safe = _safe_ledger_string(field, item)
        if safe is not None:
            projected[field] = safe
    for field in integer_fields:
        item = value.get(field)
        if item is None:
            projected[field] = item
            continue
        safe = _safe_ledger_integer(field, item)
        if safe is not None:
            projected[field] = safe
    return projected


def safe_ledger_projection(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Drop payload snapshots, provider responses, paths, and unknown fields."""

    result: dict[str, Any] = {}
    idempotency = _allowlisted_mapping(
        raw.get("idempotency"),
        string_fields=(
            "resource_id",
            "record_status",
            "stage",
            "trusted_authorization_ref",
            "safe_error_code",
        ),
    )
    if idempotency is not None:
        result["idempotency"] = idempotency
    account = _allowlisted_mapping(
        raw.get("account"),
        string_fields=(
            "account_id",
            "job_id",
            "state",
            "safe_error_code",
        ),
        integer_fields=(
            "cap_usd_nanos",
            "reserved_usd_nanos",
            "settled_usd_nanos",
        ),
    )
    if account is not None:
        result["account"] = account
    attempts_raw = raw.get("attempts")
    if type(attempts_raw) is list:
        if len(attempts_raw) > 64:
            raise OperatorBlocked("operator_ledger_projection_invalid")
        attempts: list[dict[str, Any]] = []
        for item in attempts_raw:
            projected = _allowlisted_mapping(
                item,
                string_fields=(
                    "logical_operation",
                    "provider",
                    "canonical_model",
                    "state",
                    "external_task_id",
                    "safe_error_code",
                ),
                integer_fields=(
                    "ordinal",
                    "reserved_usd_nanos",
                    "settled_usd_nanos",
                ),
            )
            if projected is not None:
                attempts.append(projected)
        result["attempts"] = attempts
    return result


def run_with_provider_off_restore(
    *,
    operation: Callable[[], int],
    restore: Callable[[], None],
) -> int:
    """Run restoration for all returns and failures; restoration failure wins."""

    try:
        result = operation()
    except BaseException:
        try:
            restore()
        except BaseException:
            raise OperatorBlocked("provider_off_restore_failed") from None
        raise
    try:
        restore()
    except BaseException:
        raise OperatorBlocked("provider_off_restore_failed") from None
    return result


__all__ = [
    "BackendResponse",
    "EvidenceStore",
    "OperatorBlocked",
    "TransportAmbiguous",
    "assert_backend_route_contract",
    "execute_submit_once",
    "poll_status",
    "run_with_provider_off_restore",
    "safe_ledger_projection",
]
