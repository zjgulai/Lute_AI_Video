"""Models for human review checkpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.enums import ApprovalStatus


class HumanReview(BaseModel):
    node: str  # strategy_review, script_review, edit_review, thumbnail_review
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewer_notes: str = ""
    content_snapshot: dict[str, Any] = Field(default_factory=dict)
    reviewed_at: datetime | None = None
