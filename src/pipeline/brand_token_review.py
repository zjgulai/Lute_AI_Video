"""Explicit review boundary for candidate brand tokens."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    BrandConstraintBundle,
    CandidateTokenLedger,
    LicenseStatus,
    TokenReview,
    TokenStatus,
)


class BrandTokenReviewDecision(BaseModel):
    token_id: str
    decision: Literal["approve", "reject"]
    reviewed_by: str
    reviewed_at: str
    review_notes: str | None = None
    rights_ref: str | None = None
    license_status: LicenseStatus = LicenseStatus.UNKNOWN
    allowed_uses: list[AllowedUse] = Field(default_factory=list)

    @model_validator(mode="after")
    def _approval_requires_rights_and_generation_scope(self) -> BrandTokenReviewDecision:
        if self.decision != "approve":
            return self
        if not self.reviewed_by or not self.reviewed_at:
            raise ValueError("approved token review requires reviewer and reviewed_at")
        if self.license_status != LicenseStatus.APPROVED:
            raise ValueError("approved token review requires approved license status")
        if AllowedUse.GENERATION not in self.allowed_uses:
            raise ValueError("approved token review requires generation allowed use")
        if not self.rights_ref:
            raise ValueError("approved token review requires rights_ref")
        return self


class BrandTokenReviewReport(BaseModel):
    brand_id: str
    source_ledger_status: str
    reviewed_token_count: int
    approved_token_count: int
    rejected_token_ids: list[str] = Field(default_factory=list)
    skipped_token_ids: list[str] = Field(default_factory=list)
    approved_tokens: list[BrandAssetToken] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def apply_brand_token_review(
    ledger: CandidateTokenLedger,
    decisions: list[BrandTokenReviewDecision],
) -> BrandTokenReviewReport:
    """Apply explicit review decisions without mutating the candidate ledger."""
    decision_by_id = {decision.token_id: decision for decision in decisions}
    approved_tokens: list[BrandAssetToken] = []
    rejected_token_ids: list[str] = []
    skipped_token_ids: list[str] = []

    for token in ledger.candidate_tokens:
        decision = decision_by_id.get(token.token_id)
        if decision is None:
            skipped_token_ids.append(token.token_id)
            continue
        if decision.decision == "reject":
            rejected_token_ids.append(token.token_id)
            continue
        approved_tokens.append(_approved_token_from_decision(token, decision))

    return BrandTokenReviewReport(
        brand_id=ledger.brand_id,
        source_ledger_status=ledger.status,
        reviewed_token_count=len(decisions),
        approved_token_count=len(approved_tokens),
        rejected_token_ids=rejected_token_ids,
        skipped_token_ids=skipped_token_ids,
        approved_tokens=approved_tokens,
    )


def build_brand_constraint_bundle_from_review(
    report: BrandTokenReviewReport,
    *,
    scenario: str,
    step: str,
    platform: str | None = None,
) -> BrandConstraintBundle:
    return BrandConstraintBundle.build_approved(
        bundle_id=f"bcb_{report.brand_id}_{scenario}_{step}_reviewed",
        brand_id=report.brand_id,
        scenario=scenario,
        step=step,
        platform=platform,
        tokens=report.approved_tokens,
    )


def _approved_token_from_decision(
    token: BrandAssetToken,
    decision: BrandTokenReviewDecision,
) -> BrandAssetToken:
    return token.model_copy(deep=True, update={
        "status": TokenStatus.APPROVED,
        "license_status": decision.license_status,
        "allowed_uses": decision.allowed_uses,
        "rights_ref": decision.rights_ref,
        "rights_gate": "explicit_review_approved",
        "review": TokenReview(
            review_status="approved",
            reviewed_by=decision.reviewed_by,
            reviewed_at=decision.reviewed_at,
            review_notes=decision.review_notes,
        ),
    })
