from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.token_smoke_preflight import (
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_REF,
    build_token_smoke_preflight_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_authorized_live_approval_record.py"


def test_builder_writes_private_record_that_preflight_accepts(tmp_path: Path):
    output_path = tmp_path / "authorized-live-approval.json"
    statement = _approval_statement()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--approved-by",
            "pray",
            "--approved-at",
            "2026-06-06T16:00:00Z",
            "--approval-statement",
            statement,
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
    assert payload["scope"] == APPROVAL_SCOPE
    assert payload["sample_plan_ref"] == SAMPLE_PLAN_REF
    assert payload["approval_statement"] == statement
    assert payload["sample_plan"]["scenarios"] == ["fast", "s1"]
    assert "sk_fixture_secret" not in output_path.read_text()

    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(output_path)
    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is False
    assert report.provider_call_allowed is True


def test_builder_rejects_loose_approval_statement(tmp_path: Path):
    output_path = tmp_path / "authorized-live-approval.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--approved-by",
            "pray",
            "--approval-statement",
            "同意下一步",
            "--output",
            str(output_path),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "approval_statement must exactly match" in result.stderr
    assert not output_path.exists()


def test_builder_refuses_formal_repo_output_path():
    blocked_path = REPO_ROOT / "configs" / "should-not-write-approval.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--approved-by",
            "pray",
            "--approval-statement",
            _approval_statement(),
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


def test_builder_prints_required_statement_without_output():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--approved-by",
            "pray",
            "--approval-statement",
            "ignored-for-print-mode",
            "--print-required-statement",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == _approval_statement()


def _approval_statement() -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(
        provider="poyo",
        model="seedance-2",
        budget_limit="$1.00",
    )


def _ready_env() -> dict[str, str]:
    env = {RUN_TOKEN_SMOKE_ENV: "1"}
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env
