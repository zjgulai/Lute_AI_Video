"""Private exact-request binding for one W5 Fast activation.

This module is provider-off. It hashes a validated Fast request and one
idempotency key digest, but it cannot read environment configuration, create a
durable claim, initialize a provider account, or call a provider.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from src.pipeline.generation_policy_constants import GENERATION_POLICY_VERSION
from src.pipeline.w5_acceptance_harness import (
    W5ProviderJobCategory,
    W5ScenarioPlanDraftV1,
)
from src.pipeline.w5_fast_activation import W5FastActivationRecordV1
from src.services.provider_cost import ValidatedPlanBudgetAuthorization
from src.services.submission_idempotency import (
    FINGERPRINT_VERSION,
    build_request_fingerprint,
)

W5_FAST_RUNTIME_VERSION = "w5-fast-runtime-binding.v1"
_MAX_RUNTIME_JSON_BYTES = 64_000
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

SafeIdentifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    ),
]
Sha256Digest = Annotated[str, Field(pattern=_SHA256_RE.pattern)]
PositiveMoneyNanos = Annotated[int, Field(strict=True, ge=1)]
PositiveJobCap = Annotated[int, Field(strict=True, ge=1, le=10_000)]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class W5FastRuntimeBindingV1(_StrictFrozenModel):
    """Hash-only private runtime authority for one exact Fast request."""

    version: Literal["w5-fast-runtime-binding.v1"] = W5_FAST_RUNTIME_VERSION
    scope: Literal["w5-fast-runtime-binding"] = "w5-fast-runtime-binding"
    binding_id: SafeIdentifier
    plan_id: SafeIdentifier
    activation_id: SafeIdentifier
    activation_sha256: Sha256Digest
    tenant_id: SafeIdentifier
    sample_ref: SafeIdentifier
    request_fingerprint_version: Literal["submit-fingerprint.v1"] = (
        FINGERPRINT_VERSION
    )
    request_hash: Sha256Digest
    idempotency_key_sha256: Sha256Digest
    generation_policy_version: Literal["generation-safety.v2"] = (
        GENERATION_POLICY_VERSION
    )
    duration_seconds: Literal[10, 15]
    enable_tts: bool
    artifact_disposition: Literal["pending_review"] = "pending_review"
    provider_max_retries: Literal[0] = 0
    expected_llm_provider: Literal["deepseek"] = "deepseek"
    expected_llm_model: Literal["deepseek-v4-flash"] = "deepseek-v4-flash"
    expected_video_provider: Literal["poyo"] = "poyo"
    expected_video_model: Literal["seedance-2"] = "seedance-2"
    expected_video_resolution: Literal["720p"] = "720p"
    budget_limit_usd_nanos: PositiveMoneyNanos
    provider_job_caps: tuple[
        tuple[W5ProviderJobCategory, PositiveJobCap],
        ...,
    ]
    submission_cap: Literal[1] = 1
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
    def _validate_binding_shape(self) -> W5FastRuntimeBindingV1:
        if len(dict(self.provider_job_caps)) != len(self.provider_job_caps):
            raise ValueError("provider job cap categories must be unique")
        return self


def _require_utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")
    return value.astimezone(UTC)


def _model_projection(value: object, *, name: str) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        payload = value.model_dump(
            mode="json",
            exclude_none=False,
            exclude_defaults=False,
            exclude_unset=False,
        )
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        raise ValueError(f"{name} must be a validated mapping")
    return payload


def _validate_plan_activation(
    *,
    plan: W5ScenarioPlanDraftV1,
    activation: W5FastActivationRecordV1,
    now: datetime,
    require_active: bool = True,
) -> None:
    normalized_now = _require_utc(now, "runtime binding time")
    if not isinstance(plan, W5ScenarioPlanDraftV1):
        raise ValueError("canonical W5 plan is required")
    if not isinstance(activation, W5FastActivationRecordV1):
        raise ValueError("validated W5 activation is required")
    if plan.scenario != "fast" or activation.scenario != "fast":
        raise ValueError("runtime binding scenario must be Fast")
    if activation.plan_id != plan.plan_id:
        raise ValueError("runtime binding plan mismatch")
    if activation.tenant_id != plan.tenant_id:
        raise ValueError("runtime binding tenant mismatch")
    if activation.sample_ref != plan.sample_ref:
        raise ValueError("runtime binding sample mismatch")
    if activation.budget_limit_usd_nanos != plan.budget_limit_usd_nanos:
        raise ValueError("runtime binding budget mismatch")
    if dict(activation.provider_job_caps) != dict(plan.provider_job_caps):
        raise ValueError("runtime binding provider job caps mismatch")
    if activation.selected_optional_media != plan.selected_optional_media:
        raise ValueError("runtime binding optional media mismatch")
    if activation.approved_at < plan.created_at:
        raise ValueError("runtime binding approval precedes plan")
    if activation.expires_at > plan.expires_at:
        raise ValueError("runtime binding activation exceeds plan")
    if require_active:
        if normalized_now < plan.created_at or normalized_now >= plan.expires_at:
            raise ValueError("runtime binding plan is not active")
        if normalized_now < activation.approved_at:
            raise ValueError("runtime binding activation is not active")
        if normalized_now >= activation.expires_at:
            raise ValueError("runtime binding activation is expired")


def _validate_request_policy(
    *,
    plan: W5ScenarioPlanDraftV1,
    validated_request: object,
    effective_policy: object,
) -> tuple[dict[str, Any], dict[str, Any], Literal[10, 15], bool]:
    request = _model_projection(validated_request, name="Fast request")
    policy = _model_projection(effective_policy, name="effective policy")

    if policy.get("tenant_id") != plan.tenant_id:
        raise ValueError("runtime binding tenant mismatch")
    if policy.get("scenario") != "fast":
        raise ValueError("runtime binding scenario mismatch")
    if request.get("enable_media_synthesis") is not True:
        raise ValueError("runtime binding requires request media synthesis")
    if policy.get("enable_media_synthesis") is not True:
        raise ValueError("runtime binding requires policy media synthesis")
    if request.get("artifact_disposition") != "pending_review":
        raise ValueError("runtime binding request disposition mismatch")
    if policy.get("artifact_disposition") != "pending_review":
        raise ValueError("runtime binding policy disposition mismatch")
    if request.get("provider_max_retries") != 0 or policy.get(
        "provider_max_retries"
    ) != 0:
        raise ValueError("runtime binding retry cap mismatch")
    if policy.get("version") != GENERATION_POLICY_VERSION:
        raise ValueError("runtime binding generation policy mismatch")

    raw_duration = request.get("duration")
    if type(raw_duration) is not int:
        raise ValueError("runtime binding duration is invalid")
    duration = max(10, min(15, raw_duration))
    if duration not in (10, 15):
        raise ValueError("runtime binding duration is invalid")

    enable_tts = request.get("enable_tts")
    if type(enable_tts) is not bool:
        raise ValueError("runtime binding TTS choice is invalid")
    planned_tts = plan.selected_optional_media == ("tts_audio",)
    expected_caps = {"llm": 1, "video": 1}
    if planned_tts:
        expected_caps["tts"] = 1
    if enable_tts is not planned_tts:
        raise ValueError("runtime binding TTS selection mismatch")
    if dict(plan.provider_job_caps) != expected_caps:
        raise ValueError("runtime binding TTS or provider cap mismatch")
    return request, policy, cast(Literal[10, 15], duration), enable_tts


def _binding_id(
    *,
    plan_id: str,
    activation_id: str,
    activation_sha256: str,
    request_hash: str,
    idempotency_key_sha256: str,
) -> str:
    digest = hashlib.sha256(
        (
            f"{plan_id}:{activation_id}:{activation_sha256}:{request_hash}:"
            f"{idempotency_key_sha256}"
        ).encode()
    ).hexdigest()[:32]
    return f"w5fastbind:{digest}"


def _activation_sha256(activation: W5FastActivationRecordV1) -> str:
    payload = activation.model_dump(
        mode="json",
        exclude_none=False,
        exclude_defaults=False,
        exclude_unset=False,
    )
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _build_w5_fast_runtime_binding(
    *,
    plan: W5ScenarioPlanDraftV1,
    activation: W5FastActivationRecordV1,
    validated_request: object,
    effective_policy: object,
    idempotency_key_sha256: str,
    now: datetime,
    require_active: bool,
) -> W5FastRuntimeBindingV1:
    _validate_plan_activation(
        plan=plan,
        activation=activation,
        now=now,
        require_active=require_active,
    )
    _, _, duration, enable_tts = _validate_request_policy(
        plan=plan,
        validated_request=validated_request,
        effective_policy=effective_policy,
    )
    if not isinstance(idempotency_key_sha256, str) or _SHA256_RE.fullmatch(
        idempotency_key_sha256
    ) is None:
        raise ValueError("runtime binding idempotency digest is invalid")
    fingerprint = build_request_fingerprint(
        cast(BaseModel | Mapping[str, Any], validated_request),
        operation="fast.submit",
        scenario="fast",
        effective_policy=cast(
            BaseModel | Mapping[str, Any],
            effective_policy,
        ),
    )
    activation_sha256 = _activation_sha256(activation)
    return W5FastRuntimeBindingV1(
        binding_id=_binding_id(
            plan_id=plan.plan_id,
            activation_id=activation.activation_id,
            activation_sha256=activation_sha256,
            request_hash=fingerprint.request_hash,
            idempotency_key_sha256=idempotency_key_sha256,
        ),
        plan_id=plan.plan_id,
        activation_id=activation.activation_id,
        activation_sha256=activation_sha256,
        tenant_id=plan.tenant_id,
        sample_ref=plan.sample_ref,
        request_hash=fingerprint.request_hash,
        idempotency_key_sha256=idempotency_key_sha256,
        duration_seconds=duration,
        enable_tts=enable_tts,
        budget_limit_usd_nanos=plan.budget_limit_usd_nanos,
        provider_job_caps=plan.provider_job_caps,
    )


def build_w5_fast_runtime_binding(
    *,
    plan: W5ScenarioPlanDraftV1,
    activation: W5FastActivationRecordV1,
    validated_request: object,
    effective_policy: object,
    idempotency_key_sha256: str,
    now: datetime,
) -> W5FastRuntimeBindingV1:
    """Build one active hash-only binding from validated private authority."""

    return _build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=validated_request,
        effective_policy=effective_policy,
        idempotency_key_sha256=idempotency_key_sha256,
        now=now,
        require_active=True,
    )


def derive_w5_fast_plan_budget_authorization(
    *,
    plan: W5ScenarioPlanDraftV1,
    activation: W5FastActivationRecordV1,
    now: datetime,
) -> ValidatedPlanBudgetAuthorization:
    """Project exact reviewed W5 total authority without provider/model fiction."""

    _validate_plan_activation(plan=plan, activation=activation, now=now)
    return ValidatedPlanBudgetAuthorization(
        authorization_ref=activation.activation_id,
        authorization_scope="w5-fast",
        approved_at=activation.approved_at,
        expires_at=activation.expires_at,
        budget_limit_usd_nanos=plan.budget_limit_usd_nanos,
        max_total_cost_usd_nanos=plan.budget_limit_usd_nanos,
        per_job_cost_ceiling_usd_nanos=plan.budget_limit_usd_nanos,
        provider_job_caps=plan.provider_job_caps,
    )


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


def _parse_runtime_json(raw: str | bytes) -> str:
    if not isinstance(raw, (str, bytes)):
        raise ValueError("runtime binding must be bounded original JSON")
    raw_size = len(raw.encode("utf-8")) if isinstance(raw, str) else len(raw)
    if raw_size > _MAX_RUNTIME_JSON_BYTES:
        raise ValueError("runtime binding must be bounded original JSON")
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
        raise ValueError("runtime binding must be valid strict JSON") from exc


def validate_w5_fast_runtime_binding_json(
    raw: str | bytes,
    *,
    plan: W5ScenarioPlanDraftV1,
    activation: W5FastActivationRecordV1,
    validated_request: object,
    effective_policy: object,
    idempotency_key_sha256: str,
    now: datetime,
    require_active: bool = True,
) -> W5FastRuntimeBindingV1:
    """Recompute and compare every exact runtime-binding field."""

    strict_raw = _parse_runtime_json(raw)
    binding = W5FastRuntimeBindingV1.model_validate_json(strict_raw)
    expected = _build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=validated_request,
        effective_policy=effective_policy,
        idempotency_key_sha256=idempotency_key_sha256,
        now=now,
        require_active=require_active,
    )
    if binding.idempotency_key_sha256 != expected.idempotency_key_sha256:
        raise ValueError("runtime binding idempotency digest mismatch")
    if binding.request_hash != expected.request_hash:
        raise ValueError("runtime binding request mismatch")
    if binding.activation_sha256 != expected.activation_sha256:
        raise ValueError("runtime binding activation digest mismatch")
    if binding != expected:
        raise ValueError("runtime binding exact authority mismatch")
    return binding


__all__ = [
    "W5_FAST_RUNTIME_VERSION",
    "W5FastRuntimeBindingV1",
    "build_w5_fast_runtime_binding",
    "derive_w5_fast_plan_budget_authorization",
    "validate_w5_fast_runtime_binding_json",
]
