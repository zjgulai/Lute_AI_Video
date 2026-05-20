"""Models for compliance checking stage."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from src.models.enums import ComplianceStatus, Severity


class ComplianceFlag(BaseModel):
    severity: Severity
    line_index: int
    text: str
    issue: str
    suggestion: str


class ComplianceReport(BaseModel):
    script_id: str
    status: ComplianceStatus
    flags: list[ComplianceFlag] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=datetime.now)
