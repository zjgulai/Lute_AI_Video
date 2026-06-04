"""Evidence-bounded longform production audit bundle."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from src.models.commercial_contracts import (
    AuditEvidenceBundle,
    GateDecision,
    LongformProductionContract,
    QualityContract,
    RepairAction,
    RepairPlan,
)
from src.quality.commercial_gate import evaluate_quality_contract

LONGFORM_AUDIT_EVIDENCE_LEVEL = "L2-fixture-or-dry-run"


@dataclass(frozen=True)
class LongformFailure:
    check: str
    reason: str
    evidence_ref: str | None = None


class LongformAuditBundle(BaseModel):
    """UI/API-safe longform gate package; no media, prompt, or source body."""

    model_config = ConfigDict(extra="forbid")

    audit_bundle_id: str
    longform_contract_id: str
    quality_contract_id: str
    evidence_bundle_id: str
    scenario: str
    brand_id: str
    target_duration_seconds: int
    evidence_level: str = LONGFORM_AUDIT_EVIDENCE_LEVEL
    gate_decision: GateDecision
    repair_plan: RepairPlan
    delivery_accepted: bool = False
    publish_allowed: bool = False
    forbidden_claims: list[str] = Field(default_factory=list)
    next_evidence: list[str] = Field(default_factory=list)


def build_longform_audit_bundle(
    *,
    longform_contract: LongformProductionContract,
    quality_contract: QualityContract,
    evidence: AuditEvidenceBundle,
    advisory_scores: dict[str, float] | None = None,
) -> LongformAuditBundle:
    """Evaluate longform delivery floors without live provider or publish side effects."""
    gate_result = evaluate_quality_contract(quality_contract, evidence, advisory_scores=advisory_scores)
    existing_failure_checks = {failure.check for failure in gate_result.blocking.failures}
    longform_failures = [
        failure
        for failure in [
            *_structure_failures(longform_contract),
            *_evidence_floor_failures(longform_contract, evidence),
        ]
        if failure.check not in existing_failure_checks
    ]
    repair_plan = _merge_repair_plan(
        contract=quality_contract,
        evidence=evidence,
        base_plan=gate_result.repair_plan,
        longform_failures=longform_failures,
    )
    gate_decision = _longform_gate_decision(
        contract=quality_contract,
        evidence=evidence,
        base_decision=gate_result.gate_decision,
        repair_plan=repair_plan,
        longform_failures=longform_failures,
    )

    return LongformAuditBundle(
        audit_bundle_id=f"lfab_{longform_contract.contract_id}_{evidence.evidence_bundle_id}",
        longform_contract_id=longform_contract.contract_id,
        quality_contract_id=quality_contract.contract_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        scenario=longform_contract.scenario,
        brand_id=longform_contract.brand_id,
        target_duration_seconds=longform_contract.target_duration_seconds,
        gate_decision=gate_decision,
        repair_plan=repair_plan,
        delivery_accepted=False,
        publish_allowed=False,
        forbidden_claims=_forbidden_claims(),
        next_evidence=_next_evidence(gate_decision.status),
    )


def _structure_failures(contract: LongformProductionContract) -> list[LongformFailure]:
    failures: list[LongformFailure] = []
    if contract.target_duration_seconds >= 90:
        manifest = contract.timeline_manifest
        if manifest is None or not manifest.timeline_blocks:
            failures.append(LongformFailure(
                check="longform_timeline_blocks_present",
                reason="90s+ longform output requires timeline blocks",
                evidence_ref=contract.timeline_manifest_id,
            ))
    if (
        contract.target_duration_seconds >= 300
        and contract.shot_ledger is not None
        and contract.shot_ledger.shot_count <= 1
    ):
        failures.append(LongformFailure(
            check="longform_shot_structure_pass",
            reason="300s longform output cannot be represented as a single-shot structure",
            evidence_ref=contract.shot_ledger.shot_ledger_id,
        ))
    return failures


def _evidence_floor_failures(
    contract: LongformProductionContract,
    evidence: AuditEvidenceBundle,
) -> list[LongformFailure]:
    failures: list[LongformFailure] = []
    rights_check = "footage_rights_pass" if contract.scenario == "s4" else "source_rights_pass"
    if not evidence.rights_evidence_refs:
        failures.append(LongformFailure(check=rights_check, reason="missing longform source or footage rights evidence"))
    if not evidence.source_fingerprint_refs:
        failures.append(LongformFailure(check="source_fingerprint_pass", reason="missing source fingerprint evidence"))
    if not evidence.timeline_manifest_refs:
        failures.append(LongformFailure(check="timeline_manifest_pass", reason="missing timeline manifest evidence"))
    if not evidence.edit_decision_list_refs:
        failures.append(LongformFailure(check="edl_pass", reason="missing edit decision list evidence"))
    if not evidence.caption_safe_zone_refs:
        failures.append(LongformFailure(check="caption_safe_zone_pass", reason="missing caption safe-zone evidence"))
    elif evidence.caption_safe_zone_violations:
        failures.append(LongformFailure(
            check="caption_safe_zone_pass",
            reason="caption safe-zone violations present",
            evidence_ref=",".join(evidence.caption_safe_zone_violations),
        ))
    return failures


def _merge_repair_plan(
    *,
    contract: QualityContract,
    evidence: AuditEvidenceBundle,
    base_plan: RepairPlan,
    longform_failures: list[LongformFailure],
) -> RepairPlan:
    actions = list(base_plan.actions)
    for failure in longform_failures:
        actions.append(RepairAction(
            action_id=f"repair_{evidence.evidence_bundle_id}_{len(actions) + 1:02d}",
            check=failure.check,
            severity="blocker",
            evidence_ref=failure.evidence_ref,
            recommendation=_repair_recommendation(failure),
            required_before="delivery_acceptance",
        ))
    return RepairPlan(
        plan_id=f"repair_{evidence.evidence_bundle_id}",
        contract_id=contract.contract_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        actions=actions,
    )


def _longform_gate_decision(
    *,
    contract: QualityContract,
    evidence: AuditEvidenceBundle,
    base_decision: GateDecision,
    repair_plan: RepairPlan,
    longform_failures: list[LongformFailure],
) -> GateDecision:
    reasons = [*base_decision.reasons, *[failure.reason for failure in longform_failures]]
    blocking_count = base_decision.blocking_failure_count + len(longform_failures)
    status = "blocked" if blocking_count > 0 else "review_required"
    if not reasons and status == "review_required":
        reasons = ["longform blocking passed; human review required before delivery acceptance"]
    return GateDecision(
        decision_id=f"gate_{evidence.evidence_bundle_id}",
        contract_id=contract.contract_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        status=status,
        publish_allowed=False,
        requires_human_review=True,
        blocking_failure_count=blocking_count,
        advisory_warning_count=base_decision.advisory_warning_count,
        reasons=reasons,
        repair_plan_id=repair_plan.plan_id if repair_plan.actions else None,
    )


def _repair_recommendation(failure: LongformFailure) -> str:
    if failure.check == "longform_timeline_blocks_present":
        return "attach timeline blocks before longform delivery acceptance"
    if failure.check == "longform_shot_structure_pass":
        return "split 300s longform output into multiple shots or scenes before delivery acceptance"
    if failure.check in {"source_rights_pass", "footage_rights_pass"}:
        return "attach reviewed longform source or footage rights evidence"
    if failure.check == "source_fingerprint_pass":
        return "attach source fingerprint evidence before remix or cutdown delivery"
    if failure.check == "timeline_manifest_pass":
        return "attach timeline manifest evidence before longform delivery acceptance"
    if failure.check == "edl_pass":
        return "attach edit decision list evidence before longform delivery acceptance"
    if failure.check == "caption_safe_zone_pass":
        return "repair caption safe-zone evidence before delivery acceptance"
    return "repair longform blocking evidence before delivery acceptance"


def _forbidden_claims() -> list[str]:
    return [
        "provider job submitted",
        "delivery accepted",
        "publish allowed",
        "customer evidence collected",
        "commercial production ready",
    ]


def _next_evidence(status: str) -> list[str]:
    if status == "blocked":
        return [
            "repair blocker checks and rerun longform audit bundle",
            "keep provider calls disabled until explicit authorized-live approval exists",
        ]
    return [
        "complete human review before delivery acceptance",
        "run no-token commercial benchmark before any authorized-live smoke",
    ]
