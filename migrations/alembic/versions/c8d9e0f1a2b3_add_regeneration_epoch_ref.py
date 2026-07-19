"""Persist trusted regeneration epoch consumption on provider attempts.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "provider_cost_attempts",
        sa.Column("regeneration_epoch_ref", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_cost_attempts", "regeneration_epoch_ref")
