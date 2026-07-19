"""Hermetic contracts for the manual Alembic migration runner.

The runner sees a fake ``sudo docker`` executable through ``PATH``.  These
tests never connect to a database or container and never expose provider
credentials.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "run_alembic_upgrade.sh"
PG18_TEST_MODULE = "tests.test_publish_attempt_pg18"
APPROVED_PG18_DSN = (
    "postgresql://postgres@127.0.0.1:55439/w1_23_migration"
)
PG18_LANE_ERROR = "disposable PostgreSQL 18 lane is not authorized"


def _write_fake_sudo(tmp_path: Path) -> None:
    fake = tmp_path / "sudo"
    fake.write_text(
        r"""#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" != "docker" ]; then
  printf 'unexpected sudo command: %s\n' "$*" >&2
  exit 64
fi
shift

docker_command="${1:-}"
shift || true
printf '%s %s\n' "$docker_command" "$*" >>"${FAKE_ALEMBIC_LOG:?}"

case "$docker_command" in
  ps)
    printf '%s\n' 'ai-video-backend-fixture'
    ;;
  exec)
    args="$*"
    if [[ "$args" == *"alembic current"* || "$args" == *" current" ]]; then
      current="$(cat "${FAKE_CURRENT_STATE:?}")"
      if [ -n "$current" ]; then
        if [ "$current" = "${FAKE_SINGLE_HEAD:-}" ]; then
          printf '%s (head)\n' "$current"
        else
          printf '%s\n' "$current"
        fi
      fi
    elif [[ "$args" == *"alembic heads"* || "$args" == *" heads" ]]; then
      printf '%b\n' "${FAKE_HEADS:?}"
    elif [[ "$args" == *"upgrade --sql"* ]]; then
      printf '%s\n' '-- fixture upgrade SQL --'
    elif [[ "$args" == *"downgrade --sql"* ]]; then
      printf '%s\n' '-- fixture downgrade SQL --'
    elif [[ "$args" == *"upgrade head"* ]]; then
      printf '%s' "${FAKE_SINGLE_HEAD:?}" >"${FAKE_CURRENT_STATE:?}"
    elif [[ "$args" == *"downgrade -1"* ]]; then
      printf '%s' "${FAKE_PARENT_REVISION:?}" >"${FAKE_CURRENT_STATE:?}"
    else
      printf 'unexpected fake docker exec: %s\n' "$args" >&2
      exit 65
    fi
    ;;
  *)
    printf 'unexpected fake docker command: %s\n' "$docker_command" >&2
    exit 66
    ;;
esac
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)


def _run(
    tmp_path: Path,
    *args: str,
    current: str = "current_revision_fixture",
    heads: str = "target_head_fixture (head)",
    single_head: str = "target_head_fixture",
    parent: str = "parent_revision_fixture",
    confirmation: str = "yes\n",
) -> tuple[subprocess.CompletedProcess[str], str]:
    _write_fake_sudo(tmp_path)
    command_log = tmp_path / "alembic-command.log"
    current_state = tmp_path / "current-revision.txt"
    command_log.write_text("", encoding="utf-8")
    current_state.write_text(current, encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "FAKE_ALEMBIC_LOG": str(command_log),
            "FAKE_CURRENT_STATE": str(current_state),
            "FAKE_HEADS": heads,
            "FAKE_SINGLE_HEAD": single_head,
            "FAKE_PARENT_REVISION": parent,
        }
    )
    result = subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        env=env,
        input=confirmation,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result, command_log.read_text(encoding="utf-8")


def _import_pg18_test_module(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
    monkeypatch.delenv("W1_23_PG18_DSN", raising=False)
    return importlib.import_module(PG18_TEST_MODULE)


def _run_pg18_capture_probe(
    tmp_path: Path,
    *,
    inject_from_fake_dotenv: bool,
    preload_src_config: bool = False,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("W1_23_PG18_DSN", None)
    python_path = [str(REPO_ROOT)]
    if inject_from_fake_dotenv:
        dotenv_package = tmp_path / "dotenv"
        dotenv_package.mkdir()
        (dotenv_package / "__init__.py").write_text(
            """import os

def load_dotenv(*args, **kwargs):
    os.environ[\"W1_23_PG18_DSN\"] = (
        \"postgresql://postgres@127.0.0.1:55439/w1_23_migration\"
    )
    return True
""",
            encoding="utf-8",
        )
        python_path.insert(0, str(tmp_path))
        env.pop("PYTHON_DOTENV_DISABLED", None)
    else:
        env["PYTHON_DOTENV_DISABLED"] = "1"
    inherited_python_path = env.get("PYTHONPATH")
    if inherited_python_path:
        python_path.append(inherited_python_path)
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    if preload_src_config:
        probe = """
import asyncio
import asyncpg
import json
import os

pool_created = False

async def fake_create_pool(*args, **kwargs):
    global pool_created
    pool_created = True
    raise RuntimeError("blocked fake pool")

asyncpg.create_pool = fake_create_pool
import src.config
from tests import test_publish_attempt_pg18 as module

async def verify_lane():
    try:
        await module._create_verified_pg18_pool(module._PG18_DSN)
    except (ValueError, RuntimeError):
        return
    raise AssertionError("guard unexpectedly accepted the lane")

asyncio.run(verify_lane())
print(json.dumps({
    "captured_is_none": module._PG18_DSN is None,
    "dotenv_injected": os.environ.get("W1_23_PG18_DSN") is not None,
    "pool_created": pool_created,
}, sort_keys=True))
"""
    else:
        probe = """
import json
import os
from tests import test_publish_attempt_pg18 as module

print(json.dumps({
    "captured_is_none": module._PG18_DSN is None,
    "dotenv_injected": os.environ.get("W1_23_PG18_DSN") is not None,
}, sort_keys=True))
"""
    return subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_upgrade_discovers_current_and_head_then_applies_head(tmp_path: Path) -> None:
    result, log = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "current" in log
    assert "heads" in log
    assert "upgrade --sql current_revision_fixture:head" in log
    assert "upgrade head" in log
    assert "Current revision: current_revision_fixture" in result.stdout
    assert "Target head: target_head_fixture" in result.stdout
    assert "Post-migration revision: target_head_fixture" in result.stdout


def test_downgrade_uses_relative_step_and_warns_about_submission_ledger(
    tmp_path: Path,
) -> None:
    result, log = _run(
        tmp_path,
        "--downgrade",
        current="target_head_fixture",
    )
    output = f"{result.stdout}\n{result.stderr}".lower()

    assert result.returncode == 0, result.stderr
    assert "downgrade --sql target_head_fixture:-1" in log
    assert "downgrade -1" in log
    assert "idempotency_records" in output
    assert "submission ledger" in output
    assert "permanent" in output
    assert "verified backup" in output
    assert "not an application rollback" in output
    assert "Post-migration revision: parent_revision_fixture" in result.stdout


def test_multiple_heads_fail_before_render_or_mutation(tmp_path: Path) -> None:
    result, log = _run(
        tmp_path,
        heads="head_one (head)\nhead_two (head)",
        single_head="",
    )

    assert result.returncode != 0
    assert "exactly one alembic head" in f"{result.stdout}\n{result.stderr}".lower()
    assert "--sql" not in log
    assert "upgrade head" not in log
    assert "downgrade -1" not in log


def test_abort_never_applies_a_migration(tmp_path: Path) -> None:
    result, log = _run(tmp_path, confirmation="no\n")

    assert result.returncode != 0
    assert "Aborted." in result.stdout
    assert "upgrade --sql current_revision_fixture:head" in log
    assert "upgrade head" not in log
    assert "downgrade -1" not in log


def test_upgrade_at_head_is_an_idempotent_noop(tmp_path: Path) -> None:
    result, log = _run(tmp_path, current="target_head_fixture")

    assert result.returncode == 0, result.stderr
    assert "Already at Alembic head; no migration was applied." in result.stdout
    assert "--sql" not in log
    assert "upgrade head" not in log
    assert "downgrade -1" not in log


def test_downgrade_from_base_fails_before_render_or_mutation(
    tmp_path: Path,
) -> None:
    result, log = _run(tmp_path, "--downgrade", current="")

    assert result.returncode != 0
    assert "cannot downgrade -1 from Alembic base" in result.stderr
    assert "--sql" not in log
    assert "upgrade head" not in log
    assert "downgrade -1" not in log


def test_unknown_arguments_are_rejected_before_docker_access(tmp_path: Path) -> None:
    result, log = _run(tmp_path, "--unexpected")

    assert result.returncode == 2
    assert "Usage:" in f"{result.stdout}\n{result.stderr}"
    assert log == ""


def test_script_contains_no_historical_revision_literal() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert re.findall(r"\b[0-9a-f]{12}\b", source) == []
    assert 'ACTION="upgrade head"' in source
    assert 'ACTION="downgrade -1"' in source
    assert "python3 -m alembic $*" not in source


def test_pg18_harness_captures_no_implicit_dsn(tmp_path: Path) -> None:
    result = _run_pg18_capture_probe(
        tmp_path,
        inject_from_fake_dotenv=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "captured_is_none": True,
        "dotenv_injected": False,
    }


def test_pg18_harness_ignores_dsn_injected_by_later_dotenv_import(
    tmp_path: Path,
) -> None:
    result = _run_pg18_capture_probe(
        tmp_path,
        inject_from_fake_dotenv=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "captured_is_none": True,
        "dotenv_injected": True,
    }


def test_pg18_harness_rejects_dotenv_dsn_when_src_config_loaded_first(
    tmp_path: Path,
) -> None:
    result = _run_pg18_capture_probe(
        tmp_path,
        inject_from_fake_dotenv=True,
        preload_src_config=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "captured_is_none": True,
        "dotenv_injected": True,
        "pool_created": False,
    }


def test_pg18_harness_dsn_validator_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_pg18_test_module(monkeypatch)
    validator = module._validate_pg18_dsn
    invalid_cases = {
        "missing": None,
        "wrong_scheme": "https://postgres@127.0.0.1:55439/w1_23_migration",
        "non_loopback": "postgresql://postgres@localhost:55439/w1_23_migration",
        "wrong_port": "postgresql://postgres@127.0.0.1:5432/w1_23_migration",
        "wrong_database": "postgresql://postgres@127.0.0.1:55439/postgres",
        "missing_user": "postgresql://127.0.0.1:55439/w1_23_migration",
        "wrong_user": "postgresql://fixture@127.0.0.1:55439/w1_23_migration",
        "password": (
            "postgresql://postgres:fixture-password@127.0.0.1:55439/"
            "w1_23_migration"
        ),
        "query": (
            "postgresql://postgres@127.0.0.1:55439/w1_23_migration"
            "?sslmode=disable"
        ),
        "fragment": (
            "postgresql://postgres@127.0.0.1:55439/w1_23_migration#fixture"
        ),
    }

    for label, candidate in invalid_cases.items():
        with pytest.raises(ValueError, match=f"^{PG18_LANE_ERROR}$"):
            validator(candidate)
        assert label

    assert validator(APPROVED_PG18_DSN) is None
    assert validator(
        "postgres://postgres@127.0.0.1:55439/w1_23_migration"
    ) is None


@pytest.mark.asyncio
async def test_pg18_harness_invalid_dsn_never_creates_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_pg18_test_module(monkeypatch)
    create_pool_called = False

    async def fake_create_pool(*args, **kwargs):
        nonlocal create_pool_called
        create_pool_called = True
        raise AssertionError("pool creation must remain unreachable")

    monkeypatch.setattr(module.asyncpg, "create_pool", fake_create_pool)
    with pytest.raises(ValueError, match=f"^{PG18_LANE_ERROR}$"):
        await module._create_verified_pg18_pool(
            "postgresql://postgres@localhost:55439/w1_23_migration"
        )
    assert create_pool_called is False


@pytest.mark.asyncio
async def test_pg18_harness_rejects_wrong_server_identity_and_closes_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _import_pg18_test_module(monkeypatch)
    assert module._validate_pg18_server_identity(
        "w1_23_migration",
        "180004",
    ) is None

    class FakeConnection:
        def __init__(self, database_name: str, version_num: str) -> None:
            self.database_name = database_name
            self.version_num = version_num
            self.queries: list[str] = []

        async def fetchrow(self, query: str):
            self.queries.append(query)
            return {
                "database_name": self.database_name,
                "server_version_num": self.version_num,
            }

    class FakeAcquire:
        def __init__(self, connection: FakeConnection) -> None:
            self.connection = connection

        async def __aenter__(self) -> FakeConnection:
            return self.connection

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

    class FakePool:
        def __init__(self, connection: FakeConnection) -> None:
            self.connection = connection
            self.closed = False

        def acquire(self) -> FakeAcquire:
            return FakeAcquire(self.connection)

        async def close(self) -> None:
            self.closed = True

    identities = (
        ("wrong_database", "180004"),
        ("w1_23_migration", "170009"),
    )
    for database_name, version_num in identities:
        connection = FakeConnection(database_name, version_num)
        pool = FakePool(connection)

        async def fake_create_pool(*args, **kwargs):
            return pool

        monkeypatch.setattr(module.asyncpg, "create_pool", fake_create_pool)
        with pytest.raises(RuntimeError, match=f"^{PG18_LANE_ERROR}$"):
            await module._create_verified_pg18_pool(APPROVED_PG18_DSN)
        assert pool.closed is True
        assert len(connection.queries) == 1
        assert connection.queries[0].lstrip().startswith("SELECT")
        assert not any(
            keyword in connection.queries[0].upper()
            for keyword in ("INSERT", "UPDATE", "DELETE")
        )
        assert "current_database()" in connection.queries[0]
        assert "server_version_num" in connection.queries[0]
