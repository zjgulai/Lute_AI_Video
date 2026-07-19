"""Strict, server-owned provider cost and billing-fact contracts."""

from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator

MAX_SIGNED_BIGINT = 2**63 - 1
USD_NANOS_PER_USD = 1_000_000_000

AttemptState = Literal[
    "reserved",
    "submission_started",
    "submitted",
    "settled",
    "released",
    "ambiguous",
    "accounting_error",
]
BudgetJobKind = Literal["canonical", "compatibility"]
BudgetSourceKind = Literal["server_config", "validated_authorization"]
ProviderBillingRegion = Literal[
    "deepseek_global_usd",
    "poyo_global_usd",
    "siliconflow_global_usd",
]
CatalogOperation = Literal[
    "chat_completion",
    "speech_synthesis",
    "image_generation",
    "text_to_video",
    "image_to_video",
]
ProviderCostErrorCode = Literal[
    "provider_execution_context_missing",
    "provider_budget_configuration_invalid",
    "provider_cost_rule_unavailable",
    "provider_budget_exhausted",
    "provider_cost_store_unavailable",
    "provider_cost_attempt_conflict",
    "provider_cost_usage_invalid",
    "provider_cost_outcome_ambiguous",
    "provider_cost_accounting_error",
    "provider_cost_artifact_failed",
    "provider_cost_legacy_path_blocked",
]
MediaType = Literal["text", "audio", "image", "video"]
BillingFactKind = Literal[
    "llm_tokens.v1",
    "tts_utf8_bytes.v1",
    "image_count.v1",
    "video_task.v1",
    "video_duration.v1",
]

_BUDGET_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]{1,9})?$")
_INTERNAL_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"
_LOGICAL_OPERATION_PATTERN = r"^[a-z][a-z0-9_.:-]{0,159}$"
_PROVIDER_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
_MODEL_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$"

BoundedNonNegativeInt = Annotated[
    int,
    Field(strict=True, ge=0, le=MAX_SIGNED_BIGINT),
]
BoundedPositiveInt = Annotated[
    int,
    Field(strict=True, ge=1, le=MAX_SIGNED_BIGINT),
]
BoundedInternalIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_INTERNAL_ID_PATTERN),
]


class ProviderCostContractError(RuntimeError):
    """Stable, safe provider-cost contract failure."""

    def __init__(self, code: ProviderCostErrorCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if not detail else f"{code}: {detail}")


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderCostAccountIdentity(_StrictFrozenModel):
    tenant_id: BoundedInternalIdentifier
    job_kind: BudgetJobKind
    job_id: BoundedInternalIdentifier
    scenario_or_resource_type: BoundedInternalIdentifier
    budget_source_kind: BudgetSourceKind
    budget_source_ref: BoundedInternalIdentifier | None = None
    budget_policy_version: BoundedInternalIdentifier


class ProviderCostAttemptIdentity(_StrictFrozenModel):
    logical_operation: str = Field(
        min_length=1,
        max_length=160,
        pattern=_LOGICAL_OPERATION_PATTERN,
    )
    catalog_operation: CatalogOperation
    ordinal: BoundedNonNegativeInt
    provider: str = Field(
        min_length=1,
        max_length=64,
        pattern=_PROVIDER_PATTERN,
    )
    canonical_model: str = Field(
        min_length=1,
        max_length=128,
        pattern=_MODEL_PATTERN,
    )
    provider_billing_region: ProviderBillingRegion
    media_type: MediaType
    billing_fact_kind: BillingFactKind
    state: AttemptState


class LLMTokensBillingFacts(_StrictFrozenModel):
    schema_version: Literal["llm_tokens.v1"]
    input_tokens: BoundedNonNegativeInt
    input_cache_hit_tokens: BoundedNonNegativeInt
    input_cache_miss_tokens: BoundedNonNegativeInt
    output_tokens: BoundedNonNegativeInt
    total_tokens: BoundedNonNegativeInt

    @model_validator(mode="after")
    def validate_token_conservation(self) -> LLMTokensBillingFacts:
        if self.input_cache_hit_tokens + self.input_cache_miss_tokens != self.input_tokens:
            raise ValueError("cache token components must equal input_tokens")
        if self.input_tokens + self.output_tokens != self.total_tokens:
            raise ValueError("input and output tokens must equal total_tokens")
        if self.total_tokens <= 0:
            raise ValueError("total_tokens must be positive")
        return self


class TTSUtf8BytesBillingFacts(_StrictFrozenModel):
    schema_version: Literal["tts_utf8_bytes.v1"]
    input_utf8_bytes: BoundedPositiveInt


class ImageCountBillingFacts(_StrictFrozenModel):
    schema_version: Literal["image_count.v1"]
    image_count: BoundedPositiveInt


class VideoTaskBillingFacts(_StrictFrozenModel):
    schema_version: Literal["video_task.v1"]
    task_count: BoundedPositiveInt
    duration_ms: BoundedPositiveInt | None = None


class VideoDurationBillingFacts(_StrictFrozenModel):
    schema_version: Literal["video_duration.v1"]
    task_count: BoundedPositiveInt
    duration_ms: BoundedPositiveInt


ProviderBillingFacts = Annotated[
    LLMTokensBillingFacts
    | TTSUtf8BytesBillingFacts
    | ImageCountBillingFacts
    | VideoTaskBillingFacts
    | VideoDurationBillingFacts,
    Field(discriminator="schema_version"),
]

_BILLING_FACTS_ADAPTER = TypeAdapter(ProviderBillingFacts)


def parse_billing_facts(value: object) -> ProviderBillingFacts:
    """Validate one exact billing-fact union member without coercion."""

    return _BILLING_FACTS_ADAPTER.validate_python(value, strict=True)


def _reject_json_non_integer(value: str) -> int:
    raise ValueError(f"non-integer JSON number is forbidden: {value}")


def parse_billing_facts_json(raw: str) -> ProviderBillingFacts:
    """Parse strict JSON while rejecting floats, NaN, and Infinity before validation."""

    parsed = json.loads(
        raw,
        parse_float=_reject_json_non_integer,
        parse_constant=_reject_json_non_integer,
    )
    return parse_billing_facts(parsed)


def parse_provider_job_budget_usd_to_nanos(raw: object) -> int:
    """Convert a canonical positive USD decimal string to signed-64-bit nanos."""

    if not isinstance(raw, str) or len(raw) > 32 or _BUDGET_RE.fullmatch(raw) is None:
        raise ProviderCostContractError(
            "provider_budget_configuration_invalid",
            "budget must be a canonical positive decimal with at most 9 fractional digits",
        )

    whole, separator, fraction = raw.partition(".")
    try:
        nanos = int(whole) * USD_NANOS_PER_USD
        if separator:
            nanos += int(fraction.ljust(9, "0"))
    except ValueError as exc:
        raise ProviderCostContractError(
            "provider_budget_configuration_invalid",
            "budget decimal is invalid",
        ) from exc

    if nanos <= 0 or nanos > MAX_SIGNED_BIGINT:
        raise ProviderCostContractError(
            "provider_budget_configuration_invalid",
            "budget is outside the signed-64-bit positive nanos range",
        )
    return nanos
