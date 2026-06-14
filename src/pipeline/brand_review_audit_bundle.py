"""Evidence-bounded audit package for reviewed brand token readiness."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.models.commercial_contracts import AllowedUse, BrandAssetToken, CandidateTokenLedger
from src.pipeline.brand_token_review import BrandTokenReviewReport

BRAND_REVIEW_AUDIT_EVIDENCE_LEVEL = "L2-fixture-or-dry-run"


class BrandReviewAuditBundle(BaseModel):
    """UI/API-safe review summary; token payloads and source bodies are absent."""

    model_config = ConfigDict(extra="forbid")

    audit_bundle_id: str
    brand_id: str
    source_ledger_status: str
    approved_token_count: int = 0
    rejected_token_ids: list[str] = Field(default_factory=list)
    skipped_token_ids: list[str] = Field(default_factory=list)
    evidence_level: str = BRAND_REVIEW_AUDIT_EVIDENCE_LEVEL
    approved_for_runtime_injection: bool = False
    forbidden_claims: list[str] = Field(default_factory=list)
    next_evidence: list[str] = Field(default_factory=list)


def build_brand_review_audit_bundle(
    ledger: CandidateTokenLedger,
    *,
    review_report: BrandTokenReviewReport | None = None,
    required_use: AllowedUse = AllowedUse.GENERATION,
) -> BrandReviewAuditBundle:
    """Summarize explicit brand-token review without mutating candidate tokens."""
    if review_report is None:
        return _candidate_only_bundle(ledger)
    if review_report.brand_id != ledger.brand_id:
        raise ValueError("brand review report brand_id must match candidate ledger brand_id")

    approved_tokens = [
        token
        for token in review_report.approved_tokens
        if _token_is_runtime_ready(token, required_use=required_use)
    ]
    approved = len(approved_tokens) > 0
    return BrandReviewAuditBundle(
        audit_bundle_id=f"brab_{ledger.brand_id}_reviewed",
        brand_id=ledger.brand_id,
        source_ledger_status=review_report.source_ledger_status or ledger.status,
        approved_token_count=len(approved_tokens),
        rejected_token_ids=list(review_report.rejected_token_ids),
        skipped_token_ids=list(review_report.skipped_token_ids),
        approved_for_runtime_injection=approved,
        forbidden_claims=_forbidden_claims(candidate_only=not approved),
        next_evidence=_next_evidence(approved=approved),
    )


def _candidate_only_bundle(ledger: CandidateTokenLedger) -> BrandReviewAuditBundle:
    return BrandReviewAuditBundle(
        audit_bundle_id=f"brab_{ledger.brand_id}_candidate_only",
        brand_id=ledger.brand_id,
        source_ledger_status=ledger.status,
        approved_token_count=0,
        rejected_token_ids=[],
        skipped_token_ids=[token.token_id for token in ledger.candidate_tokens],
        approved_for_runtime_injection=False,
        forbidden_claims=_forbidden_claims(candidate_only=True),
        next_evidence=[
            "apply explicit brand token review decisions with approved rights and generation scope",
            "build reviewed BrandConstraintBundle before runtime injection",
        ],
    )


def _token_is_runtime_ready(token: BrandAssetToken, *, required_use: AllowedUse) -> bool:
    return token.is_approved_for_bundle() and required_use in token.allowed_uses


def _forbidden_claims(*, candidate_only: bool) -> list[str]:
    claims = [
        "provider job submitted",
        "delivery accepted",
        "publish allowed",
        "customer evidence collected",
        "commercial production ready",
    ]
    if candidate_only:
        claims.insert(0, "candidate ledger approved for runtime injection")
        claims.insert(1, "approved brand tokens available")
    return claims


def _next_evidence(*, approved: bool) -> list[str]:
    if not approved:
        return [
            "approve at least one generation-scoped token through explicit brand review",
            "rerun brand review audit bundle after rights evidence is attached",
        ]
    return [
        "build reviewed BrandConstraintBundle from approved tokens",
        "run runtime injection and prompt preview dry-run gates before provider use",
        "keep provider calls disabled until explicit authorized-live approval exists",
    ]
