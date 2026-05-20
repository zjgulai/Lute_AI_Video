"""Models for self-audit checkpoint reporting."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import AuditCheckpoint, AuditCriterionStatus


class AuditCriterion(BaseModel):
    """A single scored criterion within an audit report."""

    name: str  # e.g. "Platform Coverage", "Hook Strength"
    status: AuditCriterionStatus
    score: float = Field(ge=0.0, le=1.0, description="0-1 score for this criterion")
    observation: str  # What the auditor observed
    recommendation: str = ""  # How to improve if not PASS


class AuditReport(BaseModel):
    """Self-audit report generated at a checkpoint before human review."""

    audit_id: str  # e.g. "AUDIT-STRATEGY-001"
    checkpoint: AuditCheckpoint
    target_artifact_id: str  # The artifact being audited (brief/script/composition)
    overall_score: float = Field(ge=0.0, le=1.0)
    overall_status: AuditCriterionStatus
    criteria: list[AuditCriterion]
    summary: str  # Human-readable summary of findings
    generated_at: datetime = Field(default_factory=datetime.now)
