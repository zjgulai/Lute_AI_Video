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
