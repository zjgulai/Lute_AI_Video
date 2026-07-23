"""Fail-closed lifecycle derivation for scenario generation results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

from src.models.runtime_contracts import ScenarioLifecycleResult
from src.pipeline.artifact_paths import extract_assemble_paths
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS
from src.pipeline.step_utils import get_step_output

CompletionKind = Literal["no_media", "bounded_media", "full_media"]

_PATH_KEYS = (
    "path",
    "local_path",
    "image_path",
    "video_path",
    "audio_path",
    "url",
)


def _failed() -> ScenarioLifecycleResult:
    return {
        "status": "error",
        "lifecycle_status": "error",
        "completion_kind": "execution_failed",
        "request_succeeded": False,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
    }


def _bounded(kind: Literal["no_media", "bounded_media"]) -> ScenarioLifecycleResult:
    return {
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": kind,
        "request_succeeded": True,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
    }


def _full() -> ScenarioLifecycleResult:
    return {
        "status": "completed_full",
        "lifecycle_status": "completed_full",
        "completion_kind": "full_media",
        "request_succeeded": True,
        "success": True,
        "full_media_success": True,
        "pipeline_complete": True,
        "publish_allowed": False,
        "delivery_accepted": False,
    }


def _contains_simulated_or_stub(value: Any) -> bool:
    if isinstance(value, Mapping):
        if value.get("simulated") is True or value.get("is_stub") is True:
            return True
        stub_mode = value.get("_stub_mode")
        if stub_mode not in (None, False, ""):
            return True
        return any(_contains_simulated_or_stub(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_simulated_or_stub(item) for item in value)
    return False


def _has_path(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_path(value.get(key)) for key in _PATH_KEYS if key in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_has_path(item) for item in value)
    return False


def _has_named_paths(value: Any, *keys: str) -> bool:
    if not isinstance(value, Mapping):
        return _has_path(value)
    return any(key in value and _has_path(value[key]) for key in keys)


def _has_exact_real_truth(value: Any) -> bool:
    if isinstance(value, Mapping):
        return value.get("simulated") is False
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return bool(value) and all(
            isinstance(item, Mapping) and item.get("simulated") is False
            for item in value
        )
    return False


def _is_exact_real_final_artifact(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("simulated") is False
        and value.get("is_stub") is False
    )


def _audit_passed(value: Any) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    overall = str(value.get("overall_status") or "").upper()
    asset_ready = value.get("asset_ready_audit")
    asset_status = (
        str(asset_ready.get("status") or "").upper()
        if isinstance(asset_ready, Mapping)
        else ""
    )
    if "FAIL" in {overall, asset_status} or "ERROR" in {overall, asset_status}:
        return False
    return overall == "PASS" or asset_status == "PASS"


def _all_required_steps_done(state: Mapping[str, Any], scenario: str) -> bool:
    steps = state.get("steps")
    if not isinstance(steps, Mapping):
        return False
    return all(
        isinstance(steps.get(step), Mapping)
        and steps[step].get("status") == "done"
        for step in SCENARIO_STEP_ORDERS[scenario]
    )


def _views_are_complete(config: Mapping[str, Any]) -> bool:
    product_sku = config.get("product_sku")
    views = product_sku.get("views") if isinstance(product_sku, Mapping) else None
    return (
        isinstance(views, Sequence)
        and not isinstance(views, (str, bytes, bytearray))
        and len(views) == 6
        and all(_has_path(view) for view in views)
    )


def _footage_is_complete(
    state: Mapping[str, Any],
    config: Mapping[str, Any],
) -> bool:
    footage = config.get("footage_assets")
    tenant_id = state.get("tenant_id") or config.get("tenant_id")
    return (
        isinstance(tenant_id, str)
        and bool(tenant_id.strip())
        and isinstance(footage, Sequence)
        and not isinstance(footage, (str, bytes, bytearray))
        and bool(footage)
        and all(
            isinstance(item, Mapping)
            and item.get("source") == "upload"
            and item.get("tenant_id") == tenant_id
            and isinstance(item.get("asset_id"), str)
            and bool(item["asset_id"].strip())
            and item.get("ownership_verified") is True
            and isinstance(item.get("rights_evidence_refs"), Sequence)
            and not isinstance(
                item.get("rights_evidence_refs"),
                (str, bytes, bytearray),
            )
            and bool(item["rights_evidence_refs"])
            and all(
                isinstance(ref, str) and bool(ref.strip())
                for ref in item["rights_evidence_refs"]
            )
            and item.get("is_stock") is not True
            and _has_path(item)
            for item in footage
        )
    )


def _required_artifacts_present(state: Mapping[str, Any], scenario: str) -> bool:
    steps = state["steps"]
    assert isinstance(steps, dict)

    clips = get_step_output(steps, "seedance_clips")
    audio = get_step_output(steps, "tts_audio")
    assemble = get_step_output(steps, "assemble_final")
    audit = get_step_output(steps, "audit")
    final_video, _ = extract_assemble_paths(assemble)
    common = (
        _has_named_paths(clips, "clip_paths", "video_paths")
        and _has_exact_real_truth(clips)
        and _has_named_paths(audio, "audio_paths")
        and _has_exact_real_truth(audio)
        and bool(final_video.strip())
        and _is_exact_real_final_artifact(assemble)
        and _audit_passed(audit)
    )
    if not common:
        return False

    if scenario in {"s1", "s2"}:
        keyframes = get_step_output(steps, "keyframe_images")
        thumbnails = get_step_output(steps, "thumbnail_images")
        return (
            _has_path(keyframes)
            and _has_exact_real_truth(keyframes)
            and _has_named_paths(thumbnails, "image_paths")
            and _has_exact_real_truth(thumbnails)
        )
    if scenario == "s3":
        return bool(get_step_output(steps, "video_analysis")) and bool(
            get_step_output(steps, "storyboards")
        )
    config = state.get("config")
    if not isinstance(config, Mapping):
        return False
    if scenario == "s4":
        thumbnails = get_step_output(steps, "thumbnails")
        return (
            _footage_is_complete(state, config)
            and _has_path(thumbnails)
            and _has_exact_real_truth(thumbnails)
        )
    return _views_are_complete(config)


def derive_scenario_completion(
    state: Mapping[str, Any],
    *,
    expected_completion_kind: CompletionKind,
) -> ScenarioLifecycleResult:
    """Derive one exact terminal envelope from persisted scenario truth."""

    if expected_completion_kind not in {"no_media", "bounded_media", "full_media"}:
        raise ValueError("unsupported expected completion kind")
    scenario = state.get("scenario")
    if not isinstance(scenario, str) or scenario not in SCENARIO_STEP_ORDERS:
        return _failed()
    if (
        state.get("current_step") is not None
        or state.get("pipeline_degraded") is True
    ):
        return _failed()

    if expected_completion_kind != "full_media":
        return _bounded(
            cast(Literal["no_media", "bounded_media"], expected_completion_kind)
        )

    if (
        bool(state.get("errors"))
        or bool(state.get("media_synthesis_errors"))
        or bool(state.get("soft_degraded_reasons"))
    ):
        return _failed()

    steps = state.get("steps")
    if (
        not _all_required_steps_done(state, scenario)
        or not isinstance(steps, Mapping)
        or _contains_simulated_or_stub(steps)
        or not _required_artifacts_present(state, scenario)
    ):
        return _failed()
    return _full()


def read_coherent_scenario_lifecycle(
    value: Mapping[str, Any],
) -> ScenarioLifecycleResult | None:
    """Return an exact lifecycle projection, or ``None`` for any contradiction."""

    status = value.get("status")
    lifecycle_status = value.get("lifecycle_status")
    completion_kind = value.get("completion_kind")
    request_succeeded = value.get("request_succeeded")
    success = value.get("success")
    full_media_success = value.get("full_media_success")
    pipeline_complete = value.get("pipeline_complete")
    publish_allowed = value.get("publish_allowed")
    delivery_accepted = value.get("delivery_accepted")

    if (
        status == "completed_full"
        and lifecycle_status == "completed_full"
        and completion_kind == "full_media"
        and request_succeeded is True
        and success is True
        and full_media_success is True
        and pipeline_complete is True
        and publish_allowed is False
        and delivery_accepted is False
    ):
        return _full()
    if (
        status == "completed_bounded"
        and lifecycle_status == "completed_bounded"
        and completion_kind in {"no_media", "bounded_media"}
        and request_succeeded is True
        and success is False
        and full_media_success is False
        and pipeline_complete is False
        and publish_allowed is False
        and delivery_accepted is False
    ):
        return _bounded(cast(Literal["no_media", "bounded_media"], completion_kind))
    if (
        status == "error"
        and lifecycle_status == "error"
        and completion_kind == "execution_failed"
        and request_succeeded is False
        and success is False
        and full_media_success is False
        and pipeline_complete is False
        and publish_allowed is False
        and delivery_accepted is False
    ):
        return _failed()
    return None


def project_scenario_wrapper_result(
    result: Mapping[str, Any],
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Align a wrapper result with coherent persisted lifecycle truth."""

    projected = dict(result)
    lifecycle = read_coherent_scenario_lifecycle(state)
    if lifecycle is None:
        projected["_execution_completed"] = False
        return projected
    projected.update(lifecycle)
    projected["_execution_completed"] = lifecycle["request_succeeded"]
    projected["pipeline_degraded"] = state.get("pipeline_degraded") is True
    return projected
