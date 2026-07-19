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
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS regenerate_chain JSONB DEFAULT '[]';
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS soft_degraded_reasons JSONB DEFAULT '[]';

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
    tenant_id VARCHAR(64),
    acceptance_id VARCHAR(36),
    post_id VARCHAR(128),
    content JSONB DEFAULT '{}',
    status VARCHAR(32),
    url TEXT,
    error TEXT,
    receipt JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);

ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);
ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS acceptance_id VARCHAR(36);
ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS receipt JSONB;

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
    permissions JSONB DEFAULT '[]',
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

-- idempotency_records: durable tenant-scoped arbitration for canonical async
-- generation submits, mirrors Alembic d5e6f7a8b9c0. Raw Idempotency-Key values
-- and request/provider credentials are intentionally not stored.
CREATE TABLE IF NOT EXISTS idempotency_records (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    key_hash VARCHAR(64) NOT NULL,
    fingerprint_version VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    scenario VARCHAR(16) NOT NULL
        CONSTRAINT ck_idempotency_records_scenario
        CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
    resource_type VARCHAR(16) NOT NULL
        CONSTRAINT ck_idempotency_records_resource_type
        CHECK (resource_type IN ('fast', 'scenario')),
    resource_id VARCHAR(128) NOT NULL,
    record_status VARCHAR(32) NOT NULL
        CONSTRAINT ck_idempotency_records_status
        CHECK (record_status IN (
            'reserved', 'initializing', 'queued', 'running',
            'completed', 'failed', 'recovery_required'
        )),
    stage VARCHAR(64),
    effective_policy_version VARCHAR(64) NOT NULL,
    response_status INTEGER NOT NULL,
    response_body JSONB NOT NULL DEFAULT '{}',
    result_snapshot JSONB,
    safe_error_code VARCHAR(64),
    owner_instance_id VARCHAR(128),
    lease_expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT uq_idempotency_records_tenant_key
        UNIQUE (tenant_id, key_hash),
    CONSTRAINT uq_idempotency_records_tenant_resource
        UNIQUE (tenant_id, resource_type, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_idempotency_records_status
    ON idempotency_records(tenant_id, record_status);
CREATE INDEX IF NOT EXISTS idx_idempotency_records_lease
    ON idempotency_records(lease_expires_at)
    WHERE lease_expires_at IS NOT NULL;

-- acceptance_records: single-use human acceptance authority, mirrors Alembic
-- e8f1a2b3c4d5. Creation keys are stored only as SHA-256 hashes.
CREATE TABLE IF NOT EXISTS acceptance_records (
    id VARCHAR(36) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    creation_key_hash VARCHAR(64) NOT NULL,
    fingerprint_version VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    source_resource_type VARCHAR(16) NOT NULL
        CHECK (source_resource_type IN ('fast', 'scenario')),
    source_resource_id VARCHAR(128) NOT NULL,
    scenario VARCHAR(16) NOT NULL
        CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
    artifact_path TEXT NOT NULL,
    artifact_sha256 VARCHAR(64) NOT NULL,
    artifact_size_bytes BIGINT NOT NULL CHECK (artifact_size_bytes > 0),
    artifact_kind VARCHAR(16) NOT NULL
        CHECK (artifact_kind IN ('text', 'image', 'audio', 'video')),
    decision VARCHAR(16) NOT NULL
        CHECK (decision IN ('accepted', 'rejected')),
    record_status VARCHAR(16) NOT NULL
        CHECK (record_status IN (
            'available', 'rejected', 'consumed', 'expired', 'revoked'
        )),
    reviewer_key_id VARCHAR(128) NOT NULL,
    reviewer_key_type VARCHAR(32) NOT NULL
        CHECK (reviewer_key_type IN ('tenant', 'test_bundle', 'env_fallback')),
    review_notes TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    consumed_by_operation VARCHAR(64),
    consumed_by_resource_id VARCHAR(128),
    revoked_at TIMESTAMPTZ,
    revoked_by_key_id VARCHAR(128),
    revoked_by_record_id VARCHAR(36),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
    CONSTRAINT ck_acceptance_records_expiry CHECK (expires_at > created_at)
);
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

-- job_budget_accounts/provider_cost_attempts: tenant-bound W1-27/W1-30
-- paid-provider budget authority and immutable attempt ledger.
CREATE TABLE IF NOT EXISTS job_budget_accounts (
    account_id UUID PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    job_kind VARCHAR(32) NOT NULL
        CHECK (job_kind IN ('canonical', 'compatibility')),
    job_id VARCHAR(128) NOT NULL,
    scenario_or_resource_type VARCHAR(128) NOT NULL,
    cap_usd_nanos BIGINT NOT NULL CHECK (cap_usd_nanos > 0),
    reserved_usd_nanos BIGINT NOT NULL DEFAULT 0
        CHECK (reserved_usd_nanos >= 0),
    settled_usd_nanos BIGINT NOT NULL DEFAULT 0
        CHECK (settled_usd_nanos >= 0),
    budget_source_kind VARCHAR(32) NOT NULL
        CHECK (budget_source_kind IN (
            'server_config', 'validated_authorization'
        )),
    budget_source_ref VARCHAR(128),
    budget_policy_version VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_job_budget_accounts_tenant_job
        UNIQUE (tenant_id, job_kind, job_id),
    CONSTRAINT ck_job_budget_accounts_source_ref CHECK (
        (budget_source_kind = 'server_config' AND budget_source_ref IS NULL)
        OR (budget_source_kind = 'validated_authorization'
            AND budget_source_ref IS NOT NULL)
    ),
    CONSTRAINT ck_job_budget_accounts_conservation CHECK (
        reserved_usd_nanos + settled_usd_nanos <= cap_usd_nanos
    )
);

CREATE TABLE IF NOT EXISTS provider_cost_attempts (
    attempt_id UUID PRIMARY KEY,
    account_id UUID NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    job_kind VARCHAR(32) NOT NULL
        CHECK (job_kind IN ('canonical', 'compatibility')),
    job_id VARCHAR(128) NOT NULL,
    scenario_or_resource_type VARCHAR(128) NOT NULL,
    logical_operation VARCHAR(160) NOT NULL,
    ordinal BIGINT NOT NULL CHECK (ordinal >= 0),
    attempt_fingerprint VARCHAR(64) NOT NULL,
    regeneration_epoch_ref VARCHAR(128),
    provider VARCHAR(64) NOT NULL,
    canonical_model VARCHAR(128) NOT NULL,
    provider_billing_region VARCHAR(64) NOT NULL
        CHECK (provider_billing_region IN (
            'deepseek_global_usd', 'poyo_global_usd',
            'siliconflow_global_usd'
        )),
    catalog_operation VARCHAR(64) NOT NULL
        CHECK (catalog_operation IN (
            'chat_completion', 'speech_synthesis', 'image_generation',
            'text_to_video', 'image_to_video'
        )),
    media_type VARCHAR(16) NOT NULL
        CHECK (media_type IN ('text', 'audio', 'image', 'video')),
    billing_fact_kind VARCHAR(32) NOT NULL
        CHECK (billing_fact_kind IN (
            'llm_tokens.v1', 'tts_utf8_bytes.v1', 'image_count.v1',
            'video_task.v1', 'video_duration.v1'
        )),
    price_rule_id VARCHAR(160) NOT NULL,
    price_catalog_version VARCHAR(128) NOT NULL,
    price_rule_version VARCHAR(32) NOT NULL,
    reservation_billing_facts JSONB NOT NULL,
    settlement_billing_facts JSONB,
    reserved_usd_nanos BIGINT NOT NULL CHECK (reserved_usd_nanos > 0),
    settled_usd_nanos BIGINT NOT NULL DEFAULT 0 CHECK (
        settled_usd_nanos >= 0
        AND settled_usd_nanos <= reserved_usd_nanos
    ),
    provider_reported_cost_usd_nanos BIGINT CHECK (
        provider_reported_cost_usd_nanos IS NULL
        OR provider_reported_cost_usd_nanos >= 0
    ),
    provider_reported_credit_micro_units BIGINT CHECK (
        provider_reported_credit_micro_units IS NULL
        OR provider_reported_credit_micro_units >= 0
    ),
    provider_reported_currency VARCHAR(16) CHECK (
        provider_reported_currency IS NULL OR provider_reported_currency = 'USD'
    ),
    state VARCHAR(32) NOT NULL CHECK (state IN (
        'reserved', 'submission_started', 'submitted', 'settled',
        'released', 'ambiguous', 'accounting_error'
    )),
    external_task_id VARCHAR(128),
    provider_trace_id VARCHAR(128),
    safe_error_code VARCHAR(64),
    reservation_expires_at TIMESTAMPTZ NOT NULL,
    submission_started_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ,
    terminal_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
CREATE INDEX IF NOT EXISTS idx_provider_cost_attempts_account_state
    ON provider_cost_attempts(account_id, state);
CREATE INDEX IF NOT EXISTS idx_provider_cost_attempts_reservation_expiry
    ON provider_cost_attempts(reservation_expires_at)
    WHERE state = 'reserved';

-- Create indexes
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
CREATE INDEX IF NOT EXISTS idx_vm_video_platform_pulled ON video_metrics(video_id, platform, pulled_at DESC);
CREATE INDEX IF NOT EXISTS idx_vm_pulled_scenario_platform ON video_metrics(pulled_at DESC, scenario, platform);
