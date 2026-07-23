"""Server-owned provider budget authority and durable cost transitions."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_serializer,
    field_validator,
    model_validator,
)

from src.models.provider_cost import (
    MAX_SIGNED_BIGINT,
    USD_NANOS_PER_USD,
    AttemptState,
    BillingFactKind,
    CatalogOperation,
    MediaType,
    ProviderBillingFacts,
    ProviderBillingRegion,
    ProviderCostAccountIdentity,
    ProviderCostAttemptIdentity,
    ProviderCostContractError,
    parse_billing_facts,
    parse_provider_job_budget_usd_to_nanos,
)
from src.services.provider_price_catalog import PriceRule, ProviderPriceCatalog
from src.storage.provider_cost_repository import (
    ProviderCostRepository,
    ProviderCostReserveResult,
)

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_SAFE_OPERATION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,159}$")
_SAFE_DIMENSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$")
_CANONICAL_JSON_NUMBER_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

PositiveMoney = Annotated[int, Field(strict=True, ge=1, le=MAX_SIGNED_BIGINT)]
PositiveTtlSeconds = Annotated[int, Field(strict=True, ge=1, le=86_400)]
SafeIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_SAFE_ID_RE.pattern),
]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ValidatedProviderBudgetAuthorization(_StrictFrozenModel):
    """Trusted, exact hard-cap authority derived from original approval JSON."""

    authorization_ref: SafeIdentifier
    provider: str = Field(min_length=1, max_length=64)
    canonical_model: str = Field(min_length=1, max_length=128)
    approved_at: datetime
    expires_at: datetime
    budget_limit_usd_nanos: PositiveMoney
    max_total_cost_usd_nanos: PositiveMoney
    per_job_cost_ceiling_usd_nanos: PositiveMoney

    @model_validator(mode="after")
    def validate_authority(self) -> ValidatedProviderBudgetAuthorization:
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("approval time must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("approval expiry must be timezone-aware")
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must follow approval time")
        if self.max_total_cost_usd_nanos > self.budget_limit_usd_nanos:
            raise ValueError("approval total exceeds budget limit")
        if self.per_job_cost_ceiling_usd_nanos > self.max_total_cost_usd_nanos:
            raise ValueError("approval per-job ceiling exceeds total")
        return self


class ValidatedPlanBudgetAuthorization(_StrictFrozenModel):
    """Trusted provider-neutral total cap for one reviewed execution plan."""

    authorization_ref: SafeIdentifier
    authorization_scope: SafeIdentifier
    approved_at: datetime
    expires_at: datetime
    budget_limit_usd_nanos: PositiveMoney
    max_total_cost_usd_nanos: PositiveMoney
    per_job_cost_ceiling_usd_nanos: PositiveMoney
    provider_job_caps: tuple[tuple[str, int], ...]

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
        value: tuple[tuple[str, int], ...],
    ) -> dict[str, int]:
        return dict(value)

    @model_validator(mode="after")
    def validate_authority(self) -> ValidatedPlanBudgetAuthorization:
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("approval time must be timezone-aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("approval expiry must be timezone-aware")
        if self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must follow approval time")
        if self.max_total_cost_usd_nanos > self.budget_limit_usd_nanos:
            raise ValueError("approval total exceeds budget limit")
        if self.per_job_cost_ceiling_usd_nanos > self.max_total_cost_usd_nanos:
            raise ValueError("approval per-job ceiling exceeds total")
        allowed_categories = {"llm", "image", "video", "tts", "thumbnail"}
        caps = dict(self.provider_job_caps)
        if (
            not caps
            or len(caps) != len(self.provider_job_caps)
            or set(caps) - allowed_categories
            or any(type(value) is not int or value <= 0 or value > 10_000 for value in caps.values())
        ):
            raise ValueError("provider job caps must be unique positive bounded integers")
        return self


ValidatedBudgetAuthorization = (
    ValidatedProviderBudgetAuthorization | ValidatedPlanBudgetAuthorization
)


def _is_validated_budget_authorization(value: object) -> bool:
    return isinstance(
        value,
        (ValidatedProviderBudgetAuthorization, ValidatedPlanBudgetAuthorization),
    )


class TrustedRegenerationEpoch(_StrictFrozenModel):
    """Persisted server authority for repository allocation of a new ordinal."""

    operation_key: SafeIdentifier
    epoch_ref: SafeIdentifier


class ProviderCostOperationDefinition(_StrictFrozenModel):
    """Code-owned exact provider operation and reservation template."""

    registry_key: SafeIdentifier
    logical_operation: str = Field(
        min_length=1,
        max_length=160,
        pattern=_SAFE_OPERATION_RE.pattern,
    )
    provider: str = Field(min_length=1, max_length=64)
    canonical_model: str = Field(min_length=1, max_length=128)
    provider_billing_region: ProviderBillingRegion
    catalog_operation: CatalogOperation
    media_type: MediaType
    billing_fact_kind: BillingFactKind
    dimensions: tuple[tuple[str, str], ...]
    reservation_billing_facts: ProviderBillingFacts
    reservation_ttl_seconds: PositiveTtlSeconds

    @model_validator(mode="after")
    def validate_definition(self) -> ProviderCostOperationDefinition:
        if self.reservation_billing_facts.schema_version != self.billing_fact_kind:
            raise ValueError("reservation facts conflict with billing kind")
        seen_names: set[str] = set()
        for name, value in self.dimensions:
            if (
                _SAFE_DIMENSION_RE.fullmatch(name) is None
                or _SAFE_DIMENSION_RE.fullmatch(value) is None
                or name in seen_names
            ):
                raise ValueError("catalog dimensions must be unique bounded identifiers")
            seen_names.add(name)
        ProviderCostAttemptIdentity(
            logical_operation=self.logical_operation,
            catalog_operation=self.catalog_operation,
            ordinal=0,
            provider=self.provider,
            canonical_model=self.canonical_model,
            provider_billing_region=self.provider_billing_region,
            media_type=self.media_type,
            billing_fact_kind=self.billing_fact_kind,
            state="reserved",
        )
        return self


def _invalid_authorization(detail: str) -> ProviderCostContractError:
    return ProviderCostContractError(
        "provider_budget_configuration_invalid",
        detail,
    )


def _parse_decimal_token(token: str) -> Decimal:
    if _CANONICAL_JSON_NUMBER_RE.fullmatch(token) is None:
        raise ValueError("approval JSON number is not canonical decimal notation")
    return Decimal(token)


def _reject_json_constant(token: str) -> Decimal:
    raise ValueError(f"approval JSON constant is forbidden: {token}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("approval JSON contains duplicate object keys")
        result[key] = value
    return result


def _parse_utc_timestamp(value: object, field_name: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise ValueError(f"{field_name} must be a bounded UTC timestamp")
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return timestamp.astimezone(UTC)


def _decimal_to_usd_nanos(value: object, field_name: str) -> int:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{field_name} must be a positive exact decimal")
    scaled = value * USD_NANOS_PER_USD
    integral = scaled.to_integral_value()
    if scaled != integral:
        raise ValueError(f"{field_name} exceeds nine decimal places")
    nanos = int(integral)
    if nanos <= 0 or nanos > MAX_SIGNED_BIGINT:
        raise ValueError(f"{field_name} is outside the signed-64-bit nanos range")
    return nanos


def validate_provider_budget_authorization_json(
    raw: object,
    *,
    expected_provider: str,
    expected_model: str,
    now: datetime,
) -> ValidatedProviderBudgetAuthorization:
    """Parse original JSON numeric tokens into one immutable budget authority."""

    try:
        if not isinstance(raw, str) or len(raw) > 64_000:
            raise ValueError("approval authority must be original bounded JSON text")
        payload = json.loads(
            raw,
            parse_int=_parse_decimal_token,
            parse_float=_parse_decimal_token,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
        if not isinstance(payload, dict):
            raise ValueError("approval JSON must be an object")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("authorization validation time must be timezone-aware")
        normalized_now = now.astimezone(UTC)

        provider = payload.get("provider")
        canonical_model = payload.get("model")
        authorization_ref = payload.get("approval_id")
        if (
            not isinstance(provider, str)
            or not isinstance(canonical_model, str)
            or not isinstance(authorization_ref, str)
        ):
            raise ValueError("approval identity fields are missing")
        if provider != expected_provider or canonical_model != expected_model:
            raise ValueError("approval provider or model binding conflicts")

        budget_display = payload.get("budget_limit")
        display_nanos = parse_provider_job_budget_usd_to_nanos(budget_display)
        if not isinstance(budget_display, str):
            raise ValueError("approval budget display is missing")
        budget_decimal = payload.get("budget_limit_usd")
        if budget_decimal != Decimal(budget_display):
            raise ValueError("approval budget display and numeric token conflict")
        budget_nanos = _decimal_to_usd_nanos(
            budget_decimal,
            "budget_limit_usd",
        )
        if budget_nanos != display_nanos:
            raise ValueError("approval budget nanos conflict")

        stop_loss = payload.get("budget_stop_loss")
        if not isinstance(stop_loss, dict):
            raise ValueError("approval budget stop-loss object is missing")
        max_total_nanos = _decimal_to_usd_nanos(
            stop_loss.get("max_total_cost_usd"),
            "max_total_cost_usd",
        )
        per_job_nanos = _decimal_to_usd_nanos(
            stop_loss.get("per_job_cost_ceiling_usd"),
            "per_job_cost_ceiling_usd",
        )
        if max_total_nanos > budget_nanos:
            raise ValueError("approval total exceeds budget limit")
        if per_job_nanos > max_total_nanos:
            raise ValueError("approval per-job ceiling exceeds total")

        approved_at = _parse_utc_timestamp(payload.get("approved_at"), "approved_at")
        expires_at = _parse_utc_timestamp(payload.get("expires_at"), "expires_at")
        if approved_at > normalized_now:
            raise ValueError("approval time is in the future")
        if expires_at <= normalized_now:
            raise ValueError("approval is expired")
        return ValidatedProviderBudgetAuthorization(
            authorization_ref=authorization_ref,
            provider=provider,
            canonical_model=canonical_model,
            approved_at=approved_at,
            expires_at=expires_at,
            budget_limit_usd_nanos=budget_nanos,
            max_total_cost_usd_nanos=max_total_nanos,
            per_job_cost_ceiling_usd_nanos=per_job_nanos,
        )
    except ProviderCostContractError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError, ValidationError) as exc:
        raise _invalid_authorization("trusted budget authorization is invalid") from exc


async def initialize_provider_cost_account(
    *,
    repository: ProviderCostRepository,
    identity: ProviderCostAccountIdentity,
    server_cap_usd_nanos: int,
    now: datetime,
    authorization: ValidatedBudgetAuthorization | None = None,
) -> dict[str, Any]:
    """Create or replay one account without requiring a paid-operation registry.

    Task 4 needs the exact Task 3 account-authority rules before provider
    operation registries are connected.  Keeping the rules here lets the full
    cost service and the execution-context service share one implementation.
    """

    if not isinstance(repository, ProviderCostRepository):
        raise ProviderCostContractError(
            "provider_cost_store_unavailable",
            "provider cost repository injection is invalid",
        )
    if not isinstance(identity, ProviderCostAccountIdentity):
        raise _invalid_authorization("account identity must be server-owned")
    if type(server_cap_usd_nanos) is not int or not (0 < server_cap_usd_nanos <= MAX_SIGNED_BIGINT):
        raise _invalid_authorization("server job cap must be positive integer USD nanos")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise _invalid_authorization("account validation time must be timezone-aware")
    normalized_now = now.astimezone(UTC)

    effective_cap = server_cap_usd_nanos
    if authorization is None:
        if identity.budget_source_kind != "server_config" or identity.budget_source_ref is not None:
            raise _invalid_authorization("server budget source identity conflicts")
    else:
        if not _is_validated_budget_authorization(authorization):
            raise _invalid_authorization("budget authority must be a validated object")
        if normalized_now >= authorization.expires_at:
            raise _invalid_authorization("budget authority is expired")
        if (
            identity.budget_source_kind != "validated_authorization"
            or identity.budget_source_ref != authorization.authorization_ref
        ):
            raise _invalid_authorization("validated budget source identity conflicts")
        effective_cap = min(
            server_cap_usd_nanos,
            authorization.budget_limit_usd_nanos,
            authorization.per_job_cost_ceiling_usd_nanos,
        )

    return await repository.create_or_get_account(
        identity=identity,
        cap_usd_nanos=effective_cap,
    )


class ProviderCostService:
    """Compose exact catalog arithmetic with atomic repository transitions."""

    def __init__(
        self,
        *,
        repository: ProviderCostRepository,
        price_catalog: ProviderPriceCatalog,
        operation_registry: Mapping[str, ProviderCostOperationDefinition],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(repository, ProviderCostRepository):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost repository injection is invalid",
            )
        if not isinstance(price_catalog, ProviderPriceCatalog):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider price catalog injection is invalid",
            )
        if not isinstance(operation_registry, Mapping):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider operation registry is invalid",
            )
        normalized_registry: dict[str, ProviderCostOperationDefinition] = {}
        logical_operations: set[str] = set()
        for key, definition in operation_registry.items():
            if (
                not isinstance(key, str)
                or not isinstance(definition, ProviderCostOperationDefinition)
                or key != definition.registry_key
                or definition.logical_operation in logical_operations
            ):
                raise ProviderCostContractError(
                    "provider_cost_rule_unavailable",
                    "provider operation registry contains invalid authority",
                )
            normalized_registry[key] = definition
            logical_operations.add(definition.logical_operation)
        if not normalized_registry:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider operation registry is empty",
            )
        if clock is not None and not callable(clock):
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "provider cost clock injection is invalid",
            )

        self._repository = repository
        self._price_catalog = price_catalog
        self._operation_registry = MappingProxyType(normalized_registry)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def initialize_account(
        self,
        *,
        identity: ProviderCostAccountIdentity,
        server_cap_usd_nanos: int,
        authorization: ValidatedBudgetAuthorization | None = None,
    ) -> dict[str, Any]:
        return await initialize_provider_cost_account(
            repository=self._repository,
            identity=identity,
            server_cap_usd_nanos=server_cap_usd_nanos,
            authorization=authorization,
            now=self._now(),
        )

    async def reserve_or_replay(
        self,
        *,
        tenant_id: str,
        account_id: str,
        operation_key: str,
        attempt_fingerprint: str,
        regeneration_epoch: TrustedRegenerationEpoch | None = None,
    ) -> ProviderCostReserveResult:
        definition = self._require_operation(operation_key)
        start_new_epoch = False
        regeneration_epoch_ref: str | None = None
        if regeneration_epoch is not None:
            if not isinstance(regeneration_epoch, TrustedRegenerationEpoch):
                raise ProviderCostContractError(
                    "provider_cost_attempt_conflict",
                    "regeneration epoch authority is invalid",
                )
            # The trusted epoch is a workflow authority (for example
            # ``gate.regenerate.scripts``), while ``operation_key`` is the
            # provider-cost template (for example ``agent.script_writer``).
            # They intentionally live in different vocabularies. The epoch is
            # validated by the immutable execution context and authorizes one
            # new ordinal for the already-selected logical operation. The epoch
            # reference is persisted with that attempt so the same authority
            # cannot allocate a second ordinal after restart or concurrency.
            start_new_epoch = True
            regeneration_epoch_ref = regeneration_epoch.epoch_ref

        now = self._now()
        rule = self._price_catalog.require_rule(
            provider=definition.provider,
            canonical_model=definition.canonical_model,
            provider_billing_region=definition.provider_billing_region,
            catalog_operation=definition.catalog_operation,
            media_type=definition.media_type,
            billing_fact_kind=definition.billing_fact_kind,
            dimensions=dict(definition.dimensions),
            at=now,
        )
        reserved_usd_nanos = self._price_catalog.calculate_cost_usd_nanos(
            rule,
            definition.reservation_billing_facts,
        )
        return await self._repository.reserve_or_replay(
            tenant_id=tenant_id,
            account_id=account_id,
            logical_operation=definition.logical_operation,
            attempt_fingerprint=attempt_fingerprint,
            start_new_epoch=start_new_epoch,
            regeneration_epoch_ref=regeneration_epoch_ref,
            provider=definition.provider,
            canonical_model=definition.canonical_model,
            provider_billing_region=definition.provider_billing_region,
            catalog_operation=definition.catalog_operation,
            media_type=definition.media_type,
            billing_fact_kind=definition.billing_fact_kind,
            price_rule_id=rule.price_rule_id,
            price_catalog_version=rule.catalog_version,
            price_rule_version=rule.rule_version,
            reservation_billing_facts=definition.reservation_billing_facts,
            reserved_usd_nanos=reserved_usd_nanos,
            reservation_expires_at=now + timedelta(seconds=definition.reservation_ttl_seconds),
        )

    async def mark_submission_started(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, dict[str, Any]]:
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state="reserved",
            new_state="submission_started",
        )

    async def mark_submitted(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        external_task_id: str,
        provider_trace_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(external_task_id, str) or _SAFE_ID_RE.fullmatch(external_task_id) is None:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "submitted attempt requires a bounded external task ID",
            )
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state="submission_started",
            new_state="submitted",
            external_task_id=external_task_id,
            provider_trace_id=provider_trace_id,
        )

    async def settle(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_state: AttemptState,
        settlement_billing_facts: object,
        provider_reported_cost_usd_nanos: int | None = None,
        provider_reported_credit_micro_units: int | None = None,
        provider_reported_currency: str | None = None,
        external_task_id: str | None = None,
        provider_trace_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        self._require_settle_source_state(expected_state)
        attempt = await self._require_attempt(tenant_id, attempt_id)
        try:
            facts = parse_billing_facts(settlement_billing_facts)
            rule = self._require_frozen_rule(attempt)
            actual_usd_nanos = self._price_catalog.calculate_cost_usd_nanos(rule, facts)
        except (TypeError, ValueError, ValidationError, ProviderCostContractError):
            return await self.mark_accounting_error(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                expected_state=expected_state,
                provider_reported_cost_usd_nanos=provider_reported_cost_usd_nanos,
                provider_reported_credit_micro_units=(provider_reported_credit_micro_units),
                provider_reported_currency=provider_reported_currency,
                external_task_id=external_task_id,
                provider_trace_id=provider_trace_id,
            )

        if actual_usd_nanos > attempt["reserved_usd_nanos"]:
            return await self.mark_accounting_error(
                tenant_id=tenant_id,
                attempt_id=attempt_id,
                expected_state=expected_state,
                settlement_billing_facts=facts,
                provider_reported_cost_usd_nanos=provider_reported_cost_usd_nanos,
                provider_reported_credit_micro_units=(provider_reported_credit_micro_units),
                provider_reported_currency=provider_reported_currency,
                external_task_id=external_task_id,
                provider_trace_id=provider_trace_id,
            )
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state=expected_state,
            new_state="settled",
            settlement_billing_facts=facts,
            settled_usd_nanos=actual_usd_nanos,
            provider_reported_cost_usd_nanos=provider_reported_cost_usd_nanos,
            provider_reported_credit_micro_units=provider_reported_credit_micro_units,
            provider_reported_currency=provider_reported_currency,
            external_task_id=external_task_id,
            provider_trace_id=provider_trace_id,
        )

    async def release(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_state: AttemptState,
        external_task_id: str | None = None,
        provider_trace_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state=expected_state,
            new_state="released",
            external_task_id=external_task_id,
            provider_trace_id=provider_trace_id,
        )

    async def mark_ambiguous(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_state: AttemptState,
        external_task_id: str | None = None,
        provider_trace_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state=expected_state,
            new_state="ambiguous",
            external_task_id=external_task_id,
            provider_trace_id=provider_trace_id,
            safe_error_code="provider_cost_outcome_ambiguous",
        )

    async def mark_accounting_error(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
        expected_state: AttemptState,
        settlement_billing_facts: object | None = None,
        provider_reported_cost_usd_nanos: int | None = None,
        provider_reported_credit_micro_units: int | None = None,
        provider_reported_currency: str | None = None,
        external_task_id: str | None = None,
        provider_trace_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state=expected_state,
            new_state="accounting_error",
            settlement_billing_facts=settlement_billing_facts,
            settled_usd_nanos=0,
            provider_reported_cost_usd_nanos=provider_reported_cost_usd_nanos,
            provider_reported_credit_micro_units=provider_reported_credit_micro_units,
            provider_reported_currency=provider_reported_currency,
            external_task_id=external_task_id,
            provider_trace_id=provider_trace_id,
            safe_error_code="provider_cost_accounting_error",
        )

    async def release_expired_reserved(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, dict[str, Any]]:
        attempt = await self._require_attempt(tenant_id, attempt_id)
        account = await self._require_account(tenant_id, attempt["account_id"])
        if attempt["state"] != "reserved":
            return {"account": account, "attempt": attempt}
        expires_at = attempt["reservation_expires_at"]
        if self._now() < expires_at:
            return {"account": account, "attempt": attempt}
        return await self._repository.transition_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
            expected_state="reserved",
            new_state="released",
        )

    async def get_account(
        self,
        *,
        tenant_id: str,
        account_id: str,
    ) -> dict[str, Any] | None:
        return await self._repository.get_account(
            tenant_id=tenant_id,
            account_id=account_id,
        )

    async def get_attempt(
        self,
        *,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, Any] | None:
        return await self._repository.get_attempt(
            tenant_id=tenant_id,
            attempt_id=attempt_id,
        )

    def _now(self) -> datetime:
        instant = self._clock()
        if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "provider cost clock must return a timezone-aware timestamp",
            )
        return instant.astimezone(UTC)

    def _require_operation(self, operation_key: object) -> ProviderCostOperationDefinition:
        if not isinstance(operation_key, str):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider operation key is invalid",
            )
        definition = self._operation_registry.get(operation_key)
        if definition is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider operation is not registered",
            )
        return definition

    def _require_frozen_rule(self, attempt: Mapping[str, Any]) -> PriceRule:
        for rule in self._price_catalog.rules:
            if (
                rule.price_rule_id == attempt["price_rule_id"]
                and rule.catalog_version == attempt["price_catalog_version"]
                and rule.rule_version == attempt["price_rule_version"]
            ):
                expected = (
                    rule.provider,
                    rule.canonical_model,
                    rule.provider_billing_region,
                    rule.catalog_operation,
                    rule.media_type,
                    rule.billing_fact_kind,
                )
                stored = (
                    attempt["provider"],
                    attempt["canonical_model"],
                    attempt["provider_billing_region"],
                    attempt["catalog_operation"],
                    attempt["media_type"],
                    attempt["billing_fact_kind"],
                )
                if expected != stored:
                    break
                return rule
        raise ProviderCostContractError(
            "provider_cost_accounting_error",
            "frozen provider price rule is unavailable",
        )

    async def _require_account(
        self,
        tenant_id: str,
        account_id: str,
    ) -> dict[str, Any]:
        account = await self.get_account(tenant_id=tenant_id, account_id=account_id)
        if account is None:
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "provider cost account was not found",
            )
        return account

    async def _require_attempt(
        self,
        tenant_id: str,
        attempt_id: str,
    ) -> dict[str, Any]:
        attempt = await self.get_attempt(tenant_id=tenant_id, attempt_id=attempt_id)
        if attempt is None:
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "provider cost attempt was not found",
            )
        return attempt

    @staticmethod
    def _require_positive_money(value: object, name: str) -> None:
        if type(value) is not int or value <= 0 or value > MAX_SIGNED_BIGINT:
            raise _invalid_authorization(f"{name} must be positive integer USD nanos")

    @staticmethod
    def _require_settle_source_state(state: object) -> None:
        if state not in {"submission_started", "submitted"}:
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "settlement source state is invalid",
            )


def build_provider_cost_service(
    *,
    operation_registry: Mapping[str, ProviderCostOperationDefinition],
    repository: ProviderCostRepository | None = None,
    price_catalog: ProviderPriceCatalog | None = None,
    clock: Callable[[], datetime] | None = None,
    require_postgres: bool | None = None,
) -> ProviderCostService:
    """Build the service from explicit injectable authority boundaries."""

    return ProviderCostService(
        repository=repository or ProviderCostRepository(require_postgres=require_postgres),
        price_catalog=price_catalog or ProviderPriceCatalog.load_default(),
        operation_registry=operation_registry,
        clock=clock,
    )
