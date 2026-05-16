"""add_audit_logs_table

Revision ID: 9f1e2c8a4b67
Revises: 7a2f4b8c9d12
Create Date: 2026-05-16

Adds audit_logs table for business-event auditing per task_plan 3.15 +
MASTER-PLAN-2026-05-16 TODO-C10. Captures admin lifecycle events
(login / logout / tenant CRUD / api_key revoke) and pipeline lifecycle
events for compliance and incident forensics.

Forward-compatible: existing rows unaffected; queries against the table
default to empty result if app code isn't yet writing to it.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "9f1e2c8a4b67"
down_revision: Union[str, None] = "7a2f4b8c9d12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create audit_logs table."""
    op.execute("""
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
    """)


def downgrade() -> None:
    """Drop audit_logs table. Audit history is lost."""
    op.execute("DROP TABLE IF EXISTS audit_logs;")
