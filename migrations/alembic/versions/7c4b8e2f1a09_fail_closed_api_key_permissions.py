"""Fail closed for newly created tenant API-key permissions.

Revision ID: 7c4b8e2f1a09
Revises: e4b9c1d2a6f0
Create Date: 2026-07-11

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4b8e2f1a09"
down_revision: str | None = "e4b9c1d2a6f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Default future tenant keys to no permissions; do not rewrite existing rows."""

    op.execute(
        "ALTER TABLE api_keys "
        "ALTER COLUMN permissions SET DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    """Restore the historical permissive default."""

    op.execute(
        "ALTER TABLE api_keys "
        "ALTER COLUMN permissions SET DEFAULT '[\"all\"]'::jsonb"
    )
