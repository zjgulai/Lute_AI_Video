from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.models.commercial_contracts import AllowedUse, LicenseStatus, TokenStatus
from src.pipeline.brand_token_intake import build_candidate_ledger_from_token_vault
from src.pipeline.brand_token_review import (
    BrandTokenReviewDecision,
    apply_brand_token_review,
    build_brand_constraint_bundle_from_review,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_video"
TOKEN_VAULT_FIXTURE = FIXTURE_ROOT / "momcozy_token_vault_minimal.json"


def test_approval_decision_requires_approved_rights_and_generation_scope():
    with pytest.raises(ValidationError, match="approved license status"):
        BrandTokenReviewDecision(
            token_id="bat_candidate",
            decision="approve",
            reviewed_by="brand_reviewer",
            reviewed_at="2026-06-04T00:00:00Z",
            license_status=LicenseStatus.UNKNOWN,
            allowed_uses=[AllowedUse.GENERATION],
            rights_ref="rights_fixture",
        )

    with pytest.raises(ValidationError, match="generation allowed use"):
        BrandTokenReviewDecision(
            token_id="bat_candidate",
            decision="approve",
            reviewed_by="brand_reviewer",
            reviewed_at="2026-06-04T00:00:00Z",
            license_status=LicenseStatus.APPROVED,
            allowed_uses=[],
            rights_ref="rights_fixture",
        )


def test_unreviewed_candidate_tokens_do_not_enter_brand_bundle():
    ledger = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE).ledger

    report = apply_brand_token_review(ledger, decisions=[])
    bundle = build_brand_constraint_bundle_from_review(report, scenario="s1", step="strategy")

    assert report.approved_token_count == 0
    assert report.skipped_token_ids == [token.token_id for token in ledger.candidate_tokens]
    assert bundle.hard_tokens == []
    assert bundle.soft_tokens == []
    assert ledger.approved_token_count == 0
    assert {token.status for token in ledger.candidate_tokens} == {TokenStatus.CANDIDATE}


def test_explicit_approved_review_builds_brand_constraint_bundle():
    ledger = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE).ledger
    candidate = ledger.candidate_tokens[0]
    decision = BrandTokenReviewDecision(
        token_id=candidate.token_id,
        decision="approve",
        reviewed_by="brand_reviewer",
        reviewed_at="2026-06-04T00:00:00Z",
        review_notes="approved for strategy fixture",
        rights_ref="rights_momcozy_brand_soul_fixture",
        license_status=LicenseStatus.APPROVED,
        allowed_uses=[AllowedUse.GENERATION],
    )

    report = apply_brand_token_review(ledger, decisions=[decision])
    bundle = build_brand_constraint_bundle_from_review(report, scenario="s1", step="strategy")

    assert report.approved_token_count == 1
    assert report.approved_tokens[0].status == TokenStatus.APPROVED
    assert report.approved_tokens[0].review.review_status == "approved"
    assert report.approved_tokens[0].rights_ref == "rights_momcozy_brand_soul_fixture"
    assert [token.token_id for token in bundle.hard_tokens] == [candidate.token_id]
    assert bundle.rejected_token_ids == []


def test_rejected_review_is_excluded_from_bundle():
    ledger = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE).ledger
    candidate = ledger.candidate_tokens[0]
    decision = BrandTokenReviewDecision(
        token_id=candidate.token_id,
        decision="reject",
        reviewed_by="brand_reviewer",
        reviewed_at="2026-06-04T00:00:00Z",
        review_notes="source rights unclear",
    )

    report = apply_brand_token_review(ledger, decisions=[decision])
    bundle = build_brand_constraint_bundle_from_review(report, scenario="s1", step="strategy")

    assert report.approved_token_count == 0
    assert report.rejected_token_ids == [candidate.token_id]
    assert bundle.hard_tokens == []
    assert bundle.soft_tokens == []
