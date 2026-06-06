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
    assert report.approved_provider == "poyo"
    assert report.approved_model == "seedance-2"
    assert report.approved_budget_limit_usd == 1.0
    assert report.approved_max_sample_count == 2
    assert report.approved_max_provider_calls == 2
    assert report.approved_max_total_cost_usd == 1.0
    assert report.approved_per_job_cost_ceiling_usd == 0.5
    assert report.approved_max_retry_count == 0
    assert {check.status for check in report.checks} == {"pass"}
    assert "sk_fixture_secret" not in report.model_dump_json()


def test_approval_record_requires_exact_c21_statement_provider_model_and_budget(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, approval_statement="approved")
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert "exact C21 user authorization statement" in _check_detail(report, "authorized_live_approval")


def test_provider_capability_evidence_is_bound_to_approved_provider_model(tmp_path: Path):
    provider = "unknown"
    model = "mystery-video-1"
    budget_limit = "$1.00"
    approval_record = _write_approval_record(
        tmp_path,
        provider=provider,
        model=model,
        budget_limit=budget_limit,
        approval_statement=_approval_statement(provider, model, budget_limit),
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "pass"
    assert _check_status(report, "provider_capability_evidence") == "block"
    assert "unknown/mystery-video-1" in _check_detail(report, "provider_capability_evidence")


def test_approval_record_blocks_non_finite_budget(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, budget_limit_usd="NaN")
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert "budget_limit_usd must be a positive number" in _check_detail(report, "authorized_live_approval")


def test_approval_record_template_is_blocked_even_with_other_fields_present(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, template_only=True)
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "authorized_live_approval") == "block"
    assert "template_only must be false" in _check_detail(report, "authorized_live_approval")


def test_approval_record_requires_budget_stop_loss_fields(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path, budget_stop_loss={})
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "budget_stop_loss") == "block"
    assert "budget_stop_loss.max_total_cost_usd" in _check_detail(report, "budget_stop_loss")


def test_approval_record_blocks_loose_retry_or_missing_halt_policy(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        budget_stop_loss={
            "max_total_cost_usd": 1.0,
            "per_job_cost_ceiling_usd": 0.5,
            "max_retry_count": 2,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
    )
    env = _ready_env()
    env[APPROVAL_RECORD_ENV] = str(approval_record)

    report = build_token_smoke_preflight_report(env=env)

    assert report.blocked is True
    assert report.provider_call_allowed is False
    assert _check_status(report, "budget_stop_loss") == "block"
    assert "max_retry_count must be 0 or 1" in _check_detail(report, "budget_stop_loss")


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


def _write_approval_record(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "authorized-live-approval.json"
    provider = str(overrides.get("provider", "poyo"))
    model = str(overrides.get("model", "seedance-2"))
    budget_limit = str(overrides.get("budget_limit", "$1.00"))
    payload = {
        "approval_id": "approval_fixture",
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-04T00:00:00Z",
        "provider": provider,
        "model": model,
        "budget_limit": budget_limit,
        "budget_limit_usd": 1.0,
        "sample_plan": {
            "max_sample_count": 2,
            "max_provider_calls": 2,
            "scenarios": ["fast", "s1"],
            "s5_requires_separate_confirmation": True,
        },
        "budget_stop_loss": {
            "max_total_cost_usd": 1.0,
            "per_job_cost_ceiling_usd": 0.5,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
        "approval_statement": _approval_statement(provider, model, budget_limit),
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _approval_statement(provider: str, model: str, budget_limit: str) -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(provider=provider, model=model, budget_limit=budget_limit)


def _check_status(report, name: str) -> str:
    for check in report.checks:
        if check.name == name:
            return check.status
    raise AssertionError(f"missing check {name}")


def _check_detail(report, name: str) -> str:
    for check in report.checks:
        if check.name == name:
            return check.detail
    raise AssertionError(f"missing check {name}")
