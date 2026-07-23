"""HTTP guards for canonical async submit idempotency.

These tests keep every provider-capable boundary fake.  They first lock the
fail-before-side-effect ordering; replay/concurrency coverage is added as the
durable repository and shared service land.
"""

from __future__ import annotations

import asyncio
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def isolated_submission_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from src.services import submission_idempotency
    from src.services.submission_idempotency import SubmissionIdempotencyService
    from src.storage import db as db_module
    from src.storage.idempotency_repository import SubmissionIdempotencyRepository
    from src.tasks import fast_task_registry

    conn = sqlite3.connect(
        str(tmp_path / "router-idempotency.db"),
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row

    async def no_pool() -> None:
        return None

    monkeypatch.setattr(db_module, "_pool", None)
    monkeypatch.setattr(db_module, "_sqlite_conn", conn)
    monkeypatch.setattr(db_module, "get_pool", no_pool)
    monkeypatch.setattr(db_module, "is_pg_available", lambda: False)
    db_module._create_sqlite_tables()
    service = SubmissionIdempotencyService(
        SubmissionIdempotencyRepository(require_postgres=False),
        instance_id=f"router-test-{uuid.uuid4().hex}",
    )
    monkeypatch.setattr(
        submission_idempotency,
        "get_submission_idempotency_service",
        lambda: service,
    )
    fast_task_registry._fast_tasks.clear()

    yield service

    await service.shutdown()
    fast_task_registry._fast_tasks.clear()
    conn.close()


async def _wait_for_submission_status(
    service: Any,
    *,
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    expected: set[str],
) -> dict[str, Any]:
    for _ in range(100):
        snapshot = await service.readback_by_resource(
            tenant_id=tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if snapshot["status"] in expected:
            return snapshot
        await asyncio.sleep(0.01)
    raise AssertionError(f"submission did not reach {sorted(expected)}")


@pytest.mark.asyncio
async def test_fast_submit_w5_private_binding_consumes_activation_and_injects_plan_cap(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
    tmp_path: Path,
) -> None:
    from src.api import app
    from src.pipeline.generation_policy import EffectiveGenerationPolicy
    from src.pipeline.w5_acceptance_harness import build_w5_plan_draft
    from src.pipeline.w5_fast_activation import (
        W5_FAST_AUTHORIZATION_STATEMENT,
        W5FastActivationRecordV1,
    )
    from src.pipeline.w5_fast_runtime import build_w5_fast_runtime_binding
    from src.routers._state import FastModeRequest
    from src.services import fast_mode
    from src.services.submission_idempotency import hash_idempotency_key
    from src.storage import db as db_module

    now = datetime.now(UTC)
    raw_key = f"w5-fast-runtime-{uuid.uuid4()}"
    payload = {
        "user_prompt": "Create a claim-safe Momcozy sterilizer product video.",
        "duration": 15,
        "enable_tts": False,
        "api_keys": {},
        "enable_media_synthesis": True,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }
    request = FastModeRequest.model_validate(payload)
    policy = EffectiveGenerationPolicy(
        tenant_id="default",
        scenario="fast",
        enable_media_synthesis=True,
        artifact_disposition="pending_review",
        provider_max_retries=0,
        c2pa_signing_mode="local_draft",
    )
    plan = build_w5_plan_draft(
        scenario="fast",
        tenant_id="default",
        sample_ref="sample:fast:momcozy-sterilizer-001",
        budget_limit_usd_nanos=3_150_000_000,
        provider_job_caps={"llm": 1, "video": 1},
        selected_optional_media=(),
        created_at=now - timedelta(minutes=5),
        expires_at=now + timedelta(hours=2),
    )
    activation = W5FastActivationRecordV1(
        activation_id="w5fastact:http-fixture-001",
        plan_id=plan.plan_id,
        tenant_id=plan.tenant_id,
        sample_ref=plan.sample_ref,
        approved_by="reviewer:ll",
        approved_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
        authorization_statement=W5_FAST_AUTHORIZATION_STATEMENT,
        budget_limit_usd_nanos=plan.budget_limit_usd_nanos,
        provider_job_caps=plan.provider_job_caps,
    )
    binding = build_w5_fast_runtime_binding(
        plan=plan,
        activation=activation,
        validated_request=request,
        effective_policy=policy,
        idempotency_key_sha256=hash_idempotency_key(raw_key),
        now=now,
    )
    plan_path = tmp_path / "w5-plan.json"
    activation_path = tmp_path / "w5-activation.json"
    binding_path = tmp_path / "w5-binding.json"
    plan_path.write_text(plan.model_dump_json())
    activation_path.write_text(activation.model_dump_json())
    binding_path.write_text(binding.model_dump_json())
    monkeypatch.setenv("W5_FAST_PLAN_PATH", str(plan_path))
    monkeypatch.setenv("W5_FAST_ACTIVATION_PATH", str(activation_path))
    monkeypatch.setenv("W5_FAST_RUNTIME_BINDING_PATH", str(binding_path))
    monkeypatch.setenv("POYO_VIDEO_MODEL", "seedance-2")

    class FakeFastService:
        async def generate(self, **_kwargs: Any) -> dict[str, Any]:
            return {
                "status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
            }

    monkeypatch.setattr(
        fast_mode,
        "get_fast_mode_service",
        lambda: FakeFastService(),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers={**auth_headers, "Idempotency-Key": raw_key},
            json=payload,
        )

    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]
    await _wait_for_submission_status(
        isolated_submission_service,
        tenant_id="default",
        resource_type="fast",
        resource_id=task_id,
        expected={"completed"},
    )
    connection = db_module.get_sqlite_conn()
    assert connection is not None
    submission = connection.execute(
        "SELECT trusted_authorization_ref FROM idempotency_records "
        "WHERE tenant_id = ? AND key_hash = ?",
        ("default", hash_idempotency_key(raw_key)),
    ).fetchone()
    account = connection.execute(
        "SELECT cap_usd_nanos, budget_source_kind, budget_source_ref "
        "FROM job_budget_accounts WHERE tenant_id = ? AND job_id = ?",
        ("default", task_id),
    ).fetchone()
    assert submission["trusted_authorization_ref"] == activation.activation_id
    assert tuple(account) == (
        3_150_000_000,
        "validated_authorization",
        activation.activation_id,
    )

    for name in (
        "W5_FAST_PLAN_PATH",
        "W5_FAST_ACTIVATION_PATH",
        "W5_FAST_RUNTIME_BINDING_PATH",
    ):
        monkeypatch.delenv(name, raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        replay_without_packet = await client.post(
            "/fast/submit",
            headers={**auth_headers, "Idempotency-Key": raw_key},
            json=payload,
        )
    assert replay_without_packet.status_code == 200
    assert replay_without_packet.json()["task_id"] == task_id
    assert replay_without_packet.json()["idempotent_replay"] is True

    for name, path in (
        ("W5_FAST_PLAN_PATH", plan_path),
        ("W5_FAST_ACTIVATION_PATH", activation_path),
        ("W5_FAST_RUNTIME_BINDING_PATH", binding_path),
    ):
        monkeypatch.setenv(name, str(path))
    activation_path.write_text("{}")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        replay_after_rotation = await client.post(
            "/fast/submit",
            headers={**auth_headers, "Idempotency-Key": raw_key},
            json=payload,
        )
    assert replay_after_rotation.status_code == 200
    assert replay_after_rotation.json()["task_id"] == task_id
    assert replay_after_rotation.json()["idempotent_replay"] is True


@pytest.mark.asyncio
async def test_fast_submit_w5_llm_runtime_drift_fails_before_claim(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from types import SimpleNamespace

    from src.api import app
    from src.routers import scenario
    from src.services import fast_mode, submission_idempotency
    from src.services.submission_idempotency import SubmissionNotFound

    class FakeIdempotency:
        claim_calls = 0

        async def replay_submission(self, **_kwargs: Any) -> Any:
            raise SubmissionNotFound()

        async def claim_submission(self, **_kwargs: Any) -> Any:
            self.claim_calls += 1
            raise AssertionError("runtime drift must fail before claim")

    fake_idempotency = FakeIdempotency()
    fake_authority = SimpleNamespace(
        plan=SimpleNamespace(),
        activation=SimpleNamespace(activation_id="w5fastact:drift-fixture"),
        binding=SimpleNamespace(
            expected_llm_provider="deepseek",
            expected_llm_model="deepseek-v4-flash",
            expected_video_provider="poyo",
            expected_video_model="seedance-2",
            expected_video_resolution="720p",
        ),
        budget_authorization=SimpleNamespace(),
    )
    monkeypatch.setattr(
        submission_idempotency,
        "get_submission_idempotency_service",
        lambda: fake_idempotency,
    )
    monkeypatch.setattr(
        scenario,
        "configured_w5_fast_runtime_paths",
        lambda: (Path("plan"), Path("activation"), Path("binding")),
    )
    monkeypatch.setattr(
        scenario,
        "load_w5_fast_runtime_authority",
        lambda **_kwargs: fake_authority,
    )
    monkeypatch.setattr(
        scenario,
        "DEFAULT_LLM_PROVIDER",
        "openai",
        raising=False,
    )
    service_lookups = 0

    def forbidden_service_lookup() -> object:
        nonlocal service_lookups
        service_lookups += 1
        raise AssertionError("generation service must not be resolved")

    monkeypatch.setattr(
        fast_mode,
        "get_fast_mode_service",
        forbidden_service_lookup,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"w5-drift-{uuid.uuid4()}",
            },
            json={
                "user_prompt": "fixture",
                "duration": 15,
                "enable_tts": False,
                "enable_media_synthesis": True,
                "artifact_disposition": "pending_review",
                "provider_max_retries": 0,
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "w5_fast_binding_mismatch"
    }
    assert fake_idempotency.claim_calls == 0
    assert service_lookups == 0


@pytest.mark.asyncio
async def test_fast_submit_partial_w5_private_configuration_fails_before_claim(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
    tmp_path: Path,
) -> None:
    from src.api import app
    from src.services import fast_mode
    from src.storage import db as db_module

    del isolated_submission_service
    service_lookups = 0

    def forbidden_service_lookup() -> object:
        nonlocal service_lookups
        service_lookups += 1
        raise AssertionError("generation service must not be resolved")

    monkeypatch.setattr(
        fast_mode,
        "get_fast_mode_service",
        forbidden_service_lookup,
    )
    monkeypatch.setenv("W5_FAST_PLAN_PATH", str(tmp_path / "plan.json"))
    monkeypatch.delenv("W5_FAST_ACTIVATION_PATH", raising=False)
    monkeypatch.delenv("W5_FAST_RUNTIME_BINDING_PATH", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"w5-partial-{uuid.uuid4()}",
            },
            json={
                "user_prompt": "fixture",
                "duration": 15,
                "enable_tts": False,
                "enable_media_synthesis": True,
            },
        )

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == {
        "code": "w5_fast_binding_unavailable"
    }
    assert service_lookups == 0
    connection = db_module.get_sqlite_conn()
    assert connection is not None
    assert (
        connection.execute("SELECT COUNT(*) FROM idempotency_records")
        .fetchone()[0]
        == 0
    )


@pytest.mark.asyncio
async def test_fast_submit_requires_idempotency_header_before_service_lookup(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.services import fast_mode

    generate_calls = 0

    class FakeFastService:
        async def generate(self, **_kwargs: Any) -> dict[str, Any]:
            nonlocal generate_calls
            generate_calls += 1
            return {"status": "completed_bounded", "success": False}

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", lambda: FakeFastService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers=auth_headers,
            json={"user_prompt": "fixture", "duration": 10, "enable_tts": False},
        )
        await asyncio.sleep(0)

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "idempotency_key_required"
    assert generate_calls == 0


@pytest.mark.asyncio
async def test_fast_submit_validates_missing_idempotency_header_before_invalid_body(
    auth_headers: dict[str, str],
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers=auth_headers,
            json={},
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "idempotency_key_required"


@pytest.mark.asyncio
async def test_fast_submit_validation_error_never_echoes_body_keys_or_credentials(
    auth_headers: dict[str, str],
) -> None:
    from src.api import app

    provider_fixture = "provider-credential-must-not-echo"
    body_key_fixture = "body-action-key-must-not-echo"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"header-safe-{uuid.uuid4()}",
            },
            json={
                "user_prompt": "fixture",
                "idempotency_key": body_key_fixture,
                "api_keys": {"poyo": provider_fixture},
            },
        )

    assert response.status_code == 422, response.text
    assert provider_fixture not in response.text
    assert body_key_fixture not in response.text
    assert all(set(error) <= {"type", "loc", "msg"} for error in response.json()["detail"])


@pytest.mark.asyncio
async def test_scenario_submit_validation_error_never_echoes_credentials(
    auth_headers: dict[str, str],
) -> None:
    from src.api import app

    provider_fixture = "scenario-provider-credential-must-not-echo"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/scenario/s1/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"header-safe-{uuid.uuid4()}",
            },
            json={"api_keys": {"poyo": provider_fixture}},
        )

    assert response.status_code == 422, response.text
    assert provider_fixture not in response.text
    assert all(set(error) <= {"type", "loc", "msg"} for error in response.json()["detail"])


@pytest.mark.asyncio
async def test_scenario_submit_rejects_top_level_array_without_echoing_credentials(
    auth_headers: dict[str, str],
) -> None:
    from src.api import app

    provider_fixture = "array-provider-credential-must-not-echo"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/scenario/s1/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"header-safe-{uuid.uuid4()}",
            },
            json=[{"api_keys": {"poyo": provider_fixture}}],
        )

    assert response.status_code == 422, response.text
    assert provider_fixture not in response.text
    assert response.json()["detail"] == [
        {
            "type": "dict_type",
            "loc": ["body"],
            "msg": "Input should be a valid object",
        }
    ]


@pytest.mark.asyncio
async def test_initial_owner_cas_miss_replays_current_recovery_state_without_work(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.services import fast_mode, submission_idempotency
    from src.services.submission_idempotency import SubmissionClaim

    records: dict[str, dict[str, Any]] = {}
    service_lookups = 0

    class LostInitialOwnerService:
        async def replay_submission(self, **_kwargs: Any) -> None:
            from src.services.submission_idempotency import SubmissionNotFound

            raise SubmissionNotFound()

        async def claim_submission(self, **kwargs: Any) -> SubmissionClaim:
            records[kwargs["raw_key"]] = {
                "resource_type": kwargs["resource_type"],
                "resource_id": kwargs["resource_id"],
                "scenario": kwargs["scenario"],
                "submit_response": {
                    **kwargs["response_body"],
                    "status": "recovery_required",
                },
            }
            return SubmissionClaim(
                outcome="owner",
                record={
                    "id": f"record-{len(records)}",
                    "response_body": kwargs["response_body"],
                },
            )

        async def transition(self, **_kwargs: Any) -> None:
            return None

        async def readback(self, *, tenant_id: str, raw_key: str) -> dict[str, Any]:
            del tenant_id
            return {
                **records[raw_key],
                "status": "recovery_required",
            }

        def start_heartbeat(self, **_kwargs: Any) -> None:
            raise AssertionError("heartbeat must not start after owner CAS miss")

    def forbidden_fast_service_lookup() -> object:
        nonlocal service_lookups
        service_lookups += 1
        raise AssertionError("generation service must not be constructed")

    service = LostInitialOwnerService()
    monkeypatch.setattr(
        submission_idempotency,
        "get_submission_idempotency_service",
        lambda: service,
    )
    monkeypatch.setattr(fast_mode, "get_fast_mode_service", forbidden_fast_service_lookup)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        fast_response = await client.post(
            "/fast/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"lost-fast-{uuid.uuid4()}",
            },
            json={"user_prompt": "fixture", "duration": 10, "enable_tts": False},
        )
        scenario_response = await client.post(
            "/scenario/s4/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"lost-scenario-{uuid.uuid4()}",
            },
            json={"product_info": {"name": "fixture"}},
        )

    assert fast_response.status_code == 200, fast_response.text
    assert scenario_response.status_code == 200, scenario_response.text
    assert fast_response.json()["status"] == "recovery_required"
    assert scenario_response.json()["status"] == "recovery_required"
    assert fast_response.json()["idempotent_replay"] is True
    assert scenario_response.json()["idempotent_replay"] is True
    assert service_lookups == 0


@pytest.mark.asyncio
async def test_fast_stage_cas_miss_immediately_signals_owner_loss() -> None:
    from src.routers import scenario

    owner_loss_signals = 0

    class StaleStageService:
        async def transition(self, **_kwargs: Any) -> None:
            return None

    async def on_owner_lost() -> None:
        nonlocal owner_loss_signals
        owner_loss_signals += 1

    persisted = await scenario._persist_fast_submission_stage(
        StaleStageService(),
        tenant_id="tenant-a",
        record_id="record-a",
        stage="video",
        on_owner_lost=on_owner_lost,
    )

    assert persisted is False
    assert owner_loss_signals == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "idempotency_key",
    [
        "too-short",
        "contains whitespace",
        "x" * 129,
    ],
)
async def test_fast_submit_rejects_invalid_idempotency_header_before_service_lookup(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    idempotency_key: str,
) -> None:
    from src.api import app
    from src.services import fast_mode

    service_lookups = 0

    def fake_service_lookup() -> object:
        nonlocal service_lookups
        service_lookups += 1
        raise AssertionError("service lookup must not run for an invalid key")

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", fake_service_lookup)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers={**auth_headers, "Idempotency-Key": idempotency_key},
            json={"user_prompt": "fixture", "duration": 10, "enable_tts": False},
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "idempotency_key_invalid"
    assert service_lookups == 0


@pytest.mark.asyncio
async def test_fast_submit_rejects_duplicate_idempotency_header(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.services import fast_mode

    service_lookups = 0

    def fake_service_lookup() -> object:
        nonlocal service_lookups
        service_lookups += 1
        raise AssertionError("service lookup must not run for duplicate keys")

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", fake_service_lookup)
    headers = list(auth_headers.items()) + [
        ("Idempotency-Key", "duplicate-fixture-key-0001"),
        ("Idempotency-Key", "duplicate-fixture-key-0002"),
    ]

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers=headers,
            json={"user_prompt": "fixture", "duration": 10, "enable_tts": False},
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "idempotency_key_invalid"
    assert service_lookups == 0


@pytest.mark.asyncio
async def test_fast_submit_replays_one_durable_job_and_conflicts_changed_payload(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
) -> None:
    from src.api import app
    from src.services import fast_mode
    from src.tasks import fast_task_registry

    generate_calls = 0
    generate_started = asyncio.Event()
    release_generate = asyncio.Event()

    class FakeFastService:
        async def generate(self, **_kwargs: Any) -> dict[str, Any]:
            nonlocal generate_calls
            generate_calls += 1
            generate_started.set()
            await release_generate.wait()
            return {
                "status": "completed_bounded",
                "lifecycle_status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
                "video_path": "",
                "video_url": "",
                "filename": "fixture.mp4",
                "duration_seconds": 10,
                "file_size_bytes": 0,
                "generation_time_ms": 1,
                "timing": {"llm_ms": 1, "video_ms": 0, "tts_ms": 0},
                "model_info": {"llm": "fake", "video": "fake", "tts": None},
                "is_stub": True,
                "tts_path": None,
            }

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", lambda: FakeFastService())
    key = f"fast-replay-{uuid.uuid4()}"
    headers = {**auth_headers, "Idempotency-Key": key}
    payload = {"user_prompt": "fixture", "duration": 10, "enable_tts": False}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post("/fast/submit", headers=headers, json=payload)
        await asyncio.wait_for(generate_started.wait(), timeout=2)
        replay = await client.post("/fast/submit", headers=headers, json=payload)
        conflict = await client.post(
            "/fast/submit",
            headers=headers,
            json={**payload, "user_prompt": "changed fixture"},
        )

        assert first.status_code == 200, first.text
        assert replay.status_code == 200, replay.text
        assert conflict.status_code == 409, conflict.text
        first_body = first.json()
        replay_body = replay.json()
        assert replay_body["task_id"] == first_body["task_id"]
        assert first_body["idempotent_replay"] is False
        assert replay_body["idempotent_replay"] is True
        assert "account_id" not in repr(first_body).lower()
        assert "usd_nanos" not in repr(first_body).lower()
        assert conflict.json()["detail"]["code"] == "idempotency_payload_conflict"
        assert generate_calls == 1

        from src.storage import db as db_module

        connection = db_module.get_sqlite_conn()
        assert connection is not None
        account_rows = (
            connection.execute(
                "SELECT tenant_id, job_kind, job_id FROM job_budget_accounts "
                "WHERE tenant_id = ? AND job_kind = ? AND job_id = ?",
                ("default", "canonical", first_body["task_id"]),
            )
            .fetchall()
        )
        assert [tuple(row) for row in account_rows] == [("default", "canonical", first_body["task_id"])]

        release_generate.set()
        durable = await _wait_for_submission_status(
            isolated_submission_service,
            tenant_id="default",
            resource_type="fast",
            resource_id=first_body["task_id"],
            expected={"completed"},
        )
        assert durable["result_snapshot"]["status"] == "completed_bounded"

        fast_task_registry._fast_tasks.clear()
        restarted_status = await client.get(
            f"/fast/status/{first_body['task_id']}",
            headers=auth_headers,
        )

    assert restarted_status.status_code == 200, restarted_status.text
    restarted = restarted_status.json()
    assert restarted["status"] == "done"
    assert restarted["lifecycle_status"] == "completed_bounded"
    assert restarted["result"]["status"] == "completed_bounded"
    assert generate_calls == 1


@pytest.mark.asyncio
async def test_fast_submit_two_concurrent_http_posts_create_one_task(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
) -> None:
    from src.api import app
    from src.services import fast_mode

    generate_calls = 0
    generate_started = asyncio.Event()
    release_generate = asyncio.Event()

    class FakeFastService:
        async def generate(self, **_kwargs: Any) -> dict[str, Any]:
            nonlocal generate_calls
            generate_calls += 1
            generate_started.set()
            await release_generate.wait()
            return {
                "status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
            }

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", lambda: FakeFastService())
    headers = {
        **auth_headers,
        "Idempotency-Key": f"fast-concurrent-http-{uuid.uuid4()}",
    }
    payload = {"user_prompt": "fixture", "duration": 10, "enable_tts": False}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first, second = await asyncio.gather(
            client.post("/fast/submit", headers=headers, json=payload),
            client.post("/fast/submit", headers=headers, json=payload),
        )
        await asyncio.wait_for(generate_started.wait(), timeout=2)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["task_id"] == second.json()["task_id"]
        assert sorted([first.json()["idempotent_replay"], second.json()["idempotent_replay"]]) == [False, True]
        assert generate_calls == 1

        release_generate.set()
        durable = await _wait_for_submission_status(
            isolated_submission_service,
            tenant_id="default",
            resource_type="fast",
            resource_id=first.json()["task_id"],
            expected={"completed"},
        )

    assert durable["status"] == "completed"
    assert generate_calls == 1


@pytest.mark.asyncio
async def test_fast_submit_store_unavailable_fails_before_service_lookup(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.services import fast_mode, submission_idempotency
    from src.services.submission_idempotency import IdempotencyStoreUnavailable

    service_lookups = 0

    class UnavailableIdempotencyService:
        async def replay_submission(self, **_kwargs: Any) -> None:
            raise IdempotencyStoreUnavailable()

        async def claim_submission(self, **_kwargs: Any) -> None:
            raise IdempotencyStoreUnavailable()

    def fake_fast_service_lookup() -> object:
        nonlocal service_lookups
        service_lookups += 1
        raise AssertionError("generation service must not be resolved")

    monkeypatch.setattr(
        submission_idempotency,
        "get_submission_idempotency_service",
        lambda: UnavailableIdempotencyService(),
    )
    monkeypatch.setattr(fast_mode, "get_fast_mode_service", fake_fast_service_lookup)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/fast/submit",
            headers={
                **auth_headers,
                "Idempotency-Key": f"store-unavailable-{uuid.uuid4()}",
            },
            json={"user_prompt": "fixture", "duration": 10, "enable_tts": False},
        )

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "idempotency_store_unavailable"
    assert service_lookups == 0


@pytest.mark.asyncio
async def test_same_raw_key_is_independent_and_hidden_across_tenants(
    monkeypatch: pytest.MonkeyPatch,
    isolated_submission_service: Any,
) -> None:
    from src.api import app
    from src.routers import _deps, submissions
    from src.routers._deps import ApiKeyType, AuthContext
    from src.services import fast_mode

    generate_calls = 0

    class FakeFastService:
        async def generate(self, **_kwargs: Any) -> dict[str, Any]:
            nonlocal generate_calls
            generate_calls += 1
            return {
                "status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
            }

    async def fake_auth(request: Request) -> AuthContext:
        tenant_id = request.headers.get("X-Test-Tenant", "tenant-a")
        context = AuthContext(
            tenant_id=tenant_id,
            permissions=frozenset({"provider:submit"}),
            key_type=ApiKeyType.TENANT,
            key_id=f"{tenant_id}-key",
        )
        _deps._bind_auth_context(context)
        return context

    monkeypatch.setattr(fast_mode, "get_fast_mode_service", lambda: FakeFastService())
    monkeypatch.setattr(
        submissions,
        "get_submission_idempotency_service",
        lambda: isolated_submission_service,
    )
    app.dependency_overrides[_deps.verify_api_key] = fake_auth
    raw_key = f"cross-tenant-{uuid.uuid4()}"
    payload = {"user_prompt": "fixture", "duration": 10, "enable_tts": False}

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            tenant_a = await client.post(
                "/fast/submit",
                headers={
                    "X-API-Key": "fixture",
                    "X-Test-Tenant": "tenant-a",
                    "Idempotency-Key": raw_key,
                },
                json=payload,
            )
            hidden = await client.get(
                "/submissions/idempotency",
                headers={
                    "X-API-Key": "fixture",
                    "X-Test-Tenant": "tenant-b",
                    "Idempotency-Key": raw_key,
                },
            )
            tenant_b = await client.post(
                "/fast/submit",
                headers={
                    "X-API-Key": "fixture",
                    "X-Test-Tenant": "tenant-b",
                    "Idempotency-Key": raw_key,
                },
                json=payload,
            )
    finally:
        app.dependency_overrides.pop(_deps.verify_api_key, None)

    assert tenant_a.status_code == 200, tenant_a.text
    assert hidden.status_code == 404, hidden.text
    assert hidden.json()["detail"]["code"] == "submission_not_found"
    assert tenant_b.status_code == 200, tenant_b.text
    assert tenant_a.json()["task_id"] != tenant_b.json()["task_id"]

    await _wait_for_submission_status(
        isolated_submission_service,
        tenant_id="tenant-a",
        resource_type="fast",
        resource_id=tenant_a.json()["task_id"],
        expected={"completed"},
    )
    await _wait_for_submission_status(
        isolated_submission_service,
        tenant_id="tenant-b",
        resource_type="fast",
        resource_id=tenant_b.json()["task_id"],
        expected={"completed"},
    )
    assert generate_calls == 2


@pytest.mark.asyncio
async def test_fast_status_reconciles_expired_restart_to_recovery_required(
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
) -> None:
    from src.api import app
    from src.storage import db as db_module

    resource_id = f"fast_restart_{uuid.uuid4().hex}"
    claim = await isolated_submission_service.claim_submission(
        tenant_id="default",
        raw_key=f"restart-recovery-{uuid.uuid4()}",
        validated_request={"user_prompt": "fixture", "duration": 10},
        effective_policy={
            "version": "generation-safety.v1",
            "tenant_id": "default",
            "scenario": "fast",
            "provider_submit_allowed": True,
            "enable_media_synthesis": False,
            "artifact_disposition": "pending_review",
            "provider_max_retries": 0,
        },
        operation="fast.submit",
        scenario="fast",
        resource_type="fast",
        resource_id=resource_id,
        response_body={
            "task_id": resource_id,
            "status": "running",
            "started_at_unix": 1,
        },
    )
    conn = db_module.get_sqlite_conn()
    assert conn is not None
    conn.execute(
        "UPDATE idempotency_records "
        "SET record_status = 'running', lease_expires_at = datetime('now', '-1 second') "
        "WHERE id = ?",
        (claim.record["id"],),
    )
    conn.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/fast/status/{resource_id}",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["task_id"] == resource_id
    assert snapshot["status"] == "recovery_required"
    assert snapshot["stage"] == "recovery_required"
    assert snapshot["result"] is None


@pytest.mark.asyncio
async def test_scenario_status_uses_durable_recovery_when_worker_state_is_absent(
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
) -> None:
    from src.api import app
    from src.storage import db as db_module

    label = f"s4_{uuid.uuid4().hex}"
    claim = await isolated_submission_service.claim_submission(
        tenant_id="default",
        raw_key=f"scenario-restart-{uuid.uuid4()}",
        validated_request={"topic": "fixture"},
        effective_policy={
            "version": "generation-safety.v1",
            "tenant_id": "default",
            "scenario": "s4",
            "provider_submit_allowed": True,
            "enable_media_synthesis": False,
            "artifact_disposition": "pending_review",
            "provider_max_retries": 0,
        },
        operation="scenario.submit",
        scenario="s4",
        resource_type="scenario",
        resource_id=label,
        response_body={"label": label, "status": "running", "trace_id": "fixture"},
    )
    conn = db_module.get_sqlite_conn()
    assert conn is not None
    conn.execute(
        "UPDATE idempotency_records "
        "SET record_status = 'running', lease_expires_at = datetime('now', '-1 second') "
        "WHERE id = ?",
        (claim.record["id"],),
    )
    conn.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            f"/scenario/s4/status/{label}",
            headers=auth_headers,
        )

    assert response.status_code == 200, response.text
    snapshot = response.json()
    assert snapshot["label"] == label
    assert snapshot["scenario"] == "s4"
    assert snapshot["status"] == "recovery_required"
    assert snapshot["errors"] == ["submission_owner_lost"]


@pytest.mark.asyncio
async def test_s1_concurrent_replay_claims_before_translation_and_schedules_once(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
) -> None:
    from src.api import app
    from src.pipeline import state_manager, step_runner
    from src.routers import scenario as scenario_router
    from src.tools import translate

    translation_calls = 0
    init_calls = 0
    resume_calls = 0
    scheduled_calls = 0
    translation_started = asyncio.Event()
    release_translation = asyncio.Event()

    async def fake_translate(value: dict[str, Any]) -> dict[str, Any]:
        nonlocal translation_calls
        translation_calls += 1
        translation_started.set()
        await release_translation.wait()
        return value

    class FakeStateManager:
        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    class FakeStepRunner:
        def __init__(self, manager: object) -> None:
            self.state_manager = manager

        async def init_state(
            self,
            *,
            config: dict[str, Any],
            mode: str,
            scenario: str,
            label: str | None = None,
        ) -> str:
            del config, mode, scenario
            nonlocal init_calls
            init_calls += 1
            assert label is not None
            return label

        async def resume(self, label: str) -> dict[str, Any]:
            nonlocal resume_calls
            resume_calls += 1
            return {
                "label": label,
                "scenario": "s1",
                "status": "completed_bounded",
                "lifecycle_status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
                "pipeline_degraded": False,
                "current_step": None,
                "trace_id": "trace-fixture",
            }
        async def finalize_pipeline_completion(self, state: dict[str, Any], *, started_at: float) -> bool: return True
    original_register = scenario_router._register_background_task

    def counted_register(task: asyncio.Task[Any], label: str) -> str:
        nonlocal scheduled_calls
        scheduled_calls += 1
        return original_register(task, label)

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate)
    monkeypatch.setattr(state_manager, "PipelineStateManager", FakeStateManager)
    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)
    monkeypatch.setattr(scenario_router, "_register_background_task", counted_register)

    key = f"scenario-replay-{uuid.uuid4()}"
    headers = {**auth_headers, "Idempotency-Key": key}
    payload = {
        "product_catalog": {"name": "fixture"},
        "enable_media_synthesis": True,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first_request = asyncio.create_task(client.post("/scenario/s1/submit", headers=headers, json=payload))
        await asyncio.wait_for(translation_started.wait(), timeout=2)
        replay = await client.post("/scenario/s1/submit", headers=headers, json=payload)
        conflict = await client.post(
            "/scenario/s1/submit",
            headers=headers,
            json={**payload, "product_catalog": {"name": "changed"}},
        )
        release_translation.set()
        first = await first_request

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert conflict.status_code == 409, conflict.text
    assert first.json()["label"] == replay.json()["label"]
    assert first.json()["idempotent_replay"] is False
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["status"] == "initializing"
    assert "account_id" not in repr(first.json()).lower()
    assert "usd_nanos" not in repr(first.json()).lower()
    assert conflict.json()["detail"]["code"] == "idempotency_payload_conflict"

    from src.storage import db as db_module

    connection = db_module.get_sqlite_conn()
    assert connection is not None
    account_rows = (
        connection.execute(
            "SELECT tenant_id, job_kind, job_id FROM job_budget_accounts "
            "WHERE tenant_id = ? AND job_kind = ? AND job_id = ?",
            ("default", "canonical", first.json()["label"]),
        )
        .fetchall()
    )
    assert [tuple(row) for row in account_rows] == [("default", "canonical", first.json()["label"])]

    durable = await _wait_for_submission_status(
        isolated_submission_service,
        tenant_id="default",
        resource_type="scenario",
        resource_id=first.json()["label"],
        expected={"completed"},
    )
    assert durable["result_snapshot"]["status"] == "completed_bounded"
    assert translation_calls == 1
    assert init_calls == 1
    assert resume_calls == 1
    assert scheduled_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "payload", "changed_payload"),
    [
        (
            "s2",
            {"brand_package": {"brand_name": "Fixture"}},
            {"brand_package": {"brand_name": "Changed"}},
        ),
        (
            "s3",
            {"video_url": "", "product": {"name": "Fixture"}},
            {"video_url": "", "product": {"name": "Changed"}},
        ),
        (
            "s4",
            {"product_info": {"name": "Fixture"}, "topic": "Original"},
            {"product_info": {"name": "Fixture"}, "topic": "Changed"},
        ),
        (
            "s5",
            {"product_sku": {"name": "Fixture"}, "story_description": "Original"},
            {"product_sku": {"name": "Fixture"}, "story_description": "Changed"},
        ),
    ],
)
async def test_s2_s5_concurrent_replay_and_changed_payload_conflict(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    isolated_submission_service: Any,
    scenario_id: str,
    payload: dict[str, Any],
    changed_payload: dict[str, Any],
) -> None:
    from src.api import app
    from src.pipeline import state_manager, step_runner
    from src.routers import scenario as scenario_router
    from src.tools import translate

    translation_calls = 0
    init_calls = 0
    resume_calls = 0
    scheduled_calls = 0
    owner_paused = asyncio.Event()
    release_owner = asyncio.Event()

    async def fake_translate(value: dict[str, Any]) -> dict[str, Any]:
        nonlocal translation_calls
        translation_calls += 1
        owner_paused.set()
        await release_owner.wait()
        return value

    class FakeStateManager:
        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    class FakeStepRunner:
        def __init__(self, manager: object) -> None:
            self.state_manager = manager

        async def init_state(
            self,
            *,
            config: dict[str, Any],
            mode: str,
            scenario: str,
            label: str | None = None,
        ) -> str:
            del config, mode
            nonlocal init_calls
            init_calls += 1
            assert scenario == scenario_id
            assert label is not None
            if scenario_id != "s3":
                owner_paused.set()
                await release_owner.wait()
            return label

        async def resume(self, label: str) -> dict[str, Any]:
            nonlocal resume_calls
            resume_calls += 1
            return {
                "label": label,
                "scenario": scenario_id,
                "status": "completed_bounded",
                "lifecycle_status": "completed_bounded",
                "request_succeeded": True,
                "success": False,
                "full_media_success": False,
                "pipeline_complete": False,
                "publish_allowed": False,
                "delivery_accepted": False,
                "pipeline_degraded": False,
            }
        async def finalize_pipeline_completion(self, state: dict[str, Any], *, started_at: float) -> bool: return True
    original_register = scenario_router._register_background_task

    def counted_register(task: asyncio.Task[Any], label: str) -> str:
        nonlocal scheduled_calls
        scheduled_calls += 1
        return original_register(task, label)

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate)
    monkeypatch.setattr(state_manager, "PipelineStateManager", FakeStateManager)
    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)
    monkeypatch.setattr(scenario_router, "_register_background_task", counted_register)

    key = f"{scenario_id}-replay-{uuid.uuid4()}"
    headers = {**auth_headers, "Idempotency-Key": key}
    safe_payload = {
        **payload,
        "enable_media_synthesis": True,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }
    safe_changed_payload = {
        **changed_payload,
        "enable_media_synthesis": True,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        owner_request = asyncio.create_task(
            client.post(
                f"/scenario/{scenario_id}/submit",
                headers=headers,
                json=safe_payload,
            )
        )
        await asyncio.wait_for(owner_paused.wait(), timeout=2)
        replay = await client.post(
            f"/scenario/{scenario_id}/submit",
            headers=headers,
            json=safe_payload,
        )
        conflict = await client.post(
            f"/scenario/{scenario_id}/submit",
            headers=headers,
            json=safe_changed_payload,
        )
        release_owner.set()
        owner = await owner_request

    assert owner.status_code == 200, owner.text
    assert replay.status_code == 200, replay.text
    assert conflict.status_code == 409, conflict.text
    assert owner.json()["label"] == replay.json()["label"]
    assert owner.json()["idempotent_replay"] is False
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["status"] == "initializing"
    assert conflict.json()["detail"]["code"] == "idempotency_payload_conflict"

    durable = await _wait_for_submission_status(
        isolated_submission_service,
        tenant_id="default",
        resource_type="scenario",
        resource_id=owner.json()["label"],
        expected={"completed"},
    )
    assert durable["result_snapshot"]["status"] == "completed_bounded"
    assert translation_calls == (1 if scenario_id == "s3" else 0)
    assert init_calls == 1
    assert resume_calls == 1
    assert scheduled_calls == 1


@pytest.mark.asyncio
async def test_s1_submit_requires_idempotency_header_before_translation_or_state(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.pipeline import state_manager, step_runner
    from src.routers import scenario as scenario_router
    from src.tools import translate

    translation_calls = 0
    init_calls = 0
    scheduled_calls = 0

    async def fake_translate(value: dict[str, Any]) -> dict[str, Any]:
        nonlocal translation_calls
        translation_calls += 1
        return value

    class FakeStateManager:
        async def save(self, _label: str, _state: dict[str, Any]) -> None:
            return None

    class FakeStepRunner:
        def __init__(self, _manager: object) -> None:
            pass

        async def init_state(
            self,
            *,
            config: dict[str, Any],
            mode: str,
            scenario: str,
            label: str | None = None,
        ) -> str:
            del config, mode, scenario
            nonlocal init_calls
            init_calls += 1
            return label or "s1_fixture_label"

        async def resume(self, _label: str) -> dict[str, Any]:
            return {}
        async def finalize_pipeline_completion(self, state: dict[str, Any], *, started_at: float) -> bool: return True
    class DummyTask:
        pass

    def fake_create_task(coro: Any) -> DummyTask:
        nonlocal scheduled_calls
        scheduled_calls += 1
        coro.close()
        return DummyTask()

    monkeypatch.setattr(translate, "translate_catalog_to_english", fake_translate)
    monkeypatch.setattr(state_manager, "PipelineStateManager", FakeStateManager)
    monkeypatch.setattr(step_runner, "StepRunner", FakeStepRunner)
    monkeypatch.setattr(scenario_router.asyncio, "create_task", fake_create_task)
    monkeypatch.setattr(
        scenario_router,
        "_register_background_task",
        lambda _task, _label: "fixture-background-task",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/scenario/s1/submit",
            headers=auth_headers,
            json={
                "product_catalog": {"name": "fixture"},
                "enable_media_synthesis": False,
                "artifact_disposition": "pending_review",
                "provider_max_retries": 0,
            },
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "idempotency_key_required"
    assert translation_calls == 0
    assert init_calls == 0
    assert scheduled_calls == 0
