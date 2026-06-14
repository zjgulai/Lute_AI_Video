from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.models.commercial_contracts import LicenseStatus, TokenStatus, TokenStrength
from src.pipeline.brand_token_intake import build_candidate_ledger_from_token_vault

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_video"
TOKEN_VAULT_FIXTURE = FIXTURE_ROOT / "momcozy_token_vault_minimal.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "brand_token_intake.py"


def test_token_vault_intake_builds_candidate_only_ledger():
    report = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE)

    assert report.brand_id == "momcozy"
    assert report.evidence_level == "L2-fixture-or-dry-run"
    assert report.token_count == 3
    assert report.approved_token_count == 0
    assert report.ledger.approved_token_count == 0
    assert {token.status for token in report.ledger.candidate_tokens} == {TokenStatus.CANDIDATE}
    assert {token.license_status for token in report.ledger.candidate_tokens} == {LicenseStatus.UNKNOWN}


def test_token_vault_intake_maps_layers_to_strength_scope_and_summary():
    report = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE)
    tokens = {token.token_type: token for token in report.ledger.candidate_tokens}

    assert tokens["brand_soul"].strength == TokenStrength.HARD_FOR_REVIEW_ONLY
    assert tokens["brand_soul"].scenario_scope == ["s1", "s2", "s3", "s4", "s5"]
    assert tokens["brand_soul"].step_scope == ["strategy", "scripts", "caption", "audit"]
    assert tokens["brand_soul"].payload == {}
    assert tokens["brand_soul"].payload_summary == ["Always Put Moms First. The Cozy Reformer."]
    assert tokens["brand_soul"].source_refs == [
        "Momcozy/momcozy_quick_reference.md#section:brand_soul"
    ]

    assert tokens["copy_rules"].strength == TokenStrength.HARD_FOR_REVIEW_ONLY
    assert tokens["copy_rules"].scenario_scope == ["s1", "s2", "s3", "s5"]
    assert tokens["design_system"].strength == TokenStrength.SOFT
    assert tokens["design_system"].modality == "structured_data"
    assert "primary: #E30022" in tokens["design_system"].payload_summary


def test_token_vault_intake_respects_max_tokens_and_keeps_unique_ids():
    report = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE, max_tokens=2)

    token_ids = [token.token_id for token in report.ledger.candidate_tokens]
    assert len(token_ids) == 2
    assert len(set(token_ids)) == 2
    assert all(token_id.startswith("bat_momcozy_") for token_id in token_ids)


def test_brand_token_intake_cli_outputs_parseable_json_without_approving_tokens():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(TOKEN_VAULT_FIXTURE)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["brand_id"] == "momcozy"
    assert payload["ledger"]["approved_token_count"] == 0
    assert {
        token["status"] for token in payload["ledger"]["candidate_tokens"]
    } == {"candidate"}
