"""Provider-off W5 acceptance contracts, plan drafts, and human-review records.

This module is deliberately incapable of approving or executing a plan.  It
contains no environment, network, provider-client, route, or persistence code.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Annotated, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_serializer,
    field_validator,
    model_validator,
)

from src.models.provider_cost import MAX_SIGNED_BIGINT
from src.pipeline.generation_policy_constants import GENERATION_POLICY_VERSION
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.services.transparency_provenance import PRODUCER_SPECS

W5_CONTRACT_VERSION = "w5-no-provider-contract.v1"
W5_PLAN_VERSION = "w5-l4-plan-draft.v1"
W5_REVIEW_VERSION = "w5-human-review.v1"
_MAX_PLAN_WINDOW = timedelta(hours=4)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

W5Scenario = Literal["fast", "s1", "s2", "s3", "s4", "s5"]
W5ProviderJobCategory = Literal["llm", "image", "video", "tts", "thumbnail"]
W5OptionalMedia = Literal["tts_audio"]
W5ReviewGate = Literal[
    "pending_review_acceptance",
    "expert_gate",
    "hu03",
    "brand_review",
    "rights_source_review",
    "footage_ownership_review",
    "model_product_review",
]
W5ReviewDecision = Literal["pass", "revise", "reject"]
HU03Criterion = Literal[
    "hook_within_first_3_seconds",
    "two_concrete_nonduplicative_usps",
    "brand_voice_consistent",
    "explicit_platform_appropriate_claim_safe_cta",
]
SafeIdentifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=_SAFE_ID_RE.pattern),
]
PositiveMoneyNanos = Annotated[
    int,
    Field(strict=True, ge=1, le=MAX_SIGNED_BIGINT),
]
PositiveJobCap = Annotated[
    int,
    Field(strict=True, ge=1, le=10_000),
]

HU03_CRITERIA: tuple[HU03Criterion, ...] = (
    "hook_within_first_3_seconds",
    "two_concrete_nonduplicative_usps",
    "brand_voice_consistent",
    "explicit_platform_appropriate_claim_safe_cta",
)

W5_STOP_CONDITIONS = (
    "budget_exhausted",
    "provider_outcome_ambiguous",
    "provider_or_artifact_failure",
    "accounting_error",
    "audit_failure",
    "transparency_failure",
    "human_review_required",
)


class _StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class W5ScenarioContractV1(_StrictFrozenModel):
    """Code-owned no-provider contract for one acceptance scenario."""

    version: Literal["w5-no-provider-contract.v1"] = W5_CONTRACT_VERSION
    scenario: W5Scenario
    step_order: tuple[str, ...]
    required_text_evidence: tuple[str, ...]
    required_media_evidence: tuple[str, ...]
    optional_media_evidence: tuple[W5OptionalMedia, ...] = ()
    required_human_gates: tuple[W5ReviewGate, ...]
    required_provider_job_categories: tuple[W5ProviderJobCategory, ...]
    optional_provider_job_categories: tuple[W5ProviderJobCategory, ...] = ()
    tenant_isolation_required: Literal[True] = True
    generation_safety_policy_version: Literal["generation-safety.v2"] = (
        GENERATION_POLICY_VERSION
    )
    artifact_disposition: Literal["pending_review"] = "pending_review"
    provider_max_retries: Literal[0] = 0
    audit_required: Literal[True] = True
    transparency_required: Literal[True] = True
    provider_calls_allowed: Literal[False] = False
    execution_authorized: Literal[False] = False
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False


_TEXT_EVIDENCE: Mapping[str, tuple[str, ...]] = {
    "s1": ("strategy", "scripts", "compliance"),
    "s2": ("strategy", "scripts", "compliance"),
    "s3": ("video_analysis", "remix_script", "storyboards"),
    "s4": ("scripts", "video_prompts"),
    "s5": ("vlog_strategy", "video_prompts"),
}
_MEDIA_EVIDENCE: Mapping[str, tuple[str, ...]] = {
    "s1": ("keyframe_images", "seedance_clips", "tts_audio", "thumbnail_images", "assemble_final"),
    "s2": ("keyframe_images", "seedance_clips", "tts_audio", "thumbnail_images", "assemble_final"),
    "s3": ("keyframe_images", "seedance_clips", "tts_audio", "thumbnail_images", "assemble_final"),
    "s4": ("uploaded_footage_refs", "seedance_clips", "tts_audio", "thumbnail", "assemble_final"),
    "s5": ("six_product_views", "seedance_clips", "tts_audio", "assemble_final"),
}
_HUMAN_GATES: Mapping[str, tuple[W5ReviewGate, ...]] = {
    "fast": ("pending_review_acceptance",),
    "s1": ("expert_gate", "hu03"),
    "s2": ("brand_review", "hu03"),
    "s3": ("rights_source_review", "hu03"),
    "s4": ("footage_ownership_review", "hu03"),
    "s5": ("model_product_review", "hu03"),
}
_REQUIRED_JOB_CATEGORIES: Mapping[str, tuple[W5ProviderJobCategory, ...]] = {
    "fast": ("llm", "video"),
    "s1": ("llm", "image", "video", "tts", "thumbnail"),
    "s2": ("llm", "image", "video", "tts", "thumbnail"),
    "s3": ("llm", "image", "video", "tts", "thumbnail"),
    "s4": ("llm", "video", "tts"),
    "s5": ("llm", "video", "tts"),
}


def _build_contracts() -> Mapping[str, W5ScenarioContractV1]:
    contracts: dict[str, W5ScenarioContractV1] = {
        "fast": W5ScenarioContractV1(
            scenario="fast",
            step_order=(
                "prompt_normalization",
                "generation_disclosure",
                "target_video",
                "optional_tts",
                "pending_review_acceptance",
            ),
            required_text_evidence=("prompt_normalization", "generation_disclosure"),
            required_media_evidence=("target_video",),
            optional_media_evidence=("tts_audio",),
            required_human_gates=_HUMAN_GATES["fast"],
            required_provider_job_categories=_REQUIRED_JOB_CATEGORIES["fast"],
            optional_provider_job_categories=("tts",),
        )
    }
    for scenario in ("s1", "s2", "s3", "s4", "s5"):
        contracts[scenario] = W5ScenarioContractV1(
            scenario=cast(W5Scenario, scenario),
            step_order=tuple(SCENARIO_STEP_ORDERS[scenario]),
            required_text_evidence=_TEXT_EVIDENCE[scenario],
            required_media_evidence=_MEDIA_EVIDENCE[scenario],
            required_human_gates=_HUMAN_GATES[scenario],
            required_provider_job_categories=_REQUIRED_JOB_CATEGORIES[scenario],
        )
    return contracts


_CONTRACTS = _build_contracts()


def get_w5_scenario_contract(scenario: str) -> W5ScenarioContractV1:
    """Return a no-provider contract after checking canonical SSOT parity."""

    contract = _CONTRACTS.get(scenario)
    if contract is None:
        raise ValueError(f"unsupported W5 scenario: {scenario!r}")
    if scenario != "fast":
        current_steps = tuple(SCENARIO_STEP_ORDERS[scenario])
        producer_steps = tuple(PRODUCER_SPECS[scenario])
        if current_steps != contract.step_order or set(producer_steps) != set(current_steps):
            raise ValueError(f"W5 scenario step/provenance SSOT drift: {scenario}")
    return contract


class W5ScenarioPlanDraftV1(_StrictFrozenModel):
    """Exact pending-human-review plan draft; never provider authority."""

    version: Literal["w5-l4-plan-draft.v1"] = W5_PLAN_VERSION
    plan_id: SafeIdentifier
    status: Literal["draft_pending_human_review"] = "draft_pending_human_review"
    template_only: Literal[True] = True
    tenant_id: SafeIdentifier
    scenario: W5Scenario
    sample_ref: SafeIdentifier
    created_at: datetime
    expires_at: datetime
    contract: W5ScenarioContractV1
    step_order: tuple[str, ...]
    required_human_gates: tuple[W5ReviewGate, ...]
    selected_optional_media: tuple[W5OptionalMedia, ...] = ()
    budget_limit_usd_nanos: PositiveMoneyNanos
    provider_job_caps: tuple[tuple[W5ProviderJobCategory, PositiveJobCap], ...]
    submission_cap: Literal[1] = 1
    automatic_retry_cap: Literal[0] = 0
    provider_max_retries: Literal[0] = 0
    artifact_disposition: Literal["pending_review"] = "pending_review"
    expected_completion_kind: Literal["full_media"] = "full_media"
    stop_conditions: tuple[str, ...] = W5_STOP_CONDITIONS
    runtime_profile_bound: Literal[False] = False
    provider_calls_allowed: Literal[False] = False
    execution_authorized: Literal[False] = False
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False

    @field_validator("provider_job_caps", mode="before")
    @classmethod
    def _load_provider_job_caps(
        cls,
        value: object,
    ) -> object:
        if type(value) is not dict:
            return value
        category_order = ("llm", "image", "video", "tts", "thumbnail")
        if set(value) - set(category_order):
            raise ValueError("provider job cap categories contain unsupported values")
        return tuple((category, value[category]) for category in category_order if category in value)

    @field_serializer("provider_job_caps")
    def _serialize_provider_job_caps(
        self,
        value: tuple[tuple[W5ProviderJobCategory, int], ...],
    ) -> dict[str, int]:
        return dict(value)

    @model_validator(mode="after")
    def _validate_plan(self) -> W5ScenarioPlanDraftV1:
        _require_utc(self.created_at, "plan creation")
        _require_utc(self.expires_at, "plan expiry")
        if self.expires_at <= self.created_at:
            raise ValueError("plan expiry must follow plan creation")
        if self.expires_at - self.created_at > _MAX_PLAN_WINDOW:
            raise ValueError("plan validity cannot exceed four hours")
        if self.contract.scenario != self.scenario:
            raise ValueError("plan contract scenario mismatch")
        if self.step_order != self.contract.step_order:
            raise ValueError("plan step order mismatch")
        if self.required_human_gates != self.contract.required_human_gates:
            raise ValueError("plan human gate mismatch")
        if len(dict(self.provider_job_caps)) != len(self.provider_job_caps):
            raise ValueError("provider job cap categories must be unique")
        return self


def _require_utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must use UTC")


def _strict_caps(
    raw_caps: Mapping[str, object],
    *,
    expected_categories: tuple[W5ProviderJobCategory, ...],
) -> tuple[tuple[W5ProviderJobCategory, int], ...]:
    if type(raw_caps) is not dict:
        raise ValueError("provider job caps must be a plain JSON object")
    if set(raw_caps) != set(expected_categories):
        raise ValueError("provider job cap categories do not match the scenario draft")
    cap_items: list[tuple[W5ProviderJobCategory, int]] = []
    for category in expected_categories:
        value = raw_caps[category]
        if type(value) is not int or not (1 <= value <= 10_000):
            raise ValueError("provider job cap values must be positive strict integers")
        cap_items.append((category, value))
    return tuple(cap_items)


def _validate_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _SAFE_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded logical identifier")
    return value


def build_w5_plan_draft(
    *,
    scenario: str,
    tenant_id: str,
    sample_ref: str,
    budget_limit_usd_nanos: object,
    provider_job_caps: Mapping[str, object],
    created_at: datetime,
    expires_at: datetime,
    selected_optional_media: tuple[str, ...] = (),
) -> W5ScenarioPlanDraftV1:
    """Build a deterministic, secret-free, non-authorizing W5 draft."""

    contract = get_w5_scenario_contract(scenario)
    tenant = _validate_identifier(tenant_id, "tenant_id")
    sample = _validate_identifier(sample_ref, "sample_ref")
    if type(budget_limit_usd_nanos) is not int or not (
        1 <= budget_limit_usd_nanos <= MAX_SIGNED_BIGINT
    ):
        raise ValueError("budget must be a positive strict USD-nanos integer")
    if type(selected_optional_media) is not tuple or any(
        type(item) is not str for item in selected_optional_media
    ):
        raise ValueError("selected optional media must be an exact tuple")
    if len(set(selected_optional_media)) != len(selected_optional_media):
        raise ValueError("selected optional media must be unique")
    if set(selected_optional_media) - set(contract.optional_media_evidence):
        raise ValueError("selected optional media is unsupported for the scenario")
    selected = cast(tuple[W5OptionalMedia, ...], selected_optional_media)
    optional_categories: tuple[W5ProviderJobCategory, ...] = (
        ("tts",) if "tts_audio" in selected else ()
    )
    expected_categories = contract.required_provider_job_categories + optional_categories
    caps = _strict_caps(provider_job_caps, expected_categories=expected_categories)
    _require_utc(created_at, "plan creation")
    _require_utc(expires_at, "plan expiry")

    digest_payload = {
        "version": W5_PLAN_VERSION,
        "tenant_id": tenant,
        "scenario": scenario,
        "sample_ref": sample,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "contract": contract.model_dump(mode="json"),
        "selected_optional_media": list(selected),
        "budget_limit_usd_nanos": budget_limit_usd_nanos,
        "provider_job_caps": dict(caps),
        "submission_cap": 1,
        "automatic_retry_cap": 0,
        "provider_max_retries": 0,
        "artifact_disposition": "pending_review",
        "expected_completion_kind": "full_media",
        "stop_conditions": list(W5_STOP_CONDITIONS),
        "runtime_profile_bound": False,
        "provider_calls_allowed": False,
        "execution_authorized": False,
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    canonical = json.dumps(
        digest_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    plan_id = f"w5plan:{hashlib.sha256(canonical).hexdigest()[:32]}"
    return W5ScenarioPlanDraftV1(
        plan_id=plan_id,
        tenant_id=tenant,
        scenario=cast(W5Scenario, scenario),
        sample_ref=sample,
        created_at=created_at,
        expires_at=expires_at,
        contract=contract,
        step_order=contract.step_order,
        required_human_gates=contract.required_human_gates,
        selected_optional_media=selected,
        budget_limit_usd_nanos=budget_limit_usd_nanos,
        provider_job_caps=caps,
    )


def validate_w5_plan_draft_json(raw: str | bytes) -> W5ScenarioPlanDraftV1:
    """Reload a JSON draft and reject contract, field, or digest tampering."""

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON object key: {key}")
            result[key] = value
        return result

    def reject_nonfinite_constant(value: str) -> object:
        raise ValueError(f"invalid JSON numeric constant: {value}")

    decoded = json.loads(
        raw,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_nonfinite_constant,
    )
    strict_raw = json.dumps(
        decoded,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    plan = W5ScenarioPlanDraftV1.model_validate_json(strict_raw)
    canonical_contract = get_w5_scenario_contract(plan.scenario)
    if plan.contract != canonical_contract:
        raise ValueError("canonical W5 plan contract mismatch")
    rebuilt = build_w5_plan_draft(
        scenario=plan.scenario,
        tenant_id=plan.tenant_id,
        sample_ref=plan.sample_ref,
        budget_limit_usd_nanos=plan.budget_limit_usd_nanos,
        provider_job_caps=dict(plan.provider_job_caps),
        created_at=plan.created_at,
        expires_at=plan.expires_at,
        selected_optional_media=plan.selected_optional_media,
    )
    if plan != rebuilt:
        raise ValueError("canonical W5 plan digest or contract mismatch")
    return plan


class HU03CriterionResultV1(_StrictFrozenModel):
    version: Literal["w5-human-review.v1"] = W5_REVIEW_VERSION
    criterion: HU03Criterion
    passed: StrictBool
    evidence_refs: tuple[SafeIdentifier, ...]
    notes: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _nonblank(self) -> HU03CriterionResultV1:
        if not self.evidence_refs:
            raise ValueError("HU-03 criterion requires evidence refs")
        if not self.notes.strip():
            raise ValueError("HU-03 criterion notes cannot be blank")
        return self


class HU03ReviewRecordV1(_StrictFrozenModel):
    version: Literal["w5-human-review.v1"] = W5_REVIEW_VERSION
    record_id: SafeIdentifier
    plan_id: SafeIdentifier
    tenant_id: SafeIdentifier
    scenario: W5Scenario
    sample_ref: SafeIdentifier
    reviewer_id: SafeIdentifier
    reviewed_at: datetime
    outcome: W5ReviewDecision
    reason: str = Field(min_length=1, max_length=2000)
    criteria: tuple[HU03CriterionResultV1, ...]
    artifact_promoted: Literal[False] = False
    provider_authorized: Literal[False] = False
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False

    @model_validator(mode="after")
    def _validate_hu03(self) -> HU03ReviewRecordV1:
        _require_utc(self.reviewed_at, "HU-03 review time")
        if not self.reason.strip():
            raise ValueError("HU-03 reason cannot be blank")
        actual = tuple(item.criterion for item in self.criteria)
        if actual != HU03_CRITERIA:
            raise ValueError("HU-03 requires exactly the four canonical criteria in order")
        passed = tuple(item.passed for item in self.criteria)
        if self.outcome == "pass" and not all(passed):
            raise ValueError("pass requires all HU-03 criteria to pass")
        if self.outcome != "pass" and all(passed):
            raise ValueError("revise or reject requires at least one failed criterion")
        return self


class ScenarioHumanReviewRecordV1(_StrictFrozenModel):
    version: Literal["w5-human-review.v1"] = W5_REVIEW_VERSION
    record_id: SafeIdentifier
    plan_id: SafeIdentifier
    tenant_id: SafeIdentifier
    scenario: W5Scenario
    sample_ref: SafeIdentifier
    review_gate: W5ReviewGate
    reviewer_id: SafeIdentifier
    reviewed_at: datetime
    decision: W5ReviewDecision
    reason: str = Field(min_length=1, max_length=2000)
    evidence_refs: tuple[SafeIdentifier, ...]
    artifact_promoted: Literal[False] = False
    provider_authorized: Literal[False] = False
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False

    @model_validator(mode="after")
    def _validate_review(self) -> ScenarioHumanReviewRecordV1:
        _require_utc(self.reviewed_at, "scenario review time")
        if not self.reason.strip():
            raise ValueError("scenario review reason cannot be blank")
        if not self.evidence_refs:
            raise ValueError("scenario review requires evidence refs")
        if self.review_gate == "hu03":
            raise ValueError("HU-03 must use its canonical rubric record")
        return self


class W5HumanReviewPacketV1(_StrictFrozenModel):
    version: Literal["w5-human-review.v1"] = W5_REVIEW_VERSION
    packet_id: SafeIdentifier
    plan_id: SafeIdentifier
    tenant_id: SafeIdentifier
    scenario: W5Scenario
    sample_ref: SafeIdentifier
    hu03: HU03ReviewRecordV1 | None
    scenario_reviews: tuple[ScenarioHumanReviewRecordV1, ...]
    artifact_promoted: Literal[False] = False
    provider_authorized: Literal[False] = False
    publish_allowed: Literal[False] = False
    delivery_accepted: Literal[False] = False


def _assert_review_scope(
    plan: W5ScenarioPlanDraftV1,
    record: HU03ReviewRecordV1 | ScenarioHumanReviewRecordV1,
) -> None:
    if record.plan_id != plan.plan_id:
        raise ValueError("review plan mismatch")
    if record.tenant_id != plan.tenant_id:
        raise ValueError("review tenant mismatch")
    if record.scenario != plan.scenario:
        raise ValueError("review scenario mismatch")
    if record.sample_ref != plan.sample_ref:
        raise ValueError("review sample mismatch")
    if record.reviewed_at < plan.created_at:
        raise ValueError("review cannot occur before plan creation")
    if record.reviewed_at >= plan.expires_at:
        raise ValueError("review must occur before plan expiry")


def validate_w5_review_packet(
    plan: W5ScenarioPlanDraftV1,
    packet: W5HumanReviewPacketV1,
) -> W5HumanReviewPacketV1:
    """Validate review evidence without promoting artifacts or authority."""

    if packet.plan_id != plan.plan_id:
        raise ValueError("review packet plan mismatch")
    if packet.tenant_id != plan.tenant_id:
        raise ValueError("review packet tenant mismatch")
    if packet.scenario != plan.scenario:
        raise ValueError("review packet scenario mismatch")
    if packet.sample_ref != plan.sample_ref:
        raise ValueError("review packet sample mismatch")

    expected_gates = tuple(
        gate for gate in plan.required_human_gates if gate != "hu03"
    )
    actual_gates = tuple(record.review_gate for record in packet.scenario_reviews)
    if actual_gates != expected_gates:
        raise ValueError("review gates do not match the scenario contract")
    hu03_required = "hu03" in plan.required_human_gates
    if hu03_required != (packet.hu03 is not None):
        raise ValueError("HU-03 record presence does not match the scenario contract")

    for record in packet.scenario_reviews:
        _assert_review_scope(plan, record)
    if packet.hu03 is not None:
        _assert_review_scope(plan, packet.hu03)
    return packet


__all__ = [
    "HU03Criterion",
    "HU03CriterionResultV1",
    "HU03ReviewRecordV1",
    "HU03_CRITERIA",
    "ScenarioHumanReviewRecordV1",
    "W5HumanReviewPacketV1",
    "W5ProviderJobCategory",
    "W5ReviewDecision",
    "W5ReviewGate",
    "W5Scenario",
    "W5ScenarioContractV1",
    "W5ScenarioPlanDraftV1",
    "build_w5_plan_draft",
    "get_w5_scenario_contract",
    "validate_w5_plan_draft_json",
    "validate_w5_review_packet",
]
