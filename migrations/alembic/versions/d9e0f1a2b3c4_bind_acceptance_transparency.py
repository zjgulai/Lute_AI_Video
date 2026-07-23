"""Bind acceptance authority to transparency and final C2PA truth.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pipeline_states",
        sa.Column("transparency", JSONB(), nullable=True),
    )
    op.add_column(
        "acceptance_records",
        sa.Column("transparency_sidecar_path", sa.Text(), nullable=True),
    )
    op.add_column(
        "acceptance_records",
        sa.Column(
            "transparency_sidecar_sha256",
            sa.String(length=64),
            nullable=True,
        ),
    )
    op.add_column(
        "acceptance_records",
        sa.Column(
            "final_artifact_c2pa_status",
            sa.String(length=32),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_acceptance_records_transparency_v2",
        "acceptance_records",
        "fingerprint_version <> 'acceptance-create.v2' OR ("
        "transparency_sidecar_path IS NOT NULL AND "
        "transparency_sidecar_sha256 IS NOT NULL AND "
        "final_artifact_c2pa_status IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_acceptance_records_c2pa_status",
        "acceptance_records",
        "final_artifact_c2pa_status IS NULL OR "
        "final_artifact_c2pa_status IN ("
        "'unsigned_pending_review', 'signed_local_readback')",
    )
    op.create_check_constraint(
        "ck_acceptance_records_accepted_c2pa",
        "acceptance_records",
        "decision <> 'accepted' OR final_artifact_c2pa_status IS NULL OR "
        "final_artifact_c2pa_status = 'signed_local_readback'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_acceptance_records_accepted_c2pa",
        "acceptance_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_acceptance_records_c2pa_status",
        "acceptance_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_acceptance_records_transparency_v2",
        "acceptance_records",
        type_="check",
    )
    op.drop_column("acceptance_records", "final_artifact_c2pa_status")
    op.drop_column("acceptance_records", "transparency_sidecar_sha256")
    op.drop_column("acceptance_records", "transparency_sidecar_path")
    op.drop_column("pipeline_states", "transparency")
