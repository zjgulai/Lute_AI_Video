from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError


def _times() -> tuple[datetime, datetime]:
    created_at = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
    return created_at, created_at + timedelta(hours=1)


def _plan(*, with_tts: bool = False) -> Any:
    from src.pipeline.w5_acceptance_harness import build_w5_plan_draft

    created_at, _ = _times()
    caps = {"llm": 1, "video": 1}
    if with_tts:
        caps["tts"] = 1
    return build_w5_plan_draft(
        scenario="fast",
        tenant_id="tenant-alpha",
        sample_ref="sample:fast:001",
        budget_limit_usd_nanos=3_150_000_000,
        provider_job_caps=caps,
        selected_optional_media=("tts_audio",) if with_tts else (),
        created_at=created_at,
        expires_at=created_at + timedelta(hours=2),
    )


def _activation(plan: Any) -> Any:
    from src.pipeline.w5_fast_activation import (
        W5_FAST_AUTHORIZATION_STATEMENT,
        validate_w5_fast_activation_json,
    )

    created_at, now = _times()
    payload = {
        "version": "w5-fast-activation.v1",
        "scope": "w5-fast-activation",
        "activation_id": "w5fastact:fixture-001",
        "plan_id": plan.plan_id,
        "tenant_id": plan.tenant_id,
        "scenario": "fast",
        "sample_ref": plan.sample_ref,
        "approved_by": "reviewer:ll",
        "approved_at": (created_at + timedelta(minutes=30)).isoformat(),
        "expires_at": (created_at + timedelta(hours=1, minutes=30)).isoformat(),
        "authorization_statement": W5_FAST_AUTHORIZATION_STATEMENT,
        "template_only": False,
        "budget_limit_usd_nanos": plan.budget_limit_usd_nanos,
        "selected_optional_media": list(plan.selected_optional_media),
        "provider_job_caps": dict(plan.provider_job_caps),
        "submission_cap": 1,
        "automatic_retry_cap": 0,
        "provider_max_retries": 0,
        "artifact_disposition": "pending_review",
        "provider_mutation_approved": True,
        "runtime_binding_required": True,
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    return validate_w5_fast_activation_json(
        json.dumps(payload),
        plan=plan,
        now=now,
    )


def _request(*, with_tts: bool = False, duration: int = 15) -> Any:
    from src.routers._state import FastModeRequest

    return FastModeRequest(
        user_prompt="Create a claim-safe Momcozy sterilizer product video.",
        duration=duration,
        enable_tts=with_tts,
        api_keys={},
        enable_media_synthesis=True,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )


def _policy() -> Any:
    from src.pipeline.generation_policy import EffectiveGenerationPolicy

    return EffectiveGenerationPolicy(
        tenant_id="tenant-alpha",
        scenario="fast",
        enable_media_synthesis=True,
        artifact_disposition="pending_review",
        provider_max_retries=0,
        c2pa_signing_mode="required",
    )


def test_build_runtime_binding_binds_hashes_without_prompt_or_raw_key() -> None:
    from src.pipeline.w5_fast_runtime import build_w5_fast_runtime_binding

    plan = _plan()
    activation = _activation(plan)
    binding = build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=_request(),
        effective_policy=_policy(),
        idempotency_key_sha256="a" * 64,
        now=_times()[1],
    )

    payload = binding.model_dump(mode="json")
    encoded = json.dumps(payload)
    assert binding.plan_id == plan.plan_id
    assert binding.activation_id == activation.activation_id
    assert binding.duration_seconds == 15
    assert binding.provider_job_caps == (("llm", 1), ("video", 1))
    assert binding.expected_llm_model == "deepseek-v4-flash"
    assert binding.expected_video_model == "seedance-2"
    assert binding.expected_video_resolution == "720p"
    assert binding.request_hash
    assert "Create a claim-safe" not in encoded
    assert "Idempotency-Key" not in encoded


@pytest.mark.parametrize(
    ("with_tts", "caps_with_tts"),
    ((False, True), (True, False)),
)
def test_runtime_binding_rejects_tts_plan_request_cap_drift(
    with_tts: bool,
    caps_with_tts: bool,
) -> None:
    from src.pipeline.w5_fast_runtime import build_w5_fast_runtime_binding

    plan = _plan(with_tts=caps_with_tts)
    activation = _activation(plan)
    with pytest.raises(ValueError, match="TTS"):
        build_w5_fast_runtime_binding(
            plan=plan,
            activation=activation,
            validated_request=_request(with_tts=with_tts),
            effective_policy=_policy(),
            idempotency_key_sha256="a" * 64,
            now=_times()[1],
        )


@pytest.mark.parametrize(
    ("request_changes", "policy_changes", "message"),
    (
        ({"enable_media_synthesis": False}, {}, "media"),
        ({"artifact_disposition": "quarantine"}, {}, "disposition"),
        ({}, {"tenant_id": "tenant-other"}, "tenant"),
        ({}, {"scenario": "s1"}, "scenario"),
        ({}, {"enable_media_synthesis": False}, "media"),
        ({}, {"artifact_disposition": "quarantine"}, "disposition"),
    ),
)
def test_runtime_binding_rejects_request_or_policy_drift(
    request_changes: dict[str, Any],
    policy_changes: dict[str, Any],
    message: str,
) -> None:
    from src.pipeline.generation_policy import EffectiveGenerationPolicy
    from src.pipeline.w5_fast_runtime import build_w5_fast_runtime_binding

    plan = _plan()
    request_payload = _request().model_dump()
    request_payload.update(request_changes)
    policy_payload = _policy().model_dump()
    policy_payload.update(policy_changes)

    with pytest.raises((ValueError, ValidationError), match=message):
        build_w5_fast_runtime_binding(
            plan=plan,
            activation=_activation(plan),
            validated_request=_request().__class__.model_validate(request_payload),
            effective_policy=EffectiveGenerationPolicy.model_validate(policy_payload),
            idempotency_key_sha256="a" * 64,
            now=_times()[1],
        )


def test_validate_runtime_binding_detects_request_or_key_mismatch() -> None:
    from src.pipeline.w5_fast_runtime import (
        build_w5_fast_runtime_binding,
        validate_w5_fast_runtime_binding_json,
    )

    plan = _plan()
    activation = _activation(plan)
    binding = build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=_request(),
        effective_policy=_policy(),
        idempotency_key_sha256="a" * 64,
        now=_times()[1],
    )

    with pytest.raises(ValueError, match="idempotency"):
        validate_w5_fast_runtime_binding_json(
            binding.model_dump_json(),
            plan=plan,
            activation=activation,
            validated_request=_request(),
            effective_policy=_policy(),
            idempotency_key_sha256="b" * 64,
            now=_times()[1],
        )
    with pytest.raises(ValueError, match="request"):
        validate_w5_fast_runtime_binding_json(
            binding.model_dump_json(),
            plan=plan,
            activation=activation,
            validated_request=_request(duration=10),
            effective_policy=_policy(),
            idempotency_key_sha256="a" * 64,
            now=_times()[1],
        )


def test_runtime_binding_rejects_same_id_activation_content_mutation() -> None:
    from src.pipeline.w5_fast_runtime import (
        build_w5_fast_runtime_binding,
        validate_w5_fast_runtime_binding_json,
    )

    plan = _plan()
    activation = _activation(plan)
    binding = build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=_request(),
        effective_policy=_policy(),
        idempotency_key_sha256="a" * 64,
        now=_times()[1],
    )
    mutated_activation = activation.model_copy(
        update={
            "approved_by": "reviewer:other",
            "expires_at": plan.expires_at,
        },
    )

    with pytest.raises(ValueError, match="activation"):
        validate_w5_fast_runtime_binding_json(
            binding.model_dump_json(),
            plan=plan,
            activation=mutated_activation,
            validated_request=_request(),
            effective_policy=_policy(),
            idempotency_key_sha256="a" * 64,
            now=activation.expires_at + timedelta(minutes=1),
        )


def test_expired_runtime_binding_is_structurally_valid_only_for_replay() -> None:
    from src.pipeline.w5_fast_runtime import (
        build_w5_fast_runtime_binding,
        validate_w5_fast_runtime_binding_json,
    )

    plan = _plan()
    activation = _activation(plan)
    binding = build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=_request(),
        effective_policy=_policy(),
        idempotency_key_sha256="a" * 64,
        now=_times()[1],
    )
    expired_now = activation.expires_at + timedelta(minutes=1)

    with pytest.raises(ValueError, match="expired"):
        validate_w5_fast_runtime_binding_json(
            binding.model_dump_json(),
            plan=plan,
            activation=activation,
            validated_request=_request(),
            effective_policy=_policy(),
            idempotency_key_sha256="a" * 64,
            now=expired_now,
        )

    replay = validate_w5_fast_runtime_binding_json(
        binding.model_dump_json(),
        plan=plan,
        activation=activation,
        validated_request=_request(),
        effective_policy=_policy(),
        idempotency_key_sha256="a" * 64,
        now=expired_now,
        require_active=False,
    )
    assert replay == binding


def test_runtime_binding_derives_provider_neutral_plan_budget_authority() -> None:
    from src.pipeline.w5_fast_runtime import (
        derive_w5_fast_plan_budget_authorization,
    )
    from src.services.provider_cost import ValidatedPlanBudgetAuthorization

    plan = _plan()
    activation = _activation(plan)
    authority = derive_w5_fast_plan_budget_authorization(
        plan=plan,
        activation=activation,
        now=_times()[1],
    )

    assert isinstance(authority, ValidatedPlanBudgetAuthorization)
    assert authority.authorization_ref == activation.activation_id
    assert authority.authorization_scope == "w5-fast"
    assert authority.budget_limit_usd_nanos == plan.budget_limit_usd_nanos
    assert authority.max_total_cost_usd_nanos == plan.budget_limit_usd_nanos
    assert authority.per_job_cost_ceiling_usd_nanos == plan.budget_limit_usd_nanos
    assert authority.provider_job_caps == (("llm", 1), ("video", 1))


@pytest.mark.parametrize(
    "raw_transform",
    (
        lambda raw: raw.replace(
            '"budget_limit_usd_nanos":3150000000',
            '"budget_limit_usd_nanos":3150000000.0',
        ),
        lambda raw: raw.replace(
            '"budget_limit_usd_nanos":3150000000',
            '"budget_limit_usd_nanos":NaN',
        ),
        lambda raw: raw[:-1] + ',"unknown":true}',
    ),
)
def test_runtime_binding_original_json_rejects_float_nonfinite_or_unknown(
    raw_transform: Any,
) -> None:
    from src.pipeline.w5_fast_runtime import (
        build_w5_fast_runtime_binding,
        validate_w5_fast_runtime_binding_json,
    )

    plan = _plan()
    activation = _activation(plan)
    binding = build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=_request(),
        effective_policy=_policy(),
        idempotency_key_sha256="a" * 64,
        now=_times()[1],
    )
    raw = binding.model_dump_json()

    with pytest.raises((ValueError, ValidationError)):
        validate_w5_fast_runtime_binding_json(
            raw_transform(raw),
            plan=plan,
            activation=activation,
            validated_request=_request(),
            effective_policy=_policy(),
            idempotency_key_sha256="a" * 64,
            now=_times()[1],
        )
