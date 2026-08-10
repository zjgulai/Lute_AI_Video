"""Governance boundary for the archived v0.4.0 release smoke."""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = "scripts/release_smoke_v0.4.0.sh"
RUNBOOK = "docs/runbooks/release-smoke-token-opt-in.md"


def _json(relative: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def _docs_scope() -> set[str]:
    return {
        line.strip()
        for line in (REPO_ROOT / "configs/docs-link-check-scope.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_v040_release_smoke_is_archive_candidate_and_not_executable() -> None:
    scripts = _json("configs/scripts-governance-contract.json")
    matches = [
        item
        for item in scripts["legacy_one_off_scripts"]
        if item["path"] == SCRIPT
    ]
    assert matches == [
        {
            "path": SCRIPT,
            "status": "archive_candidate",
            "reason": (
                "Version-specific historical smoke reads production secrets "
                "and is not a current release entrypoint."
            ),
        }
    ]

    contract = _json("configs/release-smoke-token-opt-in-contract.json")
    assert contract["status"] == "historical"
    assert contract["execution_allowed"] is False
    assert contract["opt_in_env"] is None
    assert contract["replacement"] == "governed W5 exact-authorization executor"

    mode = (REPO_ROOT / SCRIPT).stat().st_mode
    assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH) == 0


def test_v040_release_smoke_fails_closed_even_with_hostile_live_env() -> None:
    env = os.environ.copy()
    env.update(
        {
            "RUN_TOKEN_SMOKE": "1",
            "API_KEY": "sk_fixture_secret",
            "PLAYWRIGHT_API_KEY": "sk_fixture_secret",
            "POYO_API_KEY": "sk_fixture_secret",
            "HOST": "production.invalid",
        }
    )
    result = subprocess.run(
        ["bash", str(REPO_ROOT / SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "archived v0.4.0 release smoke is disabled" in result.stderr
    source = (REPO_ROOT / SCRIPT).read_text(encoding="utf-8")
    for forbidden in ("ssh ", "scp ", "curl ", ".env.prod", "RUN_TOKEN_SMOKE"):
        assert forbidden not in source


def test_historical_release_smoke_runbook_is_not_current_guidance() -> None:
    text = (REPO_ROOT / RUNBOOK).read_text(encoding="utf-8")

    assert "status: historical" in text
    assert "not a current execution entrypoint" in text
    assert "本文件不作为当前执行入口" in text
    assert "```bash" not in text
    assert RUNBOOK not in _docs_scope()
    assert RUNBOOK not in (REPO_ROOT / ".github/workflows/ci.yml").read_text(
        encoding="utf-8"
    )


def test_archived_release_smoke_is_unreachable_from_current_entrypoints() -> None:
    entrypoints = (
        "Makefile",
        ".github/workflows/ci.yml",
        ".github/workflows/deploy.yml",
        "deploy/lighthouse/deploy.sh",
        "docs/runbooks/production-operations.md",
        "docs/workflows/deploy-lighthouse-stable.md",
    )

    for relative in entrypoints:
        assert Path(SCRIPT).name not in (REPO_ROOT / relative).read_text(
            encoding="utf-8"
        )
