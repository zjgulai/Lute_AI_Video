"""add_video_metrics_table

Revision ID: 1efc41794d64
Revises: 42eb2682e54b
Create Date: 2026-05-01 03:53:50.787006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1efc41794d64'
down_revision: Union[str, None] = '42eb2682e54b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add video_metrics table to PostgreSQL.

    This table was previously SQLite-only. Moving it to PG enables
    cross-worker metrics persistence and dashboard aggregation.
    """
    op.execute("""
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
        CREATE INDEX IF NOT EXISTS idx_vm_video_id ON video_metrics(video_id);
        CREATE INDEX IF NOT EXISTS idx_vm_scenario ON video_metrics(scenario);
        CREATE INDEX IF NOT EXISTS idx_vm_platform ON video_metrics(platform);
        CREATE INDEX IF NOT EXISTS idx_vm_pulled_at ON video_metrics(pulled_at);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vm_pulled_at;")
    op.execute("DROP INDEX IF EXISTS idx_vm_platform;")
    op.execute("DROP INDEX IF EXISTS idx_vm_scenario;")
    op.execute("DROP INDEX IF EXISTS idx_vm_video_id;")
    op.execute("DROP TABLE IF EXISTS video_metrics;")
