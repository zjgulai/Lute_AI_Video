from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.routers._state import S1StartRequest


def _authorize_generation_route(
    monkeypatch: pytest.MonkeyPatch,
    scenario: Any,
) -> None:
    from src.routers import _deps

    monkeypatch.setattr(
        scenario,
        "get_auth_context",
        lambda: _deps.AuthContext(
            tenant_id="tenant-a",
            permissions=frozenset({"provider:submit"}),
            key_type=_deps.ApiKeyType.TENANT,
            key_id="s1-completion-route-test",
        ),
    )


def _terminal_state(label: str) -> dict[str, Any]:
    return {
        "label": label,
        "scenario": "s1",
        "config": {},
        "steps": {},
        "current_step": None,
        "status": "completed_bounded",
        "lifecycle_status": "completed_bounded",
        "completion_kind": "bounded_media",
        "request_succeeded": True,
        "success": True,
        "full_media_success": False,
        "pipeline_complete": True,
        "publish_allowed": False,
        "delivery_accepted": False,
        "pipeline_degraded": False,
        "errors": [],
        "media_synthesis_errors": [],
    }


class _FakeStateManager:
    async def save(self, label: str, state: dict[str, Any]) -> None:
        del label, state


@pytest.mark.parametrize("enable_media_synthesis", [False, True])
@pytest.mark.parametrize("entrypoint", ["blocking", "start"])
@pytest.mark.asyncio
async def test_s1_manual_terminal_routes_call_completion_finalizer(
    enable_media_synthesis: bool,
    entrypoint: str,
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    del isolated_provider_cost_db
    from src.routers import scenario
    from src.tools import translate

    completion_calls: list[dict[str, Any]] = []
    paths: list[str] = []

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            del state_manager
            self.state_manager = _FakeStateManager()

        async def init_state(
            self,
            config: dict[str, Any],
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            del config, mode, scenario
            return label or "s1_manual_completion"

        async def run_step(self, label: str, step_name: str) -> dict[str, Any]:
            del step_name
            paths.append("no_media")
            return _terminal_state(label)

        async def resume(self, label: str) -> dict[str, Any]:
            raise AssertionError(f"manual bounded path unexpectedly resumed {label}")

        async def finalize_pipeline_completion(
            self,
            state: dict[str, Any],
            *,
            started_at: float,
        ) -> bool:
            del started_at
            completion_calls.append(state)
            return True

    async def identity_catalog(value: dict[str, Any]) -> dict[str, Any]:
        return value

    async def fake_bounded_resume(
        step_runner: Any,
        label: str,
        artifact_disposition: str,
        provider_max_retries: int | None,
    ) -> dict[str, Any]:
        del step_runner, artifact_disposition, provider_max_retries
        paths.append("bounded_media")
        return _terminal_state(label)

    monkeypatch.setattr(translate, "translate_catalog_to_english", identity_catalog)
    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)
    monkeypatch.setattr(scenario, "_resume_s1_bounded_media_pilot", fake_bounded_resume)
    _authorize_generation_route(monkeypatch, scenario)
    request = S1StartRequest(
        product_catalog={"product_name": "Fixture"},
        mode="auto",
        enable_media_synthesis=enable_media_synthesis,
        artifact_disposition="pending_review",
        provider_max_retries=0,
    )

    if entrypoint == "blocking":
        await scenario.run_s1_product_direct(request)
    else:
        await scenario.start_s1_pipeline(request)

    assert paths
    assert paths[0] == ("bounded_media" if enable_media_synthesis else "no_media")
    assert len(completion_calls) == 1


@pytest.mark.parametrize("enable_media_synthesis", [False, True])
@pytest.mark.asyncio
async def test_unified_s1_submit_finalizes_no_media_and_bounded_paths(
    enable_media_synthesis: bool,
    monkeypatch: pytest.MonkeyPatch,
    isolated_provider_cost_db: Any,
) -> None:
    del isolated_provider_cost_db
    from src.routers import scenario
    from src.services import submission_idempotency
    from src.services.submission_idempotency import SubmissionClaim
    from src.tools import translate

    tasks: list[asyncio.Task[Any]] = []
    completion_calls: list[dict[str, Any]] = []

    class FakeStepRunner:
        def __init__(self, state_manager: object) -> None:
            del state_manager
            self.state_manager = _FakeStateManager()

        async def init_state(
            self,
            config: dict[str, Any],
            mode: str = "auto",
            label: str | None = None,
            scenario: str = "s1",
        ) -> str:
            del config, mode, scenario
            return label or "s1_submit_completion"

        async def run_step(self, label: str, step_name: str) -> dict[str, Any]:
            del step_name
            return _terminal_state(label)

        async def resume(self, label: str) -> dict[str, Any]:
            return _terminal_state(label)

        async def finalize_pipeline_completion(
            self,
            state: dict[str, Any],
            *,
            started_at: float,
        ) -> bool:
            del started_at
            completion_calls.append(state)
            return True

    class FakeSubmissionIdempotency:
        async def claim_submission(self, **kwargs: Any) -> SubmissionClaim:
            del kwargs
            return SubmissionClaim(outcome="owner", record={"id": "submission-fixture"})

        async def transition(self, **kwargs: Any) -> dict[str, Any]:
            return {"id": kwargs["record_id"], "record_status": kwargs["new_status"]}

        def start_heartbeat(self, **kwargs: Any) -> None:
            del kwargs

        async def mark_terminal(self, **kwargs: Any) -> dict[str, Any]:
            return {"id": kwargs["record_id"], "record_status": kwargs["status"]}

        async def stop_heartbeat(self, **kwargs: Any) -> None:
            del kwargs

    async def identity_catalog(value: dict[str, Any]) -> dict[str, Any]:
        return value

    monkeypatch.setattr(translate, "translate_catalog_to_english", identity_catalog)
    monkeypatch.setattr("src.pipeline.step_runner.StepRunner", FakeStepRunner)
    monkeypatch.setattr(
        scenario,
        "_register_background_task",
        lambda task, label: tasks.append(task),
    )
    monkeypatch.setattr(
        submission_idempotency,
        "get_submission_idempotency_service",
        lambda: FakeSubmissionIdempotency(),
    )
    _authorize_generation_route(monkeypatch, scenario)

    await scenario._submit_scenario_validated(
        "s1",
        {
            "product_catalog": {"product_name": "Fixture"},
            "enable_media_synthesis": enable_media_synthesis,
            "artifact_disposition": "pending_review",
            "provider_max_retries": 0,
        },
        f"s1-submit-completion-{enable_media_synthesis}",
    )
    await asyncio.gather(*tasks)

    assert len(completion_calls) == 1
