from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.token_smoke_preflight import (
    ACCOUNT_READINESS_SCOPE,
    SAMPLE_PLAN_REF,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_provider_account_readiness_record.py"


def test_account_readiness_builder_writes_private_secret_free_record(tmp_path: Path):
    output_path = tmp_path / "provider-account-readiness.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--checked-by",
            "pray",
            "--checked-at",
            "2026-06-06T17:00:00Z",
            "--available-credit-usd",
            "3.00",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output_path.read_text())
    assert payload["template_only"] is False
    assert payload["scope"] == ACCOUNT_READINESS_SCOPE
    assert payload["evidence_level"] == "L3-production-read-only"
    assert payload["no_provider_call"] is True
    assert payload["provider"] == "poyo"
    assert payload["available_credit_usd"] == 3.0
    assert payload["minimum_required_credit_usd"] == 3.0
    assert payload["sample_plan_ref"] == SAMPLE_PLAN_REF
    assert payload["api_key_secret_not_recorded"] is True
    assert "API_KEY" not in output_path.read_text()


def test_account_readiness_builder_rejects_underfunded_record(tmp_path: Path):
    output_path = tmp_path / "provider-account-readiness.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--checked-by",
            "pray",
            "--available-credit-usd",
            "2.99",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "available_credit_usd must cover" in result.stderr
    assert not output_path.exists()


def test_account_readiness_builder_refuses_formal_repo_output_path():
    blocked_path = REPO_ROOT / "configs" / "should-not-write-account-readiness.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--checked-by",
            "pray",
            "--available-credit-usd",
            "3.00",
            "--output",
            str(blocked_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "under tmp/ or outside the repository" in result.stderr
    assert not blocked_path.exists()
