"""Exact W1-31 single-task provider charge reconciliation gate.

This module is deliberately side-effect free until :func:`consume_and_execute_once`
is called with an injected execution callback.  It never loads provider secrets,
constructs an HTTP client, or selects a sample dynamically.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

REPO_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_REPO_DIR = (REPO_ROOT / "tmp").resolve()

SCHEMA_VERSION = "w1-31-provider-billing-reconciliation.v1"
SCOPE = "w1-31-provider-billing-reconciliation"
PROVIDER = "poyo"
MODEL = "gpt-image-2"
QUALITY = "low"
SIZE = "1:1"
EFFECTIVE_RESOLUTION = "1K"
PROMPT_PROFILE_ID = "neutral-calibration-cube-v1"
EXPECTED_USD_NANOS = 10_000_000
EXPECTED_PROVIDER_CREDIT_MICRO_UNITS = 2_000_000
PRICE_EVIDENCE_MAX_AGE = timedelta(hours=24)
ACCOUNT_READINESS_MAX_AGE = timedelta(minutes=30)
APPROVAL_MAX_LIFETIME = timedelta(hours=2)
PRICE_EVIDENCE_URLS = (
    "https://poyo.ai/models/gpt-image-2",
    "https://docs.poyo.ai/api-manual/image-series/gpt-image-2",
    "https://docs.poyo.ai/api-manual/task-management/status",
)
AUTHORIZATION_STATEMENT = (
    "我授权执行 W1-31：使用 PoYo gpt-image-2 生成 1 张 low/1K 图片，"
    "硬预算上限 $0.01，provider mutation 最多 1 次、自动重试 0；"
    "仅做单 task charge 对账，不触碰生产、发布或交付。"
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_PLACEHOLDER_RE = re.compile(r"replace|template|example|todo|tbd|<|>", re.IGNORECASE)
W131AttemptState = Literal[
    "reserved",
    "submission_started",
    "submitted",
    "settled",
    "released",
    "ambiguous",
    "accounting_error",
]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class W131Sample(_StrictFrozenModel):
    workflow: Literal["text-to-image"]
    quality: Literal["low"]
    size: Literal["1:1"]
    effective_resolution: Literal["1K"]
    image_count: Literal[1]
    prompt_profile_id: Literal["neutral-calibration-cube-v1"]


class W131ApprovalRecord(_StrictFrozenModel):
    schema_version: Literal["w1-31-provider-billing-reconciliation.v1"]
    approval_id: str = Field(min_length=1, max_length=128)
    scope: Literal["w1-31-provider-billing-reconciliation"]
    provider: Literal["poyo"]
    model: Literal["gpt-image-2"]
    approved_by: str = Field(min_length=2, max_length=100)
    confirmed_by: str = Field(min_length=2, max_length=100)
    account_readiness_checked_by: str = Field(min_length=2, max_length=100)
    account_readiness_checked_at: str = Field(min_length=20, max_length=40)
    available_credit_micro_units: int = Field(
        ge=EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        le=2**63 - 1,
    )
    approved_at: str = Field(min_length=20, max_length=40)
    expires_at: str = Field(min_length=20, max_length=40)
    price_checked_at: str = Field(min_length=20, max_length=40)
    price_evidence_urls: tuple[str, str, str]
    authorization_statement: str = Field(min_length=20, max_length=300)
    sample: W131Sample
    budget_limit_usd: Literal["0.01"]
    expected_usd_nanos: Literal[10_000_000]
    expected_provider_credit_micro_units: Literal[2_000_000]
    max_provider_calls: Literal[1]
    max_retries: Literal[0]
    production_allowed: Literal[False]
    publish_allowed: Literal[False]
    delivery_allowed: Literal[False]

    @model_validator(mode="after")
    def validate_exact_authority(self) -> W131ApprovalRecord:
        if _SAFE_ID_RE.fullmatch(self.approval_id) is None:
            raise ValueError("approval ID is invalid")
        approved_by = self.approved_by.strip()
        confirmed_by = self.confirmed_by.strip()
        if (
            approved_by != self.approved_by
            or confirmed_by != self.confirmed_by
            or _PLACEHOLDER_RE.search(approved_by)
            or _PLACEHOLDER_RE.search(confirmed_by)
        ):
            raise ValueError("human confirmation identities must be concrete")
        if approved_by.casefold() == confirmed_by.casefold():
            raise ValueError("approved_by and confirmed_by must be distinct humans")
        if self.account_readiness_checked_by != self.confirmed_by:
            raise ValueError("account readiness must be confirmed by the second human")
        if self.authorization_statement != AUTHORIZATION_STATEMENT:
            raise ValueError("authorization statement is not exact")
        if self.price_evidence_urls != PRICE_EVIDENCE_URLS:
            raise ValueError("price evidence URLs conflict with the exact sample")
        return self

    def approved_datetime(self) -> datetime:
        return _parse_utc(self.approved_at, "approved_at")

    def expires_datetime(self) -> datetime:
        return _parse_utc(self.expires_at, "expires_at")

    def price_checked_datetime(self) -> datetime:
        return _parse_utc(self.price_checked_at, "price_checked_at")

    def account_readiness_checked_datetime(self) -> datetime:
        return _parse_utc(self.account_readiness_checked_at, "account_readiness_checked_at")


class W131PreflightCheck(_StrictFrozenModel):
    name: str
    status: Literal["pass", "block"]
    detail: str


class W131PreflightReport(_StrictFrozenModel):
    schema_version: Literal["w1-31-preflight.v1"] = "w1-31-preflight.v1"
    evidence_level: Literal["L2-fixture-or-dry-run"] = "L2-fixture-or-dry-run"
    blocked: bool
    provider_call_allowed: bool
    approval_id: str | None = None
    checks: tuple[W131PreflightCheck, ...]
    supported_claims: tuple[str, ...] = (
        "Exact W1-31 record and credential presence were checked without a provider call.",
    )
    forbidden_claims: tuple[str, ...] = (
        "Do not claim provider key validity, available balance, live charge, invoice truth, or reconciliation.",
    )


class W131ExecutionResult(_StrictFrozenModel):
    external_task_id: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
    attempt_state: W131AttemptState
    account_reserved_usd_nanos: int = Field(ge=0, le=2**63 - 1)
    account_settled_usd_nanos: int = Field(ge=0, le=2**63 - 1)
    attempt_reserved_usd_nanos: int = Field(ge=0, le=2**63 - 1)
    attempt_settled_usd_nanos: int = Field(ge=0, le=2**63 - 1)
    provider_reported_credit_micro_units: int = Field(ge=0, le=2**63 - 1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_size_bytes: int = Field(gt=0)


class _W131ReconciliationFacts(_StrictFrozenModel):
    schema_version: Literal["w1-31-reconciliation.v1"] = "w1-31-reconciliation.v1"
    provider: Literal["poyo"] = "poyo"
    model: Literal["gpt-image-2"] = "gpt-image-2"
    expected_usd_nanos: Literal[10_000_000] = EXPECTED_USD_NANOS
    expected_provider_credit_micro_units: Literal[2_000_000] = EXPECTED_PROVIDER_CREDIT_MICRO_UNITS
    external_task_id: str
    attempt_state: str
    account_reserved_usd_nanos: int
    account_settled_usd_nanos: int
    attempt_reserved_usd_nanos: int
    attempt_settled_usd_nanos: int
    provider_reported_credit_micro_units: int
    artifact_sha256: str
    artifact_size_bytes: int
    single_task_charge_reconciled: bool
    invoice_reconciliation: Literal[False] = False
    production_unchanged: Literal[True] = True
    mismatch_codes: tuple[str, ...]


class W131ReconciliationReport(_W131ReconciliationFacts):
    evidence_level: Literal["L2-fixture-or-dry-run"] = "L2-fixture-or-dry-run"
    provider_call_executed: Literal[False] = False


class W131AuthorizedLiveReconciliationReport(_W131ReconciliationFacts):
    """Projection emitted only by the fixed canonical authorized-live wrapper."""

    evidence_level: Literal["L4-authorized-live"] = "L4-authorized-live"
    provider_call_executed: Literal[True] = True


class W131LedgerReadback(_StrictFrozenModel):
    schema_version: Literal["w1-31-ledger-readback.v1"] = "w1-31-ledger-readback.v1"
    external_call_during_readback: Literal[False] = False
    tenant_id: Literal["w1-31-calibration"]
    approval_id: str
    account_id: str
    cap_usd_nanos: int
    account_reserved_usd_nanos: int
    account_settled_usd_nanos: int
    attempt_count: int
    attempt_state: str | None = None
    external_task_id: str | None = None
    attempt_reserved_usd_nanos: int | None = None
    attempt_settled_usd_nanos: int | None = None
    provider_reported_credit_micro_units: int | None = None


def _parse_utc(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    normalized = parsed.astimezone(UTC)
    if not value.endswith("Z") or normalized.isoformat().replace("+00:00", "Z") != value:
        raise ValueError(f"{field_name} must be canonical UTC")
    return normalized


def _reject_float(token: str) -> object:
    raise ValueError(f"floating JSON numbers are forbidden: {token}")


def _reject_constant(token: str) -> object:
    raise ValueError(f"non-finite JSON numbers are forbidden: {token}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _validate_private_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved.is_relative_to(REPO_ROOT) and not resolved.is_relative_to(PRIVATE_REPO_DIR):
        raise ValueError("W1-31 private files must be under tmp/ or outside the repository")
    return resolved


def parse_private_approval_record(
    path: str | Path,
    *,
    now: datetime | None = None,
) -> W131ApprovalRecord:
    resolved = _validate_private_path(path)
    raw = resolved.read_text()
    if len(raw) > 32_000:
        raise ValueError("W1-31 approval record is too large")
    try:
        payload = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
        if not isinstance(payload, dict):
            raise ValueError("W1-31 approval record must be an object")
        urls = payload.get("price_evidence_urls")
        if isinstance(urls, list):
            payload["price_evidence_urls"] = tuple(urls)
        record = validate_approval_payload(payload, now=now)
    except (json.JSONDecodeError, OSError, TypeError, ValidationError) as exc:
        raise ValueError("W1-31 approval record is invalid") from exc
    return record


def validate_approval_payload(
    payload: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> W131ApprovalRecord:
    try:
        record = W131ApprovalRecord.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise ValueError("W1-31 approval record is invalid") from exc
    checked_at_input = now or datetime.now(UTC)
    if checked_at_input.tzinfo is None or checked_at_input.utcoffset() is None:
        raise ValueError("validation time must be timezone-aware")
    checked_at = checked_at_input.astimezone(UTC)
    approved_at = record.approved_datetime()
    expires_at = record.expires_datetime()
    price_checked_at = record.price_checked_datetime()
    account_checked_at = record.account_readiness_checked_datetime()
    if approved_at > checked_at:
        raise ValueError("approval time is in the future")
    if expires_at <= checked_at:
        raise ValueError("approval record is expired")
    if expires_at <= approved_at:
        raise ValueError("approval expiry must follow approval time")
    if expires_at - approved_at > APPROVAL_MAX_LIFETIME:
        raise ValueError("approval lifetime exceeds the two-hour maximum")
    if price_checked_at > checked_at or checked_at - price_checked_at > PRICE_EVIDENCE_MAX_AGE:
        raise ValueError("price evidence is missing or stale")
    if account_checked_at > checked_at or checked_at - account_checked_at > ACCOUNT_READINESS_MAX_AGE:
        raise ValueError("account readiness evidence is missing or stale")
    return record


def build_preflight_report(
    *,
    approval_record_path: str | Path,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> W131PreflightReport:
    environment = os.environ if env is None else env
    checks: list[W131PreflightCheck] = []
    record: W131ApprovalRecord | None = None
    try:
        record = parse_private_approval_record(approval_record_path, now=now)
    except (OSError, ValueError):
        checks.append(
            W131PreflightCheck(
                name="exact_private_approval",
                status="block",
                detail="exact private W1-31 approval record is invalid or unavailable",
            )
        )
    else:
        checks.append(
            W131PreflightCheck(
                name="exact_private_approval",
                status="pass",
                detail="exact sample, cap, dual confirmation, and price evidence are bound",
            )
        )

    if record is None:
        checks.append(
            W131PreflightCheck(
                name="one_shot_authority",
                status="block",
                detail="cannot evaluate one-shot authority without a valid approval record",
            )
        )
    elif canonical_consumption_marker_path(record).exists():
        checks.append(
            W131PreflightCheck(
                name="one_shot_authority",
                status="block",
                detail="W1-31 approval authority was already consumed",
            )
        )
    else:
        checks.append(
            W131PreflightCheck(
                name="one_shot_authority",
                status="pass",
                detail="no durable consumption marker exists for this approval ID",
            )
        )

    if bool(environment.get("POYO_API_KEY")):
        checks.append(
            W131PreflightCheck(
                name="poyo_credential_presence",
                status="pass",
                detail="POYO_API_KEY is present; value was not inspected or emitted",
            )
        )
    else:
        checks.append(
            W131PreflightCheck(
                name="poyo_credential_presence",
                status="block",
                detail="POYO_API_KEY is absent",
            )
        )
    blocked = any(check.status == "block" for check in checks)
    return W131PreflightReport(
        blocked=blocked,
        provider_call_allowed=not blocked,
        approval_id=record.approval_id if record is not None else None,
        checks=tuple(checks),
    )


def reconcile_single_task_charge(result: W131ExecutionResult) -> W131ReconciliationReport:
    mismatches: list[str] = []
    if result.attempt_state != "settled":
        mismatches.append("attempt_not_settled")
    if result.provider_reported_credit_micro_units != EXPECTED_PROVIDER_CREDIT_MICRO_UNITS:
        mismatches.append("provider_credit_mismatch")
    if result.attempt_reserved_usd_nanos != EXPECTED_USD_NANOS:
        mismatches.append("attempt_reservation_mismatch")
    if result.attempt_settled_usd_nanos != EXPECTED_USD_NANOS:
        mismatches.append("attempt_settlement_mismatch")
    if result.account_reserved_usd_nanos != 0:
        mismatches.append("account_reservation_not_released")
    if result.account_settled_usd_nanos != EXPECTED_USD_NANOS:
        mismatches.append("account_settlement_mismatch")
    return W131ReconciliationReport(
        external_task_id=result.external_task_id,
        attempt_state=result.attempt_state,
        account_reserved_usd_nanos=result.account_reserved_usd_nanos,
        account_settled_usd_nanos=result.account_settled_usd_nanos,
        attempt_reserved_usd_nanos=result.attempt_reserved_usd_nanos,
        attempt_settled_usd_nanos=result.attempt_settled_usd_nanos,
        provider_reported_credit_micro_units=result.provider_reported_credit_micro_units,
        artifact_sha256=result.artifact_sha256,
        artifact_size_bytes=result.artifact_size_bytes,
        single_task_charge_reconciled=not mismatches,
        mismatch_codes=tuple(mismatches),
    )


async def consume_and_execute_once(
    *,
    record: W131ApprovalRecord,
    marker_path: str | Path,
    execute: Callable[[], Awaitable[W131ExecutionResult]],
) -> W131ReconciliationReport:
    if not isinstance(record, W131ApprovalRecord) or not callable(execute):
        raise ValueError("W1-31 one-shot execution inputs are invalid")
    marker = _validate_private_path(marker_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker_payload = {
        "schema_version": "w1-31-consumption.v1",
        "approval_id": record.approval_id,
        "state": "consumed_before_provider_client_construction",
        "consumed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as handle:
            handle.write(json.dumps(marker_payload, ensure_ascii=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    result = await execute()
    return reconcile_single_task_charge(result)


async def execute_canonical_authorized_live_once(
    *,
    record: W131ApprovalRecord,
    run_directory: str | Path,
) -> W131AuthorizedLiveReconciliationReport:
    """Reject the superseded W1-31 provider mutation path permanently."""

    del record, run_directory
    raise RuntimeError("w1_31_execution_retired")


def canonical_consumption_marker_path(record: W131ApprovalRecord) -> Path:
    """Return one repository-stable marker path for an approval identity."""

    if not isinstance(record, W131ApprovalRecord):
        raise ValueError("W1-31 approval record is invalid")
    return PRIVATE_REPO_DIR / "w1-31-authority-consumption" / f"{record.approval_id}.json"


def read_local_w131_ledger(run_directory: str | Path) -> W131LedgerReadback:
    """Reopen the W1-31 SQLite ledger read-only without provider or config imports."""

    run_dir = _validate_private_path(run_directory)
    ledger_path = run_dir / "provider-cost-ledger.sqlite3"
    if not ledger_path.is_file():
        raise ValueError("W1-31 local ledger is unavailable")
    uri = f"file:{quote(str(ledger_path))}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        accounts = connection.execute(
            "SELECT * FROM job_budget_accounts WHERE tenant_id = ? ORDER BY created_at, account_id",
            ("w1-31-calibration",),
        ).fetchall()
        if len(accounts) != 1:
            raise ValueError("W1-31 ledger account cardinality is invalid")
        account = accounts[0]
        attempts = connection.execute(
            "SELECT * FROM provider_cost_attempts WHERE tenant_id = ? AND account_id = ? "
            "ORDER BY ordinal, attempt_id",
            ("w1-31-calibration", account["account_id"]),
        ).fetchall()
        if len(attempts) > 1:
            raise ValueError("W1-31 ledger attempt cardinality is invalid")
        attempt = attempts[0] if attempts else None
        return W131LedgerReadback(
            tenant_id="w1-31-calibration",
            approval_id=str(account["job_id"]),
            account_id=str(account["account_id"]),
            cap_usd_nanos=int(account["cap_usd_nanos"]),
            account_reserved_usd_nanos=int(account["reserved_usd_nanos"]),
            account_settled_usd_nanos=int(account["settled_usd_nanos"]),
            attempt_count=len(attempts),
            attempt_state=str(attempt["state"]) if attempt is not None else None,
            external_task_id=(
                str(attempt["external_task_id"])
                if attempt is not None and attempt["external_task_id"] is not None
                else None
            ),
            attempt_reserved_usd_nanos=(
                int(attempt["reserved_usd_nanos"]) if attempt is not None else None
            ),
            attempt_settled_usd_nanos=(
                int(attempt["settled_usd_nanos"]) if attempt is not None else None
            ),
            provider_reported_credit_micro_units=(
                int(attempt["provider_reported_credit_micro_units"])
                if attempt is not None and attempt["provider_reported_credit_micro_units"] is not None
                else None
            ),
        )
    finally:
        connection.close()


def build_private_approval_payload(
    *,
    approval_id: str,
    approved_by: str,
    confirmed_by: str,
    approved_at: str,
    expires_at: str,
    price_checked_at: str,
    account_readiness_checked_at: str,
    available_credit_micro_units: int,
    authorization_statement: str,
) -> dict[str, Any]:
    """Build the exact JSON-safe record shape; caller still writes it privately."""

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "approval_id": approval_id,
        "scope": SCOPE,
        "provider": PROVIDER,
        "model": MODEL,
        "approved_by": approved_by,
        "confirmed_by": confirmed_by,
        "account_readiness_checked_by": confirmed_by,
        "account_readiness_checked_at": account_readiness_checked_at,
        "available_credit_micro_units": available_credit_micro_units,
        "approved_at": approved_at,
        "expires_at": expires_at,
        "price_checked_at": price_checked_at,
        "price_evidence_urls": list(PRICE_EVIDENCE_URLS),
        "authorization_statement": authorization_statement,
        "sample": {
            "workflow": "text-to-image",
            "quality": QUALITY,
            "size": SIZE,
            "effective_resolution": EFFECTIVE_RESOLUTION,
            "image_count": 1,
            "prompt_profile_id": PROMPT_PROFILE_ID,
        },
        "budget_limit_usd": "0.01",
        "expected_usd_nanos": EXPECTED_USD_NANOS,
        "expected_provider_credit_micro_units": EXPECTED_PROVIDER_CREDIT_MICRO_UNITS,
        "max_provider_calls": 1,
        "max_retries": 0,
        "production_allowed": False,
        "publish_allowed": False,
        "delivery_allowed": False,
    }
    normalized = dict(payload)
    normalized["price_evidence_urls"] = tuple(PRICE_EVIDENCE_URLS)
    validate_approval_payload(normalized, now=datetime.now(UTC))
    return payload


async def execute_canonical_w131_sample(
    *,
    record: W131ApprovalRecord,
    run_directory: str | Path,
    env: Mapping[str, str] | None = None,
) -> W131ExecutionResult:
    """Reject the superseded W1-31 provider mutation path permanently."""

    del record, run_directory, env
    raise RuntimeError("w1_31_execution_retired")
