"""Canonical lifecycle truth for S1-S5 scenario completion."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from src.models.runtime_contracts import ScenarioLifecycleResult
from src.pipeline.completion_truth import CompletionKind
from src.pipeline.scenario_config import SCENARIO_STEP_ORDERS


def _done(output: Any) -> dict[str, Any]:
    return {
        "status": "done",
        "output": output,
        "edited": False,
        "edited_output": None,
    }


def _full_state(scenario: str) -> dict[str, Any]:
    steps = {
        step: _done({"value": f"{scenario}-{step}"})
        for step in SCENARIO_STEP_ORDERS[scenario]
    }
    for step in ("strategy", "scripts", "storyboards", "video_analysis"):
        if step in steps:
            steps[step] = _done([{"id": f"{scenario}-{step}"}])
    if "keyframe_images" in steps:
        steps["keyframe_images"] = _done(
            [{"image_path": f"/tmp/{scenario}-keyframe.png", "is_stub": False, "simulated": False}]
        )
    steps["seedance_clips"] = _done(
        {
            "clip_paths": [f"/tmp/{scenario}-clip.mp4"],
            "clip_details": [{"is_stub": False, "simulated": False}],
            "simulated": False,
        }
    )
    steps["tts_audio"] = _done(
        {"audio_paths": [f"/tmp/{scenario}-audio.mp3"], "simulated": False}
    )
    if "thumbnail_images" in steps:
        steps["thumbnail_images"] = _done(
            [{"image_path": f"/tmp/{scenario}-thumbnail.png", "simulated": False}]
        )
    if "thumbnails" in steps:
        steps["thumbnails"] = _done(
            [{"image_path": f"/tmp/{scenario}-thumbnail.png", "simulated": False}]
        )
    steps["assemble_final"] = _done(
        {
            "video_path": f"/tmp/{scenario}-final.mp4",
            "render_json_path": f"/tmp/{scenario}-render.json",
            "is_stub": False,
            "simulated": False,
        }
    )
    steps["audit"] = _done(
        {
            "overall_status": "PASS",
            "asset_ready_audit": {"status": "PASS"},
        }
    )
    config: dict[str, Any] = {}
    if scenario == "s4":
        config["tenant_id"] = "tenant-a"
        config["footage_assets"] = [
            {
                "asset_id": "footage-1",
                "path": "/tmp/tenant-a/uploaded-footage.mp4",
                "source": "upload",
                "tenant_id": "tenant-a",
                "ownership_verified": True,
                "rights_evidence_refs": ["rights-review-1"],
            }
        ]
    if scenario == "s5":
        config["product_sku"] = {
            "views": [f"/tmp/tenant-a/product-view-{index}.png" for index in range(6)]
        }
    return {
        "scenario": scenario,
        "config": config,
        "steps": steps,
        "current_step": None,
        "errors": [],
        "media_synthesis_errors": [],
        "pipeline_degraded": False,
        "soft_degraded_reasons": [],
    }


def _assert_failed_truth(result: ScenarioLifecycleResult) -> None:
    assert result == {
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


@pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
def test_full_completion_requires_all_scenario_evidence(scenario: str) -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    result = derive_scenario_completion(
        _full_state(scenario),
        expected_completion_kind="full_media",
    )

    assert result == {
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


@pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
def test_full_completion_rejects_missing_final_video(scenario: str) -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    state = _full_state(scenario)
    state["steps"]["assemble_final"]["output"]["video_path"] = ""

    _assert_failed_truth(
        derive_scenario_completion(state, expected_completion_kind="full_media")
    )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda state: state["steps"]["audit"].__setitem__("status", "pending"),
            id="required-step-incomplete",
        ),
        pytest.param(
            lambda state: state.__setitem__("pipeline_degraded", True),
            id="hard-degraded",
        ),
        pytest.param(
            lambda state: state.__setitem__(
                "soft_degraded_reasons", [{"reason": "fallback"}]
            ),
            id="soft-degraded",
        ),
        pytest.param(
            lambda state: state.__setitem__("errors", ["provider failure"]),
            id="errors",
        ),
        pytest.param(
            lambda state: state["steps"]["seedance_clips"]["output"].__setitem__(
                "simulated", True
            ),
            id="simulated",
        ),
        pytest.param(
            lambda state: state["steps"]["seedance_clips"]["output"].pop(
                "simulated"
            ),
            id="simulation-truth-missing",
        ),
        pytest.param(
            lambda state: state["steps"]["tts_audio"]["output"].__setitem__(
                "simulated", "false"
            ),
            id="audio-simulation-truth-non-boolean",
        ),
        pytest.param(
            lambda state: state["steps"]["keyframe_images"]["output"][0].pop(
                "simulated"
            ),
            id="keyframe-simulation-truth-missing",
        ),
        pytest.param(
            lambda state: state["steps"]["thumbnail_images"]["output"][0].pop(
                "simulated"
            ),
            id="thumbnail-simulation-truth-missing",
        ),
        pytest.param(
            lambda state: state["steps"]["seedance_clips"]["output"][
                "clip_details"
            ][0].__setitem__("is_stub", True),
            id="stub",
        ),
        pytest.param(
            lambda state: state["steps"]["assemble_final"]["output"].__setitem__(
                "simulated", True
            ),
            id="final-video-simulated",
        ),
        pytest.param(
            lambda state: state["steps"]["assemble_final"]["output"].pop(
                "simulated"
            ),
            id="final-video-simulation-truth-missing",
        ),
        pytest.param(
            lambda state: state["steps"]["audit"].__setitem__(
                "output", {"overall_status": "FAIL"}
            ),
            id="audit-failed",
        ),
    ],
)
def test_full_completion_fails_closed_on_invalid_runtime_truth(mutation: Any) -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    state = _full_state("s1")
    mutation(state)

    _assert_failed_truth(
        derive_scenario_completion(state, expected_completion_kind="full_media")
    )


def test_s4_full_completion_requires_uploaded_footage_basis() -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    state = _full_state("s4")
    state["config"]["footage_assets"] = []

    _assert_failed_truth(
        derive_scenario_completion(state, expected_completion_kind="full_media")
    )


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param(
            lambda asset: asset.__setitem__("source", "stock"),
            id="stock-fallback",
        ),
        pytest.param(
            lambda asset: asset.__setitem__("tenant_id", "other-tenant"),
            id="cross-tenant",
        ),
        pytest.param(
            lambda asset: asset.pop("asset_id"),
            id="missing-upload-reference",
        ),
        pytest.param(
            lambda asset: asset.__setitem__("ownership_verified", False),
            id="ownership-unverified",
        ),
        pytest.param(
            lambda asset: asset.__setitem__("rights_evidence_refs", []),
            id="rights-evidence-missing",
        ),
    ],
)
def test_s4_full_completion_requires_tenant_owned_rights_evidence(
    mutation: Any,
) -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    state = _full_state("s4")
    mutation(state["config"]["footage_assets"][0])

    _assert_failed_truth(
        derive_scenario_completion(state, expected_completion_kind="full_media")
    )


@pytest.mark.parametrize("view_count", [0, 5, 7])
def test_s5_full_completion_requires_exactly_six_product_views(view_count: int) -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    state = _full_state("s5")
    state["config"]["product_sku"]["views"] = [
        f"/tmp/view-{index}.png" for index in range(view_count)
    ]

    _assert_failed_truth(
        derive_scenario_completion(state, expected_completion_kind="full_media")
    )


@pytest.mark.parametrize("kind", ["no_media", "bounded_media"])
def test_bounded_completion_never_sets_full_or_delivery_authority(
    kind: CompletionKind,
) -> None:
    from src.pipeline.completion_truth import derive_scenario_completion

    state = deepcopy(_full_state("s1"))
    result = derive_scenario_completion(state, expected_completion_kind=kind)

    assert result == {
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


@pytest.mark.parametrize(
    ("state", "expected_status", "expected_success"),
    [
        (
            {
                "status": "completed_bounded",
                "lifecycle_status": "completed_bounded",
                "completion_kind": "bounded_media",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
                "pipeline_degraded": False,
            },
            "completed_bounded",
            False,
        ),
        (
            {
                "status": "completed_full",
                "lifecycle_status": "completed_full",
                "completion_kind": "full_media",
                "request_succeeded": True,
                "success": True,
                "full_media_success": True,
                "pipeline_complete": True,
                "publish_allowed": False,
                "delivery_accepted": False,
                "pipeline_degraded": False,
            },
            "completed_full",
            True,
        ),
    ],
)
def test_wrapper_projection_uses_coherent_state_truth(
    state: dict[str, Any],
    expected_status: str,
    expected_success: bool,
) -> None:
    from src.pipeline.completion_truth import project_scenario_wrapper_result

    result = project_scenario_wrapper_result(
        {"success": not expected_success, "artifact": "preserved"},
        state,
    )

    assert result["status"] == expected_status
    assert result["success"] is expected_success
    assert result["_execution_completed"] is True
    assert result["artifact"] == "preserved"


def test_wrapper_projection_marks_partial_lifecycle_noncanonical() -> None:
    from src.pipeline.completion_truth import project_scenario_wrapper_result

    result = project_scenario_wrapper_result(
        {"success": True},
        {"lifecycle_status": "completed_bounded", "pipeline_degraded": False},
    )

    assert result["success"] is True
    assert result["_execution_completed"] is False
