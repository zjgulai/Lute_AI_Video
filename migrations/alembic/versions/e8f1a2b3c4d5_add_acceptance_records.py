"""Add durable single-use human acceptance records.

Revision ID: e8f1a2b3c4d5
Revises: d5e6f7a8b9c0
Create Date: 2026-07-12

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f1a2b3c4d5"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the durable acceptance ledger and arbitration indexes."""

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS acceptance_records (
            id VARCHAR(36) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            creation_key_hash VARCHAR(64) NOT NULL,
            fingerprint_version VARCHAR(64) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            source_resource_type VARCHAR(16) NOT NULL
                CHECK (source_resource_type IN ('fast', 'scenario')),
            source_resource_id VARCHAR(128) NOT NULL,
            scenario VARCHAR(16) NOT NULL
                CHECK (scenario IN ('fast', 's1', 's2', 's3', 's4', 's5')),
            artifact_path TEXT NOT NULL,
            artifact_sha256 VARCHAR(64) NOT NULL,
            artifact_size_bytes BIGINT NOT NULL CHECK (artifact_size_bytes > 0),
            artifact_kind VARCHAR(16) NOT NULL
                CHECK (artifact_kind IN ('text', 'image', 'audio', 'video')),
            decision VARCHAR(16) NOT NULL
                CHECK (decision IN ('accepted', 'rejected')),
            record_status VARCHAR(16) NOT NULL
                CHECK (record_status IN (
                    'available', 'rejected', 'consumed', 'expired', 'revoked'
                )),
            reviewer_key_id VARCHAR(128) NOT NULL,
            reviewer_key_type VARCHAR(32) NOT NULL
                CHECK (reviewer_key_type IN ('tenant', 'test_bundle', 'env_fallback')),
            review_notes TEXT NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            consumed_by_operation VARCHAR(64),
            consumed_by_resource_id VARCHAR(128),
            revoked_at TIMESTAMPTZ,
            revoked_by_key_id VARCHAR(128),
            revoked_by_record_id VARCHAR(36),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_acceptance_records_tenant_creation_key
                UNIQUE (tenant_id, creation_key_hash),
            CONSTRAINT ck_acceptance_records_decision_status CHECK (
                (decision = 'accepted' AND record_status IN (
                    'available', 'consumed', 'expired', 'revoked'
                ))
                OR (decision = 'rejected' AND record_status = 'rejected')
            ),
            CONSTRAINT ck_acceptance_records_consumed_fields CHECK (
                (record_status = 'consumed' AND consumed_at IS NOT NULL
                    AND consumed_by_operation IS NOT NULL
                    AND consumed_by_resource_id IS NOT NULL)
                OR (record_status <> 'consumed' AND consumed_at IS NULL
                    AND consumed_by_operation IS NULL
                    AND consumed_by_resource_id IS NULL)
            ),
            CONSTRAINT ck_acceptance_records_revoked_fields CHECK (
                (record_status = 'revoked' AND revoked_at IS NOT NULL
                    AND revoked_by_key_id IS NOT NULL)
                OR (record_status <> 'revoked' AND revoked_at IS NULL
                    AND revoked_by_key_id IS NULL AND revoked_by_record_id IS NULL)
            ),
            CONSTRAINT ck_acceptance_records_expiry CHECK (expires_at > created_at)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_acceptance_records_tenant_available_path
            ON acceptance_records(tenant_id, artifact_path)
            WHERE record_status = 'available'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_acceptance_records_source
            ON acceptance_records(
                tenant_id, source_resource_type, source_resource_id
            )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_acceptance_records_status
            ON acceptance_records(tenant_id, record_status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_acceptance_records_expiry
            ON acceptance_records(expires_at)
            WHERE record_status = 'available'
        """
    )


def downgrade() -> None:
    """Drop only the additive acceptance ledger."""

    op.execute("DROP TABLE IF EXISTS acceptance_records")
