"""W1-27–W1-30 Task 1 strict provider-cost contracts."""

from __future__ import annotations

import json
from typing import get_args

import pytest
from pydantic import ValidationError


def _valid_account_identity(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "tenant_id": "tenant_fixture",
        "job_kind": "canonical",
        "job_id": "fast_7f947625-2898-4e9e-9e71-dce4309e5f4f",
        "scenario_or_resource_type": "fast",
        "budget_source_kind": "server_config",
        "budget_source_ref": None,
        "budget_policy_version": "provider-budget.v1",
    }
    payload.update(overrides)
    return payload


def _valid_attempt_identity(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "logical_operation": "fast.script.primary",
        "catalog_operation": "chat_completion",
        "ordinal": 0,
        "provider": "deepseek",
        "canonical_model": "deepseek-v4-flash",
        "provider_billing_region": "deepseek_global_usd",
        "media_type": "text",
        "billing_fact_kind": "llm_tokens.v1",
        "state": "reserved",
    }
    payload.update(overrides)
    return payload


def test_frozen_vocabularies_are_exact() -> None:
    from src.models.provider_cost import (
        AttemptState,
        BudgetJobKind,
        BudgetSourceKind,
        CatalogOperation,
        ProviderBillingRegion,
        ProviderCostErrorCode,
    )

    assert get_args(AttemptState) == (
        "reserved",
        "submission_started",
        "submitted",
        "settled",
        "released",
        "ambiguous",
        "accounting_error",
    )
    assert get_args(BudgetJobKind) == ("canonical", "compatibility")
    assert get_args(BudgetSourceKind) == (
        "server_config",
        "validated_authorization",
    )
    assert get_args(ProviderBillingRegion) == (
        "deepseek_global_usd",
        "poyo_global_usd",
        "siliconflow_global_usd",
    )
    assert get_args(CatalogOperation) == (
        "chat_completion",
        "speech_synthesis",
        "image_generation",
        "text_to_video",
        "image_to_video",
    )
    assert set(get_args(ProviderCostErrorCode)) == {
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
    }


def test_account_and_attempt_identity_are_strict_frozen_and_bounded() -> None:
    from src.models.provider_cost import (
        ProviderCostAccountIdentity,
        ProviderCostAttemptIdentity,
    )

    account = ProviderCostAccountIdentity.model_validate(_valid_account_identity())
    attempt = ProviderCostAttemptIdentity.model_validate(_valid_attempt_identity())

    assert account.job_kind == "canonical"
    assert attempt.ordinal == 0
    with pytest.raises(ValidationError, match="frozen"):
        account.job_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError, match="frozen"):
        attempt.state = "settled"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("model_name", "payload"),
    [
        ("account", _valid_account_identity(tenant_id="")),
        ("account", _valid_account_identity(job_id="x" * 129)),
        ("account", _valid_account_identity(job_kind="legacy")),
        ("account", _valid_account_identity(budget_source_kind="request")),
        ("account", _valid_account_identity(unknown="forbidden")),
        ("attempt", _valid_attempt_identity(logical_operation="UPPER")),
        ("attempt", _valid_attempt_identity(ordinal=True)),
        ("attempt", _valid_attempt_identity(ordinal=-1)),
        ("attempt", _valid_attempt_identity(ordinal=2**63)),
        ("attempt", _valid_attempt_identity(catalog_operation="fast.script")),
        ("attempt", _valid_attempt_identity(provider_billing_region="custom")),
        ("attempt", _valid_attempt_identity(state="failed")),
        ("attempt", _valid_attempt_identity(unknown="forbidden")),
    ],
)
def test_identity_models_reject_coercion_unknowns_and_bounds(
    model_name: str,
    payload: dict[str, object],
) -> None:
    from src.models.provider_cost import (
        ProviderCostAccountIdentity,
        ProviderCostAttemptIdentity,
    )

    model = (
        ProviderCostAccountIdentity
        if model_name == "account"
        else ProviderCostAttemptIdentity
    )
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_llm_billing_facts_enforce_both_conservation_equations() -> None:
    from src.models.provider_cost import LLMTokensBillingFacts

    facts = LLMTokensBillingFacts.model_validate(
        {
            "schema_version": "llm_tokens.v1",
            "input_tokens": 10,
            "input_cache_hit_tokens": 4,
            "input_cache_miss_tokens": 6,
            "output_tokens": 3,
            "total_tokens": 13,
        }
    )
    assert facts.total_tokens == 13

    with pytest.raises(ValidationError, match="cache"):
        LLMTokensBillingFacts.model_validate(
            {**facts.model_dump(), "input_cache_miss_tokens": 5}
        )
    with pytest.raises(ValidationError, match="total"):
        LLMTokensBillingFacts.model_validate(
            {**facts.model_dump(), "total_tokens": 12}
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "tts_utf8_bytes.v1", "input_utf8_bytes": 7},
        {"schema_version": "image_count.v1", "image_count": 1},
        {"schema_version": "video_task.v1", "task_count": 1},
        {
            "schema_version": "video_task.v1",
            "task_count": 1,
            "duration_ms": 5_000,
        },
        {
            "schema_version": "video_duration.v1",
            "task_count": 1,
            "duration_ms": 5_000,
        },
    ],
)
def test_billing_fact_union_accepts_only_the_five_frozen_shapes(
    payload: dict[str, object],
) -> None:
    from src.models.provider_cost import parse_billing_facts

    facts = parse_billing_facts(payload)
    assert facts.schema_version == payload["schema_version"]


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "tts_utf8_bytes.v1", "input_utf8_bytes": True},
        {"schema_version": "tts_utf8_bytes.v1", "input_utf8_bytes": "7"},
        {"schema_version": "tts_utf8_bytes.v1", "input_utf8_bytes": 0},
        {"schema_version": "image_count.v1", "image_count": -1},
        {"schema_version": "image_count.v1", "image_count": 2**63},
        {"schema_version": "video_task.v1", "task_count": 1.0},
        {"schema_version": "video_task.v1", "task_count": 1, "duration_ms": -1},
        {"schema_version": "video_duration.v1", "task_count": 1},
        {
            "schema_version": "video_duration.v1",
            "task_count": 1,
            "duration_ms": False,
        },
        {"schema_version": "duration.v0", "duration_ms": 5_000},
        {"schema_version": "image_count.v1", "image_count": 1, "extra": 1},
    ],
)
def test_billing_facts_reject_coercion_negative_overflow_and_unknown_fields(
    payload: dict[str, object],
) -> None:
    from src.models.provider_cost import parse_billing_facts

    with pytest.raises(ValidationError):
        parse_billing_facts(payload)


def test_billing_fact_json_rejects_malformed_float_and_nonfinite_numbers() -> None:
    from src.models.provider_cost import parse_billing_facts_json

    for raw in (
        "{",
        '{"schema_version":"image_count.v1","image_count":1.0}',
        '{"schema_version":"image_count.v1","image_count":NaN}',
        '{"schema_version":"image_count.v1","image_count":Infinity}',
    ):
        with pytest.raises((ValueError, ValidationError, json.JSONDecodeError)):
            parse_billing_facts_json(raw)
