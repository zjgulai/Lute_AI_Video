"""Provider-off W5 Fast activation validation and readiness projection.

This module validates private approval evidence but deliberately cannot bind a
runtime, create a provider-cost account, consume authority, or call a provider.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from src.models.provider_cost import MAX_SIGNED_BIGINT
from src.pipeline.w5_acceptance_harness import (
    W5ProviderJobCategory,
    W5ScenarioPlanDraftV1,
    validate_w5_plan_draft_json,
)

W5_FAST_ACTIVATION_VERSION = "w5-fast-activation.v1"
W5_FAST_AUTHORIZATION_STATEMENT = (
    "I authorize exactly one W5 Fast provider submission bound to this plan; "
    "retry, publish, and delivery remain disabled."
)
_MAX_PRIVATE_JSON_BYTES = 64_000
_MAX_ACTIVATION_LIFETIME = timedelta(hours=2)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRIVATE_REPO_ROOT = (_REPO_ROOT / "tmp").resolve()

SafeIdentifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    ),
]
PositiveMoneyNanos = Annotated[
    int,
    Field(strict=True, ge=1, le=MAX_SIGNED_BIGINT),
]
PositiveJobCap = Annotated[int, Field(strict=True, ge=1, le=10_000)]
W5FastReadinessStatus = Literal["ready_for_private_binding", "blocked"]
W5FastCheckStatus = Literal["pass", "block"]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class W5FastActivationRecordV1(_StrictFrozenModel):
    """Private approval evidence bound to one canonical Fast draft."""

    version: Literal["w5-fast-activation.v1"] = W5_FAST_ACTIVATION_VERSION
    scope: Literal["w5-fast-activation"] = "w5-fast-activation"
    activation_id: SafeIdentifier
    plan_id: SafeIdentifier
    tenant_id: SafeIdentifier
    scenario: Literal["fast"] = "fast"
    sample_ref: SafeIdentifier
    approved_by: SafeIdentifier
    approved_at: datetime
    expires_at: datetime
    authorization_statement: Literal[
        "I authorize exactly one W5 Fast provider submission bound to this plan; "
        "retry, publish, and delivery remain disabled."
    ] = W5_FAST_AUTHORIZATION_STATEMENT
    template_only: Literal[False] = False
    budget_limit_usd_nanos: PositiveMoneyNanos
    selected_optional_media: tuple[Literal["tts_audio"], ...] = ()
    provider_job_caps: tuple[
        tuple[W5ProviderJobCategory, PositiveJobCap],
        ...,
    ]
    submission_cap: Literal[1] = 1
    automatic_retry_cap: Literal[0] = 0
    provider_max_retries: Literal[0] = 0
    artifact_disposition: Literal["pending_review"] = "pending_review"
    provider_mutation_approved: Literal[True] = True
    runtime_binding_required: Literal[True] = True
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False

    @field_validator("provider_job_caps", mode="before")
    @classmethod
    def _load_provider_job_caps(cls, value: object) -> object:
        if type(value) is not dict:
            return value
        category_order = ("llm", "image", "video", "tts", "thumbnail")
        if set(value) - set(category_order):
            raise ValueError("provider job cap categories contain unsupported values")
        return tuple(
            (category, value[category])
            for category in category_order
            if category in value
        )

    @field_serializer("provider_job_caps")
    def _serialize_provider_job_caps(
        self,
        value: tuple[tuple[W5ProviderJobCategory, int], ...],
    ) -> dict[str, int]:
        return dict(value)

    @model_validator(mode="after")
    def _validate_record(self) -> W5FastActivationRecordV1:
        _require_utc(self.approved_at, "approval time")
        _require_utc(self.expires_at, "approval expiry")
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must follow approval time")
        if self.expires_at - self.approved_at > _MAX_ACTIVATION_LIFETIME:
            raise ValueError("activation lifetime exceeds two hours")
        if len(dict(self.provider_job_caps)) != len(self.provider_job_caps):
            raise ValueError("provider job cap categories must be unique")
        if len(set(self.selected_optional_media)) != len(
            self.selected_optional_media
        ):
            raise ValueError("selected optional media must be unique")
        return self


class W5FastReadinessCheckV1(_StrictFrozenModel):
    name: Literal["private_paths", "plan_draft", "activation_record", "exact_binding"]
    status: W5FastCheckStatus
    detail: str = Field(min_length=1, max_length=160)


class W5FastReadinessReportV1(_StrictFrozenModel):
    version: Literal["w5-fast-activation.v1"] = W5_FAST_ACTIVATION_VERSION
    report_id: SafeIdentifier
    status: W5FastReadinessStatus
    plan_id: SafeIdentifier | None = None
    activation_id: SafeIdentifier | None = None
    ready_for_private_binding: bool
    provider_call_allowed: Literal[False] = False
    execution_authorized: Literal[False] = False
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False
    checks: tuple[W5FastReadinessCheckV1, ...]


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")


def _reject_float(token: str) -> object:
    raise ValueError(f"floating JSON number is forbidden: {token}")


def _reject_constant(token: str) -> object:
    raise ValueError(f"non-finite JSON number is forbidden: {token}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _parse_original_json(raw: str | bytes, *, name: str) -> str:
    if not isinstance(raw, (str, bytes)):
        raise ValueError(f"{name} must be bounded original JSON")
    raw_size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if raw_size > _MAX_PRIVATE_JSON_BYTES:
        raise ValueError(f"{name} must be bounded original JSON")
    try:
        payload = json.loads(
            raw,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (
        json.JSONDecodeError,
        RecursionError,
        UnicodeDecodeError,
        TypeError,
    ) as exc:
        raise ValueError(f"{name} must be valid strict JSON") from exc


def _validate_binding(
    activation: W5FastActivationRecordV1,
    *,
    plan: W5ScenarioPlanDraftV1,
    now: datetime,
    require_active: bool = True,
) -> None:
    _require_utc(now, "activation validation time")
    normalized_now = now.astimezone(UTC)
    if plan.scenario != "fast":
        raise ValueError("activation scenario requires a Fast plan")
    if activation.plan_id != plan.plan_id:
        raise ValueError("activation plan binding mismatch")
    if activation.tenant_id != plan.tenant_id:
        raise ValueError("activation tenant binding mismatch")
    if activation.sample_ref != plan.sample_ref:
        raise ValueError("activation sample binding mismatch")
    if activation.budget_limit_usd_nanos != plan.budget_limit_usd_nanos:
        raise ValueError("activation budget binding mismatch")
    if activation.selected_optional_media != plan.selected_optional_media:
        raise ValueError("activation optional media binding mismatch")
    if dict(activation.provider_job_caps) != dict(plan.provider_job_caps):
        raise ValueError("activation provider job cap binding mismatch")
    if activation.approved_at < plan.created_at:
        raise ValueError("activation approval precedes plan creation")
    if activation.expires_at > plan.expires_at:
        raise ValueError("activation expiry exceeds plan expiry")
    if require_active:
        if activation.approved_at > normalized_now:
            raise ValueError("activation approval time is in the future")
        if normalized_now < plan.created_at:
            raise ValueError("plan is not active yet")
        if normalized_now >= plan.expires_at:
            raise ValueError("plan is expired")
        if normalized_now >= activation.expires_at:
            raise ValueError("activation is expired")


def validate_w5_fast_activation_json(
    raw: str | bytes,
    *,
    plan: W5ScenarioPlanDraftV1,
    now: datetime,
) -> W5FastActivationRecordV1:
    """Validate exact private activation JSON against a canonical Fast plan."""

    if not isinstance(plan, W5ScenarioPlanDraftV1):
        raise ValueError("canonical W5 plan is required")
    strict_raw = _parse_original_json(raw, name="activation record")
    activation = W5FastActivationRecordV1.model_validate_json(strict_raw)
    _validate_binding(activation, plan=plan, now=now)
    return activation


def validate_w5_fast_activation_replay_json(
    raw: str | bytes,
    *,
    plan: W5ScenarioPlanDraftV1,
    now: datetime,
) -> W5FastActivationRecordV1:
    """Validate immutable activation binding without reopening owner authority."""

    if not isinstance(plan, W5ScenarioPlanDraftV1):
        raise ValueError("canonical W5 plan is required")
    strict_raw = _parse_original_json(raw, name="activation record")
    activation = W5FastActivationRecordV1.model_validate_json(strict_raw)
    _validate_binding(
        activation,
        plan=plan,
        now=now,
        require_active=False,
    )
    return activation


def _private_path(path: str | Path, *, name: str) -> Path:
    if not isinstance(path, (str, Path)):
        raise ValueError(f"{name} must use a private path")
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError(f"{name} must use a resolvable private path") from exc
    if resolved.is_relative_to(_REPO_ROOT) and not resolved.is_relative_to(
        _PRIVATE_REPO_ROOT
    ):
        raise ValueError(f"{name} must use a private path")
    return resolved


def _read_private_json(path: str | Path, *, name: str) -> str:
    resolved = _private_path(path, name=name)
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(resolved, flags)
    except OSError as exc:
        raise ValueError(f"{name} is unavailable") from exc
    try:
        file_info = os.fstat(descriptor)
        if not stat.S_ISREG(file_info.st_mode):
            raise ValueError(f"{name} must be a regular file")
        if file_info.st_size > _MAX_PRIVATE_JSON_BYTES:
            raise ValueError(f"{name} exceeds the private JSON size limit")
        with os.fdopen(descriptor, "rb", closefd=False) as source:
            raw = source.read(_MAX_PRIVATE_JSON_BYTES + 1)
        if len(raw) > _MAX_PRIVATE_JSON_BYTES:
            raise ValueError(f"{name} exceeds the private JSON size limit")
    except OSError as exc:
        raise ValueError(f"{name} is unavailable") from exc
    finally:
        os.close(descriptor)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{name} must be UTF-8 JSON") from exc


def read_w5_private_json(path: str | Path, *, name: str) -> str:
    """Read one bounded private regular JSON file with stable failures."""

    return _read_private_json(path, name=name)


def load_w5_fast_activation_files(
    *,
    plan_path: str | Path,
    activation_path: str | Path,
    now: datetime,
) -> tuple[W5ScenarioPlanDraftV1, W5FastActivationRecordV1]:
    """Load and bind private files without creating runtime authority."""

    plan_raw = _read_private_json(plan_path, name="W5 plan")
    activation_raw = _read_private_json(
        activation_path,
        name="W5 activation record",
    )
    plan = validate_w5_plan_draft_json(
        _parse_original_json(plan_raw, name="W5 plan"),
    )
    activation = validate_w5_fast_activation_json(
        activation_raw,
        plan=plan,
        now=now,
    )
    return plan, activation


def _report_id(plan_id: str | None, activation_id: str | None) -> str:
    digest = hashlib.sha256(
        f"{plan_id or 'blocked'}:{activation_id or 'blocked'}".encode()
    ).hexdigest()[:24]
    return f"w5fastready:{digest}"


def build_w5_fast_readiness_report(
    *,
    plan_path: str | Path,
    activation_path: str | Path,
    now: datetime,
) -> W5FastReadinessReportV1:
    """Return provider-off readiness truth with stable, secret-free failures."""

    try:
        plan, activation = load_w5_fast_activation_files(
            plan_path=plan_path,
            activation_path=activation_path,
            now=now,
        )
    except (TypeError, ValueError, ValidationError):
        return W5FastReadinessReportV1(
            report_id=_report_id(None, None),
            status="blocked",
            ready_for_private_binding=False,
            checks=(
                W5FastReadinessCheckV1(
                    name="private_paths",
                    status="block",
                    detail="private W5 plan or activation evidence is invalid or unavailable",
                ),
            ),
        )

    checks = (
        W5FastReadinessCheckV1(
            name="private_paths",
            status="pass",
            detail="private input paths are outside formal tracked authority",
        ),
        W5FastReadinessCheckV1(
            name="plan_draft",
            status="pass",
            detail="canonical non-authorizing W5 Fast draft is valid",
        ),
        W5FastReadinessCheckV1(
            name="activation_record",
            status="pass",
            detail="private bounded activation evidence is valid and active",
        ),
        W5FastReadinessCheckV1(
            name="exact_binding",
            status="pass",
            detail="activation exactly matches plan scope budget caps and time",
        ),
    )
    return W5FastReadinessReportV1(
        report_id=_report_id(plan.plan_id, activation.activation_id),
        status="ready_for_private_binding",
        plan_id=plan.plan_id,
        activation_id=activation.activation_id,
        ready_for_private_binding=True,
        checks=checks,
    )


__all__ = [
    "W5_FAST_ACTIVATION_VERSION",
    "W5_FAST_AUTHORIZATION_STATEMENT",
    "W5FastActivationRecordV1",
    "W5FastReadinessCheckV1",
    "W5FastReadinessReportV1",
    "build_w5_fast_readiness_report",
    "load_w5_fast_activation_files",
    "read_w5_private_json",
    "validate_w5_fast_activation_json",
    "validate_w5_fast_activation_replay_json",
]
