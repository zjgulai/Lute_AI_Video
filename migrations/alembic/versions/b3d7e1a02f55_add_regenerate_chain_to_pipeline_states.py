"""add_regenerate_chain_to_pipeline_states

Revision ID: b3d7e1a02f55
Revises: 9f1e2c8a4b67
Create Date: 2026-05-16

TODO-D11 (master-plan-2026-05-16): wire up the quality_score feedback gate.

When a downstream consumer (keyframe_images, seedance_video_generate,
remotion_assemble) reads upstream quality_score below the per-consumer
regenerate threshold, step_runner now writes one entry to
pipeline_states.regenerate_chain capturing:
  [
    {
      "ts": "2026-05-16T15:42:11+08:00",
      "consumer": "keyframe_images",
      "upstream_skill": "storyboard",
      "score": 0.42,
      "reason": "keyframe_images: score=0.42 < 0.50, regenerate upstream",
      "attempt": 1
    },
    ...
  ]

This is an audit trail — read-only for the user, append-only for the
runner. It is bounded by feedback_gate.max_regenerate_attempts (1-2 per
consumer), so the array stays small.

Forward-compatible: existing rows get the column as NULL/'[]' default.
state_manager and repository tolerate missing/empty regenerate_chain.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "b3d7e1a02f55"
down_revision: str | None = "9f1e2c8a4b67"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add regenerate_chain JSONB column to pipeline_states."""
    op.execute("""
        ALTER TABLE pipeline_states
            ADD COLUMN IF NOT EXISTS regenerate_chain JSONB DEFAULT '[]';
    """)


def downgrade() -> None:
    """Drop regenerate_chain column. Audit history is lost."""
    op.execute("""
        ALTER TABLE pipeline_states
            DROP COLUMN IF EXISTS regenerate_chain;
    """)
