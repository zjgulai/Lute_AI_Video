"""admin_panel_phase1

Revision ID: 2d6b8e9c0f1a
Revises: 1ffe98505ace
Create Date: 2026-05-06

Add admin panel tables:
- admin_accounts: admin operator credentials
- admin_sessions: admin session tokens
- tenants: tenant metadata registry
- error_logs: persistent error log storage
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2d6b8e9c0f1a"
down_revision: Union[str, None] = "1ffe98505ace"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create admin panel tables for Phase 1."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_accounts (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMPTZ
        );
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)

    op.execute("""
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
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_error_logs_tenant_created;")
    op.execute("DROP INDEX IF EXISTS idx_error_logs_created_at;")
    op.execute("DROP TABLE IF EXISTS error_logs;")
    op.execute("DROP TABLE IF EXISTS tenants;")
    op.execute("DROP INDEX IF EXISTS idx_admin_sessions_expires;")
    op.execute("DROP INDEX IF EXISTS idx_admin_sessions_token_hash;")
    op.execute("DROP TABLE IF EXISTS admin_sessions;")
    op.execute("DROP TABLE IF EXISTS admin_accounts;")
