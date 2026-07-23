"""Server-owned private-file loader for optional W5 Fast runtime enforcement."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from src.pipeline.w5_acceptance_harness import (
    W5ScenarioPlanDraftV1,
    validate_w5_plan_draft_json,
)
from src.pipeline.w5_fast_activation import (
    W5FastActivationRecordV1,
    read_w5_private_json,
    validate_w5_fast_activation_json,
    validate_w5_fast_activation_replay_json,
)
from src.pipeline.w5_fast_runtime import (
    W5FastRuntimeBindingV1,
    derive_w5_fast_plan_budget_authorization,
    validate_w5_fast_runtime_binding_json,
)
from src.services.provider_cost import ValidatedPlanBudgetAuthorization
from src.services.submission_idempotency import hash_idempotency_key

W5_FAST_PLAN_PATH_ENV = "W5_FAST_PLAN_PATH"
W5_FAST_ACTIVATION_PATH_ENV = "W5_FAST_ACTIVATION_PATH"
W5_FAST_RUNTIME_BINDING_PATH_ENV = "W5_FAST_RUNTIME_BINDING_PATH"
_PATH_KEYS = (
    W5_FAST_PLAN_PATH_ENV,
    W5_FAST_ACTIVATION_PATH_ENV,
    W5_FAST_RUNTIME_BINDING_PATH_ENV,
)


class W5FastRuntimeLoadError(ValueError):
    """Stable secret-free W5 runtime configuration failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ResolvedW5FastRuntimeAuthority:
    plan: W5ScenarioPlanDraftV1
    activation: W5FastActivationRecordV1
    binding: W5FastRuntimeBindingV1
    budget_authorization: ValidatedPlanBudgetAuthorization | None


def configured_w5_fast_runtime_paths(
    environment: Mapping[str, str] | None = None,
) -> tuple[Path, Path, Path] | None:
    source = os.environ if environment is None else environment
    values = tuple(str(source.get(key) or "").strip() for key in _PATH_KEYS)
    if not any(values):
        return None
    if not all(values):
        raise W5FastRuntimeLoadError("w5_fast_binding_unavailable")
    return Path(values[0]), Path(values[1]), Path(values[2])


def load_w5_fast_runtime_authority(
    *,
    paths: tuple[Path, Path, Path],
    validated_request: object,
    effective_policy: object,
    raw_idempotency_key: str,
    now: datetime | None = None,
    require_active: bool = True,
) -> ResolvedW5FastRuntimeAuthority:
    """Load exact private authority; never creates or consumes durable state."""

    instant = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        plan_path, activation_path, binding_path = paths
        plan_raw = read_w5_private_json(plan_path, name="W5 plan")
        activation_raw = read_w5_private_json(
            activation_path,
            name="W5 activation",
        )
        binding_raw = read_w5_private_json(
            binding_path,
            name="W5 runtime binding",
        )
        plan = validate_w5_plan_draft_json(plan_raw)
        if require_active:
            activation = validate_w5_fast_activation_json(
                activation_raw,
                plan=plan,
                now=instant,
            )
        else:
            activation = validate_w5_fast_activation_replay_json(
                activation_raw,
                plan=plan,
                now=instant,
            )
        binding = validate_w5_fast_runtime_binding_json(
            binding_raw,
            plan=plan,
            activation=activation,
            validated_request=validated_request,
            effective_policy=effective_policy,
            idempotency_key_sha256=hash_idempotency_key(raw_idempotency_key),
            now=instant,
            require_active=require_active,
        )
        budget_authorization = (
            derive_w5_fast_plan_budget_authorization(
                plan=plan,
                activation=activation,
                now=instant,
            )
            if require_active
            else None
        )
        return ResolvedW5FastRuntimeAuthority(
            plan=plan,
            activation=activation,
            binding=binding,
            budget_authorization=budget_authorization,
        )
    except W5FastRuntimeLoadError:
        raise
    except (OSError, TypeError, ValueError, ValidationError) as exc:
        detail = str(exc).lower()
        if require_active and (
            "expired" in detail
            or "not active" in detail
            or "future" in detail
        ):
            code = "w5_fast_activation_expired"
        elif "mismatch" in detail:
            code = "w5_fast_binding_mismatch"
        else:
            code = "w5_fast_binding_invalid"
        raise W5FastRuntimeLoadError(code) from None


__all__ = [
    "ResolvedW5FastRuntimeAuthority",
    "W5FastRuntimeLoadError",
    "configured_w5_fast_runtime_paths",
    "load_w5_fast_runtime_authority",
]
