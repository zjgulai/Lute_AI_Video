"""The retired P2/C21 provider entrypoint must be unreachable."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "p2_recharge_smoke_checklist.py"
RUNBOOK_REF = "docs/runbooks/p2-recharge-smoke-checklist.md"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "CONFIRM_P2_TOKEN_SMOKE": "1",
            "RUN_TOKEN_SMOKE": "1",
            "API_KEY": "sk_fixture_secret",
            "PLAYWRIGHT_API_KEY": "sk_fixture_secret",
            "POYO_API_KEY": "sk_fixture_secret",
            "DEEPSEEK_API_KEY": "sk_fixture_secret",
            "SILICONFLOW_API_KEY": "sk_fixture_secret",
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "1",
        }
    )
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_and_execute_modes_always_fail_closed() -> None:
    for args in ((), ("--execute",), ("--base-url", "https://production.invalid")):
        result = _run(*args)
        assert result.returncode == 2
        assert "P2/C21 recharge smoke is retired" in result.stderr
        assert result.stdout == ""


def test_stub_has_no_provider_or_subprocess_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "authorized_live_token_smoke_harness",
        "RUN_TOKEN_SMOKE",
        "POYO_API_KEY",
    ):
        assert forbidden not in source


def test_p2_script_and_runbook_are_historical_archive_candidates() -> None:
    contract = json.loads(
        (REPO_ROOT / "configs/scripts-governance-contract.json").read_text(
            encoding="utf-8"
        )
    )
    matches = [
        item
        for item in contract["legacy_one_off_scripts"]
        if item["path"] == "scripts/p2_recharge_smoke_checklist.py"
    ]
    assert len(matches) == 1
    assert matches[0]["status"] == "archive_candidate"

    runbook = (REPO_ROOT / RUNBOOK_REF).read_text(encoding="utf-8")
    assert "status: historical" in runbook
    assert "本文件不作为当前执行入口" in runbook
    assert "```bash" not in runbook

    docs_scope = (REPO_ROOT / "configs/docs-link-check-scope.txt").read_text(
        encoding="utf-8"
    )
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    index = (REPO_ROOT / "docs/runbooks/README.md").read_text(encoding="utf-8")
    assert RUNBOOK_REF not in docs_scope
    assert RUNBOOK_REF not in ci
    assert "p2-recharge-smoke-checklist.md" not in index


def test_current_entrypoints_do_not_reference_retired_p2_script() -> None:
    for relative in (
        "Makefile",
        ".github/workflows/ci.yml",
        ".github/workflows/deploy.yml",
        ".github/workflows/e2e-prod.yml",
        "deploy/lighthouse/deploy.sh",
        "docs/runbooks/production-operations.md",
        "docs/runbooks/production-e2e-token-smoke.md",
        "scripts/build_authorized_live_smoke_packet.py",
    ):
        assert "p2_recharge_smoke_checklist.py" not in (
            REPO_ROOT / relative
        ).read_text(encoding="utf-8")
