from __future__ import annotations

import asyncio
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.state_manager import PipelineStateManager
from tests.generation_policy_test_utils import attach_execution_policy


def _execution_policy_config(scenario: str, *, media: bool) -> dict:
    from src.pipeline.generation_policy import EffectiveGenerationPolicy

    policy = EffectiveGenerationPolicy(
        tenant_id="default",
        scenario=scenario,  # type: ignore[arg-type]
        enable_media_synthesis=media,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )
    return {
        "enable_media_synthesis": media,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
        "effective_generation_policy": policy.model_dump(mode="json"),
    }


async def _save_state(label: str, state: dict) -> None:
    await PipelineStateManager().save(label, state)


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/scenario/s1/step/strategy", {"label": "permission-probe"}),
        ("/scenario/s1/regenerate", {"label": "permission-probe", "step": "strategy"}),
        ("/scenario/s1/resume", {"label": "permission-probe"}),
        ("/scenario/s2/step/strategy", {"label": "permission-probe"}),
        ("/scenario/s2/regenerate/permission-probe/strategy", None),
        ("/scenario/s2/gate/permission-probe/gate_1_script/generate", None),
        (
            "/scenario/s2/gate/permission-probe/gate_1_script/approve",
            {"selected_ids": ["candidate-1"]},
        ),
        (
            "/scenario/s2/gate/permission-probe/gate_1_script/regenerate/candidate-1",
            None,
        ),
    ],
)
@pytest.mark.asyncio
async def test_continuation_routes_require_current_provider_submit_permission(
    path: str,
    body: dict | None,
) -> None:
    """Persisted authority must not be reusable by a lower-privilege API key."""
    from src.api import app
    from src.routers import _deps

    async def readonly_tenant_key() -> _deps.AuthContext:
        ctx = _deps.AuthContext(
            tenant_id="default",
            key_id="readonly-key",
            permissions=frozenset(),
            key_type=_deps.ApiKeyType.TENANT,
        )
        _deps._bind_auth_context(ctx)
        return ctx

    app.dependency_overrides[_deps.verify_api_key] = readonly_tenant_key
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                path,
                headers={"X-API-Key": "readonly-key"},
                json=body,
            )
    finally:
        app.dependency_overrides.pop(_deps.verify_api_key, None)

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Insufficient permission"


@pytest.mark.asyncio
async def test_generic_cached_step_validates_persisted_execution_policy_first(
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app

    label = "cached-legacy-state-without-policy"
    await _save_state(
        label,
        {
            "label": label,
            "tenant_id": "default",
            "scenario": "s2",
            "current_step": "strategy",
            "config": {},
            "steps": {
                "strategy": {
                    "status": "done",
                    "output": [{"id": "legacy-cache"}],
                    "edited": False,
                    "edited_output": None,
                }
            },
            "gates": {},
            "errors": [],
            "pipeline_degraded": False,
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s2/step/strategy",
            headers=auth_headers,
            json={"label": label},
        )

    assert response.status_code == 422, response.text
    assert "Persisted effective generation policy is missing or invalid" in response.text


@pytest.mark.asyncio
async def test_execute_step_supports_s2(monkeypatch: pytest.MonkeyPatch, isolated_state_dir, auth_headers) -> None:
    from src.api import app
    from src.pipeline.step_runner import StepRunner

    label = "s2-step-router"
    state = {
        "label": label,
        "scenario": "s2",
        "current_step": "strategy",
        "config": {
            "product_catalog": {"name": "MomCozy"},
            "brand_guidelines": {"brand_name": "MomCozy"},
        },
        "steps": {
            "strategy": {"status": "pending", "output": None, "edited": False, "edited_output": None},
        },
        "errors": [],
        "media_synthesis_errors": [],
    }
    attach_execution_policy(state, scenario="s2", media=False)
    await _save_state(
        label,
        state,
    )

    async def fake_run_step(self: StepRunner, run_label: str, step_name: str) -> dict:
        assert run_label == label
        assert step_name == "strategy"
        state = await self.state_manager.load(run_label)
        assert state is not None
        state["steps"]["strategy"] = {
            "status": "done",
            "output": [{"id": "brief-1"}],
            "edited": False,
            "edited_output": None,
        }
        return state

    monkeypatch.setattr(StepRunner, "run_step", fake_run_step)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s2/step/strategy",
            headers=auth_headers,
            json={"label": label},
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["step"] == "strategy"
    assert payload["status"] == "completed"
    assert payload["data"] == [{"id": "brief-1"}]


@pytest.mark.asyncio
async def test_regenerate_step_s4_provider_attempt_is_blocked_before_invalidation(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    from src.api import app
    from src.pipeline import step_editor
    from src.pipeline.generation_policy import resolve_generation_execution_profile
    from src.pipeline.step_runner import StepRunner

    label = "s4-regen-router"
    state = {
        "label": label,
        "tenant_id": "default",
        "scenario": "s4",
        "current_step": "video_prompts",
        "config": {
            "product_name": "MomCozy Pump",
            **_execution_policy_config("s4", media=False),
        },
        "steps": {
            "scripts": {"status": "done", "output": [{"text": "script"}], "edited": False, "edited_output": None},
            "continuity_storyboard_grid": {
                "status": "done",
                "output": {"clip_groups": [{"id": "cg-1"}]},
                "edited": False,
                "edited_output": None,
            },
            "video_prompts": {"status": "done", "output": [{"prompt": "p1"}], "edited": False, "edited_output": None},
            "thumbnails": {"status": "done", "output": [{"prompt": "thumb"}], "edited": False, "edited_output": None},
            "seedance_clips": {
                "status": "done",
                "output": {"clip_paths": ["clip.mp4"]},
                "edited": False,
                "edited_output": None,
            },
            "tts_audio": {"status": "done", "output": ["audio.mp3"], "edited": False, "edited_output": None},
            "assemble_final": {
                "status": "done",
                "output": ["final.mp4", "render.json"],
                "edited": False,
                "edited_output": None,
            },
            "audit": {"status": "done", "output": {"overall_status": "PASS"}, "edited": False, "edited_output": None},
        },
        "errors": [],
        "media_synthesis_errors": [],
    }
    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    state["config"]["effective_generation_execution_profile"] = profile.model_dump()
    state["config"]["provider_job_caps"] = dict(profile.provider_job_caps)
    await _save_state(label, state)
    before = await PipelineStateManager().load(label)
    invalidations = 0
    runner_calls = 0

    async def fake_regenerate_step(self: StepRunner, run_label: str, step_name: str) -> dict:
        nonlocal runner_calls
        del self, run_label, step_name
        runner_calls += 1
        raise AssertionError("provider attempt must be blocked before StepRunner")

    async def forbidden_invalidate(*args, **kwargs):
        nonlocal invalidations
        del args, kwargs
        invalidations += 1
        raise AssertionError("provider attempt must be blocked before invalidation")

    monkeypatch.setattr(StepRunner, "regenerate_step", fake_regenerate_step)
    monkeypatch.setattr(step_editor, "invalidate_downstream", forbidden_invalidate)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/scenario/s4/regenerate/{label}/scripts",
            headers=auth_headers,
        )

    assert response.status_code == 422, response.text
    assert invalidations == 0
    assert runner_calls == 0
    assert await PipelineStateManager().load(label) == before


@pytest.mark.asyncio
async def test_regenerate_step_supports_s5(monkeypatch: pytest.MonkeyPatch, isolated_state_dir, auth_headers) -> None:
    from src.api import app
    from src.pipeline.generation_policy import resolve_generation_execution_profile
    from src.pipeline.step_runner import StepRunner

    label = "s5-regen-router"
    state = {
        "label": label,
        "tenant_id": "default",
        "scenario": "s5",
        "current_step": "assemble_final",
        "config": {
            "product_name": "MomCozy Pump",
            **_execution_policy_config("s5", media=True),
        },
        "steps": {
            "vlog_strategy": {
                "status": "done",
                "output": {"shots": [], "scripts": []},
                "edited": False,
                "edited_output": None,
            },
            "continuity_storyboard_grid": {
                "status": "done",
                "output": {"clip_groups": []},
                "edited": False,
                "edited_output": None,
            },
            "video_prompts": {"status": "done", "output": [{"prompt": "p1"}], "edited": False, "edited_output": None},
            "seedance_clips": {
                "status": "done",
                "output": {"clip_paths": ["clip.mp4"]},
                "edited": False,
                "edited_output": None,
            },
            "tts_audio": {"status": "done", "output": ["audio.mp3"], "edited": False, "edited_output": None},
            "assemble_final": {
                "status": "done",
                "output": ["final.mp4", "render.json"],
                "edited": False,
                "edited_output": None,
            },
            "audit": {"status": "done", "output": {"overall_status": "PASS"}, "edited": False, "edited_output": None},
        },
        "errors": [],
        "media_synthesis_errors": [],
    }
    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    state["config"]["effective_generation_execution_profile"] = profile.model_dump()
    state["config"]["provider_job_caps"] = dict(profile.provider_job_caps)
    await _save_state(label, state)

    async def fake_regenerate_step(self: StepRunner, run_label: str, step_name: str) -> dict:
        assert run_label == label
        assert step_name == "video_prompts"
        state = await self.state_manager.load(run_label)
        assert state is not None
        state["steps"]["video_prompts"] = {
            "status": "done",
            "output": [{"prompt": "regenerated"}],
            "edited": False,
            "edited_output": None,
        }
        return state

    monkeypatch.setattr(StepRunner, "regenerate_step", fake_regenerate_step)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/scenario/s5/regenerate/{label}/video_prompts",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["invalidated"] == ["seedance_clips", "tts_audio", "assemble_final", "audit"]


@pytest.mark.asyncio
async def test_status_exposes_soft_degraded_reasons(isolated_state_dir, auth_headers) -> None:
    from src.api import app

    label = "s3-soft-status"
    await _save_state(
        label,
        {
            "label": label,
            "scenario": "s3",
            "current_step": "video_prompts",
            "config": {"product": {"name": "MomCozy Pump"}},
            "steps": {
                "video_analysis": {"status": "done", "output": {}},
                "character_identity": {"status": "done", "output": {}},
                "remix_script": {"status": "done", "output": {}},
                "storyboards": {"status": "done", "output": {}},
                "continuity_storyboard_grid": {"status": "done", "output": {}},
                "video_prompts": {"status": "pending", "output": None},
                "audit": {
                    "status": "done",
                    "output": {
                        "continuity_score": 0.8,
                        "asset_ready_audit": {
                            "status": "PASS",
                            "checks": {"director_intent_metadata": True},
                        },
                        "continuity_direction_summary": {
                            "clip_directions": [
                                {
                                    "scene_beat": "context_setup",
                                    "beat_summary": "context_setup -> product_intro",
                                    "transition_intent": "bridge setup into product interaction",
                                }
                            ],
                            "scene_beats": ["context_setup"],
                            "transition_intents": ["bridge setup into product interaction"],
                        },
                    },
                },
            },
            "soft_degraded_reasons": [
                {
                    "step": "continuity_storyboard_grid",
                    "reason": "continuity_skill_fallback",
                    "detail": "mock fallback used",
                }
            ],
            "errors": [],
            "media_synthesis_errors": [],
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/scenario/s3/status/{label}",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["soft_degraded_reasons"][0]["step"] == "continuity_storyboard_grid"
    assert payload["soft_degraded_reasons"][0]["reason"] == "continuity_skill_fallback"
    assert payload["continuity_diagnostics"]["continuity_score"] == 0.8
    assert payload["continuity_diagnostics"]["director_intent_metadata"] is True
    assert payload["continuity_diagnostics"]["clip_directions"][0]["scene_beat"] == "context_setup"


@pytest.mark.asyncio
async def test_status_preserves_completed_bounded_lifecycle_truth(
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    label = "s1-completed-bounded-status"
    config = _execution_policy_config("s1", media=False)
    state = {
        "schema_version": 1,
        "label": label,
        "tenant_id": "default",
        "scenario": "s1",
        "current_step": None,
        "config": config,
        "steps": {
            "strategy": {"status": "done"},
            "scripts": {"status": "done"},
            "compliance": {"status": "done"},
            "storyboards": {"status": "done"},
            "continuity_storyboard_grid": {"status": "done"},
        },
        "errors": ["optional fallback retained for audit"],
        "pipeline_degraded": False,
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "no_media",
        "request_succeeded": True,
        "success": False,
        "full_media_success": False,
        "pipeline_complete": False,
        "publish_allowed": False,
        "delivery_accepted": False,
    }
    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    config["effective_generation_execution_profile"] = profile.model_dump()
    config["provider_job_caps"] = dict(profile.provider_job_caps)
    state["execution_profile_id"] = profile.profile_id
    state["provider_job_caps"] = dict(profile.provider_job_caps)
    config["execution_lifecycle"] = {
        key: state[key]
        for key in (
            "status",
            "lifecycle_status",
            "completion_kind",
            "request_succeeded",
            "success",
            "full_media_success",
            "pipeline_complete",
            "publish_allowed",
            "delivery_accepted",
            "execution_profile_id",
            "provider_job_caps",
        )
    }
    await _save_state(label, state)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/scenario/s1/status/{label}",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "completed_bounded"
    assert payload["lifecycle_status"] == "completed_bounded"
    assert payload["completion_kind"] == "no_media"
    assert payload["progress"] == 1.0
    assert payload["request_succeeded"] is True
    assert payload["success"] is False
    assert payload["full_media_success"] is False
    assert payload["pipeline_complete"] is False
    assert payload["publish_allowed"] is False
    assert payload["delivery_accepted"] is False
    assert payload["errors"] == ["optional fallback retained for audit"]


@pytest.mark.asyncio
async def test_status_never_infers_completion_from_bare_empty_cursor(
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app

    label = "s1-bare-empty-cursor"
    await _save_state(
        label,
        {
            "schema_version": 1,
            "label": label,
            "tenant_id": "default",
            "scenario": "s1",
            "current_step": None,
            "config": {},
            "steps": {},
            "errors": [],
            "pipeline_degraded": False,
        },
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/scenario/s1/status/{label}",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "invalid_state"
    assert payload["progress"] == 0.0
    assert payload["request_succeeded"] is False
    assert payload["success"] is False
    assert payload["full_media_success"] is False
    assert payload["pipeline_complete"] is False
    assert payload["publish_allowed"] is False
    assert payload["delivery_accepted"] is False


@pytest.mark.asyncio
async def test_regenerate_route_preflights_policy_before_invalidation(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.pipeline import step_editor

    label = "s1-forbidden-regen-preflight"
    state = {
        "label": label,
        "tenant_id": "default",
        "scenario": "s1",
        "mode": "auto",
        "current_step": "keyframe_images",
        "config": _execution_policy_config("s1", media=False),
        "steps": {
            step: {
                "status": "done" if step == "keyframe_images" else "pending",
                "output": None,
                "edited": False,
                "edited_output": None,
            }
            for step in [
                "strategy",
                "scripts",
                "compliance",
                "storyboards",
                "continuity_storyboard_grid",
                "keyframe_images",
                "video_prompts",
                "thumbnail_prompts",
                "seedance_clips",
                "tts_audio",
                "thumbnail_images",
                "assemble_final",
                "audit",
            ]
        },
        "gates": {},
        "errors": [],
        "media_synthesis_errors": [],
        "pipeline_degraded": False,
    }
    await _save_state(label, state)
    invalidations = 0

    async def forbidden_invalidate(*args, **kwargs):
        nonlocal invalidations
        del args, kwargs
        invalidations += 1
        raise AssertionError("invalidation must be after policy preflight")

    monkeypatch.setattr(step_editor, "invalidate_downstream", forbidden_invalidate)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/scenario/s1/regenerate/{label}/keyframe_images",
            headers=auth_headers,
        )

    assert response.status_code == 422, response.text
    assert invalidations == 0
    assert await PipelineStateManager().load(label) == state


@pytest.mark.asyncio
async def test_repeated_regenerate_route_preserves_consumed_provider_attempt(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    """Repeated HTTP retries cannot turn a failed provider attempt into a new submit."""

    del isolated_state_dir
    from src.api import app
    from src.pipeline import step_editor
    from src.pipeline.generation_policy import resolve_generation_execution_profile

    label = "s1-provider-attempt-regen-guard"
    config = _execution_policy_config("s1", media=False)
    state = {
        "label": label,
        "tenant_id": "default",
        "scenario": "s1",
        "mode": "auto",
        "current_step": "strategy",
        "config": config,
        "steps": {
            "strategy": {
                "status": "error",
                "output": None,
                "edited": False,
                "edited_output": None,
                "started_at": "already-started",
                "_quality_attempt": 1,
            }
        },
        "gates": {},
        "errors": [],
        "media_synthesis_errors": [],
        "pipeline_degraded": False,
    }
    profile = resolve_generation_execution_profile(
        state,
        require_persisted_profile=False,
    )
    config["effective_generation_execution_profile"] = profile.model_dump()
    config["provider_job_caps"] = dict(profile.provider_job_caps)
    await _save_state(label, state)

    invalidations = 0

    async def forbidden_invalidate(*args, **kwargs):
        nonlocal invalidations
        del args, kwargs
        invalidations += 1
        raise AssertionError("invalidation must not run for a consumed attempt")

    monkeypatch.setattr(step_editor, "invalidate_downstream", forbidden_invalidate)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        responses = [
            await client.post(
                f"/scenario/s1/regenerate/{label}/strategy",
                headers=auth_headers,
            )
            for _ in range(2)
        ]

    assert [response.status_code for response in responses] == [422, 422]
    assert invalidations == 0
    persisted = await PipelineStateManager().load(label)
    assert persisted is not None
    assert persisted["steps"]["strategy"]["_quality_attempt"] == 1
    assert persisted["steps"]["strategy"]["started_at"] == "already-started"


@pytest.mark.parametrize(
    "protected_update",
    [
        {"tenant_id": "default"},
        {"scenario": "s1"},
        {"mode": "auto"},
        {"current_step": None},
        {"gates": {}},
        {"status": None},
        {"lifecycle_status": "completed_bounded"},
        {"errors": []},
        {"pipeline_degraded": False},
        {"config": {"enable_media_synthesis": False}},
        {"config": {"effective_generation_policy": {}}},
        {"config": {"effective_generation_execution_profile": {}}},
        {"config": {"provider_job_caps": {}}},
        {"config": {"execution_lifecycle": {}}},
        {"steps": {"scripts": {"status": "done"}}},
        {"steps": {"scripts": {"started_at": None}}},
        {"steps": {"scripts": {"completed_at": ""}}},
    ],
)
@pytest.mark.asyncio
async def test_s1_state_edit_rejects_server_owned_fields_by_presence(
    protected_update: dict,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app

    label = "s1-protected-edit"
    state = {
        "label": label,
        "tenant_id": "default",
        "scenario": "s1",
        "mode": "auto",
        "current_step": "scripts",
        "config": _execution_policy_config("s1", media=False),
        "steps": {
            "scripts": {
                "status": "done",
                "output": [{"id": "script"}],
                "edited": False,
                "edited_output": None,
                "started_at": "start",
                "completed_at": "done",
                "duration_ms": 1,
            }
        },
        "gates": {},
        "errors": [],
        "media_synthesis_errors": [],
        "pipeline_degraded": False,
    }
    await _save_state(label, state)
    before = await PipelineStateManager().load(label)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            f"/scenario/s1/state/{label}",
            headers=auth_headers,
            json=protected_update,
        )

    assert response.status_code == 422, (protected_update, response.text)
    assert await PipelineStateManager().load(label) == before


@pytest.mark.asyncio
async def test_s1_state_edit_allows_only_edited_output_fields(
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app

    label = "s1-allowed-edit"
    state = {
        "label": label,
        "tenant_id": "default",
        "scenario": "s1",
        "mode": "auto",
        "current_step": "scripts",
        "config": _execution_policy_config("s1", media=False),
        "steps": {
            "scripts": {
                "status": "done",
                "output": [{"id": "original"}],
                "edited": False,
                "edited_output": None,
                "started_at": "start",
                "completed_at": "done",
                "duration_ms": 1,
            }
        },
        "gates": {},
        "errors": [],
        "media_synthesis_errors": [],
        "pipeline_degraded": False,
    }
    await _save_state(label, state)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.put(
            f"/scenario/s1/state/{label}",
            headers=auth_headers,
            json={
                "steps": {
                    "scripts": {
                        "edited": True,
                        "edited_output": [{"id": "edited"}],
                    }
                }
            },
        )

    assert response.status_code == 200, response.text
    persisted = await PipelineStateManager().load(label)
    assert persisted is not None
    assert persisted["steps"]["scripts"]["status"] == "done"
    assert persisted["steps"]["scripts"]["output"] == [{"id": "original"}]
    assert persisted["steps"]["scripts"]["edited"] is True
    assert persisted["steps"]["scripts"]["edited_output"] == [{"id": "edited"}]


@pytest.mark.parametrize(
    ("method", "path_template", "body"),
    [
        ("POST", "/scenario/s4/step/scripts", {"label": "{label}"}),
        ("POST", "/scenario/s4/regenerate/{label}/scripts", None),
        ("POST", "/scenario/s4/gate/{label}/gate_1_script/generate", None),
        ("GET", "/scenario/s4/status/{label}", None),
    ],
)
@pytest.mark.asyncio
async def test_generic_routes_reject_url_state_scenario_mismatch_before_side_effects(
    method: str,
    path_template: str,
    body: dict | None,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.pipeline import gate_manager, step_editor
    from src.pipeline.step_runner import StepRunner

    label = "s1-state-via-s4-url"
    state = {
        "schema_version": 1,
        "label": label,
        "tenant_id": "default",
        "scenario": "s1",
        "mode": "auto",
        "current_step": "scripts",
        "config": {},
        "steps": {"scripts": {"status": "pending", "output": None}},
        "gates": {},
        "errors": [],
        "pipeline_degraded": False,
    }
    manager = PipelineStateManager()
    await manager.save(label, state)
    side_effect_calls = 0
    saves = 0
    original_save = PipelineStateManager.save

    async def forbidden(*args, **kwargs):
        nonlocal side_effect_calls
        del args, kwargs
        side_effect_calls += 1
        raise AssertionError("scenario mismatch must stop before downstream work")

    async def counted_save(self, saved_label, value):
        nonlocal saves
        saves += 1
        await original_save(self, saved_label, value)

    monkeypatch.setattr(StepRunner, "run_step", forbidden)
    monkeypatch.setattr(StepRunner, "regenerate_step", forbidden)
    monkeypatch.setattr(step_editor, "invalidate_downstream", forbidden)
    monkeypatch.setattr(gate_manager, "generate_candidates", forbidden)
    monkeypatch.setattr(PipelineStateManager, "save", counted_save)

    path = path_template.format(label=label)
    request_body = None
    if body is not None:
        request_body = {
            key: value.format(label=label) if isinstance(value, str) else value for key, value in body.items()
        }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method,
            path,
            headers=auth_headers,
            json=request_body,
        )

    assert response.status_code == 404, response.text
    assert side_effect_calls == 0
    assert saves == 0
    assert await manager.load(label) == state


@pytest.mark.parametrize(
    ("method", "path_template", "body"),
    [
        ("GET", "/scenario/s1/state/{label}", None),
        (
            "PUT",
            "/scenario/s1/state/{label}",
            {"steps": {"scripts": {"edited": True, "edited_output": []}}},
        ),
        (
            "POST",
            "/scenario/s1/regenerate",
            {"label": "{label}", "step": "scripts"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_s1_specific_routes_reject_non_s1_state_before_mutation(
    method: str,
    path_template: str,
    body: dict | None,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.pipeline import step_editor
    from src.pipeline.step_runner import StepRunner

    label = "s2-state-via-s1-url"
    state = {
        "schema_version": 1,
        "label": label,
        "tenant_id": "default",
        "scenario": "s2",
        "current_step": "scripts",
        "config": {},
        "steps": {"scripts": {"status": "done", "output": []}},
        "gates": {},
        "errors": [],
    }
    manager = PipelineStateManager()
    await manager.save(label, state)
    side_effect_calls = 0
    saves = 0
    original_save = PipelineStateManager.save

    async def forbidden(*args, **kwargs):
        nonlocal side_effect_calls
        del args, kwargs
        side_effect_calls += 1
        raise AssertionError("S1 route must not operate on non-S1 state")

    async def counted_save(self, saved_label, value):
        nonlocal saves
        saves += 1
        await original_save(self, saved_label, value)

    monkeypatch.setattr(StepRunner, "regenerate_step", forbidden)
    monkeypatch.setattr(step_editor, "invalidate_downstream", forbidden)
    monkeypatch.setattr(PipelineStateManager, "save", counted_save)

    path = path_template.format(label=label)
    request_body = body
    if body is not None and body.get("label") == "{label}":
        request_body = {**body, "label": label}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            method,
            path,
            headers=auth_headers,
            json=request_body,
        )

    assert response.status_code == 404, response.text
    assert side_effect_calls == 0
    assert saves == 0
    assert await manager.load(label) == state


@pytest.mark.parametrize("stop_step", ["assemble_final", "audit"])
@pytest.mark.asyncio
async def test_unified_s2_refs_only_submit_seeds_validated_inputs_before_background(
    stop_step: str,
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.routers import scenario as scenario_router

    refs = {
        "clip_paths": ["/tmp/tenants/default/pending_review/ref/clip.mp4"],
        "audio_paths": ["/tmp/tenants/default/pending_review/ref/audio.mp3"],
        "thumbnail_image_paths": ["/tmp/tenants/default/pending_review/ref/thumb.png"],
    }
    if stop_step == "audit":
        refs["video_path"] = "/tmp/tenants/default/pending_review/ref/final.mp4"

    scheduled = 0

    class DummyTask:
        pass

    class ScenarioAsyncioProxy:
        def __getattr__(self, name: str):
            return getattr(asyncio, name)

        def create_task(self, coro):
            nonlocal scheduled
            scheduled += 1
            coro.close()
            return DummyTask()

    monkeypatch.setattr(scenario_router, "asyncio", ScenarioAsyncioProxy())
    monkeypatch.setattr(scenario_router, "_register_background_task", lambda task, label: "task")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s2/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"s2-refs-{stop_step}-{uuid.uuid4()}",
            },
            json={
                "brand_package": {"brand_name": "Fixture"},
                "enable_media_synthesis": True,
                "artifact_disposition": "pending_review",
                "provider_max_retries": 0,
                "media_stop_step": stop_step,
                "media_refs": refs,
            },
        )

    assert response.status_code == 200, response.text
    label = response.json()["label"]
    state = await PipelineStateManager().load(label)
    assert state is not None
    assert state["current_step"] == stop_step
    assert state["config"]["effective_generation_execution_profile"]["refs_only"] is True
    assert state["config"]["provider_job_caps"] == {}
    assert state["steps"]["seedance_clips"]["status"] == "done"
    assert state["steps"]["seedance_clips"]["output"]["refs_only"] is True
    if stop_step == "audit":
        assert state["steps"]["assemble_final"]["status"] == "done"
        assert state["steps"]["assemble_final"]["output"]["refs_only"] is True
    assert scheduled == 1

    from src.services.submission_idempotency import (
        shutdown_submission_idempotency_service_if_initialized,
    )

    await shutdown_submission_idempotency_service_if_initialized()


@pytest.mark.asyncio
async def test_unified_s2_cross_tenant_refs_fail_before_first_state_save(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app

    saves = 0
    original_save = PipelineStateManager.save

    async def counted_save(self, label, state):
        nonlocal saves
        saves += 1
        await original_save(self, label, state)

    monkeypatch.setattr(PipelineStateManager, "save", counted_save)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s2/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"s2-cross-tenant-refs-{uuid.uuid4()}",
            },
            json={
                "brand_package": {"brand_name": "Fixture"},
                "enable_media_synthesis": True,
                "artifact_disposition": "pending_review",
                "provider_max_retries": 0,
                "media_stop_step": "assemble_final",
                "media_refs": {
                    "clip_paths": ["/tmp/tenants/other-tenant/pending_review/ref/clip.mp4"],
                    "audio_paths": ["/tmp/tenants/default/pending_review/ref/audio.mp3"],
                    "thumbnail_image_paths": ["/tmp/tenants/default/pending_review/ref/thumb.png"],
                },
            },
        )

    assert response.status_code == 422, response.text
    assert saves == 0


@pytest.mark.asyncio
async def test_unified_background_exception_persists_terminal_failure_state(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    import asyncio

    from src.api import app
    from src.pipeline.step_runner import StepRunner

    async def fail_background(self, label):
        del self, label
        raise RuntimeError("fixture background failure")

    monkeypatch.setattr(StepRunner, "resume", fail_background)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s3/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"s3-background-failure-{uuid.uuid4()}",
            },
            json={"video_url": "", "product": {"name": "Fixture"}},
        )
        assert response.status_code == 200, response.text
        label = response.json()["label"]

        state = None
        for _ in range(20):
            await asyncio.sleep(0)
            state = await PipelineStateManager().load(label)
            if state and state.get("pipeline_degraded"):
                break

        status_response = await client.get(
            f"/scenario/s3/status/{label}",
            headers=auth_headers,
        )

    assert state is not None
    assert state["pipeline_degraded"] is True
    assert state["degraded_reason"] == "background_run_failed"
    assert state["current_step"] is None
    assert any("background_run_failed" in error for error in state["errors"])
    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    assert status["status"] == "error"
    assert status["request_succeeded"] is False
    assert status["success"] is False
    assert status["full_media_success"] is False
    assert status["publish_allowed"] is False
    assert status["delivery_accepted"] is False


@pytest.mark.asyncio
async def test_blocking_s2_cross_tenant_refs_fail_before_pipeline_init_or_provider(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    del isolated_state_dir
    from src.api import app
    from src.pipeline.step_runner import StepRunner
    from src.skills.registry import SkillRegistry

    init_calls = 0
    provider_calls = 0

    async def forbidden_init(self, **kwargs):
        nonlocal init_calls
        del self, kwargs
        init_calls += 1
        raise AssertionError("invalid refs must fail before state initialization")

    async def forbidden_provider(self, *args, **kwargs):
        nonlocal provider_calls
        del self, args, kwargs
        provider_calls += 1
        raise AssertionError("invalid refs must fail before provider execution")

    monkeypatch.setattr(StepRunner, "init_state", forbidden_init)
    monkeypatch.setattr(SkillRegistry, "execute", forbidden_provider)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/scenario/s2",
            headers=auth_headers,
            json={
                "brand_package": {"brand_name": "Fixture"},
                "enable_media_synthesis": True,
                "artifact_disposition": "pending_review",
                "provider_max_retries": 0,
                "media_stop_step": "assemble_final",
                "media_refs": {
                    "clip_paths": ["/tmp/tenants/other-tenant/pending_review/ref/clip.mp4"],
                    "audio_paths": ["/tmp/tenants/default/pending_review/ref/audio.mp3"],
                    "thumbnail_image_paths": ["/tmp/tenants/default/pending_review/ref/thumb.png"],
                },
            },
        )

    assert response.status_code == 422, response.text
    assert init_calls == 0
    assert provider_calls == 0


def test_s2_scope_rejects_other_tenant_pre_scoped_renderer_output_without_mutation() -> None:
    from copy import deepcopy

    from src.pipeline.s2_brand_pipeline_v2 import S2BrandCampaignPipeline

    state = {
        "tenant_id": "default",
        "config": {"tenant_id": "default"},
        "steps": {
            "assemble_final": {
                "status": "done",
                "output": {
                    "video_path": ("/tmp/tenants/other-tenant/pending_review/run/assemble/final.mp4"),
                    "render_json_path": ("/tmp/tenants/default/pending_review/run/assemble/render.json"),
                },
            }
        },
    }
    before = deepcopy(state)

    with pytest.raises(ValueError):
        S2BrandCampaignPipeline()._scope_refs_only_assemble_output(
            final_state=state,
            label="run",
            artifact_disposition="pending_review",
        )

    assert state == before
