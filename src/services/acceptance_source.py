"""Durable Fast and Scenario source projections for human acceptance."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from src.pipeline.artifact_paths import extract_assemble_paths
from src.pipeline.step_utils import get_step_output_from_state
from src.services.artifact_identity import (
    ArtifactIdentityError,
    canonicalize_output_artifact_path,
    validate_output_reference,
)

ResourceType = Literal["fast", "scenario"]
Scenario = Literal["fast", "s1", "s2", "s3", "s4", "s5"]

_NONTERMINAL_STATUSES = frozenset({"reserved", "initializing", "queued", "running"})
_SOURCE_TERMINAL_STATUSES = frozenset({"completed", "failed"})
_SCENARIOS = frozenset({"s1", "s2", "s3", "s4", "s5"})
_VIDEO_SUFFIXES = {".mp4", ".webm"}


class AcceptanceSourceError(ValueError):
    """The durable submission cannot be projected into an acceptance source."""


class AcceptanceSourceMismatchError(AcceptanceSourceError):
    """Authenticated/requested identity does not match the durable record."""


class AcceptanceSourceNotTerminalError(AcceptanceSourceError):
    """The durable source is still executing."""


class AcceptanceSourceNotEligibleError(AcceptanceSourceError):
    """The durable source lacks a structurally valid final-video projection."""


@dataclass(frozen=True, slots=True)
class AcceptanceSource:
    tenant_id: str
    resource_type: ResourceType
    resource_id: str
    scenario: Scenario
    record_status: str
    artifact_path: str
    artifact_disposition: str
    artifact_kind: Literal["video"]
    full_media_success: bool
    is_stub: bool
    pipeline_degraded: bool


def project_scenario_acceptance_source(
    final_state: Mapping[str, Any],
    *,
    tenant_id: str,
    label: str,
    artifact_disposition: str,
    output_dir: Path,
) -> dict[str, object]:
    """Project a trusted terminal Scenario video into the durable safe snapshot."""

    if artifact_disposition != "pending_review":
        return {}
    steps = final_state.get("steps")
    if not isinstance(steps, Mapping):
        return {}
    assemble_step = steps.get("assemble_final")
    if not isinstance(assemble_step, Mapping) or assemble_step.get("status") != "done":
        return {}

    try:
        output = get_step_output_from_state(dict(final_state), "assemble_final")
        video_path, _ = extract_assemble_paths(output)
        if not video_path:
            return {}
        canonical = canonicalize_output_artifact_path(
            video_path,
            output_dir=output_dir,
            tenant_id=tenant_id,
            required_prefix=(
                f"tenants/{tenant_id}/pending_review/{label}"
            ),
            allowed_suffixes=_VIDEO_SUFFIXES,
            allow_absolute_under_root=True,
        )
    except (ArtifactIdentityError, OSError, TypeError, ValueError):
        return {}

    return {
        "final_artifact_path": canonical.canonical_path,
        "artifact_disposition": "pending_review",
        "artifact_kind": "video",
    }


def resolve_acceptance_source(
    record: Mapping[str, Any],
    *,
    tenant_id: str,
    requested_resource_type: str,
    requested_resource_id: str,
) -> AcceptanceSource:
    """Resolve server-owned source identity without applying decision eligibility."""

    record_tenant = record.get("tenant_id")
    resource_type = record.get("resource_type")
    resource_id = record.get("resource_id")
    scenario = record.get("scenario")
    if (
        not isinstance(record_tenant, str)
        or not isinstance(resource_type, str)
        or not isinstance(resource_id, str)
        or not isinstance(scenario, str)
    ):
        raise AcceptanceSourceMismatchError("acceptance source identity mismatch")
    if (
        record_tenant != tenant_id
        or resource_type != requested_resource_type
        or resource_id != requested_resource_id
    ):
        raise AcceptanceSourceMismatchError("acceptance source identity mismatch")
    if resource_type not in {"fast", "scenario"}:
        raise AcceptanceSourceMismatchError("acceptance source identity mismatch")
    if (resource_type == "fast" and scenario != "fast") or (
        resource_type == "scenario" and scenario not in _SCENARIOS
    ):
        raise AcceptanceSourceMismatchError("acceptance source identity mismatch")

    record_status = record.get("record_status")
    if not isinstance(record_status, str):
        raise AcceptanceSourceNotEligibleError("acceptance source is not eligible")
    if record_status in _NONTERMINAL_STATUSES:
        raise AcceptanceSourceNotTerminalError("acceptance source is not terminal")
    if record_status not in _SOURCE_TERMINAL_STATUSES:
        raise AcceptanceSourceNotEligibleError("acceptance source is not eligible")

    snapshot = record.get("result_snapshot")
    if not isinstance(snapshot, Mapping):
        raise AcceptanceSourceNotEligibleError("acceptance source projection is missing")

    if resource_type == "fast":
        artifact_path = snapshot.get("video_path")
        expected_prefix = (
            f"tenants/{tenant_id}/pending_review/fast_mode/{resource_id}"
        )
        artifact_kind = snapshot.get("artifact_kind", "video")
        full_media_success = _require_flag(snapshot, "full_media_success")
        is_stub = _require_flag(snapshot, "is_stub")
        pipeline_degraded = _require_flag(
            snapshot,
            "pipeline_degraded",
            default=False,
        )
    else:
        artifact_path = snapshot.get("final_artifact_path")
        expected_prefix = f"tenants/{tenant_id}/pending_review/{resource_id}"
        artifact_kind = snapshot.get("artifact_kind")
        full_media_success = _require_flag(snapshot, "full_media_success")
        is_stub = _require_flag(snapshot, "is_stub", default=False)
        pipeline_degraded = _require_flag(snapshot, "pipeline_degraded")

    if snapshot.get("artifact_disposition") != "pending_review" or artifact_kind != "video":
        raise AcceptanceSourceNotEligibleError("acceptance source projection is invalid")
    canonical_path = _validate_projected_path(artifact_path, expected_prefix=expected_prefix)

    return AcceptanceSource(
        tenant_id=cast(str, record_tenant),
        resource_type=cast(ResourceType, resource_type),
        resource_id=resource_id,
        scenario=cast(Scenario, scenario),
        record_status=cast(str, record_status),
        artifact_path=canonical_path,
        artifact_disposition="pending_review",
        artifact_kind="video",
        full_media_success=full_media_success,
        is_stub=is_stub,
        pipeline_degraded=pipeline_degraded,
    )


def _require_flag(
    snapshot: Mapping[str, Any],
    key: str,
    *,
    default: bool | None = None,
) -> bool:
    value = snapshot.get(key, default)
    if type(value) is not bool:
        raise AcceptanceSourceNotEligibleError("acceptance source projection is invalid")
    return value


def _validate_projected_path(value: Any, *, expected_prefix: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcceptanceSourceNotEligibleError("acceptance source projection is missing")
    try:
        canonical = validate_output_reference(value)
    except ArtifactIdentityError as exc:
        raise AcceptanceSourceNotEligibleError(
            "acceptance source projection is invalid"
        ) from exc
    if canonical != value or (
        canonical != expected_prefix and not canonical.startswith(expected_prefix + "/")
    ):
        raise AcceptanceSourceNotEligibleError("acceptance source projection is invalid")
    if PurePosixPath(canonical).suffix.lower() not in _VIDEO_SUFFIXES:
        raise AcceptanceSourceNotEligibleError("acceptance source projection is invalid")
    return canonical


__all__ = [
    "AcceptanceSource",
    "AcceptanceSourceError",
    "AcceptanceSourceMismatchError",
    "AcceptanceSourceNotEligibleError",
    "AcceptanceSourceNotTerminalError",
    "project_scenario_acceptance_source",
    "resolve_acceptance_source",
]
