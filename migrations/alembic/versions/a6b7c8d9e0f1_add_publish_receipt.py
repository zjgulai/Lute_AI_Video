"""Add W1-25 durable publish receipt.

Revision ID: a6b7c8d9e0f1
Revises: f9a2b3c4d5e6
Create Date: 2026-07-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f9a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publish_logs",
        sa.Column("receipt", JSONB(), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX idx_publish_logs_tenant_platform_post_receipt
            ON publish_logs(tenant_id, platform, post_id)
            WHERE status = 'published'
              AND receipt IS NOT NULL
              AND post_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "idx_publish_logs_tenant_platform_post_receipt",
        table_name="publish_logs",
    )
    op.drop_column("publish_logs", "receipt")
