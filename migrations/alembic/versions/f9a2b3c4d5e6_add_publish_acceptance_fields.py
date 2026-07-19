"""Add W1-23 publish acceptance correlation fields.

Revision ID: f9a2b3c4d5e6
Revises: e8f1a2b3c4d5
Create Date: 2026-07-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9a2b3c4d5e6"
down_revision: str | None = "e8f1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "publish_logs",
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "publish_logs",
        sa.Column("acceptance_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "publish_logs",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        CREATE INDEX idx_publish_logs_tenant_created_at
            ON publish_logs(tenant_id, created_at DESC)
        """
    )
    op.create_index(
        "idx_publish_logs_tenant_acceptance",
        "publish_logs",
        ["tenant_id", "acceptance_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_publish_logs_tenant_acceptance",
        table_name="publish_logs",
    )
    op.drop_index(
        "idx_publish_logs_tenant_created_at",
        table_name="publish_logs",
    )
    op.drop_column("publish_logs", "updated_at")
    op.drop_column("publish_logs", "acceptance_id")
    op.drop_column("publish_logs", "tenant_id")
