from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.no_token_commercial_benchmark import build_no_token_commercial_benchmark_report

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "no_token_commercial_benchmark.py"


def test_no_token_commercial_benchmark_report_is_l2_and_no_provider_side_effect():
    report = build_no_token_commercial_benchmark_report()
    payload = report.model_dump(mode="json")
    serialized = json.dumps(payload)

    assert report.evidence_level == "L2-fixture-or-dry-run"
    assert report.provider_calls_made is False
    assert report.authorized_live is False
    assert report.blocked_count == 1
    assert report.review_required_count == 3
    assert {check.name for check in report.checks} == {
        "brand_review_candidate_only",
        "runtime_injection_reviewed_bundle",
        "prompt_preview_audit",
        "commercial_quality_gate",
        "production_job_ledger",
        "longform_audit",
    }
    assert any(check.status == "prepared" for check in report.checks)
    assert "provider job submitted" in report.forbidden_claims
    assert "delivery accepted" in report.forbidden_claims
    assert "publish allowed" in report.forbidden_claims
    assert "payload" not in serialized
    assert "must-not-leak" not in serialized


def test_no_token_commercial_benchmark_cli_outputs_parseable_report():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["evidence_level"] == "L2-fixture-or-dry-run"
    assert payload["provider_calls_made"] is False
    assert payload["authorized_live"] is False
    assert payload["blocked_count"] == 1
    assert payload["review_required_count"] == 3
    assert "provider job submitted" in payload["forbidden_claims"]
    assert "payload" not in result.stdout
