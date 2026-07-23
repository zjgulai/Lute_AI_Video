"""Fail-closed and secret-free contracts for the release Alembic gate."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "deploy_alembic_gate.sh"


def _write_fake_python(tmp_path: Path) -> None:
    executable = tmp_path / "python3"
    executable.write_text(
        r"""#!/usr/bin/env bash
set -euo pipefail
command_name="${*: -1}"
if [ "${FAKE_FAIL_COMMAND:-}" = "$command_name" ]; then
  printf '%s\n' 'driver failed password=do-not-leak' >&2
  exit 71
fi
case "$command_name" in
  heads)
    printf '%s\n' 'head_fixture (head)'
    ;;
  current)
    current="$(cat "${FAKE_CURRENT_STATE:?}")"
    if [ -n "$current" ]; then
      printf '%s\n' "$current"
    fi
    ;;
  head)
    if [ "${FAKE_UPGRADE_STICKS:-1}" = "1" ]; then
      printf '%s' 'head_fixture' >"${FAKE_CURRENT_STATE:?}"
    fi
    ;;
  *)
    printf '%s\n' 'unexpected fake alembic command' >&2
    exit 72
    ;;
esac
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)


def _run_gate(
    tmp_path: Path,
    *,
    fail_command: str | None = None,
    current: str = "parent_fixture",
    upgrade_sticks: bool = True,
) -> subprocess.CompletedProcess[str]:
    _write_fake_python(tmp_path)
    state = tmp_path / "current.txt"
    state.write_text(current, encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "ENVIRONMENT": "production",
            "DATABASE_URL": (
                "postgresql://release_user:do-not-leak@database.invalid/ai_video"
            ),
            "DEPLOY_MIGRATION_AUTH": "APPLY_REVIEWED_RELEASE",
            "FAKE_CURRENT_STATE": str(state),
            "FAKE_UPGRADE_STICKS": "1" if upgrade_sticks else "0",
        }
    )
    if fail_command is not None:
        env["FAKE_FAIL_COMMAND"] = fail_command
    return subprocess.run(
        ["bash", str(SCRIPT), "--apply"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


@pytest.mark.parametrize(
    ("fail_command", "safe_code"),
    [
        ("heads", "alembic_heads_failed"),
        ("current", "alembic_current_failed"),
        ("head", "alembic_upgrade_failed"),
    ],
)
def test_alembic_command_failures_return_only_stable_safe_codes(
    tmp_path: Path,
    fail_command: str,
    safe_code: str,
) -> None:
    result = _run_gate(tmp_path, fail_command=fail_command)

    assert result.returncode != 0
    assert result.stderr.strip() == f"ERROR: {safe_code}"
    assert "do-not-leak" not in result.stdout + result.stderr


def test_post_apply_revision_mismatch_is_stable_and_secret_free(tmp_path: Path) -> None:
    result = _run_gate(tmp_path, upgrade_sticks=False)

    assert result.returncode != 0
    assert result.stderr.strip() == (
        "ERROR: database revision does not match the single Alembic head."
    )
    assert "do-not-leak" not in result.stdout + result.stderr
