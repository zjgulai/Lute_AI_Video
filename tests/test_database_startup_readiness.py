"""Production database startup must be read-only and fail closed."""

from __future__ import annotations

import pytest

from src.storage import db


@pytest.fixture(autouse=True)
def _reset_database_globals(monkeypatch):
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(db, "_sqlite_conn", None)
    monkeypatch.setattr(db, "_pg_available", False)


@pytest.mark.asyncio
async def test_production_get_pool_rejects_missing_database_url_without_sqlite(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SQLITE_FALLBACK_ENABLED", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sqlite_called = False

    def fake_init_sqlite() -> None:
        nonlocal sqlite_called
        sqlite_called = True

    monkeypatch.setattr(db, "_init_sqlite", fake_init_sqlite)

    with pytest.raises(RuntimeError, match="PostgreSQL is required in production"):
        await db.get_pool()

    assert sqlite_called is False


@pytest.mark.asyncio
async def test_production_get_pool_rejects_connection_failure_without_secret_or_fallback(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://release_user:do-not-leak@database.invalid:5432/ai_video",
    )

    async def fail_create_pool(*_args, **_kwargs):
        raise OSError("dial failed with do-not-leak")

    monkeypatch.setattr(db.asyncpg, "create_pool", fail_create_pool)
    monkeypatch.setattr(
        db,
        "_init_sqlite",
        lambda: pytest.fail("production must not initialize SQLite fallback"),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await db.get_pool()

    assert "PostgreSQL connection failed in production" in str(exc_info.value)
    assert "do-not-leak" not in str(exc_info.value)


class _AcquireContext:
    async def __aenter__(self):
        return _FakeConnection()

    async def __aexit__(self, *_args):
        return False


class _FakePool:
    def __init__(self):
        self.closed = False

    def acquire(self):
        return _AcquireContext()

    async def close(self):
        self.closed = True


class _FakeConnection:
    async def fetchval(self, _query):
        return 1


@pytest.mark.asyncio
async def test_production_init_db_never_runs_migrations_and_rejects_incomplete_schema(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(db, "get_pool", lambda: _async_value(_FakePool()))

    async def missing_tables(_conn):
        return False

    monkeypatch.setattr(db, "_verify_pg_tables", missing_tables)

    with pytest.raises(RuntimeError, match="required PostgreSQL schema is not ready"):
        await db.init_db()

    assert db.is_pg_available() is False
    assert not hasattr(db, "_run_alembic_migrations")


@pytest.mark.asyncio
async def test_production_init_db_rejects_schema_behind_head_without_migration(
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(db, "get_pool", lambda: _async_value(_FakePool()))
    monkeypatch.setattr(db, "_verify_pg_tables", lambda _conn: _async_value(True))
    monkeypatch.setattr(
        db,
        "_inspect_alembic_head",
        lambda _conn: _async_value(
            {
                "ready": False,
                "status": "behind_head",
                "current_revision": "prior_fixture",
                "head_revision": "head_fixture",
            }
        ),
    )

    with pytest.raises(RuntimeError, match="required PostgreSQL migration is not ready"):
        await db.init_db()

    assert db.is_pg_available() is False
    assert not hasattr(db, "_run_alembic_migrations")


@pytest.mark.asyncio
async def test_production_verification_failure_closes_and_discards_pool(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    pool = _FakePool()
    monkeypatch.setattr(db, "_pool", pool)
    monkeypatch.setattr(db, "get_pool", lambda: _async_value(pool))
    monkeypatch.setattr(db, "_verify_pg_tables", lambda _conn: _async_value(False))

    with pytest.raises(RuntimeError, match="required PostgreSQL schema is not ready"):
        await db.init_db()

    assert pool.closed is True
    assert db._pool is None
    assert db.is_pg_available() is False


@pytest.mark.asyncio
async def test_development_without_explicit_sqlite_fallback_stays_filesystem_only(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SQLITE_FALLBACK_ENABLED", raising=False)

    monkeypatch.setattr(
        db,
        "_init_sqlite",
        lambda: pytest.fail("SQLite fallback requires explicit opt-in"),
    )

    assert await db.get_pool() is None


@pytest.mark.asyncio
async def test_development_keeps_explicit_sqlite_fallback(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SQLITE_FALLBACK_ENABLED", "1")
    sqlite_called = False

    def fake_init_sqlite() -> None:
        nonlocal sqlite_called
        sqlite_called = True

    monkeypatch.setattr(db, "_init_sqlite", fake_init_sqlite)

    assert await db.get_pool() is None
    assert sqlite_called is True


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["true", "yes", "2", "on", ""])
async def test_sqlite_fallback_flag_accepts_only_exact_one(monkeypatch, value: str):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SQLITE_FALLBACK_ENABLED", value)
    monkeypatch.setattr(
        db,
        "_init_sqlite",
        lambda: pytest.fail("non-canonical flag must not enable SQLite"),
    )

    assert await db.get_pool() is None


async def _async_value(value):
    return value
