"""Test-only helpers for constructing explicitly authorized execution state."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from src.pipeline.generation_policy import (
    EffectiveGenerationPolicy,
    bind_effective_generation_policy,
    reset_effective_generation_policy,
    resolve_generation_execution_profile,
)
from src.routers import _deps
from src.services.provider_execution import (
    ProviderExecutionContext,
    bind_provider_execution_context,
    build_provider_execution_service,
    new_compatibility_job_id,
    project_provider_execution_context,
    reset_provider_execution_context,
)


def attach_execution_policy(
    state: dict[str, Any],
    *,
    scenario: str | None = None,
    media: bool = False,
    tenant_id: str | None = None,
    media_stop_step: str | None = None,
    media_refs: dict[str, Any] | None = None,
    execution_context: ProviderExecutionContext | None = None,
) -> dict[str, Any]:
    """Attach the exact immutable policy/profile required by runtime guards."""

    resolved_scenario = scenario or state.get("scenario", "s1")
    resolved_tenant = tenant_id or state.get("tenant_id") or "default"
    state["scenario"] = resolved_scenario
    state["tenant_id"] = resolved_tenant
    config = dict(state.get("config") or {})
    policy = EffectiveGenerationPolicy(
        tenant_id=resolved_tenant,
        scenario=resolved_scenario,
        enable_media_synthesis=media,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )
    config.update(
        {
            "enable_media_synthesis": media,
            "artifact_disposition": "pending_review",
            "provider_max_retries": 0,
            "effective_generation_policy": policy.model_dump(mode="json"),
        }
    )
    if media_stop_step is not None:
        config["media_stop_step"] = media_stop_step
    if media_refs is not None:
        config["media_refs"] = media_refs
    if execution_context is not None:
        if (
            execution_context.tenant_id != resolved_tenant
            or execution_context.scenario_or_resource_type != resolved_scenario
            or execution_context.generation_policy_version != policy.version
        ):
            raise ValueError("test provider execution context conflicts with policy")
        config["provider_execution_context"] = project_provider_execution_context(execution_context)
    state["config"] = config
    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    config["effective_generation_execution_profile"] = profile.model_dump()
    config["provider_job_caps"] = dict(profile.provider_job_caps)
    return state


async def attach_test_provider_execution_authority(
    state: dict[str, Any],
) -> ProviderExecutionContext:
    """Create one disposable private account and attach only its safe projection."""

    scenario = state.get("scenario", "s1")
    tenant_id = state.get("tenant_id") or "default"
    policy = state.get("config", {}).get("effective_generation_policy", {})
    version = policy.get("version")
    context = await build_provider_execution_service(
        require_postgres=False,
    ).initialize_context(
        tenant_id=tenant_id,
        budget_job_kind="compatibility",
        budget_job_id=new_compatibility_job_id(),
        scenario_or_resource_type=scenario,
        generation_policy_version=version,
    )
    state["config"]["provider_execution_context"] = project_provider_execution_context(context)
    return context


@asynccontextmanager
async def bound_generation_policy(
    scenario: str,
    *,
    media: bool = False,
    tenant_id: str = "default",
) -> AsyncIterator[EffectiveGenerationPolicy]:
    """Bind matching auth and policy context around a real StepRunner init."""

    policy = EffectiveGenerationPolicy(
        tenant_id=tenant_id,
        scenario=scenario,
        enable_media_synthesis=media,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )
    auth_token = _deps._auth_context_var.set(
        _deps.AuthContext(
            tenant_id=tenant_id,
            permissions=frozenset({"provider:submit"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id=f"{scenario}-test-key",
        )
    )
    policy_token = bind_effective_generation_policy(policy)
    execution_context = await build_provider_execution_service(
        require_postgres=False,
    ).initialize_context(
        tenant_id=tenant_id,
        budget_job_kind="compatibility",
        budget_job_id=new_compatibility_job_id(),
        scenario_or_resource_type=scenario,
        generation_policy_version=policy.version,
    )
    execution_token = bind_provider_execution_context(execution_context)
    try:
        yield policy
    finally:
        reset_provider_execution_context(execution_token)
        reset_effective_generation_policy(policy_token)
        _deps._auth_context_var.reset(auth_token)
