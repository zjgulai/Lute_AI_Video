from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.models.commercial_contracts import AllowedUse, LicenseStatus
from src.pipeline.brand_token_intake import build_candidate_ledger_from_token_vault

FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "commercial_video"
TOKEN_VAULT_FIXTURE = FIXTURE_ROOT / "momcozy_token_vault_minimal.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "brand_review_audit.py"


def test_brand_review_audit_cli_defaults_to_candidate_only_blocked(tmp_path: Path):
    ledger_path = _write_intake_report(tmp_path)

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), str(ledger_path)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["brand_id"] == "momcozy"
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert payload["approved_token_count"] == 0
    assert payload["approved_for_runtime_injection"] is False
    assert "candidate ledger approved for runtime injection" in payload["forbidden_claims"]
    assert "payload" not in result.stdout


def test_brand_review_audit_cli_applies_explicit_review_and_writes_tmp_output(tmp_path: Path):
    intake_report = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE)
    candidate = intake_report.ledger.candidate_tokens[0]
    ledger_path = tmp_path / "intake-report.json"
    ledger_path.write_text(json.dumps(intake_report.model_dump(mode="json")))
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps({
        "decisions": [
            {
                "token_id": candidate.token_id,
                "decision": "approve",
                "reviewed_by": "brand_reviewer",
                "reviewed_at": "2026-06-04T00:00:00Z",
                "rights_ref": "rights_momcozy_cli_fixture",
                "license_status": LicenseStatus.APPROVED,
                "allowed_uses": [AllowedUse.GENERATION],
            }
        ]
    }))
    output_name = "brand-review-audit-cli-fixture.json"
    output_path = REPO_ROOT / "tmp" / "outputs" / output_name
    output_path.unlink(missing_ok=True)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            str(ledger_path),
            "--decisions",
            str(decisions_path),
            "--output",
            output_name,
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    file_payload = json.loads(output_path.read_text())
    assert payload == file_payload
    assert output_path.parent == REPO_ROOT / "tmp" / "outputs"
    assert payload["approved_token_count"] == 1
    assert payload["approved_for_runtime_injection"] is True
    assert payload["skipped_token_ids"] == [
        token.token_id for token in intake_report.ledger.candidate_tokens[1:]
    ]
    assert "provider job submitted" in payload["forbidden_claims"]
    assert "payload" not in result.stdout

    output_path.unlink(missing_ok=True)


def _write_intake_report(tmp_path: Path) -> Path:
    report = build_candidate_ledger_from_token_vault(TOKEN_VAULT_FIXTURE)
    ledger_path = tmp_path / "intake-report.json"
    ledger_path.write_text(json.dumps(report.model_dump(mode="json")))
    return ledger_path
