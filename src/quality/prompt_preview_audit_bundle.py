"""Evidence-bounded audit bundle for runtime prompt preview dry-runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.models.commercial_contracts import GateDecision, QualityContract, RepairPlan
from src.pipeline.runtime_prompt_preview import RuntimePromptPreviewResult
from src.quality.commercial_gate import (
    AuditResult,
    evaluate_runtime_prompt_preview_gate,
)

PROMPT_PREVIEW_AUDIT_EVIDENCE_LEVEL = "L2-fixture-or-dry-run"


class PromptPreviewEvidenceBoundary(BaseModel):
    decision: Literal["blocked", "allowed-with-label"] = "blocked"
    evidence_level: str = PROMPT_PREVIEW_AUDIT_EVIDENCE_LEVEL
    supported_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    next_evidence: list[str] = Field(default_factory=list)


class PromptPreviewAuditBundle(BaseModel):
    """UI/API-safe audit package; prompt body and brand payloads are absent."""

    model_config = ConfigDict(extra="forbid")

    audit_bundle_id: str
    compile_id: str
    scenario: str
    step: str
    provider: str
    model: str
    prompt_hash: str | None = None
    preview: RuntimePromptPreviewResult
    gate_decision: GateDecision
    repair_plan: RepairPlan
    evidence_boundary: PromptPreviewEvidenceBoundary
    delivery_accepted: bool = False
    publish_allowed: bool = False


def build_prompt_preview_audit_bundle(
    *,
    contract: QualityContract,
    preview: RuntimePromptPreviewResult,
) -> PromptPreviewAuditBundle:
    """Package prompt preview gate output without upgrading evidence strength."""
    audit = evaluate_runtime_prompt_preview_gate(contract, preview)
    boundary = _build_evidence_boundary(audit)
    return PromptPreviewAuditBundle(
        audit_bundle_id=f"ppab_{preview.compile_id}",
        compile_id=preview.compile_id,
        scenario=preview.scenario,
        step=preview.step,
        provider=preview.provider,
        model=preview.model,
        prompt_hash=preview.prompt_hash,
        preview=preview,
        gate_decision=audit.gate_decision,
        repair_plan=audit.repair_plan,
        evidence_boundary=boundary,
        delivery_accepted=False,
        publish_allowed=False,
    )


def _build_evidence_boundary(audit: AuditResult) -> PromptPreviewEvidenceBoundary:
    if audit.gate_decision.status == "blocked":
        return PromptPreviewEvidenceBoundary(
            decision="blocked",
            supported_claims=[
                "dry-run prompt preview audit was evaluated",
                "blocking reasons and repair actions are available",
            ],
            forbidden_claims=_forbidden_claims(),
            next_evidence=[
                "repair blocker checks and rerun dry-run prompt preview audit",
                "keep provider calls disabled until explicit authorized-live approval exists",
            ],
        )

    return PromptPreviewEvidenceBoundary(
        decision="allowed-with-label",
        supported_claims=[
            "dry-run prompt preview produced an auditable prompt hash",
            "runtime injection and compile checks are ready for human review",
        ],
        forbidden_claims=_forbidden_claims(),
        next_evidence=[
            "complete human review before delivery acceptance",
            "obtain explicit authorization before any provider token smoke",
        ],
    )


def _forbidden_claims() -> list[str]:
    return [
        "provider job submitted",
        "delivery accepted",
        "publish allowed",
        "customer evidence collected",
        "commercial production ready",
    ]
