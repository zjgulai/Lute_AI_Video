"""Fail-closed commercial delivery gate for AI video 2.0 contracts."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from src.models.commercial_contracts import (
    AuditEvidenceBundle,
    GateDecision,
    QualityContract,
    RepairAction,
    RepairPlan,
)


class BlockingFailure(BaseModel):
    check: str
    severity: Literal["blocker"] = "blocker"
    reason: str
    evidence_ref: str | None = None


class AdvisoryCheckResult(BaseModel):
    check: str
    score: float | None = None
    status: Literal["pass", "warn", "not_evaluated"] = "not_evaluated"
    recommendation: str = ""


class BlockingResult(BaseModel):
    passed: bool
    failures: list[BlockingFailure] = Field(default_factory=list)


class AdvisoryResult(BaseModel):
    score: float = 0.0
    checks: list[AdvisoryCheckResult] = Field(default_factory=list)


class DeliveryDecision(BaseModel):
    accepted: bool = False
    publish_allowed: bool = False
    requires_human_review: bool = True
    reason: str = "blocking checks failed"


class AuditResult(BaseModel):
    audit_id: str
    contract_id: str
    evidence_bundle_id: str
    blocking: BlockingResult
    advisory: AdvisoryResult
    delivery: DeliveryDecision
    gate_decision: GateDecision
    repair_plan: RepairPlan
    checked_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


def evaluate_quality_contract(
    contract: QualityContract,
    evidence: AuditEvidenceBundle,
    advisory_scores: dict[str, float] | None = None,
) -> AuditResult:
    """Evaluate a commercial delivery contract without side effects.

    Blocking checks are fail-closed. Advisory scores can never override a
    blocking failure or missing required evidence.
    """
    failures: list[BlockingFailure] = []
    advisory_scores = advisory_scores or {}

    for required_ref in contract.required_evidence:
        if not _required_evidence_present(required_ref, evidence):
            failures.append(BlockingFailure(
                check="required_evidence",
                reason=f"missing required evidence: {required_ref}",
                evidence_ref=required_ref,
            ))

    for check in contract.blocking_checks:
        failure = _evaluate_blocking_check(check, evidence)
        if failure is not None:
            failures.append(failure)

    advisory = _evaluate_advisory_checks(contract, advisory_scores)
    blocking = BlockingResult(passed=not failures, failures=failures)
    delivery = _delivery_decision(contract, blocking)
    repair_plan = _build_repair_plan(contract, evidence, failures, advisory)
    gate_decision = _build_gate_decision(contract, evidence, blocking, advisory, delivery, repair_plan)

    return AuditResult(
        audit_id=f"audit_{evidence.evidence_bundle_id}",
        contract_id=contract.contract_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        blocking=blocking,
        advisory=advisory,
        delivery=delivery,
        gate_decision=gate_decision,
        repair_plan=repair_plan,
    )


def _required_evidence_present(required_ref: str, evidence: AuditEvidenceBundle) -> bool:
    if required_ref == "brand_bundle_id":
        return bool(evidence.brand_bundle_id)
    if required_ref == "source_token_ids":
        return bool(evidence.source_token_ids)
    if required_ref == "media_job_ids":
        return bool(evidence.media_job_ids)
    if required_ref == "prompt_hashes":
        return bool(evidence.prompt_hashes)
    if required_ref == "artifact_manifest_id":
        return bool(evidence.artifact_manifest_id)
    if required_ref == "rights_evidence_refs":
        return bool(evidence.rights_evidence_refs)
    if required_ref == "claim_evidence_refs":
        return bool(evidence.claim_evidence_refs)
    if required_ref == "source_fingerprint_refs":
        return bool(evidence.source_fingerprint_refs)
    return False


def _evaluate_blocking_check(check: str, evidence: AuditEvidenceBundle) -> BlockingFailure | None:
    if check == "media_file_exists":
        final_video = evidence.artifact_paths.get("final_video", "")
        if not final_video:
            return BlockingFailure(check=check, reason="final video path missing")
        if final_video.startswith("fixture://"):
            return None
        path = Path(final_video)
        if not path.exists() or path.stat().st_size <= 0:
            return BlockingFailure(check=check, reason="final video missing or empty", evidence_ref=final_video)
        return None

    if check == "artifact_manifest_complete":
        if not evidence.artifact_manifest_id:
            return BlockingFailure(check=check, reason="artifact manifest id missing")
        if "final_video" not in evidence.artifact_paths:
            return BlockingFailure(check=check, reason="final video artifact missing from manifest")
        return None

    if check == "rights_pass":
        if not evidence.rights_evidence_refs:
            return BlockingFailure(check=check, reason="missing rights evidence")
        return None

    if check == "hard_brand_token_pass":
        if evidence.hard_brand_token_violations:
            return BlockingFailure(
                check=check,
                reason="hard brand token violations present",
                evidence_ref=",".join(evidence.hard_brand_token_violations),
            )
        return None

    if check == "claim_substantiation_pass":
        if not evidence.claim_evidence_refs:
            return BlockingFailure(check=check, reason="missing claim evidence")
        return None

    if check == "platform_policy_pass":
        if evidence.platform_policy_violations:
            return BlockingFailure(
                check=check,
                reason="platform policy violations present",
                evidence_ref=",".join(evidence.platform_policy_violations),
            )
        return None

    if check == "children_safety_pass":
        if evidence.children_direct_reference:
            return BlockingFailure(check=check, reason="children direct reference is not allowed")
        return None

    if check == "source_fingerprint_pass":
        if not evidence.source_fingerprint_refs:
            return BlockingFailure(check=check, reason="missing source fingerprint evidence")
        return None

    if check == "c2pa_provenance_ready":
        if evidence.c2pa_status not in {"ready", "signed"}:
            return BlockingFailure(check=check, reason="C2PA provenance is not ready")
        return None

    return BlockingFailure(check=check, reason=f"unknown blocking check: {check}")


def _evaluate_advisory_checks(contract: QualityContract, scores: dict[str, float]) -> AdvisoryResult:
    checks: list[AdvisoryCheckResult] = []
    total = 0.0
    scored_count = 0

    for check in contract.advisory_checks:
        score = scores.get(check)
        threshold = contract.thresholds.get(check, 0.0)
        if score is None:
            checks.append(AdvisoryCheckResult(check=check))
            continue
        scored_count += 1
        total += score
        if score >= threshold:
            checks.append(AdvisoryCheckResult(check=check, score=score, status="pass"))
        else:
            checks.append(AdvisoryCheckResult(
                check=check,
                score=score,
                status="warn",
                recommendation=f"{check} below threshold {threshold:.2f}",
            ))

    return AdvisoryResult(score=(total / scored_count if scored_count else 0.0), checks=checks)


def _delivery_decision(contract: QualityContract, blocking: BlockingResult) -> DeliveryDecision:
    if not blocking.passed:
        return DeliveryDecision(
            accepted=False,
            publish_allowed=False,
            requires_human_review=contract.publish_policy.requires_human_review,
            reason="blocking checks failed",
        )

    return DeliveryDecision(
        accepted=not contract.publish_policy.requires_human_review,
        publish_allowed=False,
        requires_human_review=contract.publish_policy.requires_human_review,
        reason="blocking passed; human review required before publish"
        if contract.publish_policy.requires_human_review
        else "blocking passed; publish remains disabled by default",
    )


def _build_repair_plan(
    contract: QualityContract,
    evidence: AuditEvidenceBundle,
    failures: list[BlockingFailure],
    advisory: AdvisoryResult,
) -> RepairPlan:
    actions: list[RepairAction] = []

    for index, failure in enumerate(failures, start=1):
        actions.append(RepairAction(
            action_id=f"repair_{evidence.evidence_bundle_id}_{index:02d}",
            check=failure.check,
            severity="blocker",
            evidence_ref=failure.evidence_ref,
            recommendation=_repair_recommendation_for_failure(failure),
            required_before="delivery_acceptance",
        ))

    for check in advisory.checks:
        if check.status != "warn":
            continue
        actions.append(RepairAction(
            action_id=f"repair_{evidence.evidence_bundle_id}_{len(actions) + 1:02d}",
            check=check.check,
            severity="advisory",
            recommendation=check.recommendation or f"review advisory quality signal: {check.check}",
            required_before="next_review",
        ))

    return RepairPlan(
        plan_id=f"repair_{evidence.evidence_bundle_id}",
        contract_id=contract.contract_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        actions=actions,
    )


def _repair_recommendation_for_failure(failure: BlockingFailure) -> str:
    if failure.check == "required_evidence":
        return f"attach required evidence before delivery acceptance: {failure.evidence_ref}"
    if failure.check == "rights_pass":
        return "attach reviewed rights evidence before delivery acceptance"
    if failure.check == "claim_substantiation_pass":
        return "attach claim substantiation evidence or remove the claim from the cut"
    if failure.check == "children_safety_pass":
        return "remove direct child reference or route through explicit safety review"
    if failure.check == "source_fingerprint_pass":
        return "attach source fingerprint evidence before remix or cutdown delivery"
    if failure.check == "platform_policy_pass":
        return "resolve platform policy violations before delivery acceptance"
    if failure.check == "hard_brand_token_pass":
        return "repair hard brand token violations before delivery acceptance"
    if failure.check == "media_file_exists":
        return "attach a non-empty final video artifact"
    if failure.check == "artifact_manifest_complete":
        return "complete artifact manifest with final video reference"
    if failure.check == "c2pa_provenance_ready":
        return "prepare C2PA provenance evidence before delivery acceptance"
    return "define or repair the blocking check before delivery acceptance"


def _build_gate_decision(
    contract: QualityContract,
    evidence: AuditEvidenceBundle,
    blocking: BlockingResult,
    advisory: AdvisoryResult,
    delivery: DeliveryDecision,
    repair_plan: RepairPlan,
) -> GateDecision:
    advisory_warning_count = sum(1 for check in advisory.checks if check.status == "warn")
    reasons: list[str] = []

    if not blocking.passed:
        status: Literal["blocked", "review_required", "accepted"] = "blocked"
        reasons = [failure.reason for failure in blocking.failures]
    elif contract.publish_policy.requires_human_review:
        status = "review_required"
        reasons = ["blocking passed; human review required before delivery acceptance"]
    else:
        status = "accepted"
        reasons = ["blocking passed; delivery accepted, publish remains disabled by default"]

    for check in advisory.checks:
        if check.status == "warn":
            reasons.append(check.recommendation or f"advisory warning: {check.check}")

    return GateDecision(
        decision_id=f"gate_{evidence.evidence_bundle_id}",
        contract_id=contract.contract_id,
        evidence_bundle_id=evidence.evidence_bundle_id,
        status=status,
        publish_allowed=delivery.publish_allowed,
        requires_human_review=delivery.requires_human_review,
        blocking_failure_count=len(blocking.failures),
        advisory_warning_count=advisory_warning_count,
        reasons=reasons,
        repair_plan_id=repair_plan.plan_id if repair_plan.actions else None,
    )
