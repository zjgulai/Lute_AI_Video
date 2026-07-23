"""Bind one W5 activation to one durable submission claim.

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e0f1a2b3c4d5"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column(
            "trusted_authorization_ref",
            sa.String(length=128),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_idempotency_records_tenant_authorization",
        "idempotency_records",
        ["tenant_id", "trusted_authorization_ref"],
        unique=True,
        postgresql_where=sa.text("trusted_authorization_ref IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_idempotency_records_tenant_authorization",
        table_name="idempotency_records",
    )
    op.drop_column("idempotency_records", "trusted_authorization_ref")
