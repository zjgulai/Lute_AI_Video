"""Pure service and readback contracts for submission idempotency.

All repositories in this module are in-memory fakes.  No provider, production
database, or mutation boundary is reachable from these tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict

VALID_KEY = "submit-action-1234567890"


class _FixtureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str
    duration: int = 10
    tags: list[str] = []
    api_keys: dict[str, str] = {}
    nested: dict[str, Any] = {}


def _policy(*, version: str = "generation-safety.v1") -> dict[str, Any]:
    return {
        "version": version,
        "tenant_id": "tenant-a",
        "scenario": "fast",
        "provider_submit_allowed": True,
        "enable_media_synthesis": False,
        "artifact_disposition": "pending_review",
        "provider_max_retries": 0,
    }


@pytest.mark.parametrize(
    ("values", "error_type", "code"),
    [
        ([], "IdempotencyKeyRequired", "idempotency_key_required"),
        (
            [VALID_KEY, VALID_KEY],
            "IdempotencyKeyInvalid",
            "idempotency_key_invalid",
        ),
        (["short"], "IdempotencyKeyInvalid", "idempotency_key_invalid"),
        (["a" * 129], "IdempotencyKeyInvalid", "idempotency_key_invalid"),
        (
            ["submit action 123456"],
            "IdempotencyKeyInvalid",
            "idempotency_key_invalid",
        ),
        (
            ["submit-action-123\n456"],
            "IdempotencyKeyInvalid",
            "idempotency_key_invalid",
        ),
    ],
)
def test_header_validation_is_single_value_and_fail_closed(values: Sequence[str], error_type: str, code: str) -> None:
    from src.services import submission_idempotency as module

    with pytest.raises(getattr(module, error_type)) as caught:
        module.validate_idempotency_key_headers(values)

    assert caught.value.code == code
    assert VALID_KEY not in str(caught.value)


def test_header_validation_accepts_the_approved_opaque_format() -> None:
    from src.services.submission_idempotency import validate_idempotency_key_headers

    assert validate_idempotency_key_headers([VALID_KEY]) == VALID_KEY
    assert validate_idempotency_key_headers(["A" * 16]) == "A" * 16
    assert validate_idempotency_key_headers(["z" * 128]) == "z" * 128


def test_fingerprint_normalizes_defaults_and_object_key_order() -> None:
    from src.services.submission_idempotency import build_request_fingerprint

    omitted_defaults = _FixtureRequest(prompt="fixture")
    explicit_defaults = _FixtureRequest(
        prompt="fixture",
        duration=10,
        tags=[],
        api_keys={},
        nested={"b": 2, "a": 1},
    )
    reordered = _FixtureRequest(
        prompt="fixture",
        nested={"a": 1, "b": 2},
    )

    base = build_request_fingerprint(
        omitted_defaults,
        operation="fast.submit",
        scenario="fast",
        effective_policy=_policy(),
    )
    explicit = build_request_fingerprint(
        explicit_defaults,
        operation="fast.submit",
        scenario="fast",
        effective_policy=_policy(),
    )
    ordered = build_request_fingerprint(
        reordered,
        operation="fast.submit",
        scenario="fast",
        effective_policy=_policy(),
    )

    # The only business difference above is the nested object content.
    assert explicit.request_hash == ordered.request_hash
    assert base.request_hash != explicit.request_hash
    assert base.version == "submit-fingerprint.v1"


def test_fingerprint_preserves_list_order_and_json_scalar_types() -> None:
    from src.services.submission_idempotency import build_request_fingerprint

    def fingerprint(payload: Mapping[str, Any]) -> str:
        return build_request_fingerprint(
            payload,
            operation="fast.submit",
            scenario="fast",
            effective_policy=_policy(),
        ).request_hash

    assert fingerprint({"items": ["a", "b"]}) != fingerprint({"items": ["b", "a"]})
    assert fingerprint({"value": True}) != fingerprint({"value": 1})


def test_fingerprint_excludes_credentials_but_includes_effective_policy() -> None:
    from src.services.submission_idempotency import build_request_fingerprint

    first = _FixtureRequest(
        prompt="fixture",
        api_keys={"poyo": "credential-one"},
        nested={
            "provider_api_key": "nested-one",
            "idempotency_key": "client-owned-one",
            "business": "same",
        },
    )
    second = _FixtureRequest(
        prompt="fixture",
        api_keys={"poyo": "credential-two"},
        nested={
            "provider_api_key": "nested-two",
            "idempotency_key": "client-owned-two",
            "business": "same",
        },
    )

    first_hash = build_request_fingerprint(
        first,
        operation="fast.submit",
        scenario="fast",
        effective_policy=_policy(),
    ).request_hash
    second_hash = build_request_fingerprint(
        second,
        operation="fast.submit",
        scenario="fast",
        effective_policy=_policy(),
    ).request_hash
    changed_policy_hash = build_request_fingerprint(
        second,
        operation="fast.submit",
        scenario="fast",
        effective_policy=_policy(version="generation-safety.v2"),
    ).request_hash

    assert first_hash == second_hash
    assert changed_policy_hash != second_hash
    assert "credential-one" not in first_hash
    assert "credential-two" not in second_hash


@dataclass
class _ClaimResult:
    outcome: str
    record: dict[str, Any]


class _FakeRepository:
    def __init__(self) -> None:
        self.claim_outcome = "owner"
        self.claim_kwargs: dict[str, Any] = {}
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.renew_kwargs: list[dict[str, Any]] = []
        self.transition_kwargs: list[dict[str, Any]] = []
        self.renew_result: dict[str, Any] | None = {"record_status": "running"}
        self.reconcile_kwargs: list[dict[str, Any]] = []
        self.reconcile_result: dict[str, Any] | None = None
        self.get_by_id_kwargs: list[dict[str, Any]] = []
        self.record_by_id: dict[str, Any] | None = None

    async def claim(self, **kwargs: Any) -> _ClaimResult:
        self.claim_kwargs = kwargs
        record = {
            "id": "record-1",
            "tenant_id": kwargs["tenant_id"],
            "key_hash": kwargs["key_hash"],
            "request_hash": kwargs["request_hash"],
            "operation": kwargs["operation"],
            "scenario": kwargs["scenario"],
            "resource_type": kwargs["resource_type"],
            "resource_id": kwargs["resource_id"],
            "record_status": "reserved",
            "stage": "reserved",
            "response_body": kwargs["response_body"],
            "response_status": kwargs["response_status"],
            "created_at": "2026-07-12T00:00:00Z",
            "updated_at": "2026-07-12T00:00:00Z",
            "owner_instance_id": kwargs["owner_instance_id"],
        }
        self.records[(kwargs["tenant_id"], kwargs["key_hash"])] = record
        return _ClaimResult(self.claim_outcome, record)

    async def get_by_key_hash(self, *, tenant_id: str, key_hash: str) -> dict[str, Any] | None:
        return self.records.get((tenant_id, key_hash))

    async def get_by_resource(self, **_kwargs: Any) -> dict[str, Any] | None:
        return None

    async def get_by_id(self, **kwargs: Any) -> dict[str, Any] | None:
        self.get_by_id_kwargs.append(kwargs)
        return self.record_by_id

    async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
        self.transition_kwargs.append(kwargs)
        return {"record_status": kwargs["new_status"]}

    async def renew_lease(self, **kwargs: Any) -> dict[str, Any] | None:
        self.renew_kwargs.append(kwargs)
        return self.renew_result

    async def reconcile_expired_lease(self, **kwargs: Any) -> dict[str, Any] | None:
        self.reconcile_kwargs.append(kwargs)
        return self.reconcile_result


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["owner", "replay"])
async def test_claim_hashes_raw_key_and_maps_owner_or_replay(outcome: str) -> None:
    from src.services.submission_idempotency import SubmissionIdempotencyService

    repo = _FakeRepository()
    repo.claim_outcome = outcome
    service = SubmissionIdempotencyService(repo, instance_id="instance-a")

    result = await service.claim_submission(
        tenant_id="tenant-a",
        raw_key=VALID_KEY,
        validated_request=_FixtureRequest(prompt="fixture", api_keys={"poyo": "must-not-reach-repo"}),
        effective_policy=_policy(),
        operation="fast.submit",
        scenario="fast",
        resource_type="fast",
        resource_id="fast-fixture",
        response_body={
            "task_id": "fast-fixture",
            "status": "reserved",
            "provider_api_key": "must-not-reach-repo",
        },
    )

    assert result.outcome == outcome
    assert result.record["resource_id"] == "fast-fixture"
    assert repo.claim_kwargs["key_hash"] != VALID_KEY
    assert len(repo.claim_kwargs["key_hash"]) == 64
    assert "must-not-reach-repo" not in repr(repo.claim_kwargs)


@pytest.mark.asyncio
async def test_replay_reconciles_expired_owner_before_returning_stored_projection() -> None:
    from src.services.submission_idempotency import SubmissionIdempotencyService

    repo = _FakeRepository()
    repo.claim_outcome = "replay"
    repo.reconcile_result = {
        "id": "record-1",
        "tenant_id": "tenant-a",
        "resource_type": "fast",
        "resource_id": "fast-fixture",
        "scenario": "fast",
        "record_status": "recovery_required",
        "stage": "recovery_required",
        "response_body": {
            "task_id": "fast-fixture",
            "status": "recovery_required",
        },
    }
    service = SubmissionIdempotencyService(repo, instance_id="instance-a")

    result = await service.claim_submission(
        tenant_id="tenant-a",
        raw_key=VALID_KEY,
        validated_request=_FixtureRequest(prompt="fixture"),
        effective_policy=_policy(),
        operation="fast.submit",
        scenario="fast",
        resource_type="fast",
        resource_id="fast-new-allocation-must-not-win",
        response_body={
            "task_id": "fast-new-allocation-must-not-win",
            "status": "reserved",
        },
    )

    assert result.outcome == "replay"
    assert result.record["resource_id"] == "fast-fixture"
    assert result.record["record_status"] == "recovery_required"
    assert result.record["response_body"]["status"] == "recovery_required"
    assert repo.reconcile_kwargs == [
        {"tenant_id": "tenant-a", "record_id": "record-1", "safe_error_code": "submission_owner_lost"}
    ]


@pytest.mark.asyncio
async def test_claim_conflict_raises_stable_error_without_record_mutation() -> None:
    from src.services.submission_idempotency import (
        IdempotencyPayloadConflict,
        SubmissionIdempotencyService,
    )

    repo = _FakeRepository()
    repo.claim_outcome = "conflict"
    service = SubmissionIdempotencyService(repo, instance_id="instance-a")

    with pytest.raises(IdempotencyPayloadConflict) as caught:
        await service.claim_submission(
            tenant_id="tenant-a",
            raw_key=VALID_KEY,
            validated_request={"prompt": "changed"},
            effective_policy=_policy(),
            operation="fast.submit",
            scenario="fast",
            resource_type="fast",
            resource_id="fast-new",
            response_body={"task_id": "fast-new", "status": "reserved"},
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "idempotency_payload_conflict"


@pytest.mark.asyncio
async def test_readback_is_tenant_bound_and_returns_only_safe_projection() -> None:
    from src.services.submission_idempotency import (
        SubmissionIdempotencyService,
        SubmissionNotFound,
        hash_idempotency_key,
    )

    repo = _FakeRepository()
    key_hash = hash_idempotency_key(VALID_KEY)
    repo.records[("tenant-a", key_hash)] = {
        "id": "record-1",
        "tenant_id": "tenant-a",
        "key_hash": key_hash,
        "request_hash": "private-request-hash",
        "owner_instance_id": "private-owner",
        "resource_type": "scenario",
        "resource_id": "s1_fixture",
        "scenario": "s1",
        "record_status": "running",
        "stage": "scripts",
        "response_body": {
            "label": "s1_fixture",
            "status": "queued",
            "trace_id": "fixture-trace",
        },
        "created_at": "2026-07-12T00:00:00Z",
        "updated_at": "2026-07-12T00:00:04Z",
    }
    service = SubmissionIdempotencyService(repo, instance_id="instance-a")

    response = await service.readback(tenant_id="tenant-a", raw_key=VALID_KEY)

    assert response == {
        "resource_type": "scenario",
        "resource_id": "s1_fixture",
        "scenario": "s1",
        "status": "running",
        "stage": "scripts",
        "submit_response": {
            "label": "s1_fixture",
            "status": "queued",
            "trace_id": "fixture-trace",
        },
        "created_at": "2026-07-12T00:00:00Z",
        "updated_at": "2026-07-12T00:00:04Z",
    }
    assert "key_hash" not in response
    assert "tenant_id" not in response
    assert "owner_instance_id" not in response

    with pytest.raises(SubmissionNotFound) as unknown:
        await service.readback(tenant_id="tenant-b", raw_key=VALID_KEY)
    assert unknown.value.status_code == 404
    assert unknown.value.code == "submission_not_found"


@pytest.mark.asyncio
async def test_heartbeat_uses_repository_db_time_cas_and_recovers_lost_owner() -> None:
    from src.services.submission_idempotency import SubmissionIdempotencyService

    repo = _FakeRepository()
    repo.renew_result = None
    failure_signals = 0

    async def on_failure() -> None:
        nonlocal failure_signals
        failure_signals += 1

    service = SubmissionIdempotencyService(repo, instance_id="instance-a")
    heartbeat = service.create_heartbeat(
        tenant_id="tenant-a",
        record_id="record-1",
        on_failure=on_failure,
    )

    renewed = await heartbeat.renew_once()

    assert renewed is False
    assert failure_signals == 1
    assert repo.renew_kwargs == [
        {
            "tenant_id": "tenant-a",
            "record_id": "record-1",
            "owner_instance_id": "instance-a",
            "expected_statuses": (
                "reserved",
                "initializing",
                "queued",
                "running",
            ),
            "lease_seconds": 120,
        }
    ]
    assert "now" not in repo.renew_kwargs[0]
    assert repo.transition_kwargs[-1]["new_status"] == "recovery_required"
    assert repo.transition_kwargs[-1]["expected_statuses"] == (
        "reserved",
        "initializing",
        "queued",
        "running",
    )
    assert repo.transition_kwargs[-1]["owner_instance_id"] == "instance-a"


@pytest.mark.asyncio
async def test_heartbeat_stops_owner_when_external_reconcile_wins_recovery_cas() -> None:
    from src.services.submission_idempotency import SubmissionIdempotencyService

    class ExternallyReconciledRepository(_FakeRepository):
        async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
            self.transition_kwargs.append(kwargs)
            return None

    repo = ExternallyReconciledRepository()
    repo.renew_result = None
    repo.record_by_id = {
        "id": "record-1",
        "record_status": "recovery_required",
    }
    failure_signals = 0

    async def on_failure() -> None:
        nonlocal failure_signals
        failure_signals += 1

    heartbeat = SubmissionIdempotencyService(
        repo,
        instance_id="instance-a",
    ).create_heartbeat(
        tenant_id="tenant-a",
        record_id="record-1",
        on_failure=on_failure,
    )

    renewed = await heartbeat.renew_once()

    assert renewed is False
    assert repo.transition_kwargs[-1]["new_status"] == "recovery_required"
    assert repo.get_by_id_kwargs == [
        {"tenant_id": "tenant-a", "record_id": "record-1"}
    ]
    assert failure_signals == 1


@pytest.mark.asyncio
async def test_heartbeat_does_not_cancel_work_after_terminal_transition_wins_race() -> None:
    from src.services.submission_idempotency import SubmissionIdempotencyService

    class TerminalRepository(_FakeRepository):
        async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
            self.transition_kwargs.append(kwargs)
            return None

    repo = TerminalRepository()
    repo.renew_result = None
    repo.record_by_id = {"id": "record-1", "record_status": "completed"}
    failure_signals = 0

    async def on_failure() -> None:
        nonlocal failure_signals
        failure_signals += 1

    heartbeat = SubmissionIdempotencyService(
        repo,
        instance_id="instance-a",
    ).create_heartbeat(
        tenant_id="tenant-a",
        record_id="record-1",
        on_failure=on_failure,
    )

    renewed = await heartbeat.renew_once()

    assert renewed is False
    assert repo.get_by_id_kwargs == [
        {"tenant_id": "tenant-a", "record_id": "record-1"}
    ]
    assert failure_signals == 0


@pytest.mark.asyncio
async def test_terminal_transition_precedes_independent_heartbeat_stop() -> None:
    from src.services.submission_idempotency import SubmissionIdempotencyService

    order: list[str] = []
    sleep_entered = asyncio.Event()
    sleep_blocker = asyncio.Event()

    class OrderedRepository(_FakeRepository):
        async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
            order.append(f"transition:{kwargs['new_status']}")
            return await super().transition(**kwargs)

    async def blocked_sleep(_seconds: float) -> None:
        sleep_entered.set()
        await sleep_blocker.wait()

    repo = OrderedRepository()
    service = SubmissionIdempotencyService(
        repo,
        instance_id="instance-a",
        sleep=blocked_sleep,
    )
    heartbeat = service.start_heartbeat(
        tenant_id="tenant-a",
        record_id="record-1",
    )
    await sleep_entered.wait()
    assert heartbeat.running is True

    original_stop = heartbeat.stop

    async def ordered_stop() -> None:
        order.append("heartbeat:stop")
        await original_stop()

    heartbeat.stop = ordered_stop  # type: ignore[method-assign]
    result = await service.mark_terminal(
        tenant_id="tenant-a",
        record_id="record-1",
        status="completed",
        stage="completed",
        result_snapshot={"status": "completed", "api_keys": {"poyo": "secret"}},
    )

    assert result == {"record_status": "completed"}
    assert order == ["transition:completed", "heartbeat:stop"]
    assert "secret" not in repr(repo.transition_kwargs[-1])


@pytest.mark.asyncio
async def test_store_unavailable_maps_to_stable_503_error() -> None:
    from src.services.submission_idempotency import (
        IdempotencyStoreUnavailable,
        SubmissionIdempotencyService,
    )

    class IdempotencyStoreUnavailableError(RuntimeError):
        pass

    class UnavailableRepository(_FakeRepository):
        async def get_by_key_hash(self, *, tenant_id: str, key_hash: str) -> dict[str, Any] | None:
            del tenant_id, key_hash
            raise IdempotencyStoreUnavailableError

    service = SubmissionIdempotencyService(UnavailableRepository(), instance_id="instance-a")

    with pytest.raises(IdempotencyStoreUnavailable) as caught:
        await service.readback(tenant_id="tenant-a", raw_key=VALID_KEY)

    assert caught.value.status_code == 503
    assert caught.value.code == "idempotency_store_unavailable"


@pytest.mark.asyncio
async def test_shutdown_stops_every_heartbeat_after_store_failure() -> None:
    from src.services.submission_idempotency import (
        IdempotencyStoreUnavailable,
        SubmissionIdempotencyService,
    )

    stopped: list[str] = []

    class PartiallyUnavailableRepository(_FakeRepository):
        async def transition(self, **kwargs: Any) -> dict[str, Any] | None:
            self.transition_kwargs.append(kwargs)
            if kwargs["record_id"] == "record-1":
                raise type("IdempotencyStoreUnavailableError", (RuntimeError,), {})()
            return {"record_status": kwargs["new_status"]}

    repo = PartiallyUnavailableRepository()
    service = SubmissionIdempotencyService(repo, instance_id="instance-a")
    for record_id in ("record-1", "record-2"):
        heartbeat = service.create_heartbeat(tenant_id="tenant-a", record_id=record_id)

        async def stop(*, current: str = record_id) -> None:
            stopped.append(current)

        heartbeat.stop = stop  # type: ignore[method-assign]
        service._heartbeats[("tenant-a", record_id)] = heartbeat

    with pytest.raises(IdempotencyStoreUnavailable) as caught:
        await service.shutdown()

    assert caught.value.code == "idempotency_store_unavailable"
    assert stopped == ["record-1", "record-2"]
    assert [call["record_id"] for call in repo.transition_kwargs] == [
        "record-1",
        "record-2",
    ]
    assert service._heartbeats == {}


@pytest.mark.asyncio
async def test_readback_http_contract_and_cors(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
) -> None:
    from src.api import app
    from src.routers import submissions

    class FakeService:
        async def readback(self, *, tenant_id: str, raw_key: str) -> dict[str, Any]:
            assert tenant_id == "default"
            assert raw_key == VALID_KEY
            return {
                "resource_type": "fast",
                "resource_id": "fast-fixture",
                "scenario": "fast",
                "status": "queued",
                "submit_response": {
                    "task_id": "fast-fixture",
                    "status": "queued",
                },
                "created_at": "2026-07-12T00:00:00Z",
                "updated_at": "2026-07-12T00:00:00Z",
            }

    monkeypatch.setattr(submissions, "get_submission_idempotency_service", lambda: FakeService())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/submissions/idempotency",
            headers={**auth_headers, "Idempotency-Key": VALID_KEY},
        )
        missing = await client.get(
            "/submissions/idempotency",
            headers=auth_headers,
        )
        duplicate = await client.get(
            "/submissions/idempotency",
            headers=[
                *auth_headers.items(),
                ("Idempotency-Key", VALID_KEY),
                ("Idempotency-Key", VALID_KEY),
            ],
        )
        preflight = await client.options(
            "/submissions/idempotency",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Idempotency-Key,X-API-Key",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["resource_id"] == "fast-fixture"
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "idempotency_key_required"
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["code"] == "idempotency_key_invalid"
    assert preflight.status_code == 200, preflight.text
    assert "idempotency-key" in preflight.headers["access-control-allow-headers"].lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_name", "status_code", "code"),
    [
        ("SubmissionNotFound", 404, "submission_not_found"),
        (
            "IdempotencyStoreUnavailable",
            503,
            "idempotency_store_unavailable",
        ),
    ],
)
async def test_readback_http_errors_are_stable_and_do_not_echo_key(
    monkeypatch: pytest.MonkeyPatch,
    auth_headers: dict[str, str],
    error_name: str,
    status_code: int,
    code: str,
) -> None:
    from src.api import app
    from src.routers import submissions
    from src.services import submission_idempotency

    error_type = getattr(submission_idempotency, error_name)

    class FailingService:
        async def readback(self, *, tenant_id: str, raw_key: str) -> dict[str, Any]:
            del tenant_id, raw_key
            raise error_type()

    monkeypatch.setattr(
        submissions,
        "get_submission_idempotency_service",
        lambda: FailingService(),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/submissions/idempotency",
            headers={**auth_headers, "Idempotency-Key": VALID_KEY},
        )

    assert response.status_code == status_code
    assert response.json()["detail"] == {"code": code}
    assert VALID_KEY not in response.text
