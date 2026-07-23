"""Fail-closed liveness/readiness and migration-head contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
from httpx import ASGITransport, AsyncClient

from src.storage import db

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.release.yml"


class _AcquireContext:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    async def __aenter__(self) -> Any:
        return self.connection

    async def __aexit__(self, *_args: Any) -> bool:
        return False


class _Pool:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.connection)


class _MigrationConnection:
    async def fetchval(self, query: str, *_args: Any) -> int:
        assert query == "SELECT 1"
        return 1


class _VersionConnection:
    def __init__(self, revisions: list[str] | Exception) -> None:
        self.revisions = revisions

    async def fetch(self, query: str) -> list[dict[str, str]]:
        assert query == "SELECT version_num FROM alembic_version ORDER BY version_num"
        if isinstance(self.revisions, Exception):
            raise self.revisions
        return [{"version_num": revision} for revision in self.revisions]


@pytest.fixture(autouse=True)
def _reset_database_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_sqlite_conn", None)
    monkeypatch.setattr(db, "_pg_available", False)


@pytest.mark.asyncio
async def test_production_readiness_requires_tables_and_exact_alembic_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(db, "_pool", _Pool(_MigrationConnection()))
    monkeypatch.setattr(db, "_verify_pg_tables", lambda _conn: _async_value(True))
    monkeypatch.setattr(
        db,
        "_inspect_alembic_head",
        lambda _conn: _async_value(
            {
                "ready": True,
                "status": "at_head",
                "current_revision": "head_fixture",
                "head_revision": "head_fixture",
            }
        ),
    )

    readiness = await db.check_database_readiness()

    assert readiness == {
        "ready": True,
        "backend": "postgresql",
        "status": "ready",
        "tables_verified": True,
        "migration": {
            "ready": True,
            "status": "at_head",
            "current_revision": "head_fixture",
            "head_revision": "head_fixture",
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("migration_status", ["behind_head", "multiple_heads", "version_missing"])
async def test_production_readiness_fails_closed_on_migration_state(
    monkeypatch: pytest.MonkeyPatch,
    migration_status: str,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(db, "_pool", _Pool(_MigrationConnection()))
    monkeypatch.setattr(db, "_verify_pg_tables", lambda _conn: _async_value(True))
    monkeypatch.setattr(
        db,
        "_inspect_alembic_head",
        lambda _conn: _async_value(
            {
                "ready": False,
                "status": migration_status,
                "current_revision": None,
                "head_revision": "head_fixture",
            }
        ),
    )

    readiness = await db.check_database_readiness()

    assert readiness["ready"] is False
    assert readiness["status"] == "migration_not_ready"
    assert readiness["migration"]["status"] == migration_status


@pytest.mark.asyncio
async def test_readiness_preserves_behind_head_when_required_schema_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(db, "_pool", _Pool(_MigrationConnection()))
    monkeypatch.setattr(db, "_verify_pg_tables", lambda _conn: _async_value(False))
    monkeypatch.setattr(
        db,
        "_inspect_alembic_head",
        lambda _conn: _async_value(
            {
                "ready": False,
                "status": "behind_head",
                "current_revision": "parent_fixture",
                "head_revision": "head_fixture",
            }
        ),
    )

    readiness = await db.check_database_readiness()

    assert readiness["ready"] is False
    assert readiness["status"] == "migration_not_ready"
    assert readiness["tables_verified"] is False
    assert readiness["migration"]["status"] == "behind_head"


@pytest.mark.asyncio
async def test_legacy_health_cannot_reopen_pool_when_migration_is_behind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db, "_pool", _Pool(_MigrationConnection()))
    monkeypatch.setattr(db, "_pg_available", True)
    monkeypatch.setattr(db, "_verify_pg_tables", lambda _conn: _async_value(True))
    monkeypatch.setattr(
        db,
        "_inspect_alembic_head",
        lambda _conn: _async_value(
            {
                "ready": False,
                "status": "behind_head",
                "current_revision": "parent_fixture",
                "head_revision": "head_fixture",
            }
        ),
    )

    health = await db.check_pg_health()

    assert health["status"] == "migration_not_ready"
    assert db.is_pg_available() is False
    assert db.get_verified_pg_pool() is None


class _CrossSchemaConnection:
    async def fetchval(self, query: str, table_name: str) -> bool:
        assert "table_schema = current_schema()" in query
        assert table_name in db._REQUIRED_TABLES
        return False


@pytest.mark.asyncio
async def test_required_tables_must_exist_in_current_schema() -> None:
    assert await db._verify_pg_tables(cast(Any, _CrossSchemaConnection())) is False


def test_code_alembic_history_has_one_resolvable_head() -> None:
    head = db._code_alembic_head()

    assert isinstance(head, str)
    assert len(head) == 12


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("revisions", "expected_status", "ready"),
    [
        (["head_fixture"], "at_head", True),
        (["prior_fixture"], "behind_head", False),
        (["first_fixture", "second_fixture"], "multiple_current_revisions", False),
        ([], "version_missing", False),
    ],
)
async def test_alembic_inspector_preserves_exact_revision_truth(
    monkeypatch: pytest.MonkeyPatch,
    revisions: list[str],
    expected_status: str,
    ready: bool,
) -> None:
    monkeypatch.setattr(db, "_code_alembic_head", lambda: "head_fixture")

    result = await db._inspect_alembic_head(cast(Any, _VersionConnection(revisions)))

    assert result["ready"] is ready
    assert result["status"] == expected_status
    assert result["head_revision"] == "head_fixture"


@pytest.mark.asyncio
async def test_alembic_inspector_redacts_database_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db, "_code_alembic_head", lambda: "head_fixture")

    result = await db._inspect_alembic_head(
        cast(Any, _VersionConnection(RuntimeError("password=do-not-leak")))
    )

    assert result["status"] == "version_missing"
    assert "do-not-leak" not in repr(result)


@pytest.mark.asyncio
async def test_explicit_test_sqlite_is_ready_without_claiming_postgres(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_FALLBACK_ENABLED", "1")
    monkeypatch.setattr(db, "_sqlite_conn", object())

    assert await db.check_database_readiness() == {
        "ready": True,
        "backend": "sqlite",
        "status": "ready_development_fallback",
        "tables_verified": False,
        "migration": {"ready": False, "status": "not_applicable"},
    }


@pytest.mark.asyncio
async def test_health_routes_split_liveness_from_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api import app
    from src.storage import db as db_module

    monkeypatch.setattr(
        db_module,
        "check_database_readiness",
        lambda: _async_value(
            {
                "ready": False,
                "backend": "postgresql",
                "status": "migration_not_ready",
                "tables_verified": True,
                "migration": {"ready": False, "status": "behind_head"},
            }
        ),
        raising=False,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        live_response = await client.get("/health/live")
        ready_response = await client.get("/health/ready")

    assert live_response.status_code == 200
    assert live_response.json()["status"] == "alive"
    assert ready_response.status_code == 503
    assert ready_response.json()["status"] == "not_ready"
    assert "DATABASE_URL" not in ready_response.text


def test_release_backend_healthcheck_uses_readiness_endpoint() -> None:
    compose = RELEASE_COMPOSE.read_text(encoding="utf-8")

    assert "http://localhost:8001/health/ready" in compose
    assert "http://localhost:8001/health')" not in compose


async def _async_value(value: Any) -> Any:
    return value
