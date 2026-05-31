"""Guard the P2 recharge smoke checklist dry-run entrypoint.

The project is still in a no-token phase. This test ensures the future real
smoke checklist can be rehearsed now without accidentally creating provider
tasks, while keeping a double-confirmed execute path ready after recharge.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "p2_recharge_smoke_checklist.py"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "p2-recharge-smoke-checklist.md"
DOCS_LINK_SCOPE = REPO_ROOT / "configs" / "docs-link-check-scope.txt"
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
    assert "deploy/lighthouse/smoke.sh" in result.stdout
    assert "npm run e2e:prod" in result.stdout


def test_execute_requires_double_confirmation_before_real_smoke():
    env = {
        "API_KEY": "prod-api-key",
        "PLAYWRIGHT_API_KEY": "prod-api-key",
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
            "POYO_API_KEY": "poyo-key",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "SILICONFLOW_API_KEY": "siliconflow-key",
        },
    )

    assert result.returncode == 2
    assert "demo key" in result.stderr


def test_script_source_keeps_token_endpoints_behind_execute_path():
    source = SCRIPT.read_text()

    assert "execute: bool" in source
    assert "CONFIRM_P2_TOKEN_SMOKE" in source
    assert "RUN_TOKEN_SMOKE" in source
    assert "subprocess.run" in source
    assert "if not args.execute" in source
    assert "return 0" in source


def test_runbook_documents_recharge_checklist_and_is_link_checked():
    assert RUNBOOK.exists(), "P2 recharge smoke checklist runbook is missing"
    text = RUNBOOK.read_text()

    for token in [
        "scripts/p2_recharge_smoke_checklist.py",
        "CONFIRM_P2_TOKEN_SMOKE=1",
        "RUN_TOKEN_SMOKE=1",
        "POYO_API_KEY",
        "DEEPSEEK_API_KEY",
        "SILICONFLOW_API_KEY",
        "PLAYWRIGHT_API_KEY",
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
