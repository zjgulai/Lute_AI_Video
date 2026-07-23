"""Static and fail-closed contracts for empty PostgreSQL bootstrap."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "bootstrap_postgres.py"
INIT_SQL = REPO_ROOT / "src" / "storage" / "migrations" / "001_init.sql"
MIGRATION_README = REPO_ROOT / "migrations" / "README.md"


def _run(*, env_updates: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env.pop("POSTGRES_BOOTSTRAP_AUTH", None)
    env.update(env_updates)
    return subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), str(SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def test_bootstrap_script_uses_atomic_alembic_stamp_and_empty_database_guard() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "MigrationContext" in source
    assert "database_not_empty_use_alembic_upgrade" in source
    assert "POSTGRES_BOOTSTRAP_AUTH" in source
    assert "APPLY_EMPTY_DATABASE_BASELINE" in source
    assert "alembic upgrade head" not in source
    assert "DATABASE_URL" not in source.replace('os.environ.get("DATABASE_URL")', "")


def test_bootstrap_requires_exact_one_shot_authority_before_database_access() -> None:
    result = _run(env_updates={})

    assert result.returncode != 0
    assert result.stderr.strip() == "ERROR: bootstrap_authority_required"
    assert result.stdout == ""


def test_bootstrap_rejects_missing_database_url_with_safe_code() -> None:
    result = _run(
        env_updates={"POSTGRES_BOOTSTRAP_AUTH": "APPLY_EMPTY_DATABASE_BASELINE"}
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "ERROR: bootstrap_database_url_required"


def test_bootstrap_rejects_non_postgres_url_without_echoing_value() -> None:
    secret_url = "mysql://user:do-not-leak@database.invalid/app"
    result = _run(
        env_updates={
            "POSTGRES_BOOTSTRAP_AUTH": "APPLY_EMPTY_DATABASE_BASELINE",
            "DATABASE_URL": secret_url,
        }
    )

    assert result.returncode != 0
    assert result.stderr.strip() == "ERROR: bootstrap_database_url_invalid"
    assert "do-not-leak" not in result.stdout + result.stderr


def test_schema_docs_do_not_claim_application_side_migration() -> None:
    init_sql = INIT_SQL.read_text(encoding="utf-8")
    readme = MIGRATION_README.read_text(encoding="utf-8")

    assert "backend entrypoint also runs `alembic upgrade head`" not in init_sql
    assert "scripts/bootstrap_postgres.py" in readme
    assert "empty" in readme.lower()
    assert "historical" in readme.lower()
