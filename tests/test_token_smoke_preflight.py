from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.token_smoke_preflight import (
    APPROVAL_RECORD_ENV,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
    build_token_smoke_preflight_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "commercial_token_smoke_preflight.py"


def test_missing_approval_record_blocks_even_when_token_flag_and_keys_are_set():
    env = _ready_env()

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert report.evidence_level == "L2-fixture-or-dry-run"


def test_missing_run_token_smoke_blocks_even_with_valid_approval_record(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env()
    env[RUN_TOKEN_SMOKE_ENV] = "0"
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "run_token_smoke") == "block"


def test_valid_preflight_allows_harness_entry_without_provider_call(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is False
    assert report.provider_call_allowed is True
    assert {check.status for check in report.checks} == {"pass"}
    assert "sk_fixture_secret" not in report.model_dump_json()


def test_cli_exits_blocked_when_approval_is_missing():
    env = _ready_env()
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["blocked"] is True
    assert payload["provider_call_allowed"] is False
    assert "sk_fixture_secret" not in result.stdout


def _ready_env() -> dict[str, str]:
    env = {RUN_TOKEN_SMOKE_ENV: "1"}
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env


def _write_approval_record(tmp_path: Path) -> Path:
    path = tmp_path / "authorized-live-approval.json"
    path.write_text(json.dumps({
        "approval_id": "approval_fixture",
        "scope": "c9-token-smoke",
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-04T00:00:00Z",
    }))
    return path


def _check_status(report, name: str) -> str:
    for check in report.checks:
        if check.name == name:
            return check.status
    raise AssertionError(f"missing check {name}")
