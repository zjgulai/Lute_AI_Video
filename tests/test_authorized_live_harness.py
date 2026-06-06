from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.pipeline.authorized_live_harness import EXECUTE_ENV, run_authorized_live_harness
from src.pipeline.token_smoke_preflight import (
    APPROVAL_RECORD_ENV,
    APPROVAL_SCOPE,
    APPROVAL_STATEMENT_TEMPLATE,
    PROVIDER_REVALIDATION_REF,
    REQUIRED_API_KEY_ENVS,
    RUN_TOKEN_SMOKE_ENV,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "authorized_live_token_smoke_harness.py"


def test_harness_is_disabled_by_default_without_provider_call():
    calls: list[str] = []

    report = run_authorized_live_harness(
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"}
    )

    assert report.status == "disabled"
    assert report.provider_call_executed is False
    assert report.preflight is None
    assert calls == []


def test_dry_run_passes_after_preflight_without_provider_call(tmp_path: Path):
    calls: list[str] = []
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)

    report = run_authorized_live_harness(
        mode="dry_run",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"},
    )

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert report.preflight is not None
    assert report.preflight.provider_call_allowed is True
    assert report.job_spec is not None
    assert report.job_spec.provider == "poyo"
    assert report.job_spec.model == "seedance-2"
    assert report.job_spec.cost_ceiling_usd == 0.5
    assert calls == []


def test_dry_run_job_spec_uses_approval_provider_model_and_per_job_budget(tmp_path: Path):
    approval_record = _write_approval_record(
        tmp_path,
        provider="poyo",
        model="seedance-2-fast",
        budget_limit_usd=2.5,
        budget_stop_loss={
            "max_total_cost_usd": 2.5,
            "per_job_cost_ceiling_usd": 1.25,
            "max_retry_count": 0,
            "stop_on_first_failure": True,
            "halt_on_rate_limit": True,
            "halt_on_quota_error": True,
            "halt_on_content_rejection": True,
            "halt_on_missing_artifact": True,
        },
    )
    env = _ready_env(approval_record)

    report = run_authorized_live_harness(mode="dry_run", env=env)

    assert report.status == "dry_run_ready"
    assert report.provider_call_executed is False
    assert report.job_spec is not None
    assert report.job_spec.provider == "poyo"
    assert report.job_spec.model == "seedance-2-fast"
    assert report.job_spec.cost_ceiling_usd == 1.25


def test_execute_mode_requires_extra_execute_flag_after_preflight(tmp_path: Path):
    calls: list[str] = []
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)

    report = run_authorized_live_harness(
        mode="execute",
        env=env,
        submitter=lambda spec: calls.append(spec.job_id) or {"provider_job_id": "should_not_run"},
    )

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert report.blocked_reasons == [f"{EXECUTE_ENV}=1 is required for execute mode"]
    assert calls == []


def test_execute_mode_blocks_when_submitter_is_not_configured(tmp_path: Path):
    approval_record = _write_approval_record(tmp_path)
    env = _ready_env(approval_record)
    env[EXECUTE_ENV] = "1"

    report = run_authorized_live_harness(mode="execute", env=env)

    assert report.status == "blocked"
    assert report.provider_call_executed is False
    assert report.blocked_reasons == ["provider submitter is not configured"]


def test_cli_default_is_disabled_and_json_parseable():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "disabled"
    assert payload["provider_call_executed"] is False


def _ready_env(approval_record: Path) -> dict[str, str]:
    env = {
        RUN_TOKEN_SMOKE_ENV: "1",
        APPROVAL_RECORD_ENV: str(approval_record),
    }
    for key_name in REQUIRED_API_KEY_ENVS:
        env[key_name] = f"sk_fixture_secret_{key_name.lower()}"
    return env


def _write_approval_record(tmp_path: Path, **overrides: Any) -> Path:
    path = tmp_path / "authorized-live-approval.json"
    provider = str(overrides.get("provider", "poyo"))
    model = str(overrides.get("model", "seedance-2"))
    budget_limit = str(overrides.get("budget_limit", "$1.00"))
    payload: dict[str, Any] = {
        "approval_id": "approval_fixture",
        "scope": APPROVAL_SCOPE,
        "evidence_level": "L4-authorized-live",
        "provider_calls_allowed": True,
        "approved_by": "user",
        "approved_at": "2026-06-04T00:00:00Z",
        "provider": provider,
        "model": model,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
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
    if {"provider", "model", "budget_limit"} & overrides.keys() and "approval_statement" not in overrides:
        payload["approval_statement"] = _approval_statement(
            str(payload["provider"]),
            str(payload["model"]),
            str(payload["budget_limit"]),
        )
    path.write_text(json.dumps(payload, ensure_ascii=False))
    return path


def _approval_statement(provider: str, model: str, budget_limit: str) -> str:
    return APPROVAL_STATEMENT_TEMPLATE.format(provider=provider, model=model, budget_limit=budget_limit)
