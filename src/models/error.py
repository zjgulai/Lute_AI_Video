"""Structured error models for pipeline error classification."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.models.enums import ErrorCode


class PipelineError(BaseModel):
    """Structured error with classification, context, and recoverability hint."""

    code: ErrorCode
    message: str
    node: str | None = None
    recoverable: bool = True
    detail: dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_legacy(self) -> str:
        """Return backward-compatible string format for the errors list."""
        node_prefix = f"[{self.node}] " if self.node else ""
        return f"{node_prefix}{self.code.value}: {self.message}"
