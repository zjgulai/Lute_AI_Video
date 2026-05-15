"""add_runtime_state_columns_to_pipeline_states

Revision ID: 7a2f4b8c9d12
Revises: 2d6b8e9c0f1a
Create Date: 2026-05-15

Phase 0 #1 fix (closes Oracle-identified PG round-trip regression):
adds 5 runtime-state columns to pipeline_states that were tracked
in-memory + on FS but dropped on PG-primary load. Before this migration,
PG load returned states without:
  - schema_version (Sprint 3 P3-5 versioning)
  - pipeline_degraded (Sprint 0 degraded-guard flag)
  - degraded_reason (which step triggered degradation)
  - trace_id (cross-step debugging chain)
  - structured_errors (GAP-20 structured error classification)

Result: degraded states became invisible across loads, schema_version
mismatch warning always fired, structured error chain broke.

After this migration, PG persists these fields and they survive
round-trip. Migration is forward-compatible: all 5 columns are nullable
so existing rows continue to load (missing → NULL → defaults applied
by state_manager).
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '7a2f4b8c9d12'
down_revision: Union[str, None] = '2d6b8e9c0f1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add 5 runtime-state columns to pipeline_states (all nullable)."""
    op.execute("""
        ALTER TABLE pipeline_states
            ADD COLUMN IF NOT EXISTS schema_version INT,
            ADD COLUMN IF NOT EXISTS pipeline_degraded BOOLEAN,
            ADD COLUMN IF NOT EXISTS degraded_reason TEXT,
            ADD COLUMN IF NOT EXISTS trace_id TEXT,
            ADD COLUMN IF NOT EXISTS structured_errors JSONB DEFAULT '[]';
    """)


def downgrade() -> None:
    """Drop the 5 runtime-state columns. Existing rows lose this data."""
    op.execute("""
        ALTER TABLE pipeline_states
            DROP COLUMN IF EXISTS structured_errors,
            DROP COLUMN IF EXISTS trace_id,
            DROP COLUMN IF EXISTS degraded_reason,
            DROP COLUMN IF EXISTS pipeline_degraded,
            DROP COLUMN IF EXISTS schema_version;
    """)
