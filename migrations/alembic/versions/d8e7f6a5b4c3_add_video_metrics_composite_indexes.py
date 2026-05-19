"""add_video_metrics_composite_indexes

Revision ID: d8e7f6a5b4c3
Revises: c4a8f12d6b35
Create Date: 2026-05-18

Add composite indexes for dashboard latest-snapshot queries.
"""

from alembic import op

revision: str = "d8e7f6a5b4c3"
down_revision: str | None = "c4a8f12d6b35"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_vm_video_platform_pulled
            ON video_metrics(video_id, platform, pulled_at DESC);
        CREATE INDEX IF NOT EXISTS idx_vm_pulled_scenario_platform
            ON video_metrics(pulled_at DESC, scenario, platform);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vm_pulled_scenario_platform;")
    op.execute("DROP INDEX IF EXISTS idx_vm_video_platform_pulled;")
