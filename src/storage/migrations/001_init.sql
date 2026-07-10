-- SQL init for fresh `docker compose up` — provides a complete baseline schema.
--
-- IMPORTANT: Alembic (migrations/alembic/) is the authoritative schema manager.
-- This file mirrors the Alembic head revision for convenience but should NOT
-- contain DDL that hasn't been added via Alembic first. When adding new tables
-- or columns:
--   1. Create an Alembic migration:  alembic revision -m "description"
--   2. Implement the migration in migrations/alembic/versions/
--   3. Run alembic upgrade head to apply
--   4. THEN mirror the final DDL here (with IF NOT EXISTS guards)
--
-- The backend entrypoint also runs `alembic upgrade head` on startup when PG
-- is available (see src/storage/db.py), making the inlined DDL a belt-and-
-- suspenders safety net rather than the primary schema pathway.
--
-- Ref: debt-audit-report-2026-06-09.md item E22, Phase2.3 remediation

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Admin control-plane tables, mirrors Alembic 2d6b8e9c0f1a.
CREATE TABLE IF NOT EXISTS admin_accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    admin_id UUID NOT NULL REFERENCES admin_accounts(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_token_hash
    ON admin_sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires
    ON admin_sessions(expires_at);

CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(64) UNIQUE NOT NULL
        CHECK (tenant_id ~ '^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$'),
    display_name VARCHAR(255) NOT NULL DEFAULT '',
    contact_email VARCHAR(255) NOT NULL DEFAULT '',
    status VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS error_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(64),
    scenario VARCHAR(64),
    error_code VARCHAR(32),
    message TEXT NOT NULL,
    traceback TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_error_logs_created_at
    ON error_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_error_logs_tenant_created
    ON error_logs(tenant_id, created_at DESC);

-- threads: LangGraph pipeline threads
CREATE TABLE IF NOT EXISTS threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id TEXT UNIQUE NOT NULL,
    state JSONB NOT NULL DEFAULT '{}',
    current_step VARCHAR(50),
    pipeline_complete BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- pipeline_states: S1 step-by-step states
CREATE TABLE IF NOT EXISTS pipeline_states (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    label VARCHAR(64) UNIQUE NOT NULL,
    scenario VARCHAR(32),
    config JSONB DEFAULT '{}',
    steps JSONB DEFAULT '{}',
    current_step VARCHAR(50),
    mode VARCHAR(16) DEFAULT 'auto',
    errors JSONB DEFAULT '[]',
    media_synthesis_errors JSONB DEFAULT '[]',
    gates JSONB DEFAULT '{}',
    tenant_id VARCHAR(64),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- gates column (added 2026-05-03 for S1 step-by-step gate persistence)
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS gates JSONB DEFAULT '{}';

-- Phase 0 #1 fix (2026-05-15): runtime state columns, mirrors Alembic
-- 7a2f4b8c9d12. Inlined so a fresh `docker compose up` matches the
-- migrated PG schema without requiring `alembic upgrade head`. Closes
-- Oracle-identified regression where degraded/version/trace fields were
-- dropped on PG round-trip.
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS schema_version INT;
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS pipeline_degraded BOOLEAN;
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS degraded_reason TEXT;
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS trace_id TEXT;
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS structured_errors JSONB DEFAULT '[]';
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

-- brand_packages
CREATE TABLE IF NOT EXISTS brand_packages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(128) NOT NULL,
    brand_guidelines JSONB DEFAULT '{}',
    assets JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- influencers
CREATE TABLE IF NOT EXISTS influencers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(128) NOT NULL,
    platform VARCHAR(32),
    profile JSONB DEFAULT '{}',
    contact_info JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- publish_logs
CREATE TABLE IF NOT EXISTS publish_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    platform VARCHAR(32) NOT NULL,
    post_id VARCHAR(128),
    content JSONB DEFAULT '{}',
    status VARCHAR(32),
    url TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- video_metrics: cross-platform performance metrics, mirrors Alembic 1efc41794d64.
-- Inlined here so a fresh `docker compose up` lands a complete schema without
-- requiring a separate `alembic upgrade head` step.
CREATE TABLE IF NOT EXISTS video_metrics (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    video_id VARCHAR(128) NOT NULL,
    scenario VARCHAR(32) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    tenant_id VARCHAR(64),
    post_id VARCHAR(128),
    post_url TEXT,
    metrics JSONB DEFAULT '{}',
    pulled_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
ALTER TABLE video_metrics ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

-- api_keys: per-tenant API key management (P2-8)
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id VARCHAR(64) NOT NULL,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    permissions JSONB DEFAULT '["all"]',
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,
    revoked_at TIMESTAMP,
    last_used_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);

-- audit_logs: business-event audit trail, mirrors Alembic 9f1e2c8a4b67.
CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    ts TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    actor_type VARCHAR(32) NOT NULL,
    actor_id VARCHAR(128),
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64),
    resource_id VARCHAR(128),
    payload JSONB DEFAULT '{}',
    success BOOLEAN DEFAULT TRUE,
    client_ip INET,
    trace_id VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_logs(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_type, actor_id);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action);
CREATE INDEX IF NOT EXISTS idx_audit_resource ON audit_logs(resource_type, resource_id);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_threads_thread_id ON threads(thread_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_states_label ON pipeline_states(label);
CREATE INDEX IF NOT EXISTS idx_pipeline_states_tenant ON pipeline_states(tenant_id);
CREATE INDEX IF NOT EXISTS idx_publish_logs_platform ON publish_logs(platform);
CREATE INDEX IF NOT EXISTS idx_vm_video_id ON video_metrics(video_id);
CREATE INDEX IF NOT EXISTS idx_vm_scenario ON video_metrics(scenario);
CREATE INDEX IF NOT EXISTS idx_vm_platform ON video_metrics(platform);
CREATE INDEX IF NOT EXISTS idx_vm_tenant ON video_metrics(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vm_pulled_at ON video_metrics(pulled_at);
CREATE INDEX IF NOT EXISTS idx_vm_video_platform_pulled ON video_metrics(video_id, platform, pulled_at DESC);
CREATE INDEX IF NOT EXISTS idx_vm_pulled_scenario_platform ON video_metrics(pulled_at DESC, scenario, platform);
