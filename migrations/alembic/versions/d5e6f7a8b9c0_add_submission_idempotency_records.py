"""Add durable tenant-scoped submission idempotency records.

Revision ID: d5e6f7a8b9c0
Revises: 7c4b8e2f1a09
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "7c4b8e2f1a09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the durable submission ledger and its arbitration constraints."""

    # Fresh Docker databases load src/storage/migrations/001_init.sql before
    # Alembic starts.  IF NOT EXISTS keeps that path and an upgrade from the
    # prior Alembic head equivalent instead of failing on duplicate DDL.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_records (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            key_hash VARCHAR(64) NOT NULL,
            fingerprint_version VARCHAR(64) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            operation VARCHAR(64) NOT NULL,
            scenario VARCHAR(16) NOT NULL
                CONSTRAINT ck_idempotency_records_scenario
                CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
            resource_type VARCHAR(16) NOT NULL
                CONSTRAINT ck_idempotency_records_resource_type
                CHECK (resource_type IN ('fast', 'scenario')),
            resource_id VARCHAR(128) NOT NULL,
            record_status VARCHAR(32) NOT NULL
                CONSTRAINT ck_idempotency_records_status
                CHECK (record_status IN (
                    'reserved', 'initializing', 'queued', 'running',
                    'completed', 'failed', 'recovery_required'
                )),
            stage VARCHAR(64),
            effective_policy_version VARCHAR(64) NOT NULL,
            response_status INTEGER NOT NULL,
            response_body JSONB NOT NULL DEFAULT '{}',
            result_snapshot JSONB,
            safe_error_code VARCHAR(64),
            owner_instance_id VARCHAR(128),
            lease_expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            CONSTRAINT uq_idempotency_records_tenant_key
                UNIQUE (tenant_id, key_hash),
            CONSTRAINT uq_idempotency_records_tenant_resource
                UNIQUE (tenant_id, resource_type, resource_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_idempotency_records_status
            ON idempotency_records(tenant_id, record_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_idempotency_records_lease
            ON idempotency_records(lease_expires_at)
            WHERE lease_expires_at IS NOT NULL
        """
    )


def downgrade() -> None:
    """Drop the additive submission ledger."""

    op.execute("DROP TABLE IF EXISTS idempotency_records")
