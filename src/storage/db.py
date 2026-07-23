"""Database connection management with PostgreSQL primary and SQLite fallback."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_sqlite_conn: sqlite3.Connection | None = None
_sqlite_lock = threading.RLock()
_pg_available: bool = False  # Set to True after successful PG connection + table verification


def _production_requires_postgres() -> bool:
    return os.getenv("ENVIRONMENT", "development").strip().lower() in {
        "prod",
        "production",
    }


def _sqlite_fallback_enabled() -> bool:
    return (
        not _production_requires_postgres()
        and os.getenv("SQLITE_FALLBACK_ENABLED", "") == "1"
    )


async def get_pool() -> asyncpg.Pool | None:
    """Return asyncpg pool singleton, initializing if needed."""
    global _pool
    if _pool is None:
        dsn = os.getenv("DATABASE_URL")
        if dsn and dsn.startswith("postgresql"):
            try:
                _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
                logger.info("PostgreSQL connection pool created")
            except Exception:
                _pool = None
                if _production_requires_postgres():
                    raise RuntimeError("PostgreSQL connection failed in production") from None
                logger.warning("PostgreSQL connection failed; falling back to SQLite")
        elif _production_requires_postgres():
            raise RuntimeError("PostgreSQL is required in production")
        if _pool is None and _sqlite_conn is None and _sqlite_fallback_enabled():
            _init_sqlite()
        elif _pool is None and _sqlite_conn is None:
            logger.info("SQLite fallback disabled; using filesystem-only persistence")
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
    _sqlite_conn = sqlite3.connect(str(db_path), check_same_thread=False)
    _sqlite_conn.row_factory = sqlite3.Row
    _create_sqlite_tables()
    logger.info(f"SQLite fallback initialized at {db_path}")


def get_sqlite_lock() -> threading.RLock:
    return _sqlite_lock


def _create_sqlite_tables() -> None:
    """Create tables in SQLite for development fallback."""
    if _sqlite_conn is None:
        return
    _sqlite_conn.execute("PRAGMA foreign_keys = ON")
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
            transparency TEXT,
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
            acceptance_id TEXT,
            post_id TEXT,
            content TEXT DEFAULT '{}',
            status TEXT,
            url TEXT,
            error TEXT,
            receipt TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS idempotency_records (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            key_hash TEXT NOT NULL,
            trusted_authorization_ref TEXT,
            fingerprint_version TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            operation TEXT NOT NULL,
            scenario TEXT NOT NULL
                CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
            resource_type TEXT NOT NULL
                CHECK (resource_type IN ('fast', 'scenario')),
            resource_id TEXT NOT NULL,
            record_status TEXT NOT NULL
                CHECK (record_status IN (
                    'reserved', 'initializing', 'queued', 'running',
                    'completed', 'failed', 'recovery_required'
                )),
            stage TEXT,
            effective_policy_version TEXT NOT NULL,
            response_status INTEGER NOT NULL,
            response_body TEXT NOT NULL DEFAULT '{}',
            result_snapshot TEXT,
            safe_error_code TEXT,
            owner_instance_id TEXT,
            lease_expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP,
            CONSTRAINT uq_idempotency_records_tenant_key
                UNIQUE (tenant_id, key_hash),
            CONSTRAINT uq_idempotency_records_tenant_resource
                UNIQUE (tenant_id, resource_type, resource_id)
        );
        CREATE TABLE IF NOT EXISTS acceptance_records (
            id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            creation_key_hash TEXT NOT NULL,
            fingerprint_version TEXT NOT NULL,
            request_hash TEXT NOT NULL,
            source_resource_type TEXT NOT NULL
                CHECK (source_resource_type IN ('fast', 'scenario')),
            source_resource_id TEXT NOT NULL,
            scenario TEXT NOT NULL
                CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
            artifact_path TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            artifact_size_bytes INTEGER NOT NULL CHECK (artifact_size_bytes > 0),
            artifact_kind TEXT NOT NULL
                CHECK (artifact_kind IN ('text', 'image', 'audio', 'video')),
            transparency_sidecar_path TEXT,
            transparency_sidecar_sha256 TEXT,
            final_artifact_c2pa_status TEXT,
            decision TEXT NOT NULL
                CHECK (decision IN ('accepted', 'rejected')),
            record_status TEXT NOT NULL
                CHECK (record_status IN (
                    'available', 'rejected', 'consumed', 'expired', 'revoked'
                )),
            reviewer_key_id TEXT NOT NULL,
            reviewer_key_type TEXT NOT NULL
                CHECK (reviewer_key_type IN ('tenant', 'test_bundle', 'env_fallback')),
            review_notes TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            consumed_at TIMESTAMP,
            consumed_by_operation TEXT,
            consumed_by_resource_id TEXT,
            revoked_at TIMESTAMP,
            revoked_by_key_id TEXT,
            revoked_by_record_id TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_acceptance_records_tenant_creation_key
                UNIQUE (tenant_id, creation_key_hash),
            CONSTRAINT ck_acceptance_records_decision_status CHECK (
                (decision = 'accepted' AND record_status IN (
                    'available', 'consumed', 'expired', 'revoked'
                ))
                OR (decision = 'rejected' AND record_status = 'rejected')
            ),
            CONSTRAINT ck_acceptance_records_consumed_fields CHECK (
                (record_status = 'consumed' AND consumed_at IS NOT NULL
                    AND consumed_by_operation IS NOT NULL
                    AND consumed_by_resource_id IS NOT NULL)
                OR (record_status <> 'consumed' AND consumed_at IS NULL
                    AND consumed_by_operation IS NULL
                    AND consumed_by_resource_id IS NULL)
            ),
            CONSTRAINT ck_acceptance_records_revoked_fields CHECK (
                (record_status = 'revoked' AND revoked_at IS NOT NULL
                    AND revoked_by_key_id IS NOT NULL)
                OR (record_status <> 'revoked' AND revoked_at IS NULL
                    AND revoked_by_key_id IS NULL AND revoked_by_record_id IS NULL)
            ),
            CONSTRAINT ck_acceptance_records_transparency_v2 CHECK (
                fingerprint_version <> 'acceptance-create.v2' OR (
                    transparency_sidecar_path IS NOT NULL
                    AND transparency_sidecar_sha256 IS NOT NULL
                    AND final_artifact_c2pa_status IS NOT NULL
                )
            ),
            CONSTRAINT ck_acceptance_records_c2pa_status CHECK (
                final_artifact_c2pa_status IS NULL OR
                final_artifact_c2pa_status IN (
                    'unsigned_pending_review', 'signed_local_readback'
                )
            ),
            CONSTRAINT ck_acceptance_records_accepted_c2pa CHECK (
                decision <> 'accepted' OR final_artifact_c2pa_status IS NULL OR
                final_artifact_c2pa_status = 'signed_local_readback'
            ),
            CONSTRAINT ck_acceptance_records_expiry CHECK (expires_at > created_at)
        );
        CREATE TABLE IF NOT EXISTS job_budget_accounts (
            account_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            job_kind TEXT NOT NULL
                CHECK (job_kind IN ('canonical', 'compatibility')),
            job_id TEXT NOT NULL,
            scenario_or_resource_type TEXT NOT NULL,
            cap_usd_nanos INTEGER NOT NULL CHECK (cap_usd_nanos > 0),
            reserved_usd_nanos INTEGER NOT NULL DEFAULT 0
                CHECK (reserved_usd_nanos >= 0),
            settled_usd_nanos INTEGER NOT NULL DEFAULT 0
                CHECK (settled_usd_nanos >= 0),
            budget_source_kind TEXT NOT NULL
                CHECK (budget_source_kind IN (
                    'server_config', 'validated_authorization'
                )),
            budget_source_ref TEXT,
            budget_policy_version TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_job_budget_accounts_tenant_job
                UNIQUE (tenant_id, job_kind, job_id),
            CONSTRAINT ck_job_budget_accounts_source_ref CHECK (
                (budget_source_kind = 'server_config'
                    AND budget_source_ref IS NULL)
                OR (budget_source_kind = 'validated_authorization'
                    AND budget_source_ref IS NOT NULL)
            ),
            CONSTRAINT ck_job_budget_accounts_conservation CHECK (
                reserved_usd_nanos + settled_usd_nanos <= cap_usd_nanos
            )
        );
        CREATE TABLE IF NOT EXISTS provider_cost_attempts (
            attempt_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            tenant_id TEXT NOT NULL,
            job_kind TEXT NOT NULL
                CHECK (job_kind IN ('canonical', 'compatibility')),
            job_id TEXT NOT NULL,
            scenario_or_resource_type TEXT NOT NULL,
            logical_operation TEXT NOT NULL,
            ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
            attempt_fingerprint TEXT NOT NULL,
            regeneration_epoch_ref TEXT,
            provider TEXT NOT NULL,
            canonical_model TEXT NOT NULL,
            provider_billing_region TEXT NOT NULL
                CHECK (provider_billing_region IN (
                    'deepseek_global_usd', 'poyo_global_usd',
                    'siliconflow_global_usd'
                )),
            catalog_operation TEXT NOT NULL
                CHECK (catalog_operation IN (
                    'chat_completion', 'speech_synthesis', 'image_generation',
                    'text_to_video', 'image_to_video'
                )),
            media_type TEXT NOT NULL
                CHECK (media_type IN ('text', 'audio', 'image', 'video')),
            billing_fact_kind TEXT NOT NULL
                CHECK (billing_fact_kind IN (
                    'llm_tokens.v1', 'tts_utf8_bytes.v1', 'image_count.v1',
                    'video_task.v1', 'video_duration.v1'
                )),
            price_rule_id TEXT NOT NULL,
            price_catalog_version TEXT NOT NULL,
            price_rule_version TEXT NOT NULL,
            reservation_billing_facts TEXT NOT NULL,
            settlement_billing_facts TEXT,
            reserved_usd_nanos INTEGER NOT NULL CHECK (reserved_usd_nanos > 0),
            settled_usd_nanos INTEGER NOT NULL DEFAULT 0
                CHECK (
                    settled_usd_nanos >= 0
                    AND settled_usd_nanos <= reserved_usd_nanos
                ),
            provider_reported_cost_usd_nanos INTEGER
                CHECK (
                    provider_reported_cost_usd_nanos IS NULL
                    OR provider_reported_cost_usd_nanos >= 0
                ),
            provider_reported_credit_micro_units INTEGER
                CHECK (
                    provider_reported_credit_micro_units IS NULL
                    OR provider_reported_credit_micro_units >= 0
                ),
            provider_reported_currency TEXT
                CHECK (
                    provider_reported_currency IS NULL
                    OR provider_reported_currency = 'USD'
                ),
            state TEXT NOT NULL
                CHECK (state IN (
                    'reserved', 'submission_started', 'submitted', 'settled',
                    'released', 'ambiguous', 'accounting_error'
                )),
            external_task_id TEXT,
            provider_trace_id TEXT,
            safe_error_code TEXT,
            reservation_expires_at TIMESTAMP NOT NULL,
            submission_started_at TIMESTAMP,
            submitted_at TIMESTAMP,
            terminal_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_provider_cost_attempts_account
                FOREIGN KEY (account_id)
                REFERENCES job_budget_accounts(account_id) ON DELETE RESTRICT,
            CONSTRAINT uq_provider_cost_attempts_operation_ordinal
                UNIQUE (account_id, logical_operation, ordinal),
            CONSTRAINT ck_provider_cost_attempts_state_fields CHECK (
                (state = 'reserved'
                    AND submission_started_at IS NULL
                    AND submitted_at IS NULL
                    AND terminal_at IS NULL
                    AND settlement_billing_facts IS NULL
                    AND settled_usd_nanos = 0)
                OR (state = 'submission_started'
                    AND submission_started_at IS NOT NULL
                    AND submitted_at IS NULL
                    AND terminal_at IS NULL
                    AND settlement_billing_facts IS NULL
                    AND settled_usd_nanos = 0)
                OR (state = 'submitted'
                    AND submission_started_at IS NOT NULL
                    AND submitted_at IS NOT NULL
                    AND terminal_at IS NULL
                    AND settlement_billing_facts IS NULL
                    AND settled_usd_nanos = 0)
                OR (state = 'settled'
                    AND submission_started_at IS NOT NULL
                    AND terminal_at IS NOT NULL
                    AND settlement_billing_facts IS NOT NULL
                    AND settled_usd_nanos > 0)
                OR (state = 'released'
                    AND terminal_at IS NOT NULL
                    AND settlement_billing_facts IS NULL
                    AND settled_usd_nanos = 0)
                OR (state IN ('ambiguous', 'accounting_error')
                    AND terminal_at IS NOT NULL
                    AND settled_usd_nanos = 0
                    AND safe_error_code IS NOT NULL)
            )
        );
        CREATE INDEX IF NOT EXISTS idx_threads_thread_id ON threads(thread_id);
        CREATE INDEX IF NOT EXISTS idx_pipeline_states_label ON pipeline_states(label);
        CREATE INDEX IF NOT EXISTS idx_pipeline_states_tenant ON pipeline_states(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_publish_logs_platform ON publish_logs(platform);
        CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_created_at
            ON publish_logs(tenant_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_acceptance
            ON publish_logs(tenant_id, acceptance_id);
        CREATE INDEX IF NOT EXISTS idx_publish_logs_tenant_platform_post_receipt
            ON publish_logs(tenant_id, platform, post_id)
            WHERE status = 'published'
              AND receipt IS NOT NULL
              AND post_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_vm_video_id ON video_metrics(video_id);
        CREATE INDEX IF NOT EXISTS idx_vm_scenario ON video_metrics(scenario);
        CREATE INDEX IF NOT EXISTS idx_vm_platform ON video_metrics(platform);
        CREATE INDEX IF NOT EXISTS idx_vm_tenant ON video_metrics(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_vm_pulled_at ON video_metrics(pulled_at);
        CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_type, actor_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
        CREATE INDEX IF NOT EXISTS idx_idempotency_records_status
            ON idempotency_records(tenant_id, record_status);
        CREATE INDEX IF NOT EXISTS idx_idempotency_records_lease
            ON idempotency_records(lease_expires_at)
            WHERE lease_expires_at IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_idempotency_records_tenant_authorization
            ON idempotency_records(tenant_id, trusted_authorization_ref)
            WHERE trusted_authorization_ref IS NOT NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_acceptance_records_tenant_available_path
            ON acceptance_records(tenant_id, artifact_path)
            WHERE record_status = 'available';
        CREATE INDEX IF NOT EXISTS idx_acceptance_records_source
            ON acceptance_records(tenant_id, source_resource_type, source_resource_id);
        CREATE INDEX IF NOT EXISTS idx_acceptance_records_status
            ON acceptance_records(tenant_id, record_status);
        CREATE INDEX IF NOT EXISTS idx_acceptance_records_expiry
            ON acceptance_records(expires_at)
            WHERE record_status = 'available';
        CREATE INDEX IF NOT EXISTS idx_provider_cost_attempts_account_state
            ON provider_cost_attempts(account_id, state);
        CREATE INDEX IF NOT EXISTS idx_provider_cost_attempts_reservation_expiry
            ON provider_cost_attempts(reservation_expires_at)
            WHERE state = 'reserved';
    """)
    _sqlite_conn.commit()


def _ensure_sqlite_compat_columns() -> None:
    """Backfill columns for existing SQLite fallback databases."""
    if _sqlite_conn is None:
        return

    for table, column, column_type in (
        ("pipeline_states", "tenant_id", "TEXT"),
        ("pipeline_states", "transparency", "TEXT"),
        ("video_metrics", "tenant_id", "TEXT"),
        ("publish_logs", "tenant_id", "TEXT"),
        ("publish_logs", "acceptance_id", "TEXT"),
        ("publish_logs", "updated_at", "TIMESTAMP"),
        ("publish_logs", "receipt", "TEXT"),
        ("idempotency_records", "trusted_authorization_ref", "TEXT"),
        ("provider_cost_attempts", "regeneration_epoch_ref", "TEXT"),
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
    "idempotency_records",
    "acceptance_records",
    "job_budget_accounts",
    "provider_cost_attempts",
]

_REQUIRED_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "publish_logs": frozenset(
        {
            "tenant_id",
            "acceptance_id",
            "updated_at",
            "receipt",
        }
    ),
    "idempotency_records": frozenset(
        {
            "trusted_authorization_ref",
        }
    ),
    "job_budget_accounts": frozenset(
        {
            "account_id",
            "cap_usd_nanos",
            "reserved_usd_nanos",
            "settled_usd_nanos",
        }
    ),
    "provider_cost_attempts": frozenset(
        {
            "attempt_id",
            "account_id",
            "attempt_fingerprint",
            "regeneration_epoch_ref",
            "reservation_billing_facts",
            "state",
        }
    ),
}


async def _verify_required_columns(conn: Any) -> bool:
    for table, required in _REQUIRED_TABLE_COLUMNS.items():
        rows = await conn.fetch(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = $1
            """,
            table,
        )
        present = {row["column_name"] for row in rows}
        missing = required - present
        if missing:
            logger.warning("PG table has incomplete required schema: %s", table)
            return False
    return True


async def _verify_pg_tables(conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy) -> bool:
    """Verify all required tables exist in PG. Returns True if all present."""
    for table in _REQUIRED_TABLES:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = $1)",
            table,
        )
        if not exists:
            logger.warning("PG table missing: %s", table)
            return False
    if not await _verify_required_columns(conn):
        return False
    logger.info("PG: all %d required tables verified", len(_REQUIRED_TABLES))
    return True


def _code_alembic_head() -> str:
    """Resolve the single reviewed code head without touching a database."""

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    repo_root = Path(__file__).resolve().parents[2]
    config = Config(str(repo_root / "migrations" / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(repo_root / "migrations" / "alembic"),
    )
    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("Alembic code history must have exactly one head")
    return heads[0]


async def _inspect_alembic_head(
    conn: asyncpg.Connection | asyncpg.pool.PoolConnectionProxy,
) -> dict[str, Any]:
    """Compare the database revision with the single reviewed code head."""

    try:
        head_revision = _code_alembic_head()
    except Exception:
        return {
            "ready": False,
            "status": "code_head_unavailable",
            "current_revision": None,
            "head_revision": None,
        }
    try:
        rows = await conn.fetch(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        )
    except Exception:
        return {
            "ready": False,
            "status": "version_missing",
            "current_revision": None,
            "head_revision": head_revision,
        }
    revisions = [str(row["version_num"]) for row in rows]
    if not revisions:
        status = "version_missing"
        current_revision = None
    elif len(revisions) != 1:
        status = "multiple_current_revisions"
        current_revision = None
    else:
        current_revision = revisions[0]
        status = "at_head" if current_revision == head_revision else "behind_head"
    return {
        "ready": status == "at_head",
        "status": status,
        "current_revision": current_revision,
        "head_revision": head_revision,
    }


async def check_database_readiness() -> dict[str, Any]:
    """Return side-effect-free database readiness for HTTP and startup gates."""

    global _pg_available
    if _pool is None:
        _pg_available = False
        if _sqlite_conn is not None and _sqlite_fallback_enabled():
            return {
                "ready": True,
                "backend": "sqlite",
                "status": "ready_development_fallback",
                "tables_verified": False,
                "migration": {"ready": False, "status": "not_applicable"},
            }
        return {
            "ready": False,
            "backend": "postgresql" if _production_requires_postgres() else "filesystem",
            "status": "not_initialized",
            "tables_verified": False,
            "migration": {"ready": False, "status": "not_checked"},
        }
    try:
        async with _pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            tables_ok = await _verify_pg_tables(conn)
            migration = await _inspect_alembic_head(conn)
    except Exception:
        _pg_available = False
        return {
            "ready": False,
            "backend": "postgresql",
            "status": "connection_error",
            "tables_verified": False,
            "migration": {"ready": False, "status": "not_checked"},
        }
    ready = tables_ok and migration.get("ready") is True
    _pg_available = ready
    return {
        "ready": ready,
        "backend": "postgresql",
        "status": "ready" if ready else (
            "migration_not_ready"
            if migration.get("ready") is not True
            else "schema_not_ready"
        ),
        "tables_verified": tables_ok,
        "migration": migration,
    }


async def check_pg_health() -> dict[str, Any]:
    """Return a health-check dict describing the PG (or fallback) status.

    This is safe to call from /health — no side effects, no table creation.
    """
    global _pg_available, _pool
    if _pool is None:
        _pool = await get_pool()
    if _pool is None:
        return {
            "backend": "filesystem",
            "status": "pg_unavailable",
            "fallback": "sqlite" if _sqlite_conn else "json_only",
        }
    readiness = await check_database_readiness()
    if readiness["backend"] != "postgresql":
        return {
            "backend": readiness["backend"],
            "status": "pg_unavailable",
            "fallback": "sqlite" if _sqlite_conn else "json_only",
        }
    return {
        "backend": "postgresql",
        "status": "healthy" if readiness["ready"] else readiness["status"],
        "tables_verified": readiness["tables_verified"],
        "migration": readiness["migration"],
    }


async def _discard_failed_pool(pool: asyncpg.Pool) -> None:
    """Close a startup-failed pool without masking the verification error."""

    global _pool
    try:
        await pool.close()
    except Exception as exc:
        logger.warning("PG pool cleanup failed: %s", type(exc).__name__)
    finally:
        if _pool is pool:
            _pool = None


async def init_db() -> None:
    """Verify the configured database without applying schema migrations.

    On startup this is called from the FastAPI lifespan event.
    Production requires PostgreSQL with the complete required schema and fails
    closed. Alembic is executed only by the explicit deployment migration gate.
    Development and tests retain the existing SQLite fallback.
    """
    global _pg_available
    pool = await get_pool()
    if pool is None:
        if _production_requires_postgres():
            raise RuntimeError("PostgreSQL is required in production")
        logger.info("PG unavailable — using SQLite fallback (tables created on connection)")
        _pg_available = False
        return
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
            if await _verify_pg_tables(conn):
                migration = await _inspect_alembic_head(conn)
                if migration["ready"] is True:
                    _pg_available = True
                    logger.info(
                        "PostgreSQL initialized — required schema verified at Alembic head"
                    )
                else:
                    _pg_available = False
                    if _production_requires_postgres():
                        raise RuntimeError("required PostgreSQL migration is not ready")
                    logger.warning(
                        "PG migration is not ready: %s",
                        migration["status"],
                    )
            else:
                _pg_available = False
                if _production_requires_postgres():
                    raise RuntimeError("required PostgreSQL schema is not ready")
                logger.warning("PG connected but some tables are missing")
    except Exception as exc:
        _pg_available = False
        if _production_requires_postgres():
            await _discard_failed_pool(pool)
            if isinstance(exc, RuntimeError):
                raise
            raise RuntimeError("PostgreSQL startup verification failed in production") from None
        logger.warning("PG init failed; falling back to filesystem-only")


def is_pg_available() -> bool:
    """Return True if PG is connected and tables are verified."""
    return _pg_available


def get_verified_pg_pool() -> asyncpg.Pool | None:
    """Return the already-verified PG pool without initializing a fallback.

    Generation idempotency is fail-closed in production.  This accessor lets
    that path require the pool verified during startup without calling
    :func:`get_pool`, whose general-purpose behavior may initialize SQLite.
    """

    if not _pg_available:
        return None
    return _pool


def get_sqlite_conn() -> sqlite3.Connection | None:
    """Return the SQLite connection (for fallback mode)."""
    return _sqlite_conn
