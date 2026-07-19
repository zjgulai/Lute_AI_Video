from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.token_smoke_preflight import (
    ACCOUNT_READINESS_RECORD_ENV,
    ACCOUNT_READINESS_SCOPE,
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    DEFAULT_AUTH_BUDGET_LIMIT,
    DEFAULT_AUTH_BUDGET_LIMIT_USD,
    DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
    DEFAULT_AUTH_TEST_SCOPE,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
    SAMPLE_PLAN_REF,
    build_token_smoke_preflight_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_authorized_live_approval_record.py"


def test_builder_writes_private_record_that_preflight_accepts(tmp_path: Path):
    output_path = tmp_path / "authorized-live-approval.json"
    account_readiness = _write_account_readiness_record(tmp_path)
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
    assert payload["expires_at"] == "2026-06-06T20:00:00Z"
    assert payload["provider_model_scope"] == DEFAULT_AUTH_PROVIDER_MODEL_SCOPE
    assert payload["test_scope"] == DEFAULT_AUTH_TEST_SCOPE
    assert payload["budget_limit_usd"] == DEFAULT_AUTH_BUDGET_LIMIT_USD
    assert payload["sample_plan"]["scenarios"] == ["toolbox"]
    assert payload["sample_plan"]["toolbox_tool_ids"] == ["product-image", "ecommerce-visual", "storyboard"]
    assert payload["sample_plan"]["asset_package"]["asset_status"] == "pending_review"
    assert "sk_fixture_secret" not in output_path.read_text()

    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(output_path)
    env[ACCOUNT_READINESS_RECORD_ENV] = str(account_readiness)
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


def test_required_statement_locks_production_asset_review_boundary():
    statement = _approval_statement()

    assert "https://video.lute-tlz-dddd.top" in statement
    assert "poyo image + poyo Seedance" in statement
    assert "自动重试 0" in statement
    assert "不发布" in statement
    assert "不写入正式 brand token" in statement
    assert "产物只进入待审素材库" in statement


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
        provider_model_scope=DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
        test_scope=DEFAULT_AUTH_TEST_SCOPE,
        budget_limit=DEFAULT_AUTH_BUDGET_LIMIT,
    )


def _ready_env() -> dict[str, str]:
    env = {RUN_TOKEN_SMOKE_ENV: "1"}
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env


def _write_account_readiness_record(tmp_path: Path) -> Path:
    path = tmp_path / "provider-account-readiness.json"
    payload = {
        "template_only": False,
        "readiness_id": "account_readiness_builder_fixture",
        "scope": ACCOUNT_READINESS_SCOPE,
        "evidence_level": "L3-production-read-only",
        "no_provider_call": True,
        "provider": "poyo",
        "checked_by": "user",
        "checked_at": "2026-06-06T00:00:00Z",
        "provider_dashboard_balance_confirmed": True,
        "api_key_configured_in_runtime_env": True,
        "api_key_secret_not_recorded": True,
        "available_credit_usd": 3.0,
        "minimum_required_credit_usd": 3.0,
        "provider_revalidation_ref": "configs/poyo-current-provider-revalidation-contract.json",
        "sample_plan_ref": SAMPLE_PLAN_REF,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path
