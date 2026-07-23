# Database Migrations (Alembic)

P2-9: Managed database schema changes for PostgreSQL.

## Setup

```bash
# Ensure DATABASE_URL is set
export DATABASE_URL="postgresql://user:pass@host/dbname"

# Verify alembic can connect
alembic current
```

## Usage

### Empty PostgreSQL 18 database

Use the guarded atomic baseline bootstrap only when the target database has no
application tables:

```bash
POSTGRES_BOOTSTRAP_AUTH=APPLY_EMPTY_DATABASE_BASELINE \
  python scripts/bootstrap_postgres.py
```

The script requires `DATABASE_URL`, verifies PostgreSQL major version 18 and an
empty schema, applies `src/storage/migrations/001_init.sql`, verifies required
tables/columns, and stamps the single Alembic head in one transaction. It
refuses a non-empty database or any existing non-empty `alembic_version`
lineage and never prints the connection string. An existing revision is
historical authority and must never be overwritten by the empty bootstrap.

### Historical database

Historical databases must never run the empty baseline bootstrap. Use the
reviewed deployment gate, which executes `alembic upgrade head` and verifies
that the post-apply revision equals the single code head:

```bash
ENVIRONMENT=production DEPLOY_MIGRATION_AUTH=APPLY_REVIEWED_RELEASE \
  scripts/deploy_alembic_gate.sh --apply
```

Application startup and `/health/ready` are read-only schema/head checks. They
never create tables, stamp revisions, or apply migrations.

```bash
# Run all pending migrations
alembic upgrade head

# Create a new migration (hand-written SQL — no autogenerate)
alembic revision -m "describe_your_change"
# Then edit migrations/alembic/versions/xxx_describe_your_change.py

# Downgrade one step
alembic downgrade -1

# Downgrade to baseline
alembic downgrade base

# View history
alembic history --verbose
```

## Rules

1. **All PG schema changes must go through Alembic** — no hand-run `ALTER TABLE`
2. **Migrations are hand-written** (no SQLAlchemy ORM models) — use `op.execute("SQL...")`
3. **SQLite fallback does not use Alembic** — SQLite tables are auto-created in `db.py`
4. **Always include downgrade** — every migration must be reversible

## Current Migrations

| Revision | Description |
|----------|-------------|
| 42eb2682e54b | Baseline — existing tables (threads, pipeline_states, brand_packages, influencers, publish_logs) |
| 1efc41794d64 | Add `video_metrics` table (previously SQLite-only) |
| d9e0f1a2b3c4 | Bind new acceptance records to transparency sidecar and final C2PA truth; keep legacy rows nullable |
