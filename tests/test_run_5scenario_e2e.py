"""The historical Fast plus S1-S5 mutation runner is permanently retired."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_5scenario_e2e.py"


def test_run_5scenario_e2e_is_nonexecutable_fail_closed_stub() -> None:
    assert SCRIPT.stat().st_mode & (
        stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    ) == 0
    source = SCRIPT.read_text(encoding="utf-8")
    assert "is retired and cannot execute" in source
    for token in (
        "requests",
        "httpx",
        "/fast/generate",
        "/fast/submit",
        "/scenario/",
        "RUN_TOKEN_SMOKE",
        "POYO_API_KEY",
    ):
        assert token not in source


def test_run_5scenario_e2e_hostile_env_always_returns_two() -> None:
    env = os.environ.copy()
    env.update(
        {
            "CONFIRM_P2_TOKEN_SMOKE": "1",
            "RUN_TOKEN_SMOKE": "1",
            "API_KEY": "sk_fixture_secret",
            "POYO_API_KEY": "sk_fixture_secret",
            "DEEPSEEK_API_KEY": "sk_fixture_secret",
            "SILICONFLOW_API_KEY": "sk_fixture_secret",
        }
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--execute", "--scenario", "fast,s1,s2,s3,s4,s5"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "is retired and cannot execute" in result.stderr
