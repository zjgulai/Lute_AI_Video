from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from src.pipeline.token_smoke_preflight import (
    ACCOUNT_READINESS_RECORD_ENV,
    APPROVAL_RECORD_ENV,
    APPROVAL_STATEMENT_TEMPLATE,
    DEFAULT_AUTH_BUDGET_LIMIT,
    DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
    DEFAULT_AUTH_TEST_SCOPE,
    PROVIDER_REVALIDATION_REF,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_REF,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_authorized_live_smoke_packet.py"


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "API_KEY",
            "PLAYWRIGHT_API_KEY",
            "POYO_API_KEY",
            "DEEPSEEK_API_KEY",
            "SILICONFLOW_API_KEY",
            RUN_TOKEN_SMOKE_ENV,
            "CONFIRM_P2_TOKEN_SMOKE",
            APPROVAL_RECORD_ENV,
            ACCOUNT_READINESS_RECORD_ENV,
        }
    }
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_packet_is_no_token_and_contains_exact_authorization_gate():
    result = _run_script()

    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)

    assert packet["evidence_level"] == "L2-fixture-or-dry-run"
    assert packet["no_provider_call"] is True
    assert packet["provider_call_allowed"] is False
    assert packet["required_authorization_statement"] == _approval_statement()
    assert packet["sample_plan_ref"] == SAMPLE_PLAN_REF
    assert packet["provider_revalidation_ref"] == PROVIDER_REVALIDATION_REF
    assert packet["required_private_records"]["approval_record_env"] == APPROVAL_RECORD_ENV
    assert packet["required_private_records"]["account_readiness_record_env"] == ACCOUNT_READINESS_RECORD_ENV
    assert packet["required_runtime_env"]["CONFIRM_P2_TOKEN_SMOKE"] == "1"
    assert packet["required_runtime_env"][RUN_TOKEN_SMOKE_ENV] == "1"
    assert "继续下一步" in packet["rejected_confirmation_examples"]
    assert packet["provider_model_scope"] == DEFAULT_AUTH_PROVIDER_MODEL_SCOPE
    assert packet["test_scope"] == DEFAULT_AUTH_TEST_SCOPE
    assert packet["budget_limit"] == DEFAULT_AUTH_BUDGET_LIMIT
    assert "poyo/gpt-image-2 + poyo/seedance-2" in packet["required_authorization_statement"]
    assert "Momcozy 消毒器" in packet["required_authorization_statement"]
    assert "--available-credit-usd 3.00" in " ".join(packet["record_build_commands"])
    assert "scripts/p2_recharge_smoke_checklist.py --execute" in packet["execute_command_preview"]
    assert "sk_fixture_secret" not in result.stdout


def test_packet_can_include_empty_env_preflight_projection_that_stays_blocked():
    result = _run_script("--include-preflight")

    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    projection = packet["preflight_projection"]

    assert packet["preflight_env_source"] == "empty"
    assert projection["evidence_level"] == "L2-fixture-or-dry-run"
    assert projection["run_token_smoke"] is False
    assert projection["provider_call_allowed"] is False
    assert projection["blocked"] is True
    assert _check_status(projection, "run_token_smoke") == "block"
    assert _check_status(projection, "authorized_live_approval") == "block"
    assert "sk_fixture_secret" not in result.stdout


def test_packet_output_must_stay_private(tmp_path: Path):
    allowed_output = tmp_path / "authorized-live-smoke-packet.json"

    allowed = _run_script("--output", str(allowed_output))

    assert allowed.returncode == 0, allowed.stderr
    assert allowed_output.exists()
    packet = json.loads(allowed_output.read_text())
    assert packet["no_provider_call"] is True

    blocked_path = REPO_ROOT / "configs" / "should-not-write-smoke-packet.json"
    blocked = _run_script("--output", str(blocked_path))

    assert blocked.returncode == 2
    assert "under tmp/ or outside the repository" in blocked.stderr
    assert not blocked_path.exists()


def test_script_source_has_no_provider_or_subprocess_execution_path():
    source = SCRIPT_PATH.read_text()

    assert "subprocess.run" not in source
    assert "requests." not in source
    assert "provider_call_allowed\": False" in source
    assert "build_token_smoke_preflight_report" in source
    assert "p2_recharge_smoke_checklist.py --execute" in source


def _approval_statement() -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
        test_scope=DEFAULT_AUTH_TEST_SCOPE,
        budget_limit=DEFAULT_AUTH_BUDGET_LIMIT,
    )


def _check_status(projection: dict[str, object], name: str) -> str:
    checks = projection["checks"]
    assert isinstance(checks, list)
    for check in checks:
        assert isinstance(check, dict)
        if check["name"] == name:
            status = check["status"]
            assert isinstance(status, str)
            return status
    raise AssertionError(f"missing preflight check {name}")
