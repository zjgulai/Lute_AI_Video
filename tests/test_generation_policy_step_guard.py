from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from fastapi import HTTPException

from src.pipeline.generation_policy import EffectiveGenerationPolicy
from src.pipeline.scenario_config import get_scenario_step_order
from src.pipeline.step_runner import _SCENARIO_CONFIGS, StepRunner
from tests.generation_policy_test_utils import (
    attach_test_provider_execution_authority,
)

NO_MEDIA_ALLOWED: dict[str, tuple[str, ...]] = {
    "s1": (
        "strategy",
        "scripts",
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
    ),
    "s2": (
        "strategy",
        "scripts",
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
    ),
    "s3": (
        "video_analysis",
        "character_identity",
        "remix_script",
        "storyboards",
        "continuity_storyboard_grid",
    ),
    "s4": ("scripts", "continuity_storyboard_grid"),
    "s5": ("vlog_strategy", "continuity_storyboard_grid"),
}

BOUNDED_ALLOWED: dict[str, tuple[str, ...]] = {
    "s1": (
        "strategy",
        "scripts",
        "storyboards",
        "continuity_storyboard_grid",
        "keyframe_images",
        "video_prompts",
        "seedance_clips",
    ),
    "s3": (
        "video_analysis",
        "character_identity",
        "remix_script",
        "storyboards",
        "continuity_storyboard_grid",
        "keyframe_images",
        "video_prompts",
        "seedance_clips",
    ),
    "s4": (
        "scripts",
        "continuity_storyboard_grid",
        "video_prompts",
        "seedance_clips",
    ),
    "s5": (
        "vlog_strategy",
        "continuity_storyboard_grid",
        "video_prompts",
        "seedance_clips",
    ),
}

S2_SEGMENTED_ALLOWED: dict[str, tuple[str, ...]] = {
    "seedance_clips": (
        "strategy",
        "scripts",
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
        "keyframe_images",
        "video_prompts",
        "seedance_clips",
    ),
    "tts_audio": ("strategy", "scripts", "tts_audio"),
    "thumbnail_prompts": ("strategy", "scripts", "thumbnail_prompts"),
    "thumbnail_images": (
        "strategy",
        "scripts",
        "thumbnail_prompts",
        "thumbnail_images",
    ),
    "assemble_final": ("assemble_final",),
    "audit": ("audit",),
}

S2_PROVIDER_CAPS = {
    "seedance_clips": {"image": 1, "video": 1},
    "tts_audio": {"tts": 1},
    "thumbnail_prompts": {},
    "thumbnail_images": {"thumbnail": 1},
    "assemble_final": {},
    "audit": {},
}


def test_provider_step_classification_distinguishes_local_prompt_builders() -> None:
    from src.pipeline.generation_policy import PROVIDER_BACKED_STEPS

    assert {
        "strategy",
        "scripts",
        "video_analysis",
        "remix_script",
        "vlog_strategy",
        "keyframe_images",
        "seedance_clips",
        "tts_audio",
        "thumbnail_images",
    }.issubset(PROVIDER_BACKED_STEPS)
    assert {
        "compliance",
        "storyboards",
        "continuity_storyboard_grid",
        "video_prompts",
        "thumbnail_prompts",
        "thumbnails",
        "assemble_final",
        "audit",
    }.isdisjoint(PROVIDER_BACKED_STEPS)


class MemoryStateManager:
    def __init__(self, state: dict[str, Any]) -> None:
        self.states = {state["label"]: deepcopy(state)}
        self.saves: list[dict[str, Any]] = []

    async def load(self, label: str) -> dict[str, Any] | None:
        state = self.states.get(label)
        return deepcopy(state) if state is not None else None

    async def save(self, label: str, state: dict[str, Any]) -> None:
        snapshot = deepcopy(state)
        self.states[label] = snapshot
        self.saves.append(snapshot)


def _effective_policy(scenario: str, *, media: bool) -> dict[str, Any]:
    return EffectiveGenerationPolicy(
        tenant_id="tenant-a",
        scenario=scenario,  # type: ignore[arg-type]
        enable_media_synthesis=media,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    ).model_dump(mode="json")


def _state(
    scenario: str,
    *,
    media: bool,
    current_step: str | None = None,
    media_stop_step: str | None = None,
) -> dict[str, Any]:
    order = get_scenario_step_order(scenario)
    config: dict[str, Any] = {
        "enable_media_synthesis": media,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
        "effective_generation_policy": _effective_policy(scenario, media=media),
    }
    if media_stop_step is not None:
        config["media_stop_step"] = media_stop_step
    if scenario == "s2" and media_stop_step in {"assemble_final", "audit"}:
        media_refs: dict[str, Any] = {
            "clip_paths": ["/tmp/tenants/tenant-a/pending_review/ref/clip.mp4"],
            "audio_paths": ["/tmp/tenants/tenant-a/pending_review/ref/audio.mp3"],
            "thumbnail_image_paths": ["/tmp/tenants/tenant-a/pending_review/ref/thumb.png"],
        }
        if media_stop_step == "audit":
            media_refs["video_path"] = "/tmp/tenants/tenant-a/pending_review/ref/final.mp4"
        config["media_refs"] = media_refs
    state = {
        "label": f"{scenario}-guard",
        "tenant_id": "tenant-a",
        "scenario": scenario,
        "mode": "auto",
        "config": config,
        "steps": {
            step: {
                "status": "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
            }
            for step in order
        },
        "current_step": current_step if current_step is not None else order[0],
        "errors": [],
        "media_synthesis_errors": [],
        "gates": {},
        "pipeline_degraded": False,
    }
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    config["effective_generation_execution_profile"] = profile.model_dump()
    config["provider_job_caps"] = dict(profile.provider_job_caps)
    return state


@pytest.mark.parametrize(
    ("scenario", "forbidden_step"),
    [
        ("s1", "keyframe_images"),
        ("s2", "keyframe_images"),
        ("s3", "keyframe_images"),
        ("s4", "video_prompts"),
        ("s5", "video_prompts"),
    ],
)
@pytest.mark.asyncio
async def test_no_media_resume_stops_before_pipeline_import_and_persists_bounded(
    scenario: str,
    forbidden_step: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(scenario, media=False, current_step=forbidden_step)
    for step_name in NO_MEDIA_ALLOWED[scenario]:
        state["steps"][step_name]["status"] = "done"
    manager = MemoryStateManager(state)
    runner = StepRunner(manager)  # type: ignore[arg-type]

    original = _SCENARIO_CONFIGS[scenario]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        scenario,
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    result = await runner.resume(state["label"])

    assert result["status"] == "completed_bounded"
    assert result["completion_kind"] == "no_media"
    assert result["request_succeeded"] is True
    assert result["full_media_success"] is False
    assert result["publish_allowed"] is False
    assert result["delivery_accepted"] is False
    assert result["current_step"] is None
    assert manager.saves[-1] == result


@pytest.mark.asyncio
async def test_empty_cursor_with_all_exact_steps_done_keeps_bounded_truth_with_nonfatal_errors() -> None:
    state = _state("s1", media=False, current_step="strategy")
    for step_name in NO_MEDIA_ALLOWED["s1"]:
        state["steps"][step_name]["status"] = "done"
    state["current_step"] = None
    state["errors"] = ["optional fallback was used"]
    manager = MemoryStateManager(state)

    result = await StepRunner(manager).resume(state["label"])  # type: ignore[arg-type]

    assert result["status"] == "completed_bounded"
    assert result["success"] is False
    assert result["errors"] == ["optional fallback was used"]
    assert result["pipeline_degraded"] is False
    assert manager.saves[-1] == result


@pytest.mark.asyncio
async def test_forbidden_canonical_cursor_never_upgrades_degraded_state_to_bounded() -> None:
    state = _state("s1", media=False, current_step="keyframe_images")
    for step_name in NO_MEDIA_ALLOWED["s1"]:
        state["steps"][step_name]["status"] = "done"
    state["pipeline_degraded"] = True
    state["degraded_reason"] = "provider failure"
    manager = MemoryStateManager(state)

    with pytest.raises(HTTPException) as exc_info:
        await StepRunner(manager).resume(state["label"])  # type: ignore[arg-type]

    assert exc_info.value.status_code == 422
    assert manager.saves == []


@pytest.mark.parametrize(
    ("scenario", "forbidden_step"),
    [
        ("s1", "keyframe_images"),
        ("s2", "keyframe_images"),
        ("s3", "keyframe_images"),
        ("s4", "video_prompts"),
        ("s5", "video_prompts"),
    ],
)
@pytest.mark.asyncio
async def test_direct_forbidden_step_fails_before_pipeline_import(
    scenario: str,
    forbidden_step: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state(scenario, media=False, current_step=forbidden_step)
    manager = MemoryStateManager(state)
    runner = StepRunner(manager)  # type: ignore[arg-type]
    original = _SCENARIO_CONFIGS[scenario]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        scenario,
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await runner.run_step(state["label"], forbidden_step)

    assert exc_info.value.status_code == 422
    assert manager.saves == []


@pytest.mark.parametrize("scenario", ["s1", "s2", "s3", "s4", "s5"])
def test_no_media_profiles_are_exact_allowlists(scenario: str) -> None:
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    profile = resolve_generation_execution_profile(_state(scenario, media=False))

    assert profile.allowed_steps == NO_MEDIA_ALLOWED[scenario]
    assert profile.provider_job_caps == {}
    assert profile.completion_kind == "no_media"


@pytest.mark.parametrize("scenario", ["s1", "s3", "s4", "s5"])
def test_bounded_profiles_are_exact_and_stop_after_seedance(scenario: str) -> None:
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    profile = resolve_generation_execution_profile(_state(scenario, media=True))

    assert profile.allowed_steps == BOUNDED_ALLOWED[scenario]
    assert profile.allowed_steps[-1] == "seedance_clips"
    assert profile.provider_job_caps == {"image": 1, "video": 1}
    assert profile.completion_kind == "bounded_media"


@pytest.mark.parametrize("media_stop_step", list(S2_SEGMENTED_ALLOWED))
def test_s2_segmented_profiles_are_non_linear_exact_allowlists(
    media_stop_step: str,
) -> None:
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    state = _state(
        "s2",
        media=True,
        media_stop_step=media_stop_step,
    )
    if media_stop_step in {"assemble_final", "audit"}:
        state["config"]["media_refs"] = {
            "clip_paths": ["/tmp/tenants/tenant-a/pending_review/ref/clip.mp4"],
            "audio_paths": ["/tmp/tenants/tenant-a/pending_review/ref/audio.mp3"],
            "thumbnail_image_paths": ["/tmp/tenants/tenant-a/pending_review/ref/thumb.png"],
        }
        if media_stop_step == "audit":
            state["config"]["media_refs"]["video_path"] = "/tmp/tenants/tenant-a/pending_review/ref/final.mp4"

    profile = resolve_generation_execution_profile(state)

    assert profile.allowed_steps == S2_SEGMENTED_ALLOWED[media_stop_step]
    assert profile.provider_job_caps == S2_PROVIDER_CAPS[media_stop_step]
    assert set(profile.allowed_steps) != set(get_scenario_step_order("s2"))


@pytest.mark.parametrize(
    "policy_mutation",
    [
        pytest.param(lambda state: state["config"].pop("effective_generation_policy"), id="missing"),
        pytest.param(lambda state: state["config"].__setitem__("effective_generation_policy", "bad"), id="corrupt"),
        pytest.param(
            lambda state: state["config"]["effective_generation_policy"].__setitem__(
                "version", "generation-safety.v999"
            ),
            id="unknown-version",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_policy"].__setitem__("tenant_id", "client-tenant"),
            id="tenant-tamper",
        ),
    ],
)
@pytest.mark.asyncio
async def test_missing_or_invalid_persisted_policy_never_imports_pipeline(
    policy_mutation: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state("s1", media=False, current_step="strategy")
    policy_mutation(state)
    manager = MemoryStateManager(state)
    runner = StepRunner(manager)  # type: ignore[arg-type]
    original = _SCENARIO_CONFIGS["s1"]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        "s1",
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await runner.run_step(state["label"], "strategy")

    assert exc_info.value.status_code == 422
    assert manager.saves == []


@pytest.mark.parametrize(
    "profile_mutation",
    [
        pytest.param(
            lambda state: state["config"].pop("effective_generation_execution_profile"),
            id="missing-profile",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_execution_profile"].__setitem__(
                "version", "generation-execution.v999"
            ),
            id="profile-version",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_execution_profile"].__setitem__(
                "allowed_steps", ["strategy", "seedance_clips"]
            ),
            id="allowed-steps",
        ),
        pytest.param(
            lambda state: state["config"].__setitem__("provider_job_caps", {"image": 99, "video": 99}),
            id="provider-caps",
        ),
        pytest.param(
            lambda state: state["config"]["provider_job_caps"].__setitem__("image", True),
            id="provider-caps-bool-is-not-int",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_execution_profile"]["provider_job_caps"].__setitem__(
                "video", "1"
            ),
            id="nested-provider-cap-string",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_execution_profile"].__setitem__(
                "allowed_steps",
                tuple(state["config"]["effective_generation_execution_profile"]["allowed_steps"]),
            ),
            id="allowed-steps-must-be-json-list",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_execution_profile"].__setitem__("refs_only", 0),
            id="refs-only-must-be-bool",
        ),
        pytest.param(
            lambda state: state["config"]["effective_generation_execution_profile"].__setitem__(
                "extra", "client-field"
            ),
            id="profile-extra-field",
        ),
        pytest.param(
            lambda state: state["config"]["provider_job_caps"].pop("video"),
            id="provider-cap-missing",
        ),
    ],
)
@pytest.mark.asyncio
async def test_persisted_execution_profile_or_caps_tamper_fails_before_import(
    profile_mutation: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state("s1", media=True, current_step="strategy")
    profile_mutation(state)
    manager = MemoryStateManager(state)
    runner = StepRunner(manager)  # type: ignore[arg-type]
    original = _SCENARIO_CONFIGS["s1"]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        "s1",
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await runner.run_step(state["label"], "strategy")

    assert exc_info.value.status_code == 422
    assert manager.saves == []


@pytest.mark.asyncio
async def test_resume_none_cursor_with_pending_allowed_step_fails_closed() -> None:
    state = _state("s1", media=False, current_step="strategy")
    state["current_step"] = None
    manager = MemoryStateManager(state)

    with pytest.raises(HTTPException) as exc_info:
        await StepRunner(manager).resume(state["label"])  # type: ignore[arg-type]

    assert exc_info.value.status_code == 422
    assert manager.saves == []


@pytest.mark.asyncio
async def test_legacy_resume_without_policy_is_blocked_not_reported_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state("s1", media=False, current_step="strategy")
    state["config"].pop("effective_generation_policy")
    manager = MemoryStateManager(state)
    runner = StepRunner(manager)  # type: ignore[arg-type]
    original = _SCENARIO_CONFIGS["s1"]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        "s1",
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    result = await runner.resume(state["label"])

    assert result["status"] == "policy_blocked"
    assert result["request_succeeded"] is False
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert result["publish_allowed"] is False
    assert result["delivery_accepted"] is False
    assert result["current_step"] is None
    assert manager.saves[-1] == result


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/tenants/tenant-b/pending_review/ref/clip.mp4",
        "/tmp/tenants/tenant-a/pending_review/../tenant-b/ref/clip.mp4",
    ],
)
def test_s2_refs_only_rejects_cross_tenant_and_traversal(bad_path: str) -> None:
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    state = _state("s2", media=True, media_stop_step="assemble_final")
    state["config"]["media_refs"] = {
        "clip_paths": [bad_path],
        "audio_paths": ["/tmp/tenants/tenant-a/pending_review/ref/audio.mp3"],
        "thumbnail_image_paths": ["/tmp/tenants/tenant-a/pending_review/ref/thumb.png"],
    }

    with pytest.raises(HTTPException) as exc_info:
        resolve_generation_execution_profile(state)

    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_force_never_reexecutes_completed_provider_or_media_step() -> None:
    state = _state("s1", media=True, current_step="seedance_clips")
    state["steps"]["scripts"]["status"] = "done"
    state["steps"]["seedance_clips"]["status"] = "done"
    manager = MemoryStateManager(state)
    runner = StepRunner(manager)  # type: ignore[arg-type]

    with pytest.raises(HTTPException):
        await runner.regenerate_step(state["label"], "scripts")
    with pytest.raises(HTTPException):
        await runner.regenerate_step(state["label"], "seedance_clips")

    assert manager.saves == []


@pytest.mark.parametrize(
    ("status", "started_at"),
    [
        ("error", "already-started"),
        ("pending", "already-started"),
        ("running", "already-started"),
    ],
)
@pytest.mark.asyncio
async def test_force_never_reexecutes_provider_step_with_attempt_evidence(
    status: str,
    started_at: str,
) -> None:
    """A force request cannot erase or bypass an already consumed attempt."""

    state = _state("s1", media=False, current_step="strategy")
    state["steps"]["strategy"].update(
        {
            "status": status,
            "started_at": started_at,
            "_quality_attempt": 1,
        }
    )
    manager = MemoryStateManager(state)

    with pytest.raises(HTTPException) as exc_info:
        await StepRunner(manager).regenerate_step(state["label"], "strategy")  # type: ignore[arg-type]

    assert exc_info.value.status_code == 422
    assert manager.saves == []
    persisted = await manager.load(state["label"])
    assert persisted is not None
    assert persisted["steps"]["strategy"]["_quality_attempt"] == 1


@pytest.mark.parametrize("rendering_service_url", ["", "https://renderer.invalid"])
@pytest.mark.asyncio
async def test_assemble_force_is_blocked_before_local_or_remote_renderer_construction(
    rendering_service_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assembly writes a new artifact, so force needs a durable artifact ledger."""

    from src.pipeline.generation_policy import ARTIFACT_MUTATION_STEPS

    assert ARTIFACT_MUTATION_STEPS == frozenset({"assemble_final"})
    state = _state(
        "s2",
        media=True,
        current_step="assemble_final",
        media_stop_step="assemble_final",
    )
    state["steps"]["assemble_final"]["_quality_attempt"] = 1
    manager = MemoryStateManager(state)
    original = _SCENARIO_CONFIGS["s2"]
    monkeypatch.setenv("RENDERING_SERVICE_URL", rendering_service_url)
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        "s2",
        {**original, "pipeline_class": "sentinel.renderer.must_not_import.Pipeline"},
    )

    for _ in range(2):
        with pytest.raises(HTTPException) as exc_info:
            await StepRunner(manager).regenerate_step(  # type: ignore[arg-type]
                state["label"],
                "assemble_final",
            )
        assert exc_info.value.status_code == 422

    assert manager.saves == []
    persisted = await manager.load(state["label"])
    assert persisted is not None
    assert persisted["steps"]["assemble_final"]["_quality_attempt"] == 1


@pytest.mark.asyncio
async def test_assemble_normal_reentry_after_started_or_error_is_blocked() -> None:
    state = _state(
        "s2",
        media=True,
        current_step="assemble_final",
        media_stop_step="assemble_final",
    )
    state["steps"]["assemble_final"].update({"status": "error", "started_at": "already-started", "_quality_attempt": 1})
    manager = MemoryStateManager(state)

    for _ in range(2):
        with pytest.raises(HTTPException) as exc_info:
            await StepRunner(manager).run_step(  # type: ignore[arg-type]
                state["label"],
                "assemble_final",
            )
        assert exc_info.value.status_code == 422

    assert manager.saves == []


@pytest.mark.asyncio
async def test_first_assemble_persists_started_marker_before_renderer_call(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    state = _state(
        "s2",
        media=True,
        current_step="assemble_final",
        media_stop_step="assemble_final",
    )
    await attach_test_provider_execution_authority(state)
    manager = MemoryStateManager(state)

    async def fake_run_step(
        self: Any,
        step_name: str,
        run_state: dict[str, Any],
    ) -> dict[str, Any]:
        del self, run_state
        assert step_name == "assemble_final"
        assert manager.saves
        persisted_step = manager.saves[-1]["steps"]["assemble_final"]
        assert persisted_step["status"] == "pending"
        assert persisted_step["started_at"]
        return {"video_path": "fixture.mp4", "render_json_path": "fixture.json"}

    monkeypatch.setattr(S1ProductDirectPipeline, "run_step", fake_run_step)

    result = await StepRunner(manager).run_step(  # type: ignore[arg-type]
        state["label"],
        "assemble_final",
    )

    assert result["steps"]["assemble_final"]["status"] == "done"
    assert len(manager.saves) >= 2


@pytest.mark.parametrize("status", ["error", "running"])
@pytest.mark.asyncio
async def test_provider_step_reentry_after_started_or_error_is_blocked(
    status: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _state("s1", media=False, current_step="strategy")
    state["steps"]["strategy"]["status"] = status
    state["steps"]["strategy"]["started_at"] = "already-started"
    manager = MemoryStateManager(state)
    original = _SCENARIO_CONFIGS["s1"]
    monkeypatch.setitem(
        _SCENARIO_CONFIGS,
        "s1",
        {**original, "pipeline_class": "sentinel.must_not_import.Pipeline"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await StepRunner(manager).run_step(state["label"], "strategy")  # type: ignore[arg-type]

    assert exc_info.value.status_code == 422
    assert manager.saves == []


@pytest.mark.asyncio
async def test_auto_provider_step_persists_started_marker_before_call(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    state = _state("s1", media=False, current_step="strategy")
    await attach_test_provider_execution_authority(state)
    state["steps"]["strategy"]["started_at"] = ""
    manager = MemoryStateManager(state)

    async def fake_run_step(
        self: Any,
        step_name: str,
        run_state: dict[str, Any],
    ) -> dict[str, Any]:
        del self, run_state
        assert step_name == "strategy"
        assert manager.saves
        assert manager.saves[-1]["steps"]["strategy"]["started_at"]
        return {"briefs": []}

    monkeypatch.setattr(S1ProductDirectPipeline, "run_step", fake_run_step)

    result = await StepRunner(manager).run_step(state["label"], "strategy")  # type: ignore[arg-type]

    assert result["steps"]["strategy"]["status"] == "done"
    assert len(manager.saves) >= 2


@pytest.mark.asyncio
async def test_run_step_marks_exact_profile_terminal_as_completed_bounded(
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    from src.pipeline.s1_product_pipeline import S1ProductDirectPipeline

    state = _state(
        "s1",
        media=False,
        current_step="continuity_storyboard_grid",
    )
    await attach_test_provider_execution_authority(state)
    for step_name in NO_MEDIA_ALLOWED["s1"][:-1]:
        state["steps"][step_name]["status"] = "done"
    manager = MemoryStateManager(state)

    async def fake_run_step(
        self: Any,
        step_name: str,
        run_state: dict[str, Any],
    ) -> dict[str, Any]:
        del self, run_state
        assert step_name == "continuity_storyboard_grid"
        return {"clip_groups": []}

    monkeypatch.setattr(S1ProductDirectPipeline, "run_step", fake_run_step)

    result = await StepRunner(manager).run_step(  # type: ignore[arg-type]
        state["label"], "continuity_storyboard_grid"
    )

    assert result["status"] == "completed_bounded"
    assert result["request_succeeded"] is True
    assert result["success"] is False
    assert result["full_media_success"] is False
    assert result["publish_allowed"] is False
    assert result["delivery_accepted"] is False
    assert result["current_step"] is None


@pytest.mark.asyncio
async def test_text_gate_uses_exactly_three_slots_without_replacement(
    isolated_state_dir: Any,
    isolated_provider_cost_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.pipeline import gate_manager
    from src.pipeline.state_manager import PipelineStateManager
    from src.skills.base import SkillResult

    state = _state("s1", media=False, current_step="scripts")
    await attach_test_provider_execution_authority(state)
    state["steps"]["strategy"].update({"status": "done", "output": [{"id": "brief", "topic": "fixture"}]})
    await PipelineStateManager().save(state["label"], state)
    calls: list[str] = []

    async def fake_execute(self: Any, skill_name: str, params: dict[str, Any]) -> SkillResult:
        del self, params
        calls.append(skill_name)
        if len(calls) == 1:
            return SkillResult(success=False, error="first slot failed")
        return SkillResult(
            success=True,
            data={"scripts": [{"id": f"script-{len(calls)}"}]},
        )

    async def fake_score(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        return {"overall": 0.8, "breakdown": {}}

    monkeypatch.setattr(gate_manager.SkillRegistry, "execute", fake_execute)
    monkeypatch.setattr(gate_manager, "score_candidate", fake_score)

    result = await gate_manager.generate_candidates(state["label"], "gate_1_script")
    repeated = await gate_manager.generate_candidates(state["label"], "gate_1_script")

    assert calls == ["script-writer-skill"] * 3
    assert len(result["candidates"]) == 3
    assert result["candidates"][0]["score"]["error"] is True
    assert repeated["candidates"] == result["candidates"]


@pytest.mark.asyncio
async def test_provider_backed_text_gate_regenerate_requires_persisted_context(
    isolated_state_dir: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.models.provider_cost import ProviderCostContractError
    from src.pipeline import gate_manager
    from src.pipeline.state_manager import PipelineStateManager

    state = _state("s1", media=False, current_step="scripts")
    state["gates"]["gate_1_script"] = {
        "status": "awaiting_approval",
        "approved": False,
        "selected_ids": [],
        "candidates": [
            {
                "id": "text-candidate",
                "variant": "standard",
                "data": {"scripts": []},
                "score": {"overall": 0.5},
            }
        ],
    }
    await PipelineStateManager().save(state["label"], state)
    calls = 0

    async def forbidden_execute(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise AssertionError("provider-backed Gate regenerate must be blocked")

    monkeypatch.setattr(gate_manager.SkillRegistry, "execute", forbidden_execute)

    with pytest.raises(ProviderCostContractError) as exc_info:
        await gate_manager.regenerate_candidate(state["label"], "gate_1_script", "text-candidate")

    assert exc_info.value.code == "provider_execution_context_missing"
    assert calls == 0


@pytest.mark.asyncio
async def test_nonledger_video_prompt_gate_regenerate_fails_before_epoch_or_save(
    isolated_state_dir: Any,
    isolated_provider_cost_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.pipeline import gate_manager
    from src.pipeline.state_manager import PipelineStateManager

    state = _state("s4", media=True, current_step="video_prompts")
    state["gates"]["gate_2_prompts"] = {
        "status": "awaiting_approval",
        "approved": False,
        "selected_ids": [],
        "candidates": [
            {
                "id": "video-prompt-candidate",
                "variant": "standard",
                "data": {"prompt": "fixture"},
                "score": {"overall": 0.5},
            }
        ],
    }
    manager = PipelineStateManager()
    await manager.save(state["label"], state)
    before = await manager.load(state["label"])
    saves = 0
    calls = 0
    original_save = PipelineStateManager.save

    async def counted_save(self: Any, label: str, saved_state: dict[str, Any]) -> None:
        nonlocal saves
        saves += 1
        await original_save(self, label, saved_state)

    async def forbidden_execute(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise AssertionError("non-ledger Gate regeneration must stop before provider execution")

    monkeypatch.setattr(PipelineStateManager, "save", counted_save)
    monkeypatch.setattr(gate_manager.SkillRegistry, "execute", forbidden_execute)

    with pytest.raises(HTTPException) as exc_info:
        await gate_manager.regenerate_candidate(
            state["label"],
            "gate_2_prompts",
            "video-prompt-candidate",
        )

    assert exc_info.value.status_code == 422
    assert saves == 0
    assert calls == 0
    assert await manager.load(state["label"]) == before
    assert isolated_provider_cost_db.execute("SELECT COUNT(*) FROM provider_cost_attempts").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("gate_id", "candidate_id", "operation"),
    [
        ("gate_2_keyframe", None, "generate"),
        ("gate_3_clips", None, "generate"),
        ("gate_2_keyframe", "media-candidate", "regenerate"),
        ("gate_3_clips", "media-candidate", "regenerate"),
    ],
)
@pytest.mark.asyncio
async def test_media_gate_generate_and_regenerate_are_blocked_before_skill_or_save(
    gate_id: str,
    candidate_id: str | None,
    operation: str,
    isolated_state_dir: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.pipeline import gate_manager
    from src.pipeline.state_manager import PipelineStateManager

    state = _state("s1", media=True, current_step="keyframe_images")
    state["gates"][gate_id] = {
        "status": "awaiting_approval",
        "approved": False,
        "selected_ids": [],
        "candidates": [
            {
                "id": "media-candidate",
                "variant": "standard",
                "data": {},
                "score": {"overall": 0.5},
            }
        ],
    }
    await PipelineStateManager().save(state["label"], state)
    calls = 0

    async def forbidden_execute(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        del args, kwargs
        calls += 1
        raise AssertionError("media gate must be blocked before SkillRegistry")

    monkeypatch.setattr(gate_manager.SkillRegistry, "execute", forbidden_execute)
    before = await PipelineStateManager().load(state["label"])

    with pytest.raises(HTTPException) as exc_info:
        if operation == "generate":
            await gate_manager.generate_candidates(state["label"], gate_id)
        else:
            assert candidate_id is not None
            await gate_manager.regenerate_candidate(state["label"], gate_id, candidate_id)

    after = await PipelineStateManager().load(state["label"])
    assert exc_info.value.status_code == 422
    assert calls == 0
    assert after == before


@pytest.mark.asyncio
async def test_gate_approval_uses_exact_profile_next_cursor_before_save(
    isolated_state_dir: Any,
) -> None:
    del isolated_state_dir
    from src.pipeline.gate_manager import approve_gate
    from src.pipeline.state_manager import PipelineStateManager

    state = _state("s1", media=True, current_step="scripts")
    state["steps"]["scripts"]["status"] = "done"
    state["gates"]["gate_1_script"] = {
        "status": "awaiting_approval",
        "approved": False,
        "selected_ids": [],
        "candidates": [
            {
                "id": "script-candidate",
                "variant": "standard",
                "data": {"scripts": [{"id": "script"}]},
                "score": {"overall": 0.8},
            }
        ],
    }
    await PipelineStateManager().save(state["label"], state)

    result = await approve_gate(state["label"], "gate_1_script", ["script-candidate"])

    persisted = await PipelineStateManager().load(state["label"])
    assert result["next_step"] == "storyboards"
    assert persisted is not None
    assert persisted["current_step"] == "storyboards"


@pytest.mark.parametrize(
    "invalid_cursor",
    ["strategy", "storyboards", None, "unknown-cursor"],
)
@pytest.mark.asyncio
async def test_gate_approval_requires_cursor_exactly_at_after_step_before_side_effects(
    invalid_cursor: str | None,
    isolated_state_dir: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.pipeline.gate_manager import approve_gate
    from src.pipeline.state_manager import PipelineStateManager
    from src.quality.ab_tracker import ABTracker

    state = _state("s1", media=True, current_step="scripts")
    state["current_step"] = invalid_cursor
    state["gates"]["gate_1_script"] = {
        "status": "awaiting_approval",
        "approved": False,
        "selected_ids": [],
        "candidates": [
            {
                "id": "script-candidate",
                "variant": "standard",
                "data": {"scripts": [{"id": "script"}]},
                "score": {"overall": 0.8},
            }
        ],
    }
    manager = PipelineStateManager()
    await manager.save(state["label"], state)
    before = await manager.load(state["label"])
    saves = 0
    tracker_calls = 0
    original_save = PipelineStateManager.save

    async def counted_save(self: Any, label: str, value: dict[str, Any]) -> None:
        nonlocal saves
        saves += 1
        await original_save(self, label, value)

    def counted_tracker(*args: Any, **kwargs: Any) -> None:
        nonlocal tracker_calls
        del args, kwargs
        tracker_calls += 1

    monkeypatch.setattr(PipelineStateManager, "save", counted_save)
    monkeypatch.setattr(ABTracker, "record_gate_choice", counted_tracker)

    with pytest.raises(HTTPException) as exc_info:
        await approve_gate(state["label"], "gate_1_script", ["script-candidate"])

    assert exc_info.value.status_code == 422
    assert saves == 0
    assert tracker_calls == 0
    assert await manager.load(state["label"]) == before


@pytest.mark.asyncio
async def test_gate_rebinds_persisted_policy_and_resets_context(
    isolated_state_dir: Any,
    isolated_provider_cost_db: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.pipeline import gate_manager
    from src.pipeline.generation_policy import (
        _effective_generation_policy_var,
        get_effective_generation_policy,
    )
    from src.pipeline.state_manager import PipelineStateManager
    from src.skills.base import SkillResult

    _effective_generation_policy_var.set(None)
    state = _state("s1", media=False, current_step="scripts")
    await attach_test_provider_execution_authority(state)
    await PipelineStateManager().save(state["label"], state)
    seen: list[EffectiveGenerationPolicy | None] = []

    async def fake_execute(self: Any, skill_name: str, params: dict[str, Any]) -> SkillResult:
        del self, skill_name
        seen.append(get_effective_generation_policy())
        assert params["provider_max_retries"] == 0
        return SkillResult(success=True, data={"scripts": [{"id": "script"}]})

    async def fake_score(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        seen.append(get_effective_generation_policy())
        return {"overall": 0.8}

    monkeypatch.setattr(gate_manager.SkillRegistry, "execute", fake_execute)
    monkeypatch.setattr(gate_manager, "score_candidate", fake_score)

    await gate_manager.generate_candidates(state["label"], "gate_1_script")

    assert len(seen) == 6
    assert all(policy is not None for policy in seen)
    assert get_effective_generation_policy() is None


@pytest.mark.parametrize(
    ("scenario", "media", "gate_id", "step_name", "persisted_output"),
    [
        (
            "s4",
            True,
            "gate_2_prompts",
            "video_prompts",
            [{"prompt": "live shoot prompt", "duration": 5}],
        ),
        (
            "s5",
            False,
            "gate_1_strategy",
            "vlog_strategy",
            {
                "shots": [{"shot_id": "shot-1", "description": "opening"}],
                "scripts": [{"text": "VLOG intro"}],
            },
        ),
    ],
)
@pytest.mark.asyncio
async def test_state_assembled_text_gates_preserve_schema_with_zero_provider_calls(
    scenario: str,
    media: bool,
    gate_id: str,
    step_name: str,
    persisted_output: Any,
    isolated_state_dir: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_state_dir
    from src.pipeline import gate_manager
    from src.pipeline.state_manager import PipelineStateManager

    state = _state(scenario, media=media, current_step=step_name)
    state["steps"][step_name].update({"status": "done", "output": persisted_output})
    await PipelineStateManager().save(state["label"], state)
    provider_calls = 0

    async def forbidden_provider(*args: Any, **kwargs: Any) -> Any:
        nonlocal provider_calls
        del args, kwargs
        provider_calls += 1
        raise AssertionError("state-assembled review must not call a provider")

    monkeypatch.setattr(gate_manager.SkillRegistry, "execute", forbidden_provider)
    monkeypatch.setattr(gate_manager, "score_candidate", forbidden_provider)

    result = await gate_manager.generate_candidates(state["label"], gate_id)

    assert provider_calls == 0
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["data"] == persisted_output
    assert candidate["recommended"] is False
    assert candidate["score"] == {
        "overall": 0.5,
        "heuristic": True,
        "unscored": True,
        "explanation": "not provider-scored; human review required",
    }
