from __future__ import annotations

import json
from pathlib import Path

from src.models.commercial_contracts import (
    AllowedUse,
    BrandAssetToken,
    CandidateTokenLedger,
    LicenseStatus,
    TokenReview,
    TokenStatus,
    TokenStrength,
)
from src.pipeline.brand_review_audit_bundle import build_brand_review_audit_bundle
from src.pipeline.brand_token_intake import build_candidate_ledger_from_token_vault
from src.pipeline.brand_token_review import (
    BrandTokenReviewDecision,
    BrandTokenReviewReport,
    apply_brand_token_review,
)

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_video"
TOKEN_VAULT_FIXTURE = FIXTURE_ROOT / "momcozy_token_vault_minimal.json"


def test_candidate_ledger_alone_blocks_runtime_injection_without_payload_leak():
    ledger = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE).ledger

    bundle = build_brand_review_audit_bundle(ledger)
    payload = bundle.model_dump(mode="json")
    serialized = json.dumps(payload)

    assert bundle.brand_id == "momcozy"
    assert bundle.source_ledger_status == "draft"
    assert bundle.evidence_level == "L2-fixture-or-dry-run"
    assert bundle.approved_token_count == 0
    assert bundle.approved_for_runtime_injection is False
    assert bundle.skipped_token_ids == [token.token_id for token in ledger.candidate_tokens]
    assert "candidate ledger approved for runtime injection" in bundle.forbidden_claims
    assert "provider job submitted" in bundle.forbidden_claims
    assert "payload" not in serialized
    assert "Always Put Moms First" not in serialized


def test_explicit_review_report_with_generation_scope_allows_runtime_injection_readiness():
    ledger = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE).ledger
    candidate = ledger.candidate_tokens[0]
    review_report = apply_brand_token_review(
        ledger,
        decisions=[
            BrandTokenReviewDecision(
                token_id=candidate.token_id,
                decision="approve",
                reviewed_by="brand_reviewer",
                reviewed_at="2026-06-04T00:00:00Z",
                rights_ref="rights_momcozy_brand_soul_fixture",
                license_status=LicenseStatus.APPROVED,
                allowed_uses=[AllowedUse.GENERATION],
            )
        ],
    )

    bundle = build_brand_review_audit_bundle(ledger, review_report=review_report)
    serialized = json.dumps(bundle.model_dump(mode="json"))

    assert bundle.audit_bundle_id == "brab_momcozy_reviewed"
    assert bundle.approved_token_count == 1
    assert bundle.approved_for_runtime_injection is True
    assert bundle.skipped_token_ids == [token.token_id for token in ledger.candidate_tokens[1:]]
    assert bundle.rejected_token_ids == []
    assert "provider job submitted" in bundle.forbidden_claims
    assert "candidate ledger approved for runtime injection" not in bundle.forbidden_claims
    assert "runtime injection and prompt preview dry-run gates" in " ".join(bundle.next_evidence)
    assert "payload" not in serialized


def test_review_report_without_generation_scope_stays_blocked_and_sanitized():
    ledger = CandidateTokenLedger(
        brand_id="momcozy",
        status="draft",
        candidate_tokens=[_candidate_token()],
    )
    approved_reference_only = ledger.candidate_tokens[0].model_copy(
        deep=True,
        update={
            "status": TokenStatus.APPROVED,
            "license_status": LicenseStatus.APPROVED,
            "allowed_uses": [AllowedUse.REFERENCE],
            "rights_ref": "rights_reference_only_fixture",
            "review": TokenReview(
                review_status="approved",
                reviewed_by="brand_reviewer",
                reviewed_at="2026-06-04T00:00:00Z",
            ),
        },
    )
    review_report = BrandTokenReviewReport(
        brand_id="momcozy",
        source_ledger_status="draft",
        reviewed_token_count=1,
        approved_token_count=1,
        approved_tokens=[approved_reference_only],
    )

    bundle = build_brand_review_audit_bundle(ledger, review_report=review_report)
    serialized = json.dumps(bundle.model_dump(mode="json"))

    assert bundle.approved_token_count == 0
    assert bundle.approved_for_runtime_injection is False
    assert "approve at least one generation-scoped token" in bundle.next_evidence[0]
    assert "must-not-leak" not in serialized
    assert "payload" not in serialized


def _candidate_token() -> BrandAssetToken:
    return BrandAssetToken(
        token_id="bat_momcozy_reference_only_candidate",
        brand_id="momcozy",
        token_type="brand_voice",
        status=TokenStatus.CANDIDATE,
        strength=TokenStrength.HARD_FOR_REVIEW_ONLY,
        payload={"raw": "must-not-leak"},
        payload_summary=["must-not-leak"],
        license_status=LicenseStatus.UNKNOWN,
    )
