"""add_api_keys_table

Revision ID: 1ffe98505ace
Revises: a3c8f2d1b450
Create Date: 2026-05-06

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "1ffe98505ace"
down_revision: Union[str, None] = "a3c8f2d1b450"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add api_keys table for per-tenant API key management (P2-8)."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id VARCHAR(64) NOT NULL,
            key_hash VARCHAR(64) UNIQUE NOT NULL,
            permissions JSONB DEFAULT '"["all"]"',
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP,
            revoked_at TIMESTAMP,
            last_used_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
        CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_keys_tenant;")
    op.execute("DROP INDEX IF EXISTS idx_api_keys_hash;")
    op.execute("DROP TABLE IF EXISTS api_keys;")
