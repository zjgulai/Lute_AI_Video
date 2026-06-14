"""Gated execution contract for the 5-scenario production smoke script."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_5scenario_e2e.py"
DEMO_KEY = "ai_video_demo_2026"


def _run_script(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    clean_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"API_KEY", "PLAYWRIGHT_API_KEY", "POYO_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"}
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


def test_default_run_is_dry_run_and_only_prints_plan():
    result = _run_script()
    assert result.returncode == 0
    assert "5-scenario production smoke checker — DRY RUN" in result.stdout
    assert "No commands were executed." in result.stdout
    assert "Planned steps:" in result.stdout
    assert "FAST" in result.stdout
    assert "S1" in result.stdout
    assert "S5" in result.stdout
    assert "Run command:" in result.stdout
    assert "CONFIRM_P2_TOKEN_SMOKE=1" in result.stdout
    assert "RUN_TOKEN_SMOKE=1" in result.stdout


def test_execute_requires_confirmation_and_token_flags():
    base_env = {
        "API_KEY": "prod-api-key",
        "PLAYWRIGHT_API_KEY": "prod-api-key",
        "POYO_API_KEY": "poyo-key",
        "DEEPSEEK_API_KEY": "deepseek-key",
        "SILICONFLOW_API_KEY": "siliconflow-key",
    }

    missing_confirm = _run_script("--execute", env=base_env)
    assert missing_confirm.returncode == 2
    assert "CONFIRM_P2_TOKEN_SMOKE=1 is required" in missing_confirm.stderr

    missing_token = _run_script("--execute", env={**base_env, "CONFIRM_P2_TOKEN_SMOKE": "1"})
    assert missing_token.returncode == 2
    assert "RUN_TOKEN_SMOKE=1 is required" in missing_token.stderr


def test_execute_rejects_demo_key_values():
    env = {
        "CONFIRM_P2_TOKEN_SMOKE": "1",
        "RUN_TOKEN_SMOKE": "1",
        "API_KEY": DEMO_KEY,
        "PLAYWRIGHT_API_KEY": DEMO_KEY,
        "POYO_API_KEY": DEMO_KEY,
        "DEEPSEEK_API_KEY": DEMO_KEY,
        "SILICONFLOW_API_KEY": DEMO_KEY,
    }

    result = _run_script("--execute", env=env)
    assert result.returncode == 2
    assert "must be non-demo key, rejected demo key" in result.stderr


def test_selective_dry_run_respects_scenario_filter():
    result = _run_script("--scenario", "fast", "--scenario", "s2")
    assert result.returncode == 0
    assert "1. FAST" in result.stdout
    assert "2. S2" in result.stdout
    assert "S1" not in result.stdout
    assert "S3" not in result.stdout
    assert "S4" not in result.stdout
    assert "S5" not in result.stdout


def test_invalid_scenario_key_is_rejected_by_parser():
    result = _run_script("--scenario", "unknown")
    assert result.returncode == 2
    assert "invalid choice: 'unknown'" in result.stderr
