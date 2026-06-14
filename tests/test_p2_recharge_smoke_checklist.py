"""Guard the P2 recharge smoke checklist dry-run entrypoint.

The project is still in a no-token phase. This test ensures the future real
smoke checklist can be rehearsed now without accidentally creating provider
tasks, while keeping a double-confirmed execute path ready after recharge.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "p2_recharge_smoke_checklist.py"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "p2-recharge-smoke-checklist.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
APPROVAL_TEMPLATE = REPO_ROOT / "configs" / "authorized-live-token-smoke-approval-template.json"
DEMO_KEY = "ai_video_demo_2026"


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
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
            "RUN_TOKEN_SMOKE",
            "CONFIRM_P2_TOKEN_SMOKE",
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS",
            "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD",
            "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD",
        }
    }
    if env:
        clean_env.update(env)

    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=clean_env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_run_is_dry_run_and_does_not_require_tokens():
    result = _run_script()

    assert result.returncode == 0
    assert "DRY RUN" in result.stdout
    assert "No commands were executed" in result.stdout
    assert "CONFIRM_P2_TOKEN_SMOKE=1" in result.stdout
    assert "RUN_TOKEN_SMOKE=1" in result.stdout
    assert "Before execute, build a no-token launch packet" in result.stdout
    assert "python scripts/build_authorized_live_smoke_packet.py --include-preflight" in result.stdout
    assert "Momcozy sterilizer authorized-live asset smoke harness" in result.stdout
    assert "scripts/authorized_live_token_smoke_harness.py --execute --enable-poyo-http-submitter --pretty" in result.stdout
    assert "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1" in result.stdout
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1" in result.stdout
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json>" in result.stdout
    assert "deploy/lighthouse/smoke.sh" not in result.stdout
    assert "npm run e2e:prod" not in result.stdout
    assert "Running:" not in result.stdout


def test_execute_requires_double_confirmation_before_real_smoke():
    env = {
        "API_KEY": "prod-api-key",
        "PLAYWRIGHT_API_KEY": "prod-api-key",
        "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD": "/private/approval.json",
        "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD": "/private/account-readiness.json",
        "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
        "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "1",
        "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS": "/private/poyo-payloads.json",
        "POYO_API_KEY": "poyo-key",
        "DEEPSEEK_API_KEY": "deepseek-key",
        "SILICONFLOW_API_KEY": "siliconflow-key",
    }

    missing_confirm = _run_script("--execute", env=env)
    assert missing_confirm.returncode == 2
    assert "CONFIRM_P2_TOKEN_SMOKE=1" in missing_confirm.stderr

    missing_token_flag = _run_script("--execute", env={**env, "CONFIRM_P2_TOKEN_SMOKE": "1"})
    assert missing_token_flag.returncode == 2
    assert "RUN_TOKEN_SMOKE=1" in missing_token_flag.stderr


def test_execute_rejects_demo_key_even_when_confirmed():
    result = _run_script(
        "--execute",
        env={
            "CONFIRM_P2_TOKEN_SMOKE": "1",
            "RUN_TOKEN_SMOKE": "1",
            "API_KEY": DEMO_KEY,
            "PLAYWRIGHT_API_KEY": DEMO_KEY,
            "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD": "/private/approval.json",
            "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD": "/private/account-readiness.json",
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS": "/private/poyo-payloads.json",
            "POYO_API_KEY": "poyo-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "SILICONFLOW_API_KEY": "siliconflow-key",
        },
    )

    assert result.returncode == 2
    assert "demo key" in result.stderr


def test_execute_requires_approval_record_path_even_when_confirmed():
    result = _run_script(
        "--execute",
        env={
            "CONFIRM_P2_TOKEN_SMOKE": "1",
            "RUN_TOKEN_SMOKE": "1",
            "API_KEY": "prod-api-key",
            "PLAYWRIGHT_API_KEY": "prod-api-key",
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS": "/private/poyo-payloads.json",
            "POYO_API_KEY": "poyo-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "SILICONFLOW_API_KEY": "siliconflow-key",
        },
    )

    assert result.returncode == 2
    assert "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD" in result.stderr


def test_execute_requires_poyo_runtime_wiring_even_when_confirmed():
    base_env = {
        "CONFIRM_P2_TOKEN_SMOKE": "1",
        "RUN_TOKEN_SMOKE": "1",
        "API_KEY": "prod-api-key",
        "PLAYWRIGHT_API_KEY": "prod-api-key",
        "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD": "/private/approval.json",
        "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD": "/private/account-readiness.json",
        "POYO_API_KEY": "poyo-key",
        "DEEPSEEK_API_KEY": "deepseek-key",
        "SILICONFLOW_API_KEY": "siliconflow-key",
    }

    missing_runtime = _run_script("--execute", env=base_env)
    assert missing_runtime.returncode == 2
    assert "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE is required" in missing_runtime.stderr
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT is required" in missing_runtime.stderr
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS is required" in missing_runtime.stderr

    disabled_transport = _run_script(
        "--execute",
        env={
            **base_env,
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "0",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS": "/private/poyo-payloads.json",
        },
    )

    assert disabled_transport.returncode == 2
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT must be 1" in disabled_transport.stderr


def test_execute_runs_preflight_before_any_token_smoke_command():
    result = _run_script(
        "--execute",
        env={
            "CONFIRM_P2_TOKEN_SMOKE": "1",
            "RUN_TOKEN_SMOKE": "1",
            "API_KEY": "prod-api-key",
            "PLAYWRIGHT_API_KEY": "prod-api-key",
            "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD": str(APPROVAL_TEMPLATE),
            "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD": "/private/account-readiness.json",
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS": "/private/poyo-payloads.json",
            "POYO_API_KEY": "poyo-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "SILICONFLOW_API_KEY": "siliconflow-key",
        },
    )

    assert result.returncode == 2
    assert "token smoke preflight blocked execute" in result.stderr
    assert "template_only must be false" in result.stderr
    assert "Running:" not in result.stdout


def test_script_source_keeps_token_endpoints_behind_execute_path():
    source = SCRIPT.read_text()

    assert "execute: bool" in source
    assert "CONFIRM_P2_TOKEN_SMOKE" in source
    assert "RUN_TOKEN_SMOKE" in source
    assert "build_token_smoke_preflight_report" in source
    assert "_validate_execute_preflight" in source
    assert "--enable-poyo-http-submitter" in source
    assert "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE" in source
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT" in source
    assert "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS" in source
    assert "subprocess.run" in source
    assert "if not args.execute" in source
    assert "return 0" in source
    assert "deploy/lighthouse/smoke.sh" not in source
    assert "npm run e2e:prod" not in source


def test_runbook_documents_recharge_checklist_and_is_link_checked():
    assert RUNBOOK.exists(), "P2 recharge smoke checklist runbook is missing"
    text = RUNBOOK.read_text()

    for token in [
        "scripts/p2_recharge_smoke_checklist.py",
        "scripts/commercial_token_smoke_preflight.py",
        "scripts/build_authorized_live_smoke_packet.py",
        "scripts/build_provider_account_readiness_record.py",
        "configs/authorized-live-token-smoke-approval-template.json",
        "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD",
        "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD",
        "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD",
        "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE",
        "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT",
        "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS",
        "--enable-poyo-http-submitter",
        "CONFIRM_P2_TOKEN_SMOKE=1",
        "RUN_TOKEN_SMOKE=1",
        "POYO_API_KEY",
        "DEEPSEEK_API_KEY",
        "SILICONFLOW_API_KEY",
        "PLAYWRIGHT_API_KEY",
        "budget_stop_loss",
        "sample_plan",
        "dry-run",
        "充值后",
    ]:
        assert token in text

    scope_targets = {
        line.strip()
        for line in DOCS_LINK_SCOPE.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    }
    assert "docs/runbooks/p2-recharge-smoke-checklist.md" in scope_targets


def test_authorized_live_approval_template_is_present_and_blocked_by_default():
    payload = json.loads(APPROVAL_TEMPLATE.read_text())

    assert payload["template_only"] is True
    assert payload["scope"] == "c21-token-smoke"
    assert payload["provider_revalidation_ref"] == "configs/poyo-current-provider-revalidation-contract.json"
    assert payload["sample_plan_ref"] == "configs/authorized-live-token-smoke-sample-plan-contract.json"
    assert payload["provider_model_scope"] == "poyo/gpt-image-2 + poyo/seedance-2"
    assert payload["test_scope"] == "Momcozy 消毒器 3 张图片 + 1 条 15 秒竖版图片驱动视频"
    assert payload["budget_limit_usd"] == 3.0
    assert payload["sample_plan"]["max_sample_count"] == 4
    assert payload["sample_plan"]["asset_package"]["asset_status"] == "pending_review"
    assert payload["budget_stop_loss"]["max_retry_count"] == 0
    assert payload["budget_stop_loss"]["stop_on_first_failure"] is True
    assert payload["budget_stop_loss"]["halt_on_rate_limit"] is True
    assert payload["budget_stop_loss"]["halt_on_quota_error"] is True
    assert payload["budget_stop_loss"]["halt_on_content_rejection"] is True
    assert payload["budget_stop_loss"]["halt_on_missing_artifact"] is True
    assert "API_KEY" not in json.dumps(payload)
