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
    PROVIDER_REVALIDATION_REF,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_REF,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_authorized_live_test_plan_readiness_report.py"


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


def test_default_report_is_ready_for_discussion_but_not_live_execution():
    result = _run_script()

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)

    assert report["evidence_level"] == "L2-fixture-or-dry-run"
    assert report["no_provider_call"] is True
    assert report["ready_for_test_plan_discussion"] is True
    assert report["ready_for_live_execution"] is False
    assert report["provider_call_allowed"] is False
    assert report["required_authorization_statement"] == _approval_statement()
    assert report["required_private_records"]["approval_record_env"] == APPROVAL_RECORD_ENV
    assert report["required_private_records"]["account_readiness_record_env"] == ACCOUNT_READINESS_RECORD_ENV
    assert report["required_runtime_env"]["CONFIRM_P2_TOKEN_SMOKE"] == "1"
    assert report["required_runtime_env"][RUN_TOKEN_SMOKE_ENV] == "1"
    assert report["sample_plan"]["sample_plan_ref"] == SAMPLE_PLAN_REF
    assert report["sample_plan"]["limits"]["max_provider_calls"] == 2
    assert report["sample_plan"]["limits"]["max_total_cost_usd"] == 1.0
    assert report["provider_revalidation_summary"]["provider_revalidation_ref"] == PROVIDER_REVALIDATION_REF
    assert "poyo/seedance-2" in report["required_authorization_statement"]
    assert "sk_fixture_secret" not in result.stdout


def test_default_report_lists_all_discussion_artifacts_and_execution_blockers():
    result = _run_script()

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    artifact_status = {item["ref"]: item["status"] for item in report["discussion_artifacts"]}
    blocker_names = {item["name"] for item in report["execution_blockers"]}

    for ref in [
        "docs/workflows/ai-video-project-2-0-e2e-test-plan-stable.md",
        "docs/runbooks/p2-recharge-smoke-checklist.md",
        "scripts/commercial_token_smoke_preflight.py",
        "scripts/build_authorized_live_approval_record.py",
        "scripts/build_provider_account_readiness_record.py",
        "scripts/build_authorized_live_smoke_packet.py",
        "scripts/p2_recharge_smoke_checklist.py",
        SAMPLE_PLAN_REF,
        PROVIDER_REVALIDATION_REF,
    ]:
        assert artifact_status[ref] == "pass"

    assert "exact_c21_authorization_statement" in blocker_names
    assert "production_backend_keys" in blocker_names
    assert "double_execute_flags" in blocker_names
    assert "run_token_smoke" in blocker_names
    assert "authorized_live_approval" in blocker_names
    assert "api_key:POYO_API_KEY" in blocker_names
    assert "provider_account_readiness" in blocker_names


def test_report_output_must_stay_private(tmp_path: Path):
    allowed_output = tmp_path / "authorized-live-test-plan-readiness.json"

    allowed = _run_script("--output", str(allowed_output))

    assert allowed.returncode == 0, allowed.stderr
    assert allowed_output.exists()
    report = json.loads(allowed_output.read_text())
    assert report["ready_for_test_plan_discussion"] is True
    assert report["ready_for_live_execution"] is False

    blocked_path = REPO_ROOT / "configs" / "should-not-write-test-plan-readiness.json"
    blocked = _run_script("--output", str(blocked_path))

    assert blocked.returncode == 2
    assert "under tmp/ or outside the repository" in blocked.stderr
    assert not blocked_path.exists()


def test_script_source_has_no_provider_or_subprocess_execution_path():
    source = SCRIPT_PATH.read_text()

    assert "subprocess.run" not in source
    assert "requests." not in source
    assert "httpx." not in source
    assert "build_token_smoke_preflight_report" in source
    assert "ready_for_test_plan_discussion" in source
    assert "ready_for_live_execution" in source


def _approval_statement() -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(
        provider="poyo",
        model="seedance-2",
        budget_limit="$1.00",
    )
