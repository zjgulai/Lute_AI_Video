from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from pydantic import ValidationError

from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.pipeline.w5_acceptance_harness import (
    HU03Criterion,
    HU03ReviewRecordV1,
    ScenarioHumanReviewRecordV1,
    W5ProviderJobCategory,
    W5ReviewDecision,
    W5ReviewGate,
    W5Scenario,
    W5ScenarioPlanDraftV1,
)
from src.services.transparency_provenance import PRODUCER_SPECS

SCENARIOS: tuple[W5Scenario, ...] = ("fast", "s1", "s2", "s3", "s4", "s5")
EXPECTED_GATES: dict[W5Scenario, tuple[W5ReviewGate, ...]] = {
    "fast": ("pending_review_acceptance",),
    "s1": ("expert_gate", "hu03"),
    "s2": ("brand_review", "hu03"),
    "s3": ("rights_source_review", "hu03"),
    "s4": ("footage_ownership_review", "hu03"),
    "s5": ("model_product_review", "hu03"),
}
EXPECTED_JOB_CATEGORIES: dict[W5Scenario, tuple[W5ProviderJobCategory, ...]] = {
    "fast": ("llm", "video"),
    "s1": ("llm", "image", "video", "tts", "thumbnail"),
    "s2": ("llm", "image", "video", "tts", "thumbnail"),
    "s3": ("llm", "image", "video", "tts", "thumbnail"),
    "s4": ("llm", "video", "tts"),
    "s5": ("llm", "video", "tts"),
}
HU03_CRITERIA: tuple[HU03Criterion, ...] = (
    "hook_within_first_3_seconds",
    "two_concrete_nonduplicative_usps",
    "brand_voice_consistent",
    "explicit_platform_appropriate_claim_safe_cta",
)


def _times() -> tuple[datetime, datetime]:
    created = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
    return created, created + timedelta(hours=2)


def _caps(scenario: W5Scenario, *, fast_tts: bool = False) -> dict[str, int]:
    caps = {category: 1 for category in EXPECTED_JOB_CATEGORIES[scenario]}
    if scenario == "fast" and fast_tts:
        caps["tts"] = 1
    return caps


def _build_plan(
    scenario: W5Scenario,
    *,
    fast_tts: bool = False,
    **overrides: Any,
) -> W5ScenarioPlanDraftV1:
    from src.pipeline.w5_acceptance_harness import build_w5_plan_draft

    created, expires = _times()
    kwargs: dict[str, Any] = {
        "scenario": scenario,
        "tenant_id": "tenant-alpha",
        "sample_ref": f"sample:{scenario}:001",
        "budget_limit_usd_nanos": 25_000_000,
        "provider_job_caps": _caps(scenario, fast_tts=fast_tts),
        "selected_optional_media": ("tts_audio",) if fast_tts else (),
        "created_at": created,
        "expires_at": expires,
    }
    kwargs.update(overrides)
    return build_w5_plan_draft(**kwargs)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_contract_matrix_is_no_provider_pending_review_and_scenario_exact(scenario: W5Scenario) -> None:
    from src.pipeline.w5_acceptance_harness import get_w5_scenario_contract

    contract = get_w5_scenario_contract(scenario)

    assert contract.scenario == scenario
    assert contract.tenant_isolation_required is True
    assert contract.generation_safety_policy_version == "generation-safety.v2"
    assert contract.artifact_disposition == "pending_review"
    assert contract.audit_required is True
    assert contract.transparency_required is True
    assert contract.required_human_gates == EXPECTED_GATES[scenario]
    assert contract.required_provider_job_categories == EXPECTED_JOB_CATEGORIES[scenario]
    assert contract.provider_max_retries == 0
    assert contract.provider_calls_allowed is False
    assert contract.execution_authorized is False
    assert contract.publish_allowed is False
    assert contract.delivery_accepted is False

    if scenario == "fast":
        assert contract.step_order == (
            "prompt_normalization",
            "generation_disclosure",
            "target_video",
            "optional_tts",
            "pending_review_acceptance",
        )
        assert contract.required_media_evidence == ("target_video",)
        assert contract.optional_media_evidence == ("tts_audio",)
    else:
        assert contract.step_order == tuple(SCENARIO_STEP_ORDERS[scenario])
        assert set(PRODUCER_SPECS[scenario]) == set(contract.step_order)


def test_unknown_scenario_is_rejected() -> None:
    from src.pipeline.w5_acceptance_harness import get_w5_scenario_contract

    with pytest.raises(ValueError, match="unsupported W5 scenario"):
        get_w5_scenario_contract("s6")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_plan_draft_binds_single_submit_budget_caps_and_stop_conditions(scenario: W5Scenario) -> None:
    plan = _build_plan(scenario)

    assert plan.status == "draft_pending_human_review"
    assert plan.template_only is True
    assert plan.submission_cap == 1
    assert plan.automatic_retry_cap == 0
    assert plan.provider_max_retries == 0
    assert plan.budget_limit_usd_nanos == 25_000_000
    assert dict(plan.provider_job_caps) == _caps(scenario)
    assert plan.expected_completion_kind == "full_media"
    assert plan.artifact_disposition == "pending_review"
    assert plan.provider_calls_allowed is False
    assert plan.execution_authorized is False
    assert plan.publish_allowed is False
    assert plan.delivery_accepted is False
    assert plan.runtime_profile_bound is False
    assert plan.required_human_gates == EXPECTED_GATES[scenario]
    assert plan.step_order == plan.contract.step_order
    assert "budget_exhausted" in plan.stop_conditions
    assert "provider_outcome_ambiguous" in plan.stop_conditions
    assert "human_review_required" in plan.stop_conditions
    assert plan.plan_id.startswith("w5plan:")


def test_plan_id_is_deterministic_and_scope_sensitive() -> None:
    first = _build_plan("s3")
    second = _build_plan("s3")
    other_sample = _build_plan("s3", sample_ref="sample:s3:002")

    assert first == second
    assert first.plan_id != other_sample.plan_id


def test_plan_json_readback_revalidates_canonical_digest_and_contract() -> None:
    from src.pipeline.w5_acceptance_harness import validate_w5_plan_draft_json

    plan = _build_plan("s2")
    raw = plan.model_dump_json()

    assert validate_w5_plan_draft_json(raw) == plan


def test_plan_json_readback_rejects_unknown_provider_job_cap() -> None:
    from src.pipeline.w5_acceptance_harness import validate_w5_plan_draft_json

    payload = _build_plan("fast").model_dump(mode="json")
    caps = payload["provider_job_caps"]
    assert isinstance(caps, dict)
    caps["publish"] = 999

    with pytest.raises((ValueError, ValidationError), match="provider job cap"):
        validate_w5_plan_draft_json(json.dumps(payload))


@pytest.mark.parametrize("duplicate_value", (1, 2))
def test_plan_json_readback_rejects_duplicate_provider_job_cap(
    duplicate_value: int,
) -> None:
    from src.pipeline.w5_acceptance_harness import validate_w5_plan_draft_json

    raw = _build_plan("fast").model_dump_json()
    original = '"provider_job_caps":{"llm":1,"video":1}'
    duplicated = (
        f'"provider_job_caps":{{"llm":1,"llm":{duplicate_value},"video":1}}'
    )
    assert original in raw

    with pytest.raises(ValueError, match="duplicate JSON object key"):
        validate_w5_plan_draft_json(raw.replace(original, duplicated))


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("budget_limit_usd_nanos",), 25_000_001),
        (("provider_job_caps", "video"), 2),
        (("contract", "required_media_evidence"), ["assemble_final"]),
        (("plan_id",), "w5plan:00000000000000000000000000000000"),
    ),
)
def test_plan_json_readback_rejects_tampering(path: tuple[str, ...], value: object) -> None:
    from src.pipeline.w5_acceptance_harness import validate_w5_plan_draft_json

    payload = _build_plan("s2").model_dump(mode="json")
    target: dict[str, Any] = payload
    for key in path[:-1]:
        nested = target[key]
        assert isinstance(nested, dict)
        target = nested
    target[path[-1]] = value

    with pytest.raises((ValueError, ValidationError), match="canonical|digest|contract"):
        validate_w5_plan_draft_json(json.dumps(payload))


def test_fast_tts_selection_requires_and_binds_tts_cap() -> None:
    plan = _build_plan("fast", fast_tts=True)

    assert plan.selected_optional_media == ("tts_audio",)
    assert dict(plan.provider_job_caps) == {"llm": 1, "video": 1, "tts": 1}

    with pytest.raises(ValueError, match="provider job cap categories"):
        _build_plan(
            "fast",
            selected_optional_media=("tts_audio",),
            provider_job_caps={"llm": 1, "video": 1},
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("budget_limit_usd_nanos", True, "budget"),
        ("budget_limit_usd_nanos", 1.5, "budget"),
        ("budget_limit_usd_nanos", 0, "budget"),
        ("budget_limit_usd_nanos", 2**63, "budget"),
        ("provider_job_caps", {"llm": True, "video": 1}, "provider job cap"),
        ("provider_job_caps", {"llm": 1, "video": 0}, "provider job cap"),
        ("provider_job_caps", {"llm": 1, "video": 1, "publish": 1}, "provider job cap categories"),
        ("sample_ref", "/tmp/sample.json", "sample_ref"),
        ("tenant_id", "../tenant", "tenant_id"),
    ),
)
def test_plan_builder_rejects_noncanonical_inputs(field: str, value: object, message: str) -> None:
    with pytest.raises((ValueError, ValidationError), match=message):
        cast(Any, _build_plan)("fast", **{field: value})


def test_plan_builder_rejects_naive_or_invalid_time_window() -> None:
    created, expires = _times()

    with pytest.raises(ValueError, match="timezone-aware"):
        _build_plan("s1", created_at=created.replace(tzinfo=None))
    with pytest.raises(ValueError, match="expiry"):
        _build_plan("s1", expires_at=created)
    with pytest.raises(ValueError, match="four hours"):
        _build_plan("s1", expires_at=expires + timedelta(hours=3))


def _hu03(
    plan: W5ScenarioPlanDraftV1,
    *,
    outcome: W5ReviewDecision = "pass",
    failed: HU03Criterion | None = None,
    reviewed_at: datetime | None = None,
) -> HU03ReviewRecordV1:
    from src.pipeline.w5_acceptance_harness import HU03CriterionResultV1

    criteria = tuple(
        HU03CriterionResultV1(
            criterion=criterion,
            passed=criterion != failed,
            evidence_refs=(f"evidence:{criterion}",),
            notes=f"reviewed {criterion}",
        )
        for criterion in HU03_CRITERIA
    )
    return HU03ReviewRecordV1(
        record_id=f"hu03:{plan.scenario}:001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        scenario=plan.scenario,
        sample_ref=plan.sample_ref,
        reviewer_id="reviewer:ll",
        reviewed_at=reviewed_at or plan.created_at + timedelta(hours=1),
        outcome=outcome,
        reason="manual script review completed",
        criteria=criteria,
    )


def _scenario_review(
    plan: W5ScenarioPlanDraftV1,
    gate: W5ReviewGate,
    *,
    decision: W5ReviewDecision = "pass",
    reviewed_at: datetime | None = None,
) -> ScenarioHumanReviewRecordV1:
    return ScenarioHumanReviewRecordV1(
        record_id=f"review:{plan.scenario}:{gate}:001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        scenario=plan.scenario,
        sample_ref=plan.sample_ref,
        review_gate=gate,
        reviewer_id="reviewer:ll",
        reviewed_at=reviewed_at or plan.created_at + timedelta(hours=1),
        decision=decision,
        reason=f"manual {gate} review completed",
        evidence_refs=(f"evidence:{gate}:001",),
    )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_review_packet_requires_exact_scenario_gates_and_hu03(scenario: W5Scenario) -> None:
    from src.pipeline.w5_acceptance_harness import W5HumanReviewPacketV1, validate_w5_review_packet

    plan = _build_plan(scenario)
    non_hu03_gates = cast(
        tuple[W5ReviewGate, ...],
        tuple(gate for gate in EXPECTED_GATES[scenario] if gate != "hu03"),
    )
    packet = W5HumanReviewPacketV1(
        packet_id=f"review-packet:{scenario}:001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        scenario=scenario,
        sample_ref=plan.sample_ref,
        hu03=_hu03(plan) if "hu03" in EXPECTED_GATES[scenario] else None,
        scenario_reviews=tuple(_scenario_review(plan, gate) for gate in non_hu03_gates),
    )

    validated = validate_w5_review_packet(plan, packet)
    assert validated == packet
    assert packet.artifact_promoted is False
    assert packet.provider_authorized is False
    assert packet.publish_allowed is False
    assert packet.delivery_accepted is False


def test_hu03_pass_requires_all_four_exact_criteria() -> None:
    plan = _build_plan("s2")

    with pytest.raises(ValidationError, match="all HU-03 criteria"):
        _hu03(plan, outcome="pass", failed="brand_voice_consistent")

    valid = _hu03(plan)
    payload = valid.model_dump()
    payload["criteria"] = payload["criteria"][:-1]
    with pytest.raises(ValidationError, match="exactly the four canonical"):
        type(valid).model_validate(payload)


def test_hu03_nonpass_requires_at_least_one_failed_criterion() -> None:
    plan = _build_plan("s3")

    with pytest.raises(ValidationError, match="failed criterion"):
        _hu03(plan, outcome="revise")

    assert _hu03(plan, outcome="reject", failed="hook_within_first_3_seconds").outcome == "reject"


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"tenant_id": "tenant-other"}, "tenant"),
        ({"sample_ref": "sample:s1:other"}, "sample"),
        ({"scenario": "s2"}, "scenario"),
    ),
)
def test_review_packet_rejects_cross_scope_records(change: dict[str, str], message: str) -> None:
    from src.pipeline.w5_acceptance_harness import W5HumanReviewPacketV1, validate_w5_review_packet

    plan = _build_plan("s1")
    review = _scenario_review(plan, "expert_gate")
    review = type(review).model_validate({**review.model_dump(), **change})
    packet = W5HumanReviewPacketV1(
        packet_id="review-packet:s1:001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        scenario="s1",
        sample_ref=plan.sample_ref,
        hu03=_hu03(plan),
        scenario_reviews=(review,),
    )

    with pytest.raises(ValueError, match=message):
        validate_w5_review_packet(plan, packet)


def test_review_packet_rejects_missing_duplicate_or_wrong_gate() -> None:
    from src.pipeline.w5_acceptance_harness import W5HumanReviewPacketV1, validate_w5_review_packet

    plan = _build_plan("s4")
    base = {
        "packet_id": "review-packet:s4:001",
        "plan_id": plan.plan_id,
        "tenant_id": plan.tenant_id,
        "scenario": "s4",
        "sample_ref": plan.sample_ref,
        "hu03": _hu03(plan),
    }

    for reviews in (
        (),
        (_scenario_review(plan, "footage_ownership_review"),) * 2,
        (_scenario_review(plan, "brand_review"),),
    ):
        packet = W5HumanReviewPacketV1(**base, scenario_reviews=reviews)
        with pytest.raises(ValueError, match="review gates"):
            validate_w5_review_packet(plan, packet)


def test_review_models_reject_blank_or_unsafe_human_evidence() -> None:
    plan = _build_plan("fast")
    review = _scenario_review(plan, "pending_review_acceptance")

    for change in (
        {"reviewer_id": ""},
        {"reason": ""},
        {"evidence_refs": ()},
        {"evidence_refs": ("/tmp/private.json",)},
    ):
        with pytest.raises(ValidationError):
            type(review).model_validate({**review.model_dump(), **change})


def test_review_packet_rejects_review_before_plan_creation() -> None:
    from src.pipeline.w5_acceptance_harness import W5HumanReviewPacketV1, validate_w5_review_packet

    plan = _build_plan("fast")
    review = _scenario_review(plan, "pending_review_acceptance")
    review = type(review).model_validate(
        {**review.model_dump(), "reviewed_at": plan.created_at - timedelta(seconds=1)}
    )
    packet = W5HumanReviewPacketV1(
        packet_id="review-packet:fast:001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        scenario="fast",
        sample_ref=plan.sample_ref,
        hu03=None,
        scenario_reviews=(review,),
    )

    with pytest.raises(ValueError, match="before plan creation"):
        validate_w5_review_packet(plan, packet)


@pytest.mark.parametrize("offset", (timedelta(0), timedelta(seconds=1)))
@pytest.mark.parametrize("record_kind", ("scenario", "hu03"))
def test_review_packet_rejects_review_at_or_after_plan_expiry(
    offset: timedelta,
    record_kind: str,
) -> None:
    from src.pipeline.w5_acceptance_harness import (
        W5HumanReviewPacketV1,
        validate_w5_review_packet,
    )

    plan = _build_plan("s1")
    reviewed_at = plan.expires_at + offset
    packet = W5HumanReviewPacketV1(
        packet_id="review-packet:s1:expiry",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        scenario="s1",
        sample_ref=plan.sample_ref,
        hu03=_hu03(
            plan,
            reviewed_at=reviewed_at if record_kind == "hu03" else None,
        ),
        scenario_reviews=(
            _scenario_review(
                plan,
                "expert_gate",
                reviewed_at=reviewed_at if record_kind == "scenario" else None,
            ),
        ),
    )

    with pytest.raises(ValueError, match="before plan expiry"):
        validate_w5_review_packet(plan, packet)
