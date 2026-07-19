from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class AcceptanceCreateRequest(_StrictModel):
    source_resource_type: Literal["fast", "scenario"]
    source_resource_id: str = Field(min_length=1, max_length=128)
    artifact_path: str = Field(min_length=1, max_length=1024)
    decision: Literal["accepted", "rejected"]
    review_notes: str = Field(min_length=1, max_length=2000)
    expires_in_seconds: int = Field(default=3600, strict=True, ge=300, le=86400)

    @field_validator("source_resource_id")
    @classmethod
    def validate_resource_id(cls, value: str) -> str:
        if _RESOURCE_ID_RE.fullmatch(value) is None:
            raise ValueError("source_resource_id is invalid")
        return value


class AcceptanceArtifactProjection(_StrictModel):
    path: str
    sha256: str
    size_bytes: int
    kind: Literal["text", "image", "audio", "video"]


class AcceptanceReviewerProjection(_StrictModel):
    key_id: str
    key_type: Literal["tenant", "test_bundle", "env_fallback"]


class AcceptanceRecordResponse(_StrictModel):
    acceptance_id: str
    tenant_id: str
    source_resource_type: Literal["fast", "scenario"]
    source_resource_id: str
    scenario: Literal["fast", "s1", "s2", "s3", "s4", "s5"]
    artifact: AcceptanceArtifactProjection
    decision: Literal["accepted", "rejected"]
    status: Literal["available", "rejected", "consumed", "expired", "revoked"]
    reviewer: AcceptanceReviewerProjection
    review_notes: str
    expires_at: str
    consumed_at: str | None
    revoked_at: str | None
    idempotent_replay: bool
    created_at: str
    updated_at: str
