"""Database connection management with PostgreSQL primary and SQLite fallback."""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_sqlite_conn: sqlite3.Connection | None = None
_pg_available: bool = False  # Set to True after successful PG connection + table verification


async def get_pool() -> asyncpg.Pool | None:
    """Return asyncpg pool singleton, initializing if needed."""
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if dsn and dsn.startswith("postgresql"):
            try:
                _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
                logger.info("PostgreSQL connection pool created")
            except Exception as e:
                logger.warning(f"PostgreSQL connection failed: {e}. Falling back to SQLite.")
                _pool = None
        if _pool is None:
            _init_sqlite()
    return _pool


async def close_pool() -> None:
    """Close the asyncpg pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")


def _init_sqlite() -> None:
    """Initialize SQLite connection and tables."""
    global _sqlite_conn
    db_path = Path("./output/ai_video.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _sqlite_conn = sqlite3.connect(str(db_path))
    _sqlite_conn.row_factory = sqlite3.Row
    _create_sqlite_tables()
    logger.info(f"SQLite fallback initialized at {db_path}")


def _create_sqlite_tables() -> None:
    """Create tables in SQLite for development fallback."""
    if _sqlite_conn is None:
        return
    _ensure_sqlite_compat_columns()
    _sqlite_conn.executescript("""
        CREATE TABLE IF NOT EXISTS threads (
            id TEXT PRIMARY KEY,
            thread_id TEXT UNIQUE NOT NULL,
            state TEXT NOT NULL DEFAULT '{}',
            current_step TEXT,
            pipeline_complete INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS pipeline_states (
            id TEXT PRIMARY KEY,
            label TEXT UNIQUE NOT NULL,
            scenario TEXT,
            config TEXT DEFAULT '{}',
            steps TEXT DEFAULT '{}',
            current_step TEXT,
            mode TEXT DEFAULT 'auto',
            errors TEXT DEFAULT '[]',
            media_synthesis_errors TEXT DEFAULT '[]',
            gates TEXT DEFAULT '{}',
            schema_version INTEGER,
            pipeline_degraded INTEGER,
            degraded_reason TEXT,
            trace_id TEXT,
            structured_errors TEXT DEFAULT '[]',
            regenerate_chain TEXT DEFAULT '[]',
            soft_degraded_reasons TEXT DEFAULT '[]',
            tenant_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS brand_packages (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            brand_guidelines TEXT DEFAULT '{}',
            assets TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS influencers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            platform TEXT,
            profile TEXT DEFAULT '{}',
            contact_info TEXT DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS publish_logs (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            tenant_id TEXT,
            post_id TEXT,
            content TEXT DEFAULT '{}',
            status TEXT,
            url TEXT,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS video_metrics (
            id TEXT PRIMARY KEY,
            video_id TEXT NOT NULL,
            scenario TEXT NOT NULL,
            platform TEXT NOT NULL,
            tenant_id TEXT,
            post_id TEXT,
            post_url TEXT,
            metrics TEXT DEFAULT '{}',
            pulled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            actor_type TEXT NOT NULL,
            actor_id TEXT,
            action TEXT NOT NULL,
            resource_type TEXT,
            resource_id TEXT,
            payload TEXT DEFAULT '{}',
            success INTEGER DEFAULT 1,
            client_ip TEXT,
            trace_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_threads_thread_id ON threads(thread_id);
        CREATE INDEX IF NOT EXISTS idx_pipeline_states_label ON pipeline_states(label);
        CREATE INDEX IF NOT EXISTS idx_pipeline_states_tenant ON pipeline_states(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_publish_logs_platform ON publish_logs(platform);
        CREATE INDEX IF NOT EXISTS idx_vm_video_id ON video_metrics(video_id);
        CREATE INDEX IF NOT EXISTS idx_vm_scenario ON video_metrics(scenario);
        CREATE INDEX IF NOT EXISTS idx_vm_platform ON video_metrics(platform);
        CREATE INDEX IF NOT EXISTS idx_vm_tenant ON video_metrics(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_vm_pulled_at ON video_metrics(pulled_at);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_type, actor_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
    """)
    _sqlite_conn.commit()


def _ensure_sqlite_compat_columns() -> None:
    """Backfill columns for existing SQLite fallback databases."""
    if _sqlite_conn is None:
        return

    for table, column, column_type in (
        ("pipeline_states", "tenant_id", "TEXT"),
        ("video_metrics", "tenant_id", "TEXT"),
    ):
        rows = _sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
        if not rows:
            continue
        existing = {row["name"] for row in rows}
        if column in existing:
            continue
        _sqlite_conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        logger.info("SQLite fallback schema backfilled %s.%s", table, column)


# Required tables for the application to function with PG persistence
_REQUIRED_TABLES: list[str] = [
    "threads",
    "pipeline_states",
    "brand_packages",
    "influencers",
    "publish_logs",
    "video_metrics",
]


async def _verify_pg_tables(conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy) -> bool:
    """Verify all required tables exist in PG. Returns True if all present."""
    for table in _REQUIRED_TABLES:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = $1)",
            table,
        )
        if not exists:
            logger.warning("PG table missing: %s", table)
            return False
    logger.info("PG: all %d required tables verified", len(_REQUIRED_TABLES))
    return True


async def check_pg_health() -> dict[str, Any]:
    """Return a health-check dict describing the PG (or fallback) status.

    This is safe to call from /health — no side effects, no table creation.
    """
    global _pg_available, _pool
    if _pool is None:
        _pool = await get_pool()
    if _pool is None:
        return {"backend": "filesystem", "status": "pg_unavailable", "fallback": "sqlite" if _sqlite_conn else "json_only"}
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            tables_ok = await _verify_pg_tables(conn)
        _pg_available = tables_ok
        return {
            "backend": "postgresql",
            "status": "healthy" if tables_ok else "tables_missing",
            "tables_verified": tables_ok,
        }
    except Exception as e:
        _pg_available = False
        logger.warning("PG health check failed: %s", e)
        return {"backend": "postgresql", "status": "connection_error", "error": str(e)[:200]}


async def init_db() -> None:
    """Initialize database (PostgreSQL via Alembic migrations or SQLite fallback).

    On startup this is called from the FastAPI lifespan event.
    For PG: runs `alembic upgrade head` to apply any pending migrations,
    then verifies required tables exist. Sets _pg_available so the rest
    of the app can skip PG calls when it's unhealthy.
    """
    global _pg_available
    pool = await get_pool()
    if pool is None:
        logger.info("PG unavailable — using SQLite fallback (tables created on connection)")
        _pg_available = False
        return
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            # Run Alembic migrations to bring schema up to date.
            # The inlined SQL in 001_init.sql is a belt-and-suspenders safety net
            # for fresh docker compose environments; Alembic is the authoritative
            # schema manager.
            _run_alembic_migrations()
            if await _verify_pg_tables(conn):
                _pg_available = True
                logger.info("PostgreSQL initialized — pipeline_states and all tables verified")
            else:
                logger.warning("PG connected but some tables missing — check migrations")
                _pg_available = False
    except Exception as e:
        logger.warning("PG init failed: %s — falling back to filesystem-only", e)
        _pg_available = False


def _run_alembic_migrations() -> None:
    """Run Alembic migrations if available. Non-fatal on failure."""
    try:
        import os

        from alembic import command
        from alembic.config import Config
        # Look for alembic.ini relative to the project root
        project_root = os.environ.get("PROJECT_ROOT", os.getcwd())
        ini_path = os.path.join(project_root, "migrations", "alembic.ini")
        if os.path.exists(ini_path):
            alembic_cfg = Config(ini_path)
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations applied successfully")
        else:
            logger.info("alembic.ini not found at %s — skipping migrations (using SQL init)", ini_path)
    except Exception:
        logger.debug("Alembic migration skipped (non-fatal): %s", str(_e)[:100] if (_e := None) else "")


def is_pg_available() -> bool:
    """Return True if PG is connected and tables are verified."""
    return _pg_available


def get_sqlite_conn() -> sqlite3.Connection | None:
    """Return the SQLite connection (for fallback mode)."""
    return _sqlite_conn
