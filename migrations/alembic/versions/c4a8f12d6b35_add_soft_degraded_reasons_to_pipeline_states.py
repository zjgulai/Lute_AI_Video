"""add_soft_degraded_reasons_to_pipeline_states

Revision ID: c4a8f12d6b35
Revises: b3d7e1a02f55
Create Date: 2026-05-16

TODO-D10 PR2 (master-plan-2026-05-16; chain-fault-tolerance-design
§三): when a step hits a recoverable failure but produces fallback
output (so pipeline can continue), step_runner now records ONE entry
to pipeline_states.soft_degraded_reasons capturing:
  [
    {
      "ts": "2026-05-16T16:00:00+08:00",
      "step": "video_analysis",
      "reason": "video_analysis_failed_using_fallback",
      "detail": "DeepSeek timeout after 60s",
      "trace_id": "..."
    },
    ...
  ]

Distinct from pipeline_degraded (which halts) — soft_degraded_reasons
is audit-only. partial_artifacts.summarize reads both fields when
deciding artifact availability.

Forward-compatible: existing rows get the column as NULL/'[]' default.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c4a8f12d6b35"
down_revision: str | None = "b3d7e1a02f55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add soft_degraded_reasons JSONB column to pipeline_states."""
    op.execute("""
        ALTER TABLE pipeline_states
            ADD COLUMN IF NOT EXISTS soft_degraded_reasons JSONB DEFAULT '[]';
    """)


def downgrade() -> None:
    """Drop soft_degraded_reasons column. Audit history is lost."""
    op.execute("""
        ALTER TABLE pipeline_states
            DROP COLUMN IF EXISTS soft_degraded_reasons;
    """)
