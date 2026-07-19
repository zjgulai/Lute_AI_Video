"""Canonical request-time generation-safety policy.

This module intentionally covers only controls that exist today: media intent,
pending/quarantine disposition, zero mutation retry, authenticated tenant, and
provider-submit permission.  Durable idempotency, budget reservation/ledger,
artifact transition records, human acceptance, publish/delivery authority, and
transparency sidecars remain deferred controls and are rejected when asserted
by a client.
"""

from __future__ import annotations

import contextvars
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Annotated, Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

from src.routers._deps import AuthContext

GENERATION_POLICY_VERSION = "generation-safety.v1"
GENERATION_EXECUTION_PROFILE_VERSION = "generation-execution.v1"
GENERATION_SAFETY_FIELDS = frozenset(
    {
        "enable_media_synthesis",
        "artifact_disposition",
        "provider_max_retries",
    }
)

# These names represent authority or durable controls that are not implemented
# by this request normalizer.  Accepting and silently dropping any of them would
# let a client appear to self-authorize behavior that the server cannot enforce.
DEFERRED_GENERATION_CONTROL_KEYS = frozenset(
    {
        "tenant_id",
        "idempotency_key",
        "budget",
        "budget_limit",
        "budget_limit_usd",
        "budget_spent",
        "budget_spent_usd",
        "approved_budget_limit_usd",
        "per_spec_budget",
        "per_spec_budget_usd",
        "cost_budget",
        "budget_reservation",
        "budget_reservation_id",
        "client_budget",
        "client_spend",
        "provider_budget",
        "transparency_policy",
        "transparency_sidecar",
        "transparency_sidecars",
        "human_approval",
        "human_approved",
        "approval",
        "approval_id",
        "approval_record",
        "approval_record_ref",
        "acceptance_record",
        "accepted",
        "accepted_for_delivery",
        "publish",
        "publish_allowed",
        "publish_policy",
        "publish_requested",
        "publication_requested",
        "delivery",
        "delivery_accepted",
        "delivery_acceptance",
        "delivery_requested",
        "artifact_policy",
        "artifact_public",
        "artifact_published",
        "effective_policy",
        "effective_policy_version",
        "effective_generation_policy",
        "effective_generation_policy_version",
        "generation_safety_policy",
        "policy_version",
        "generation_policy_version",
        "provider_execution_context",
        "provider_account_id",
        "budget_job_kind",
        "budget_job_id",
        "effective_cap_usd_nanos",
        "trusted_authorization_ref",
        "regeneration_epoch",
    }
)

GenerationScenario = Literal["fast", "s1", "s2", "s3", "s4", "s5"]
ArtifactDisposition = Literal["pending_review", "quarantine"]
ZeroMutationRetry = Annotated[int, Field(strict=True, ge=0, le=0)]


class GenerationSafetyIntent(BaseModel):
    """Strict client intent with fail-closed defaults."""

    model_config = ConfigDict(extra="forbid", strict=True)

    enable_media_synthesis: StrictBool = False
    artifact_disposition: ArtifactDisposition = "pending_review"
    provider_max_retries: ZeroMutationRetry = 0


class EffectiveGenerationPolicy(BaseModel):
    """Server-owned projection derived from auth plus strict client intent."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    version: Literal["generation-safety.v1"] = GENERATION_POLICY_VERSION
    tenant_id: str
    scenario: GenerationScenario
    provider_submit_allowed: Literal[True] = True
    enable_media_synthesis: StrictBool
    artifact_disposition: ArtifactDisposition
    provider_max_retries: ZeroMutationRetry


_effective_generation_policy_var: contextvars.ContextVar[EffectiveGenerationPolicy | None] = contextvars.ContextVar(
    "effective_generation_policy", default=None
)


def get_effective_generation_policy() -> EffectiveGenerationPolicy | None:
    """Return the effective policy bound to the current request task."""

    return _effective_generation_policy_var.get()


def bind_effective_generation_policy(
    policy: EffectiveGenerationPolicy,
) -> contextvars.Token[EffectiveGenerationPolicy | None]:
    """Bind a resolved server-owned policy for downstream config builders."""

    return _effective_generation_policy_var.set(policy)


def reset_effective_generation_policy(
    token: contextvars.Token[EffectiveGenerationPolicy | None],
) -> None:
    """Restore the prior request policy after a persisted-state scope exits."""

    _effective_generation_policy_var.reset(token)


def get_effective_provider_max_retries(default: int) -> int:
    """Clamp a provider mutation retry count to the bound policy cap."""

    policy = get_effective_generation_policy()
    if policy is None:
        return max(0, int(default))
    return min(max(0, int(default)), policy.provider_max_retries)


@dataclass(frozen=True)
class GenerationExecutionProfile:
    """Exact server-owned step allowlist for one bounded execution shape."""

    version: str
    profile_id: str
    scenario: str
    allowed_steps: tuple[str, ...]
    provider_job_caps: Mapping[str, int]
    completion_kind: Literal["no_media", "bounded_media"]
    refs_only: bool = False

    def model_dump(self) -> dict[str, Any]:
        """Return a JSON-safe immutable-profile projection for persistence."""

        return {
            "version": self.version,
            "profile_id": self.profile_id,
            "scenario": self.scenario,
            "allowed_steps": list(self.allowed_steps),
            "provider_job_caps": dict(self.provider_job_caps),
            "completion_kind": self.completion_kind,
            "refs_only": self.refs_only,
        }


NO_MEDIA_STEP_PROFILES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "s1": (
            "strategy",
            "scripts",
            "compliance",
            "storyboards",
            "continuity_storyboard_grid",
        ),
        "s2": (
            "strategy",
            "scripts",
            "compliance",
            "storyboards",
            "continuity_storyboard_grid",
        ),
        "s3": (
            "video_analysis",
            "character_identity",
            "remix_script",
            "storyboards",
            "continuity_storyboard_grid",
        ),
        "s4": ("scripts", "continuity_storyboard_grid"),
        "s5": ("vlog_strategy", "continuity_storyboard_grid"),
    }
)

BOUNDED_MEDIA_STEP_PROFILES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "s1": (
            "strategy",
            "scripts",
            "storyboards",
            "continuity_storyboard_grid",
            "keyframe_images",
            "video_prompts",
            "seedance_clips",
        ),
        "s3": (
            "video_analysis",
            "character_identity",
            "remix_script",
            "storyboards",
            "continuity_storyboard_grid",
            "keyframe_images",
            "video_prompts",
            "seedance_clips",
        ),
        "s4": (
            "scripts",
            "continuity_storyboard_grid",
            "video_prompts",
            "seedance_clips",
        ),
        "s5": (
            "vlog_strategy",
            "continuity_storyboard_grid",
            "video_prompts",
            "seedance_clips",
        ),
    }
)

S2_SEGMENTED_MEDIA_STEP_PROFILES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "seedance_clips": (
            "strategy",
            "scripts",
            "compliance",
            "storyboards",
            "continuity_storyboard_grid",
            "keyframe_images",
            "video_prompts",
            "seedance_clips",
        ),
        "tts_audio": ("strategy", "scripts", "tts_audio"),
        "thumbnail_prompts": ("strategy", "scripts", "thumbnail_prompts"),
        "thumbnail_images": (
            "strategy",
            "scripts",
            "thumbnail_prompts",
            "thumbnail_images",
        ),
        "assemble_final": ("assemble_final",),
        "audit": ("audit",),
    }
)

S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS: Mapping[str, Mapping[str, int]] = MappingProxyType(
    {
        "seedance_clips": MappingProxyType({"image": 1, "video": 1}),
        "tts_audio": MappingProxyType({"tts": 1}),
        "thumbnail_prompts": MappingProxyType({}),
        "thumbnail_images": MappingProxyType({"thumbnail": 1}),
        "assemble_final": MappingProxyType({}),
        "audit": MappingProxyType({}),
    }
)

MEDIA_PROVIDER_STEPS = frozenset({"keyframe_images", "seedance_clips", "tts_audio", "thumbnail_images"})
# These steps may not call an AI provider, but they still create or overwrite
# durable artifacts.  Until an artifact-attempt ledger exists they share the
# same fail-closed force/regenerate boundary as provider submissions.
ARTIFACT_MUTATION_STEPS = frozenset({"assemble_final"})
PROVIDER_BACKED_STEPS = frozenset(
    {
        "strategy",
        "scripts",
        "video_analysis",
        "remix_script",
        "vlog_strategy",
        "keyframe_images",
        "seedance_clips",
        "tts_audio",
        "thumbnail_images",
    }
)
ATTEMPT_GUARDED_STEPS = PROVIDER_BACKED_STEPS | ARTIFACT_MUTATION_STEPS


def _policy_error(detail: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detail)


def _load_persisted_policy(state: Mapping[str, Any]) -> EffectiveGenerationPolicy:
    config = state.get("config")
    if not isinstance(config, Mapping):
        raise _policy_error("Generation state config is missing or invalid")
    raw_policy = config.get("effective_generation_policy")
    if not isinstance(raw_policy, Mapping):
        raise _policy_error("Persisted effective generation policy is missing or invalid")
    try:
        policy = EffectiveGenerationPolicy.model_validate(raw_policy)
    except ValidationError as exc:
        raise _policy_error("Persisted effective generation policy is invalid") from exc

    scenario = state.get("scenario")
    if scenario not in NO_MEDIA_STEP_PROFILES:
        raise _policy_error(f"Unsupported generation scenario: {scenario!r}")
    if policy.scenario != scenario:
        raise _policy_error("Persisted generation policy scenario mismatch")
    tenant_id = state.get("tenant_id")
    if not isinstance(tenant_id, str) or not tenant_id or policy.tenant_id != tenant_id:
        raise _policy_error("Persisted generation policy tenant mismatch")

    exact_config = {
        "enable_media_synthesis": policy.enable_media_synthesis,
        "artifact_disposition": policy.artifact_disposition,
        "provider_max_retries": policy.provider_max_retries,
    }
    for key, expected in exact_config.items():
        if key not in config or config[key] != expected or type(config[key]) is not type(expected):
            raise _policy_error(f"Persisted generation policy/config mismatch: {key}")
    return policy


def _validate_s2_refs_only_config(
    config: Mapping[str, Any],
    *,
    stop_step: str,
    disposition: str,
    tenant_id: str,
) -> None:
    if stop_step not in {"assemble_final", "audit"}:
        return
    refs = config.get("media_refs")
    if not isinstance(refs, Mapping):
        raise _policy_error(f"S2 {stop_step} requires validated refs-only media_refs")

    def paths(*keys: str) -> list[str]:
        for key in keys:
            value = refs.get(key)
            if isinstance(value, str) and value:
                return [value]
            if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
                return list(value)
        return []

    required = {
        "clip_paths": paths("clip_paths", "clips"),
        "audio_paths": paths("audio_paths", "audios"),
        "thumbnail_image_paths": paths("thumbnail_image_paths", "thumbnail_paths", "thumbnails"),
    }
    if stop_step == "audit":
        required["video_path"] = paths("video_path", "intermediate_video_path", "assemble_video_path", "video_paths")
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise _policy_error(f"S2 {stop_step} refs-only media_refs missing required keys: " + ", ".join(missing))
    for ref_name, values in required.items():
        for path in values:
            try:
                assert_review_scoped_media_ref(
                    path,
                    tenant_id=tenant_id,
                    disposition=disposition,
                )
            except ValueError as exc:
                raise _policy_error(f"S2 {stop_step} {ref_name} must be tenant-scoped {disposition}") from exc


def assert_review_scoped_media_ref(
    path: str,
    *,
    tenant_id: str,
    disposition: str,
) -> None:
    """Validate one canonical tenant review path without resolving the file."""

    normalized = path.replace("\\", "/")
    pure_path = PurePosixPath(normalized)
    parts = pure_path.parts
    if not pure_path.is_absolute() or ".." in parts or parts.count("tenants") != 1:
        raise ValueError("review-scoped media path is non-canonical")
    tenant_index = parts.index("tenants")
    if parts[tenant_index + 1 : tenant_index + 3] != (tenant_id, disposition):
        raise ValueError("review-scoped media path tenant/disposition mismatch")
    if any(segment in parts for segment in ("final_work", "renders", "fast_mode", "gpt_images")):
        raise ValueError("review-scoped media path uses a forbidden artifact root")


def _strict_provider_caps_match(
    raw_caps: Any,
    expected_caps: Mapping[str, int],
) -> bool:
    """Compare JSON caps without Python's bool-equals-int coercion."""

    if type(raw_caps) is not dict or set(raw_caps) != set(expected_caps):
        return False
    return all(
        type(key) is str and type(raw_caps[key]) is int and raw_caps[key] == expected_caps[key] for key in raw_caps
    )


def _strict_execution_profile_match(
    raw_profile: Any,
    expected_profile: Mapping[str, Any],
) -> bool:
    """Validate the persisted execution profile as a strict JSON schema."""

    if type(raw_profile) is not dict or set(raw_profile) != set(expected_profile):
        return False
    for key in ("version", "profile_id", "scenario", "completion_kind"):
        if type(raw_profile.get(key)) is not str or raw_profile[key] != expected_profile[key]:
            return False
    allowed_steps = raw_profile.get("allowed_steps")
    if (
        type(allowed_steps) is not list
        or any(type(step) is not str for step in allowed_steps)
        or allowed_steps != expected_profile["allowed_steps"]
    ):
        return False
    if type(raw_profile.get("refs_only")) is not bool:
        return False
    if raw_profile["refs_only"] is not expected_profile["refs_only"]:
        return False
    return _strict_provider_caps_match(
        raw_profile.get("provider_job_caps"),
        expected_profile["provider_job_caps"],
    )


def resolve_generation_execution_profile(
    state: Mapping[str, Any],
    *,
    require_persisted_profile: bool = True,
) -> GenerationExecutionProfile:
    """Validate persisted authority and return its exact execution allowlist."""

    policy = _load_persisted_policy(state)
    scenario = policy.scenario
    config = state["config"]
    assert isinstance(config, Mapping)

    if not policy.enable_media_synthesis:
        profile = GenerationExecutionProfile(
            version=GENERATION_EXECUTION_PROFILE_VERSION,
            profile_id=f"{GENERATION_EXECUTION_PROFILE_VERSION}:{scenario}:no-media",
            scenario=scenario,
            allowed_steps=NO_MEDIA_STEP_PROFILES[scenario],
            provider_job_caps=MappingProxyType({}),
            completion_kind="no_media",
        )
    elif scenario == "s2":
        stop_step = config.get("media_stop_step") or "seedance_clips"
        if not isinstance(stop_step, str) or stop_step not in S2_SEGMENTED_MEDIA_STEP_PROFILES:
            raise _policy_error(f"Unsupported S2 media_stop_step: {stop_step!r}")
        _validate_s2_refs_only_config(
            config,
            stop_step=stop_step,
            disposition=policy.artifact_disposition,
            tenant_id=policy.tenant_id,
        )
        profile = GenerationExecutionProfile(
            version=GENERATION_EXECUTION_PROFILE_VERSION,
            profile_id=f"{GENERATION_EXECUTION_PROFILE_VERSION}:s2:{stop_step}",
            scenario="s2",
            allowed_steps=S2_SEGMENTED_MEDIA_STEP_PROFILES[stop_step],
            provider_job_caps=S2_SEGMENTED_MEDIA_PROVIDER_JOB_CAPS[stop_step],
            completion_kind="bounded_media",
            refs_only=stop_step in {"assemble_final", "audit"},
        )
    else:
        profile = GenerationExecutionProfile(
            version=GENERATION_EXECUTION_PROFILE_VERSION,
            profile_id=f"{GENERATION_EXECUTION_PROFILE_VERSION}:{scenario}:bounded-seedance",
            scenario=scenario,
            allowed_steps=BOUNDED_MEDIA_STEP_PROFILES[scenario],
            provider_job_caps=MappingProxyType({"image": 1, "video": 1}),
            completion_kind="bounded_media",
        )

    expected_profile = profile.model_dump()
    persisted_profile = config.get("effective_generation_execution_profile")
    if require_persisted_profile and type(persisted_profile) is not dict:
        raise _policy_error("Persisted generation execution profile is missing")
    if persisted_profile is not None and not _strict_execution_profile_match(
        persisted_profile,
        expected_profile,
    ):
        raise _policy_error("Persisted generation execution profile is invalid or tampered")
    persisted_caps = config.get("provider_job_caps")
    if require_persisted_profile and type(persisted_caps) is not dict:
        raise _policy_error("Persisted provider job caps are missing")
    if persisted_caps is not None and not _strict_provider_caps_match(
        persisted_caps,
        profile.provider_job_caps,
    ):
        raise _policy_error("Persisted provider job caps are invalid or tampered")
    return profile


def assert_generation_step_allowed(
    state: Mapping[str, Any],
    step_name: str,
    *,
    force: bool = False,
) -> GenerationExecutionProfile:
    """Fail before construction whenever a step exceeds persisted authority."""

    profile = resolve_generation_execution_profile(state)
    if step_name not in profile.allowed_steps:
        raise _policy_error(f"Step {step_name!r} is outside execution profile {profile.profile_id}")
    steps = state.get("steps")
    step_data = steps.get(step_name, {}) if isinstance(steps, Mapping) else {}
    if force and step_name in ARTIFACT_MUTATION_STEPS:
        raise _policy_error("Artifact-producing step force-regeneration requires a durable attempt ledger")
    if force and step_name in MEDIA_PROVIDER_STEPS:
        raise _policy_error("Media force-regenerate requires a durable provider attempt ledger")
    if force and step_name in PROVIDER_BACKED_STEPS and isinstance(step_data, Mapping):
        status = step_data.get("status", "pending")
        if status in {"done", "error"} or bool(step_data.get("started_at")):
            raise _policy_error(
                "Provider-backed step already consumed an attempt; "
                "durable attempt ledger required before force-regeneration"
            )
    if not force and step_name in ATTEMPT_GUARDED_STEPS and isinstance(step_data, Mapping):
        status = step_data.get("status", "pending")
        if status != "done" and (status != "pending" or bool(step_data.get("started_at"))):
            raise _policy_error("Attempt-guarded step already started or failed; durable ledger required")
    return profile


def project_bounded_generation_result(
    result: Mapping[str, Any],
    *,
    policy: EffectiveGenerationPolicy,
    execution_completed: bool,
) -> dict[str, Any]:
    """Project an HTTP result without upgrading a bounded run to full success."""

    projected = dict(result)
    projected.update(
        {
            "status": "completed_bounded" if execution_completed else "error",
            "lifecycle_status": ("completed_bounded" if execution_completed else "error"),
            "completion_kind": (
                ("bounded_media" if policy.enable_media_synthesis else "no_media")
                if execution_completed
                else "execution_failed"
            ),
            "request_succeeded": execution_completed,
            "success": False,
            "full_media_success": False,
            "pipeline_complete": False,
            "publish_allowed": False,
            "delivery_accepted": False,
            "current_step": None if execution_completed else result.get("current_step"),
        }
    )
    return projected


@contextmanager
def persisted_generation_policy_scope(state: Mapping[str, Any]):
    """Bind validated persisted authority for one provider-capable call tree."""

    policy = _load_persisted_policy(state)
    token = bind_effective_generation_policy(policy)
    try:
        yield policy
    finally:
        reset_effective_generation_policy(token)


def _as_request_mapping(body: Mapping[str, Any] | BaseModel) -> Mapping[str, Any]:
    if isinstance(body, BaseModel):
        return body.model_dump(mode="python")
    if isinstance(body, Mapping):
        return body
    raise HTTPException(status_code=422, detail="Generation request body must be an object")


def validate_generation_request_shape(value: Any) -> Any:
    """Pydantic ``mode=before`` guard for server-owned/deferred fields."""

    if not isinstance(value, Mapping):
        return value
    forbidden = sorted(DEFERRED_GENERATION_CONTROL_KEYS.intersection(value))
    if forbidden:
        raise ValueError("Client-supplied generation authority is not supported: " + ", ".join(forbidden))
    return value


def resolve_generation_policy(
    body: Mapping[str, Any] | BaseModel,
    *,
    auth: AuthContext,
    scenario: GenerationScenario,
) -> EffectiveGenerationPolicy:
    """Resolve strict request intent against authenticated server authority."""

    request_data = _as_request_mapping(body)
    forbidden = sorted(DEFERRED_GENERATION_CONTROL_KEYS.intersection(request_data))
    if forbidden:
        raise HTTPException(
            status_code=422,
            detail=("Client-supplied generation authority is not supported: " + ", ".join(forbidden)),
        )

    intent_data = {key: request_data[key] for key in GENERATION_SAFETY_FIELDS if key in request_data}
    try:
        intent = GenerationSafetyIntent.model_validate(intent_data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    if not auth.has_permission("provider:submit"):
        raise HTTPException(status_code=403, detail="Insufficient provider submit permission")

    return EffectiveGenerationPolicy(
        tenant_id=auth.tenant_id,
        scenario=scenario,
        enable_media_synthesis=intent.enable_media_synthesis,
        artifact_disposition=intent.artifact_disposition,
        provider_max_retries=intent.provider_max_retries,
    )
