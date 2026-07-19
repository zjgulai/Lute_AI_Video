"""Immutable server-owned execution authority for provider-capable work."""

from __future__ import annotations

import contextvars
import os
import re
import uuid
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.models.provider_cost import (
    MAX_SIGNED_BIGINT,
    BudgetJobKind,
    BudgetSourceKind,
    CatalogOperation,
    ProviderCostAccountIdentity,
    ProviderCostContractError,
    parse_provider_job_budget_usd_to_nanos,
)
from src.services.provider_cost import (
    TrustedRegenerationEpoch,
    ValidatedProviderBudgetAuthorization,
    initialize_provider_cost_account,
)
from src.storage.provider_cost_repository import ProviderCostRepository

PROVIDER_EXECUTION_CONTEXT_VERSION = "provider-execution.v1"
PROVIDER_EXECUTION_CONFIG_KEY = "provider_execution_context"
PROVIDER_BUDGET_POLICY_VERSION = "provider-budget.v1"
PROVIDER_OPERATION_SCOPE_VERSION = "provider-operation-scope.v1"

SafeIdentifier = Annotated[
    str,
    Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$",
    ),
]
PositiveMoney = Annotated[int, Field(strict=True, ge=1, le=MAX_SIGNED_BIGINT)]
ZeroMutationRetry = Annotated[int, Field(strict=True, ge=0, le=0)]
OperationSlot = Annotated[
    str,
    Field(
        min_length=1,
        max_length=96,
        pattern=r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*|\.[0-9]{1,3}){0,7}$",
    ),
]
GenerationScenario = Literal["fast", "s1", "s2", "s3", "s4", "s5"]


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProviderExecutionContext(_StrictFrozenModel):
    """Full in-process authority reconstructed from private durable truth."""

    version: Literal["provider-execution.v1"] = PROVIDER_EXECUTION_CONTEXT_VERSION
    tenant_id: SafeIdentifier
    budget_job_kind: BudgetJobKind
    budget_job_id: SafeIdentifier
    account_id: SafeIdentifier
    scenario_or_resource_type: SafeIdentifier
    effective_cap_usd_nanos: PositiveMoney
    budget_source_kind: BudgetSourceKind
    trusted_authorization_ref: SafeIdentifier | None = None
    budget_policy_version: SafeIdentifier
    generation_policy_version: SafeIdentifier
    provider_max_retries: ZeroMutationRetry = 0
    regeneration_epoch: TrustedRegenerationEpoch | None = None


class PersistedProviderExecutionProjection(_StrictFrozenModel):
    """Minimal JSON-safe reference persisted with pipeline state."""

    version: Literal["provider-execution.v1"]
    budget_job_kind: BudgetJobKind
    budget_job_id: SafeIdentifier
    scenario_or_resource_type: SafeIdentifier
    budget_policy_version: SafeIdentifier
    trusted_authorization_ref: SafeIdentifier | None = None
    generation_policy_version: SafeIdentifier
    provider_max_retries: ZeroMutationRetry = 0
    regeneration_epoch: TrustedRegenerationEpoch | None = None


class ProviderOperationScope(_StrictFrozenModel):
    """Finite server-owned identity for one provider-capable execution path.

    The scope is deliberately separate from the public request and from the
    monetary catalog.  It supplies a stable logical-operation prefix while the
    caller can only select a bounded server-derived slot through
    :func:`build_provider_operation_instance`.
    """

    version: Literal["provider-operation-scope.v1"] = PROVIDER_OPERATION_SCOPE_VERSION
    scenario: GenerationScenario
    step: SafeIdentifier
    logical_operation_template: SafeIdentifier
    catalog_operation: CatalogOperation
    max_slots: Annotated[int, Field(strict=True, ge=1, le=256)] = 64

    @property
    def scope_id(self) -> str:
        return self.logical_operation_template


class _OperationSlotModel(_StrictFrozenModel):
    slot: OperationSlot


_TEXT_OPERATION_STEPS = frozenset(
    {
        "strategy",
        "scripts",
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
        "video_analysis",
        "character_identity",
        "remix_script",
        "video_prompts",
        "thumbnail_prompts",
        "vlog_strategy",
        "audit",
    }
)
_IMAGE_OPERATION_STEPS = frozenset({"keyframe_images", "thumbnail_images", "thumbnails"})
_VIDEO_OPERATION_STEPS = frozenset({"seedance_clips"})
_AUDIO_OPERATION_STEPS = frozenset({"tts_audio"})
_NON_PROVIDER_STEPS = frozenset({"assemble_final"})
_SLOT_PREFIXES = frozenset(
    {
        "candidate",
        "gate",
        "item",
        "lang",
        "primary",
        "prompt",
        "script",
        "segment",
        "tts",
        "variant",
        "video",
    }
)
_GATE_SLOT_RE = re.compile(r"^gate_[1-4]_[a-z][a-z0-9_]*$")
_VARIANT_SLOT_VALUES = frozenset({"standard", "creative", "conservative", "primary"})
_LANGUAGE_SLOT_RE = re.compile(r"^[a-z]{2,8}$")


def _operation_scope_error(detail: str) -> ProviderCostContractError:
    return ProviderCostContractError("provider_cost_rule_unavailable", detail)


def resolve_provider_operation_scope(
    scenario: str,
    step: str,
) -> ProviderOperationScope:
    """Resolve one exact scenario/step pair from the code-owned registry."""

    if not isinstance(scenario, str) or not isinstance(step, str):
        raise _operation_scope_error("provider operation scope identity is invalid")

    if scenario == "fast":
        fast_operations: dict[str, CatalogOperation] = {
            "generate": "text_to_video",
            "prompt_enhance": "chat_completion",
            "tts": "speech_synthesis",
        }
        catalog_operation = fast_operations.get(step)
        if catalog_operation is None:
            raise _operation_scope_error("provider operation scope is not registered")
    else:
        try:
            from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS

            if scenario not in {"s1", "s2", "s3", "s4", "s5"} or step not in SCENARIO_STEP_ORDERS[scenario]:
                raise _operation_scope_error("provider operation scope is not registered")
        except KeyError as exc:
            raise _operation_scope_error("provider operation scope is not registered") from exc

        if step in _TEXT_OPERATION_STEPS:
            catalog_operation = "chat_completion"
        elif step in _IMAGE_OPERATION_STEPS:
            catalog_operation = "image_generation"
        elif step in _VIDEO_OPERATION_STEPS:
            catalog_operation = "text_to_video"
        elif step in _AUDIO_OPERATION_STEPS:
            catalog_operation = "speech_synthesis"
        elif step in _NON_PROVIDER_STEPS:
            # A no-provider step still receives a bounded scope so a future
            # paid call cannot silently bypass the route binding.
            catalog_operation = "chat_completion"
        else:
            raise _operation_scope_error("provider operation scope is not registered")

    try:
        return ProviderOperationScope(
            scenario=cast(GenerationScenario, scenario),
            step=step,
            logical_operation_template=f"{scenario}.{step}",
            catalog_operation=catalog_operation,
        )
    except ValidationError as exc:
        raise _operation_scope_error("provider operation scope is invalid") from exc


def build_provider_operation_instance(
    scope: ProviderOperationScope,
    *,
    slot: str,
) -> str:
    """Build one bounded logical-operation instance from a server slot."""

    if not isinstance(scope, ProviderOperationScope):
        raise _operation_scope_error("provider operation scope is invalid")
    try:
        # Reuse the strict Pydantic parser so slots cannot contain paths,
        # wildcards, unbounded ordinals, or empty components.
        validated_slot = _OperationSlotModel(slot=slot).slot
    except (ValidationError, TypeError, ValueError) as exc:
        raise _operation_scope_error("provider operation slot is invalid") from exc
    parts = validated_slot.split(".")
    if parts[0] not in _SLOT_PREFIXES:
        raise _operation_scope_error("provider operation slot namespace is not registered")
    if parts[0] == "gate" and (len(parts) != 2 or _GATE_SLOT_RE.fullmatch(parts[1]) is None):
        raise _operation_scope_error("provider operation gate slot is invalid")
    if parts[0] in {"candidate", "variant"} and (
        len(parts) != 2 or parts[1] not in _VARIANT_SLOT_VALUES
    ):
        raise _operation_scope_error("provider operation variant slot is invalid")
    if parts[0] in {"item", "script", "segment"} and (
        len(parts) != 2 or not parts[1].isdigit()
    ):
        raise _operation_scope_error("provider operation ordinal slot is invalid")
    if parts[0] == "lang" and (len(parts) != 2 or re.fullmatch(r"[a-z]{2,8}", parts[1]) is None):
        raise _operation_scope_error("provider operation language slot is invalid")
    if parts[0] in {"primary", "prompt", "tts", "video"} and len(parts) != 1:
        raise _operation_scope_error("provider operation singleton slot is invalid")
    numeric_parts = [part for part in validated_slot.split(".") if part.isdigit()]
    if any(int(part) >= scope.max_slots for part in numeric_parts):
        raise _operation_scope_error("provider operation slot exceeds the server bound")
    instance = f"{scope.logical_operation_template}.{validated_slot}"
    if len(instance) > 128:
        raise _operation_scope_error("provider operation instance is too long")
    return instance


def derive_provider_operation_scope(
    scope: ProviderOperationScope,
    *,
    slot: str,
) -> ProviderOperationScope:
    """Return a child scope for a server-owned gate/item namespace."""

    instance = build_provider_operation_instance(scope, slot=slot)
    return scope.model_copy(update={"logical_operation_template": instance})


def validate_bound_operation_instance(
    scope: ProviderOperationScope,
    operation_instance: object,
) -> str:
    """Validate legacy server-owned instances when a scope is bound.

    Existing pipeline skills use a few stable prefixes (script/segment/
    seedance/language/vlog) rather than the new scope prefix.  They remain
    accepted only in those finite shapes; arbitrary client labels are rejected.
    """

    if not isinstance(scope, ProviderOperationScope) or not isinstance(operation_instance, str):
        raise _operation_scope_error("provider operation instance is invalid")
    try:
        validated = _OperationSlotModel(slot=operation_instance).slot
    except (ValidationError, TypeError, ValueError) as exc:
        raise _operation_scope_error("provider operation instance is invalid") from exc

    if validated.startswith(f"{scope.scope_id}."):
        build_provider_operation_instance(
            scope,
            slot=validated[len(scope.scope_id) + 1 :],
        )
        return validated

    parts = validated.split(".")
    prefix = parts[0]
    if prefix == "primary" and len(parts) == 1:
        return validated
    if prefix in {"script", "segment", "item"} and len(parts) == 2 and parts[1].isdigit():
        if int(parts[1]) >= scope.max_slots:
            raise _operation_scope_error("provider operation instance exceeds the server bound")
        return validated
    if prefix == "seedance_clips" and len(parts) == 3 and parts[1] in {"segment", "filler"}:
        if not parts[2].isdigit() or int(parts[2]) >= scope.max_slots:
            raise _operation_scope_error("provider operation instance exceeds the server bound")
        return validated
    if prefix == "language" and len(parts) == 2 and _LANGUAGE_SLOT_RE.fullmatch(parts[1]):
        return validated
    if prefix == "vlog" and len(parts) == 2 and parts[1] == "primary":
        return validated
    raise _operation_scope_error("provider operation instance namespace is not registered")


_provider_operation_scope_var: contextvars.ContextVar[ProviderOperationScope | None] = contextvars.ContextVar(
    "provider_operation_scope", default=None
)


def get_provider_operation_scope() -> ProviderOperationScope | None:
    return _provider_operation_scope_var.get()


def bind_provider_operation_scope(
    scope: ProviderOperationScope,
) -> contextvars.Token[ProviderOperationScope | None]:
    if not isinstance(scope, ProviderOperationScope):
        raise _operation_scope_error("provider operation scope is invalid")
    return _provider_operation_scope_var.set(scope)


def reset_provider_operation_scope(
    token: contextvars.Token[ProviderOperationScope | None],
) -> None:
    _provider_operation_scope_var.reset(token)


@asynccontextmanager
async def provider_operation_scope(
    scope: ProviderOperationScope,
) -> AsyncIterator[ProviderOperationScope]:
    """Bind and restore one server-owned operation scope."""

    token = bind_provider_operation_scope(scope)
    try:
        yield scope
    finally:
        reset_provider_operation_scope(token)


class ProviderExecutionStateWriter(Protocol):
    async def save(self, label: str, state: dict[str, Any]) -> None: ...


_provider_execution_context_var: contextvars.ContextVar[ProviderExecutionContext | None] = contextvars.ContextVar(
    "provider_execution_context", default=None
)


def _context_missing(detail: str) -> ProviderCostContractError:
    return ProviderCostContractError("provider_execution_context_missing", detail)


def get_provider_execution_context() -> ProviderExecutionContext | None:
    return _provider_execution_context_var.get()


def bind_provider_execution_context(
    context: ProviderExecutionContext,
) -> contextvars.Token[ProviderExecutionContext | None]:
    if not isinstance(context, ProviderExecutionContext):
        raise _context_missing("provider execution context is invalid")
    return _provider_execution_context_var.set(context)


def reset_provider_execution_context(
    token: contextvars.Token[ProviderExecutionContext | None],
) -> None:
    _provider_execution_context_var.reset(token)


async def provider_execution_request_scope() -> AsyncIterator[None]:
    """FastAPI yield dependency that restores the pre-request authority."""

    context_token = _provider_execution_context_var.set(None)
    operation_scope_token = _provider_operation_scope_var.set(None)
    try:
        yield None
    finally:
        _provider_operation_scope_var.reset(operation_scope_token)
        _provider_execution_context_var.reset(context_token)


def new_compatibility_job_id() -> str:
    """Return one bounded server UUID; client labels never enter this ID."""

    return f"compat_{uuid.uuid4().hex}"


def project_provider_execution_context(
    context: ProviderExecutionContext,
) -> dict[str, Any]:
    """Persist only the composite identity and safe policy references."""

    if not isinstance(context, ProviderExecutionContext):
        raise _context_missing("provider execution context is invalid")
    projection = PersistedProviderExecutionProjection(
        version=context.version,
        budget_job_kind=context.budget_job_kind,
        budget_job_id=context.budget_job_id,
        scenario_or_resource_type=context.scenario_or_resource_type,
        budget_policy_version=context.budget_policy_version,
        trusted_authorization_ref=context.trusted_authorization_ref,
        generation_policy_version=context.generation_policy_version,
        provider_max_retries=context.provider_max_retries,
        regeneration_epoch=context.regeneration_epoch,
    )
    return projection.model_dump(mode="json")


def with_trusted_regeneration_epoch(
    context: ProviderExecutionContext,
    epoch: TrustedRegenerationEpoch,
) -> ProviderExecutionContext:
    """Return a new frozen context after a caller persists code-owned epoch truth."""

    if not isinstance(context, ProviderExecutionContext) or not isinstance(epoch, TrustedRegenerationEpoch):
        raise ProviderCostContractError(
            "provider_cost_attempt_conflict",
            "trusted regeneration epoch is invalid",
        )
    return ProviderExecutionContext.model_validate(
        {
            **context.model_dump(mode="python"),
            "regeneration_epoch": epoch,
        },
        strict=True,
    )


def new_trusted_regeneration_epoch(operation_key: str) -> TrustedRegenerationEpoch:
    """Create one server-owned epoch; callers provide only a code-owned key."""

    try:
        return TrustedRegenerationEpoch(
            operation_key=operation_key,
            epoch_ref=f"regen_{uuid.uuid4().hex}",
        )
    except ValidationError as exc:
        raise ProviderCostContractError(
            "provider_cost_attempt_conflict",
            "trusted regeneration operation is invalid",
        ) from exc


class ProviderExecutionService:
    """Create and reconstruct execution authority without provider mutation."""

    def __init__(
        self,
        *,
        repository: ProviderCostRepository,
        server_cap_usd_nanos: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(repository, ProviderCostRepository):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost repository injection is invalid",
            )
        if server_cap_usd_nanos is not None and (
            type(server_cap_usd_nanos) is not int
            or server_cap_usd_nanos <= 0
            or server_cap_usd_nanos > MAX_SIGNED_BIGINT
        ):
            raise ProviderCostContractError(
                "provider_budget_configuration_invalid",
                "server job cap must be positive integer USD nanos",
            )
        if clock is not None and not callable(clock):
            raise ProviderCostContractError(
                "provider_budget_configuration_invalid",
                "provider execution clock injection is invalid",
            )
        self._repository = repository
        self._server_cap_usd_nanos = server_cap_usd_nanos
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        instant = self._clock()
        if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
            raise ProviderCostContractError(
                "provider_budget_configuration_invalid",
                "provider execution clock must return a timezone-aware timestamp",
            )
        return instant.astimezone(UTC)

    def _server_cap(self) -> int:
        if self._server_cap_usd_nanos is not None:
            return self._server_cap_usd_nanos
        return parse_provider_job_budget_usd_to_nanos(os.environ.get("PROVIDER_JOB_BUDGET_USD"))

    async def initialize_context(
        self,
        *,
        tenant_id: str,
        budget_job_kind: BudgetJobKind,
        budget_job_id: str,
        scenario_or_resource_type: str,
        generation_policy_version: str,
        authorization: ValidatedProviderBudgetAuthorization | None = None,
        regeneration_epoch: TrustedRegenerationEpoch | None = None,
    ) -> ProviderExecutionContext:
        if authorization is not None and not isinstance(authorization, ValidatedProviderBudgetAuthorization):
            raise ProviderCostContractError(
                "provider_budget_configuration_invalid",
                "budget authority must be a validated object",
            )
        if regeneration_epoch is not None and not isinstance(regeneration_epoch, TrustedRegenerationEpoch):
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "trusted regeneration epoch is invalid",
            )
        source_kind: BudgetSourceKind = "validated_authorization" if authorization is not None else "server_config"
        source_ref = authorization.authorization_ref if authorization is not None else None
        try:
            identity = ProviderCostAccountIdentity(
                tenant_id=tenant_id,
                job_kind=budget_job_kind,
                job_id=budget_job_id,
                scenario_or_resource_type=scenario_or_resource_type,
                budget_source_kind=source_kind,
                budget_source_ref=source_ref,
                budget_policy_version=PROVIDER_BUDGET_POLICY_VERSION,
            )
        except ValidationError as exc:
            raise _context_missing("provider execution identity is invalid") from exc
        account = await initialize_provider_cost_account(
            repository=self._repository,
            identity=identity,
            server_cap_usd_nanos=self._server_cap(),
            authorization=authorization,
            now=self._now(),
        )
        try:
            return ProviderExecutionContext(
                tenant_id=account["tenant_id"],
                budget_job_kind=account["job_kind"],
                budget_job_id=account["job_id"],
                account_id=account["account_id"],
                scenario_or_resource_type=account["scenario_or_resource_type"],
                effective_cap_usd_nanos=account["cap_usd_nanos"],
                budget_source_kind=account["budget_source_kind"],
                trusted_authorization_ref=account["budget_source_ref"],
                budget_policy_version=account["budget_policy_version"],
                generation_policy_version=generation_policy_version,
                provider_max_retries=0,
                regeneration_epoch=regeneration_epoch,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise _context_missing("provider execution account truth is invalid") from exc

    async def reconstruct_context(
        self,
        projection: object,
        *,
        expected_tenant_id: str,
        expected_scenario_or_resource_type: str,
        expected_generation_policy_version: str,
    ) -> ProviderExecutionContext:
        try:
            persisted = PersistedProviderExecutionProjection.model_validate(
                projection,
                strict=True,
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise _context_missing("persisted provider execution projection is invalid") from exc
        if (
            persisted.scenario_or_resource_type != expected_scenario_or_resource_type
            or persisted.generation_policy_version != expected_generation_policy_version
            or persisted.budget_policy_version != PROVIDER_BUDGET_POLICY_VERSION
        ):
            raise _context_missing("persisted provider execution authority mismatch")

        account = await self._repository.get_account_by_job_identity(
            tenant_id=expected_tenant_id,
            job_kind=persisted.budget_job_kind,
            job_id=persisted.budget_job_id,
        )
        if account is None:
            raise _context_missing("provider execution account was not found")
        if (
            account["scenario_or_resource_type"] != persisted.scenario_or_resource_type
            or account["budget_policy_version"] != persisted.budget_policy_version
            or account["budget_source_ref"] != persisted.trusted_authorization_ref
        ):
            raise _context_missing("persisted provider execution account mismatch")
        try:
            return ProviderExecutionContext(
                tenant_id=account["tenant_id"],
                budget_job_kind=account["job_kind"],
                budget_job_id=account["job_id"],
                account_id=account["account_id"],
                scenario_or_resource_type=account["scenario_or_resource_type"],
                effective_cap_usd_nanos=account["cap_usd_nanos"],
                budget_source_kind=account["budget_source_kind"],
                trusted_authorization_ref=account["budget_source_ref"],
                budget_policy_version=account["budget_policy_version"],
                generation_policy_version=persisted.generation_policy_version,
                provider_max_retries=persisted.provider_max_retries,
                regeneration_epoch=persisted.regeneration_epoch,
            )
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise _context_missing("provider execution account truth is invalid") from exc


def build_provider_execution_service(
    *,
    repository: ProviderCostRepository | None = None,
    server_cap_usd_nanos: int | None = None,
    clock: Callable[[], datetime] | None = None,
    require_postgres: bool | None = None,
) -> ProviderExecutionService:
    return ProviderExecutionService(
        repository=repository or ProviderCostRepository(require_postgres=require_postgres),
        server_cap_usd_nanos=server_cap_usd_nanos,
        clock=clock,
    )


async def initialize_and_bind_provider_execution_context(
    *,
    tenant_id: str,
    budget_job_kind: BudgetJobKind,
    budget_job_id: str,
    scenario_or_resource_type: str,
    generation_policy_version: str,
    authorization: ValidatedProviderBudgetAuthorization | None = None,
    service: ProviderExecutionService | None = None,
) -> ProviderExecutionContext:
    """Initialize durable authority, then bind it to the current request task."""

    execution_service = service or build_provider_execution_service()
    context = await execution_service.initialize_context(
        tenant_id=tenant_id,
        budget_job_kind=budget_job_kind,
        budget_job_id=budget_job_id,
        scenario_or_resource_type=scenario_or_resource_type,
        generation_policy_version=generation_policy_version,
        authorization=authorization,
    )
    bind_provider_execution_context(context)
    return context


@asynccontextmanager
async def persisted_provider_execution_scope(
    state: Mapping[str, Any],
    *,
    service: ProviderExecutionService | None = None,
) -> AsyncIterator[ProviderExecutionContext]:
    """Reconstruct and bind one state-owned context for provider-capable work."""

    config = state.get("config") if isinstance(state, Mapping) else None
    projection = config.get(PROVIDER_EXECUTION_CONFIG_KEY) if isinstance(config, Mapping) else None
    generation_policy = config.get("effective_generation_policy") if isinstance(config, Mapping) else None
    generation_policy_version = generation_policy.get("version") if isinstance(generation_policy, Mapping) else None
    tenant_id = state.get("tenant_id") if isinstance(state, Mapping) else None
    scenario = state.get("scenario") if isinstance(state, Mapping) else None
    if not isinstance(tenant_id, str) or not tenant_id:
        raise _context_missing("persisted provider execution state is incomplete")
    if not isinstance(scenario, str) or not scenario:
        raise _context_missing("persisted provider execution state is incomplete")
    if not isinstance(generation_policy_version, str) or not generation_policy_version:
        raise _context_missing("persisted provider execution state is incomplete")
    execution_service = service or build_provider_execution_service()
    context = await execution_service.reconstruct_context(
        projection,
        expected_tenant_id=tenant_id,
        expected_scenario_or_resource_type=scenario,
        expected_generation_policy_version=generation_policy_version,
    )
    token = bind_provider_execution_context(context)
    try:
        yield context
    finally:
        reset_provider_execution_context(token)


async def persist_trusted_regeneration_epoch(
    state: dict[str, Any],
    *,
    state_writer: ProviderExecutionStateWriter,
    operation_key: str,
    service: ProviderExecutionService | None = None,
) -> ProviderExecutionContext:
    """Persist a safe epoch projection before any new attempt ordinal exists."""

    label = state.get("label") if isinstance(state, dict) else None
    config = state.get("config") if isinstance(state, dict) else None
    if (
        not isinstance(label, str)
        or not label
        or not isinstance(config, dict)
        or not callable(getattr(state_writer, "save", None))
    ):
        raise _context_missing("regeneration state persistence is invalid")

    epoch = new_trusted_regeneration_epoch(operation_key)
    async with persisted_provider_execution_scope(state, service=service) as context:
        regenerated = with_trusted_regeneration_epoch(context, epoch)
        updated_state = {
            **state,
            "config": {
                **config,
                PROVIDER_EXECUTION_CONFIG_KEY: project_provider_execution_context(regenerated),
            },
        }
        await state_writer.save(label, updated_state)

    state.clear()
    state.update(updated_state)
    return regenerated
