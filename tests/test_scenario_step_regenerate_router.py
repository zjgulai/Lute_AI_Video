from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from src.pipeline.state_manager import PipelineStateManager


async def _save_state(label: str, state: dict) -> None:
    await PipelineStateManager().save(label, state)


@pytest.mark.asyncio
async def test_execute_step_supports_s2(monkeypatch: pytest.MonkeyPatch, isolated_state_dir, auth_headers) -> None:
    from src.api import app
    from src.pipeline.step_runner import StepRunner

    label = "s2-step-router"
    await _save_state(
        label,
        {
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
        },
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
async def test_regenerate_step_s4_invalidates_continuity_downstream(
    monkeypatch: pytest.MonkeyPatch,
    isolated_state_dir,
    auth_headers,
) -> None:
    from src.api import app
    from src.pipeline.step_runner import StepRunner

    label = "s4-regen-router"
    await _save_state(
        label,
        {
            "label": label,
            "scenario": "s4",
            "current_step": "video_prompts",
            "config": {"product_name": "MomCozy Pump"},
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
                "seedance_clips": {"status": "done", "output": {"clip_paths": ["clip.mp4"]}, "edited": False, "edited_output": None},
                "tts_audio": {"status": "done", "output": ["audio.mp3"], "edited": False, "edited_output": None},
                "assemble_final": {"status": "done", "output": ["final.mp4", "render.json"], "edited": False, "edited_output": None},
                "audit": {"status": "done", "output": {"overall_status": "PASS"}, "edited": False, "edited_output": None},
            },
            "errors": [],
            "media_synthesis_errors": [],
        },
    )

    async def fake_regenerate_step(self: StepRunner, run_label: str, step_name: str) -> dict:
        assert run_label == label
        assert step_name == "scripts"
        state = await self.state_manager.load(run_label)
        assert state is not None
        state["steps"]["scripts"] = {
            "status": "done",
            "output": [{"text": "regenerated"}],
            "edited": False,
            "edited_output": None,
        }
        return state

    monkeypatch.setattr(StepRunner, "regenerate_step", fake_regenerate_step)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/scenario/s4/regenerate/{label}/scripts",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["regenerated_step"] == "scripts"
    assert payload["invalidated"][0] == "continuity_storyboard_grid"

    updated = await PipelineStateManager().load(label)
    assert updated is not None
    assert updated["current_step"] == "continuity_storyboard_grid"
    assert updated["steps"]["continuity_storyboard_grid"]["status"] == "pending"
    assert updated["steps"]["video_prompts"]["status"] == "pending"
    assert updated["steps"]["thumbnails"]["status"] == "pending"


@pytest.mark.asyncio
async def test_regenerate_step_supports_s5(monkeypatch: pytest.MonkeyPatch, isolated_state_dir, auth_headers) -> None:
    from src.api import app
    from src.pipeline.step_runner import StepRunner

    label = "s5-regen-router"
    await _save_state(
        label,
        {
            "label": label,
            "scenario": "s5",
            "current_step": "assemble_final",
            "config": {"product_name": "MomCozy Pump"},
            "steps": {
                "vlog_strategy": {"status": "done", "output": {"shots": [], "scripts": []}, "edited": False, "edited_output": None},
                "continuity_storyboard_grid": {"status": "done", "output": {"clip_groups": []}, "edited": False, "edited_output": None},
                "video_prompts": {"status": "done", "output": [{"prompt": "p1"}], "edited": False, "edited_output": None},
                "seedance_clips": {"status": "done", "output": {"clip_paths": ["clip.mp4"]}, "edited": False, "edited_output": None},
                "tts_audio": {"status": "done", "output": ["audio.mp3"], "edited": False, "edited_output": None},
                "assemble_final": {"status": "done", "output": ["final.mp4", "render.json"], "edited": False, "edited_output": None},
                "audit": {"status": "done", "output": {"overall_status": "PASS"}, "edited": False, "edited_output": None},
            },
            "errors": [],
            "media_synthesis_errors": [],
        },
    )

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
