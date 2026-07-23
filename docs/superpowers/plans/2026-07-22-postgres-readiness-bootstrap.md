# W2-05-W2-09 PostgreSQL Readiness and Bootstrap Plan

**Scope:** Local/disposable-only closure for production database fail-fast, explicit SQLite
fallback, liveness/readiness, Alembic-head truth, canonical PostgreSQL 18 bootstrap, and a guarded
disposable verification lane. No production database, remote infrastructure, GitHub mutation,
provider, publish, or delivery action is permitted.

**Completion truth:** This batch is complete locally only when focused/full tests, static gates,
disposable PG18 fresh/historical bootstrap, documentation synchronization, and an independent
six-dimension review all pass. Remote CI and new-code deployment remain separate gates while GitHub
updates are forbidden.

## Task 1 — Explicit fallback and production startup truth (W2-05)

**Files:** `src/storage/db.py`, `tests/test_database_startup_readiness.py`, `tests/conftest.py`.

**RED:** prove development without `SQLITE_FALLBACK_ENABLED=1` does not create SQLite; explicit
development/test opt-in does; production ignores the flag and fails on missing/invalid PostgreSQL;
connection and schema failures expose stable safe codes without DSN/password values.

**GREEN:** add one strict boolean fallback setting, keep production PostgreSQL-only, close partial
pools on failed initialization, and preserve fail-fast startup.

## Task 2 — Liveness/readiness and Docker health (W2-06)

**Files:** `src/routers/health.py`, `src/storage/db.py`,
`deploy/lighthouse/docker-compose.release.yml`, tracked deployment-contract tests.

**RED:** `/health/live` is process-only 200; `/health/ready` is 200 only when required PostgreSQL
tables and the single Alembic head match in production, otherwise sanitized 503. Development with
explicit SQLite may be ready but must identify its lower evidence backend. Docker backend health
must use `/health/ready`, not `/health`.

**GREEN:** implement side-effect-free readiness projection and status code, preserve `/health`
compatibility, and point the immutable release compose healthcheck to readiness.

## Task 3 — Alembic error truth and canonical head (W2-07)

**Files:** `src/storage/db.py`, `scripts/deploy_alembic_gate.sh`, focused tests/runbook.

**RED:** multiple heads, missing `alembic_version`, command failure, or post-apply mismatch remains
nonzero and records a stable safe reason; no exception is converted to a healthy response and no
connection string reaches logs or HTTP.

**GREEN:** use one canonical code-head resolver and sanitized readiness reason. Keep schema mutation
only in the explicit deployment gate; application startup/readiness remains read-only.

## Task 4 — PostgreSQL 18 canonical bootstrap (W2-08)

**Files:** guarded PG18 test helper, `docs/runbooks/postgresql-readiness-bootstrap.md`, runbook index
or docs scope where required.

**RED:** an empty disposable PG18 database and an historical/base disposable database do not yet
have recorded proof of reaching the same single head and required schema.

**GREEN:** because the first Alembic revision is an existing-schema no-op, use the guarded
`001_init.sql` mirror plus an atomic single-head stamp only for a verified empty PostgreSQL 18
database. Historical databases use only `alembic upgrade head` via the reviewed migration config.
Prove both paths and an idempotent historical re-upgrade converge to one head. Never run
application-side migration or rewrite migration history.

## Task 5 — Guarded disposable/CI lane (W2-09)

**Files:** `tests/test_database_bootstrap_pg18.py`, a local verification script if existing project
conventions require it, and roadmap/Kiro evidence.

The lane must capture its DSN before application imports, accept only
`postgresql://postgres@127.0.0.1:55441/ai_video_bootstrap`, reject passwords/other hosts/ports/dbs,
verify actual server major version 18 and database identity before mutation, and drop/recreate only
that disposable database. It must assert fresh bootstrap, historical upgrade, current=head,
required tables/columns, and readiness 200. Remote CI execution remains `blocked_external` until
GitHub updates are allowed; local execution is not remote CI evidence.

## Task 6 — Integration, review, and release boundary

Run focused tests, full backend, deployment contracts, Ruff, Pyright, diff/secret/log scans, and the
guarded disposable PG18 lane. Synchronize the roadmap and runbook without calling local evidence
production readiness. Send the complete diff to the existing independent read-only reviewer for
requirements, logic, edge cases, quality, coverage, and actual results; fix/reverify until
`PASS / APPROVE` or a concrete blocker.

**Deployment gate:** The canonical release wrapper requires a clean reviewed `origin/main` SHA.
Because the user currently forbids GitHub updates, do not stage/commit/push/deploy this new code and
do not replace provenance with rsync or mutable source. Existing production remains unchanged.
