-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- gates column (added 2026-05-03 for S1 step-by-step gate persistence)
ALTER TABLE pipeline_states ADD COLUMN IF NOT EXISTS gates JSONB DEFAULT '{}';

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
    post_id VARCHAR(128),
    post_url TEXT,
    metrics JSONB DEFAULT '{}',
    pulled_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

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

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_threads_thread_id ON threads(thread_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_states_label ON pipeline_states(label);
CREATE INDEX IF NOT EXISTS idx_publish_logs_platform ON publish_logs(platform);
CREATE INDEX IF NOT EXISTS idx_vm_video_id ON video_metrics(video_id);
CREATE INDEX IF NOT EXISTS idx_vm_scenario ON video_metrics(scenario);
CREATE INDEX IF NOT EXISTS idx_vm_platform ON video_metrics(platform);
CREATE INDEX IF NOT EXISTS idx_vm_pulled_at ON video_metrics(pulled_at);
