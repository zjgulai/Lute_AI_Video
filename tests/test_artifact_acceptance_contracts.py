from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

_RESOURCE_ID = "s2_1783830000_abcdef12"
_RESOURCE_PREFIX = (
    "tenants/tenant-alpha/pending_review/" f"{_RESOURCE_ID}"
)
_FINAL_VIDEO_PATH = f"{_RESOURCE_PREFIX}/assemble/final.mp4"
_FINAL_VIDEO_BYTES = b"final-video-fixture"
_VIDEO_SUFFIXES = {".mp4", ".webm"}


def _valid_request() -> dict[str, object]:
    return {
        "source_resource_type": "scenario",
        "source_resource_id": _RESOURCE_ID,
        "artifact_path": _FINAL_VIDEO_PATH,
        "decision": "accepted",
        "review_notes": "Reviewed exact final render.",
        "expires_in_seconds": 3600,
    }


def _write_artifact(
    output_dir: Path,
    relative_path: str = _FINAL_VIDEO_PATH,
    content: bytes = _FINAL_VIDEO_BYTES,
) -> Path:
    target = output_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return target


def test_acceptance_request_is_strict_and_forbids_server_authority_fields() -> None:
    from src.models.acceptance import AcceptanceCreateRequest

    parsed = AcceptanceCreateRequest.model_validate(_valid_request())
    assert parsed.expires_in_seconds == 3600

    for field, value in {
        "tenant_id": "attacker-tenant",
        "scenario": "s5",
        "reviewer_id": "self-asserted",
        "artifact_sha256": "a" * 64,
        "publish_allowed": True,
    }.items():
        with pytest.raises(ValidationError):
            AcceptanceCreateRequest.model_validate({**_valid_request(), field: value})


@pytest.mark.parametrize("value", [True, 299, 86401, 3600.0, "3600"])
def test_acceptance_expiry_is_a_bounded_strict_integer(value: object) -> None:
    from src.models.acceptance import AcceptanceCreateRequest

    with pytest.raises(ValidationError):
        AcceptanceCreateRequest.model_validate(
            {**_valid_request(), "expires_in_seconds": value}
        )


@pytest.mark.parametrize(
    "source_resource_id",
    ["contains/slash", "contains space", "", "x" * 129],
)
def test_acceptance_source_resource_id_uses_safe_bounded_grammar(
    source_resource_id: str,
) -> None:
    from src.models.acceptance import AcceptanceCreateRequest

    with pytest.raises(ValidationError):
        AcceptanceCreateRequest.model_validate(
            {**_valid_request(), "source_resource_id": source_resource_id}
        )


def test_resolver_returns_canonical_tenant_file_and_digest(tmp_path: Path) -> None:
    from src.services.artifact_identity import resolve_output_artifact

    _write_artifact(tmp_path)

    resolved = resolve_output_artifact(
        _FINAL_VIDEO_PATH,
        output_dir=tmp_path,
        tenant_id="tenant-alpha",
        required_prefix=_RESOURCE_PREFIX,
        allowed_suffixes=_VIDEO_SUFFIXES,
    )

    assert resolved.canonical_path == _FINAL_VIDEO_PATH
    assert resolved.size_bytes == len(_FINAL_VIDEO_BYTES)
    assert resolved.sha256 == hashlib.sha256(_FINAL_VIDEO_BYTES).hexdigest()


@pytest.mark.parametrize(
    "invalid_path",
    [
        f"{_RESOURCE_PREFIX}/assemble/../final.mp4",
        f"{_RESOURCE_PREFIX}/assemble/%2e%2e/final.mp4",
        f"{_RESOURCE_PREFIX}/assemble/%252e%252e/final.mp4",
        "https://evil.example/final.mp4",
        "javascript:alert(1)",
        f"{_FINAL_VIDEO_PATH}?download=1",
        f"{_FINAL_VIDEO_PATH}#reviewed",
    ],
)
def test_resolver_rejects_untrusted_reference_syntax_without_host_path(
    tmp_path: Path,
    invalid_path: str,
) -> None:
    from src.services.artifact_identity import (
        ArtifactIdentityError,
        resolve_output_artifact,
    )

    _write_artifact(tmp_path)

    with pytest.raises(ArtifactIdentityError) as exc:
        resolve_output_artifact(
            invalid_path,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(tmp_path) not in str(exc.value)


def test_resolver_hides_cross_tenant_artifact_as_not_found(tmp_path: Path) -> None:
    from src.services.artifact_identity import (
        ArtifactNotFoundError,
        resolve_output_artifact,
    )

    cross_tenant = _FINAL_VIDEO_PATH.replace("tenant-alpha", "tenant-beta")
    _write_artifact(tmp_path, cross_tenant)

    with pytest.raises(ArtifactNotFoundError) as exc:
        resolve_output_artifact(
            cross_tenant,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(exc.value) == "artifact not found"
    assert str(tmp_path) not in str(exc.value)


@pytest.mark.parametrize("disposition", ["quarantine", "intermediate"])
def test_resolver_rejects_non_pending_review_prefixes(
    tmp_path: Path,
    disposition: str,
) -> None:
    from src.services.artifact_identity import (
        ArtifactIdentityError,
        resolve_output_artifact,
    )

    invalid_path = (
        f"tenants/tenant-alpha/{disposition}/{_RESOURCE_ID}/assemble/final.mp4"
    )
    _write_artifact(tmp_path, invalid_path)

    with pytest.raises(ArtifactIdentityError) as exc:
        resolve_output_artifact(
            invalid_path,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(tmp_path) not in str(exc.value)


def test_resolver_rejects_unsupported_suffix_as_not_found(tmp_path: Path) -> None:
    from src.services.artifact_identity import (
        ArtifactNotFoundError,
        resolve_output_artifact,
    )

    unsupported_path = f"{_RESOURCE_PREFIX}/assemble/final.mov"
    _write_artifact(tmp_path, unsupported_path)

    with pytest.raises(ArtifactNotFoundError) as exc:
        resolve_output_artifact(
            unsupported_path,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(exc.value) == "artifact not found"


def test_resolver_rejects_empty_artifact(tmp_path: Path) -> None:
    from src.services.artifact_identity import (
        ArtifactIdentityError,
        resolve_output_artifact,
    )

    _write_artifact(tmp_path, content=b"")

    with pytest.raises(ArtifactIdentityError) as exc:
        resolve_output_artifact(
            _FINAL_VIDEO_PATH,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(exc.value) == "artifact is empty"
    assert str(tmp_path) not in str(exc.value)


def test_resolver_rejects_symlink_escape_without_host_path(tmp_path: Path) -> None:
    from src.services.artifact_identity import (
        ArtifactIdentityError,
        resolve_output_artifact,
    )

    outside = tmp_path.parent / f"{tmp_path.name}-outside.mp4"
    outside.write_bytes(_FINAL_VIDEO_BYTES)
    target = tmp_path / _FINAL_VIDEO_PATH
    target.parent.mkdir(parents=True)
    target.symlink_to(outside)

    with pytest.raises(ArtifactIdentityError) as exc:
        resolve_output_artifact(
            _FINAL_VIDEO_PATH,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(tmp_path) not in str(exc.value)


def test_canonicalizer_wraps_symlink_loop_without_host_path(tmp_path: Path) -> None:
    from src.services.artifact_identity import (
        ArtifactIdentityError,
        canonicalize_output_artifact_path,
    )

    loop_path = tmp_path / _FINAL_VIDEO_PATH
    loop_path.parent.mkdir(parents=True)
    loop_path.symlink_to(loop_path.name)

    with pytest.raises(ArtifactIdentityError) as exc:
        canonicalize_output_artifact_path(
            _FINAL_VIDEO_PATH,
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(exc.value) == "invalid artifact path"
    assert str(tmp_path) not in str(exc.value)


def test_client_absolute_path_is_rejected_even_below_output_root(tmp_path: Path) -> None:
    from src.services.artifact_identity import (
        ArtifactIdentityError,
        resolve_output_artifact,
    )

    target = _write_artifact(tmp_path)

    with pytest.raises(ArtifactIdentityError) as exc:
        resolve_output_artifact(
            str(target),
            output_dir=tmp_path,
            tenant_id="tenant-alpha",
            required_prefix=_RESOURCE_PREFIX,
            allowed_suffixes=_VIDEO_SUFFIXES,
        )

    assert str(tmp_path) not in str(exc.value)


def test_server_owned_absolute_path_requires_opt_in_and_returns_relative_path(
    tmp_path: Path,
) -> None:
    from src.services.artifact_identity import resolve_output_artifact

    target = _write_artifact(tmp_path)

    resolved = resolve_output_artifact(
        str(target),
        output_dir=tmp_path,
        tenant_id="tenant-alpha",
        required_prefix=_RESOURCE_PREFIX,
        allowed_suffixes=_VIDEO_SUFFIXES,
        allow_absolute_under_root=True,
    )

    assert resolved.canonical_path == _FINAL_VIDEO_PATH
    assert resolved.absolute_path == target.resolve()


def test_media_resolver_preserves_root_level_file_compatibility(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.routers import media

    target = tmp_path / "legacy-root.mp4"
    target.write_bytes(_FINAL_VIDEO_BYTES)
    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)

    canonical_path, absolute_path = media._resolve_media_path(target.name)

    assert canonical_path == target.name
    assert absolute_path == target.resolve()


def test_media_resolver_decodes_untrusted_reference_only_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from src.routers import media

    monkeypatch.setattr(media, "OUTPUT_DIR", tmp_path)
    four_layer_encoded = "renders/%2525252e%2525252e/missing.mp4"

    with pytest.raises(HTTPException) as exc:
        media._resolve_media_path(four_layer_encoded)

    assert exc.value.status_code == 404
    assert exc.value.detail == "File not found"


def _durable_submission_record(
    *,
    scenario: str,
    resource_type: str,
    resource_id: str,
    record_status: str = "completed",
    result_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    """Mirror the complete durable idempotency row consumed by source resolution."""

    terminal = record_status in {"completed", "failed", "recovery_required"}
    response_body: dict[str, object]
    if resource_type == "fast":
        response_body = {
            "task_id": resource_id,
            "status": record_status,
            "started_at_unix": 1,
            "idempotent_replay": False,
        }
    else:
        response_body = {
            "label": resource_id,
            "status": record_status,
            "trace_id": "trace-fixture",
            "idempotent_replay": False,
        }
    return {
        "id": "00000000-0000-4000-8000-000000000001",
        "tenant_id": "tenant-alpha",
        "key_hash": "a" * 64,
        "fingerprint_version": "submit-fingerprint.v1",
        "request_hash": "b" * 64,
        "operation": f"{resource_type}.submit",
        "scenario": scenario,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "record_status": record_status,
        "stage": record_status,
        "effective_policy_version": "generation-safety.v1",
        "response_status": 200,
        "response_body": response_body,
        "result_snapshot": result_snapshot,
        "safe_error_code": None,
        "owner_instance_id": "fixture-owner",
        "lease_expires_at": None if terminal else "2026-07-12T12:00:00Z",
        "created_at": "2026-07-12T11:00:00Z",
        "updated_at": "2026-07-12T11:01:00Z",
        "completed_at": "2026-07-12T11:01:00Z" if terminal else None,
    }


def _fast_source_snapshot(
    resource_id: str,
    *,
    full_media_success: bool = True,
    is_stub: bool = False,
) -> dict[str, object]:
    path = (
        "tenants/tenant-alpha/pending_review/fast_mode/"
        f"{resource_id}/final.mp4"
    )
    return {
        "status": "completed_full" if full_media_success else "completed_bounded",
        "lifecycle_status": (
            "completed_full" if full_media_success else "completed_bounded"
        ),
        "completion_kind": "full_media" if full_media_success else "bounded_media",
        "request_succeeded": True,
        "success": full_media_success,
        "full_media_success": full_media_success,
        "pipeline_complete": full_media_success,
        "publish_allowed": False,
        "delivery_accepted": False,
        "video_path": path,
        "video_url": path,
        "poster_path": None,
        "poster_url": None,
        "thumbnail_path": None,
        "thumbnail_url": None,
        "filename": "final.mp4",
        "duration_seconds": 10,
        "file_size_bytes": len(_FINAL_VIDEO_BYTES),
        "generation_time_ms": 1,
        "timing": {"llm_ms": 0, "video_ms": 1, "tts_ms": 0},
        "model_info": {"llm": "fixture", "video": "fixture", "tts": None},
        "is_stub": is_stub,
        "tts_path": None,
        "tts_is_fallback": False,
        "artifact_disposition": "pending_review",
        "artifact_review_status": "pending_review",
        "artifact_storage_scope": "tenant_pending_review",
    }


def _scenario_source_snapshot(
    scenario: str,
    resource_id: str,
    *,
    record_status: str = "completed",
    full_media_success: bool = True,
    pipeline_degraded: bool = False,
) -> dict[str, object]:
    lifecycle = "error" if record_status == "failed" else "completed_full"
    return {
        "status": lifecycle,
        "lifecycle_status": lifecycle,
        "completion_kind": "execution_failed" if pipeline_degraded else "full_media",
        "request_succeeded": not pipeline_degraded,
        "success": full_media_success,
        "full_media_success": full_media_success,
        "pipeline_complete": full_media_success,
        "publish_allowed": False,
        "delivery_accepted": False,
        "current_step": None,
        "pipeline_degraded": pipeline_degraded,
        "trace_id": f"trace-{scenario}",
        "final_artifact_path": (
            "tenants/tenant-alpha/pending_review/"
            f"{resource_id}/assemble/final.mp4"
        ),
        "artifact_disposition": "pending_review",
        "artifact_kind": "video",
    }


@pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
def test_scenario_projection_is_canonical_and_tenant_bound(
    scenario: str,
    tmp_path: Path,
) -> None:
    from src.services.acceptance_source import project_scenario_acceptance_source

    label = f"{scenario}_source_fixture"
    relative = f"tenants/tenant-alpha/pending_review/{label}/assemble/final.mp4"
    final_path = _write_artifact(tmp_path, relative, b"video")
    output: object = (
        {"video_path": str(final_path), "render_json_path": "render.json"}
        if scenario in {"s2", "s4"}
        else [str(final_path), "render.json"]
    )
    state = {
        "pipeline_degraded": False,
        "steps": {"assemble_final": {"status": "done", "output": output}},
    }

    projection = project_scenario_acceptance_source(
        state,
        tenant_id="tenant-alpha",
        label=label,
        artifact_disposition="pending_review",
        output_dir=tmp_path,
    )

    assert projection == {
        "final_artifact_path": relative,
        "artifact_disposition": "pending_review",
        "artifact_kind": "video",
    }
    assert str(tmp_path) not in str(projection)


@pytest.mark.parametrize(
    "case",
    [
        "assemble_not_done",
        "intermediate_step_only",
        "missing_file",
        "outside_output_root",
        "cross_tenant",
        "quarantine",
        "wrong_resource",
        "unsupported_suffix",
    ],
)
def test_scenario_projection_omits_invalid_terminal_artifacts(
    case: str,
    tmp_path: Path,
) -> None:
    from src.services.acceptance_source import project_scenario_acceptance_source

    label = "s2_source_fixture"
    disposition = "pending_review"
    relative = f"tenants/tenant-alpha/pending_review/{label}/assemble/final.mp4"
    candidate = tmp_path / relative
    state: dict[str, object] = {
        "steps": {
            "assemble_final": {
                "status": "done",
                "output": [str(candidate), "render.json"],
            }
        }
    }

    if case == "assemble_not_done":
        _write_artifact(tmp_path, relative)
        state["steps"] = {
            "assemble_final": {
                "status": "running",
                "output": [str(candidate), "render.json"],
            }
        }
    elif case == "intermediate_step_only":
        intermediate = _write_artifact(
            tmp_path,
            f"tenants/tenant-alpha/pending_review/{label}/clips/clip-01.mp4",
        )
        state["steps"] = {
            "seedance_clips": {"status": "done", "output": [str(intermediate)]}
        }
    elif case == "outside_output_root":
        candidate = tmp_path.parent / f"{tmp_path.name}-outside.mp4"
        candidate.write_bytes(_FINAL_VIDEO_BYTES)
        state["steps"] = {
            "assemble_final": {
                "status": "done",
                "output": [str(candidate), "render.json"],
            }
        }
    elif case == "cross_tenant":
        candidate = _write_artifact(
            tmp_path,
            relative.replace("tenant-alpha", "tenant-beta"),
        )
        state["steps"] = {
            "assemble_final": {
                "status": "done",
                "output": [str(candidate), "render.json"],
            }
        }
    elif case == "quarantine":
        disposition = "quarantine"
        candidate = _write_artifact(
            tmp_path,
            relative.replace("pending_review", "quarantine"),
        )
        state["steps"] = {
            "assemble_final": {
                "status": "done",
                "output": [str(candidate), "render.json"],
            }
        }
    elif case == "wrong_resource":
        candidate = _write_artifact(
            tmp_path,
            relative.replace(label, "s2_other_fixture"),
        )
        state["steps"] = {
            "assemble_final": {
                "status": "done",
                "output": [str(candidate), "render.json"],
            }
        }
    elif case == "unsupported_suffix":
        candidate = _write_artifact(tmp_path, relative.replace(".mp4", ".json"))
        state["steps"] = {
            "assemble_final": {
                "status": "done",
                "output": [str(candidate), "render.json"],
            }
        }

    assert project_scenario_acceptance_source(
        state,
        tenant_id="tenant-alpha",
        label=label,
        artifact_disposition=disposition,
        output_dir=tmp_path,
    ) == {}


def test_scenario_projection_omits_symlink_loop(tmp_path: Path) -> None:
    from src.services.acceptance_source import project_scenario_acceptance_source

    label = "s2_symlink_loop"
    relative = f"tenants/tenant-alpha/pending_review/{label}/assemble/final.mp4"
    loop_path = tmp_path / relative
    loop_path.parent.mkdir(parents=True)
    loop_path.symlink_to(loop_path.name)
    state = {
        "steps": {
            "assemble_final": {
                "status": "done",
                "output": [str(loop_path), "render.json"],
            }
        }
    }

    assert project_scenario_acceptance_source(
        state,
        tenant_id="tenant-alpha",
        label=label,
        artifact_disposition="pending_review",
        output_dir=tmp_path,
    ) == {}


def test_scenario_submission_snapshot_allowlists_source_projection() -> None:
    from src.routers.scenario import (
        _SCENARIO_RESULT_SNAPSHOT_KEYS,
        _safe_result_snapshot,
    )

    projection = {
        "final_artifact_path": _FINAL_VIDEO_PATH,
        "artifact_disposition": "pending_review",
        "artifact_kind": "video",
    }

    assert _safe_result_snapshot(
        projection,
        allowed_keys=_SCENARIO_RESULT_SNAPSHOT_KEYS,
    ) == projection


@pytest.mark.parametrize("scenario", ["fast", "s1", "s2", "s3", "s4", "s5"])
def test_resolver_derives_fast_and_scenario_identity_from_durable_record(
    scenario: str,
) -> None:
    from src.services.acceptance_source import resolve_acceptance_source

    resource_type = "fast" if scenario == "fast" else "scenario"
    resource_id = f"{scenario}_source_fixture"
    snapshot = (
        _fast_source_snapshot(resource_id)
        if scenario == "fast"
        else _scenario_source_snapshot(scenario, resource_id)
    )
    record = _durable_submission_record(
        scenario=scenario,
        resource_type=resource_type,
        resource_id=resource_id,
        result_snapshot=snapshot,
    )

    source = resolve_acceptance_source(
        record,
        tenant_id="tenant-alpha",
        requested_resource_type=resource_type,
        requested_resource_id=resource_id,
    )

    assert source.tenant_id == record["tenant_id"]
    assert source.resource_type == record["resource_type"]
    assert source.resource_id == record["resource_id"]
    assert source.scenario == record["scenario"]
    assert source.record_status == record["record_status"]
    assert source.artifact_path == snapshot[
        "video_path" if scenario == "fast" else "final_artifact_path"
    ]


@pytest.mark.parametrize(
    ("tenant_id", "resource_type", "resource_id"),
    [
        ("tenant-beta", "scenario", "s2_source_fixture"),
        ("tenant-alpha", "fast", "s2_source_fixture"),
        ("tenant-alpha", "scenario", "s2_other_fixture"),
    ],
)
def test_resolver_rejects_requested_authority_mismatch(
    tenant_id: str,
    resource_type: str,
    resource_id: str,
) -> None:
    from src.services.acceptance_source import (
        AcceptanceSourceMismatchError,
        resolve_acceptance_source,
    )

    durable_id = "s2_source_fixture"
    record = _durable_submission_record(
        scenario="s2",
        resource_type="scenario",
        resource_id=durable_id,
        result_snapshot=_scenario_source_snapshot("s2", durable_id),
    )

    with pytest.raises(AcceptanceSourceMismatchError):
        resolve_acceptance_source(
            record,
            tenant_id=tenant_id,
            requested_resource_type=resource_type,
            requested_resource_id=resource_id,
        )


@pytest.mark.parametrize("field", ["scenario", "record_status"])
def test_resolver_rejects_malformed_durable_scalar_with_typed_error(
    field: str,
) -> None:
    from src.services.acceptance_source import (
        AcceptanceSourceMismatchError,
        AcceptanceSourceNotEligibleError,
        resolve_acceptance_source,
    )

    resource_id = "s2_source_fixture"
    record = _durable_submission_record(
        scenario="s2",
        resource_type="scenario",
        resource_id=resource_id,
        result_snapshot=_scenario_source_snapshot("s2", resource_id),
    )
    record[field] = []
    expected_error = (
        AcceptanceSourceMismatchError
        if field == "scenario"
        else AcceptanceSourceNotEligibleError
    )

    with pytest.raises(expected_error):
        resolve_acceptance_source(
            record,
            tenant_id="tenant-alpha",
            requested_resource_type="scenario",
            requested_resource_id=resource_id,
        )


@pytest.mark.parametrize("record_status", ["reserved", "initializing", "queued", "running"])
def test_resolver_rejects_truly_nonterminal_source(record_status: str) -> None:
    from src.services.acceptance_source import (
        AcceptanceSourceNotTerminalError,
        resolve_acceptance_source,
    )

    resource_id = "s3_source_fixture"
    record = _durable_submission_record(
        scenario="s3",
        resource_type="scenario",
        resource_id=resource_id,
        record_status=record_status,
        result_snapshot=None,
    )

    with pytest.raises(AcceptanceSourceNotTerminalError):
        resolve_acceptance_source(
            record,
            tenant_id="tenant-alpha",
            requested_resource_type="scenario",
            requested_resource_id=resource_id,
        )


def test_resolver_rejects_recovery_required_source() -> None:
    from src.services.acceptance_source import (
        AcceptanceSourceNotEligibleError,
        resolve_acceptance_source,
    )

    resource_id = "s4_source_fixture"
    record = _durable_submission_record(
        scenario="s4",
        resource_type="scenario",
        resource_id=resource_id,
        record_status="recovery_required",
        result_snapshot=None,
    )

    with pytest.raises(AcceptanceSourceNotEligibleError):
        resolve_acceptance_source(
            record,
            tenant_id="tenant-alpha",
            requested_resource_type="scenario",
            requested_resource_id=resource_id,
        )


def test_resolver_preserves_terminal_failed_degraded_source_for_rejected_decision() -> None:
    from src.services.acceptance_source import resolve_acceptance_source

    resource_id = "s5_source_fixture"
    record = _durable_submission_record(
        scenario="s5",
        resource_type="scenario",
        resource_id=resource_id,
        record_status="failed",
        result_snapshot=_scenario_source_snapshot(
            "s5",
            resource_id,
            record_status="failed",
            full_media_success=False,
            pipeline_degraded=True,
        ),
    )

    source = resolve_acceptance_source(
        record,
        tenant_id="tenant-alpha",
        requested_resource_type="scenario",
        requested_resource_id=resource_id,
    )

    assert source.record_status == "failed"
    assert source.full_media_success is False
    assert source.pipeline_degraded is True
    assert source.is_stub is False


def test_resolver_preserves_bounded_stub_flags_for_decision_specific_check() -> None:
    from src.services.acceptance_source import resolve_acceptance_source

    resource_id = "fast_source_fixture"
    record = _durable_submission_record(
        scenario="fast",
        resource_type="fast",
        resource_id=resource_id,
        result_snapshot=_fast_source_snapshot(
            resource_id,
            full_media_success=False,
            is_stub=True,
        ),
    )

    source = resolve_acceptance_source(
        record,
        tenant_id="tenant-alpha",
        requested_resource_type="fast",
        requested_resource_id=resource_id,
    )

    assert source.record_status == "completed"
    assert source.full_media_success is False
    assert source.is_stub is True
    assert source.pipeline_degraded is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("result_snapshot", None),
        ("final_artifact_path", ""),
        ("artifact_disposition", "quarantine"),
        ("artifact_kind", "image"),
        (
            "final_artifact_path",
            "tenants/tenant-alpha/pending_review/s2_other_fixture/assemble/final.mp4",
        ),
    ],
)
def test_resolver_rejects_missing_or_invalid_scenario_projection(
    field: str,
    value: object,
) -> None:
    from src.services.acceptance_source import (
        AcceptanceSourceNotEligibleError,
        resolve_acceptance_source,
    )

    resource_id = "s2_source_fixture"
    snapshot = _scenario_source_snapshot("s2", resource_id)
    record = _durable_submission_record(
        scenario="s2",
        resource_type="scenario",
        resource_id=resource_id,
        result_snapshot=snapshot,
    )
    if field == "result_snapshot":
        record[field] = value
    else:
        snapshot[field] = value

    with pytest.raises(AcceptanceSourceNotEligibleError):
        resolve_acceptance_source(
            record,
            tenant_id="tenant-alpha",
            requested_resource_type="scenario",
            requested_resource_id=resource_id,
        )
