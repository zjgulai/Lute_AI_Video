"""add_tenant_id_to_pipeline_states_and_video_metrics

Revision ID: e4b9c1d2a6f0
Revises: d8e7f6a5b4c3
Create Date: 2026-05-18

Persist tenant ownership on pipeline state and metrics rows so API keys can
only access their own scenario runs and performance data.
"""

from alembic import op


revision: str = "e4b9c1d2a6f0"
down_revision: str | None = "d8e7f6a5b4c3"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE pipeline_states
        ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

        CREATE INDEX IF NOT EXISTS idx_pipeline_states_tenant
            ON pipeline_states(tenant_id);

        ALTER TABLE video_metrics
        ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

        CREATE INDEX IF NOT EXISTS idx_vm_tenant
            ON video_metrics(tenant_id);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vm_tenant;")
    op.execute("ALTER TABLE video_metrics DROP COLUMN IF EXISTS tenant_id;")
    op.execute("DROP INDEX IF EXISTS idx_pipeline_states_tenant;")
    op.execute("ALTER TABLE pipeline_states DROP COLUMN IF EXISTS tenant_id;")
