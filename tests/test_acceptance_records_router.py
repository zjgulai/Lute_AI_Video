"""HTTP contract for tenant-bound human acceptance records."""

from __future__ import annotations

import hashlib
import importlib
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.models.acceptance import AcceptanceCreateRequest, AcceptanceRecordResponse
from src.routers._deps import AuthContext
from src.services.artifact_acceptance import (
    AcceptanceNotFound,
    AcceptanceStoreUnavailable,
)


def _valid_request(
    *,
    tenant_id: str = "default",
    source_resource_id: str = "s2_1783830000_abcdef12",
) -> dict[str, object]:
    return {
        "source_resource_type": "scenario",
        "source_resource_id": source_resource_id,
        "artifact_path": (
            f"tenants/{tenant_id}/pending_review/"
            f"{source_resource_id}/assemble/final.mp4"
        ),
        "decision": "accepted",
        "review_notes": "Reviewed exact final render.",
        "expires_in_seconds": 3600,
    }


def _record(
    *,
    acceptance_id: str,
    auth: AuthContext,
    request: AcceptanceCreateRequest,
    replay: bool,
    status: str | None = None,
    revoked_at: str | None = None,
) -> AcceptanceRecordResponse:
    scenario = (
        "fast"
        if request.source_resource_type == "fast"
        else request.source_resource_id.split("_", 1)[0]
    )
    return AcceptanceRecordResponse.model_validate(
        {
            "acceptance_id": acceptance_id,
            "tenant_id": auth.tenant_id,
            "source_resource_type": request.source_resource_type,
            "source_resource_id": request.source_resource_id,
            "scenario": scenario,
            "artifact": {
                "path": request.artifact_path,
                "sha256": "a" * 64,
                "size_bytes": 20,
                "kind": "video",
            },
            "decision": request.decision,
            "status": status
            or ("available" if request.decision == "accepted" else "rejected"),
            "reviewer": {
                "key_id": auth.key_id,
                "key_type": str(auth.key_type),
            },
            "review_notes": request.review_notes,
            "expires_at": "2026-07-12T12:00:00Z",
            "consumed_at": None,
            "revoked_at": revoked_at,
            "idempotent_replay": replay,
            "created_at": "2026-07-12T11:00:00Z",
            "updated_at": "2026-07-12T11:00:00Z",
        }
    )


class _FakeAcceptanceService:
    def __init__(self) -> None:
        self._key_records: dict[tuple[str, str], str] = {}
        self._records: dict[tuple[str, str], AcceptanceRecordResponse] = {}
        self.calls: list[tuple[str, str]] = []

    async def create(
        self,
        *,
        auth: AuthContext,
        raw_key: str,
        request: AcceptanceCreateRequest,
    ) -> tuple[AcceptanceRecordResponse, bool]:
        self.calls.append(("create", auth.tenant_id))
        if request.source_resource_id == "store_unavailable":
            raise AcceptanceStoreUnavailable

        key = (auth.tenant_id, raw_key)
        acceptance_id = self._key_records.get(key)
        if acceptance_id is not None:
            current = self._records[(auth.tenant_id, acceptance_id)]
            return current.model_copy(update={"idempotent_replay": True}), True

        acceptance_id = f"acceptance-http-fixture-{len(self._key_records) + 1}"
        current = _record(
            acceptance_id=acceptance_id,
            auth=auth,
            request=request,
            replay=False,
        )
        self._key_records[key] = acceptance_id
        self._records[(auth.tenant_id, acceptance_id)] = current
        return current, False

    async def read(
        self,
        *,
        auth: AuthContext,
        acceptance_id: str,
    ) -> AcceptanceRecordResponse:
        self.calls.append(("read", auth.tenant_id))
        record = self._records.get((auth.tenant_id, acceptance_id))
        if record is None:
            raise AcceptanceNotFound
        return record.model_copy(update={"idempotent_replay": False})

    async def revoke(
        self,
        *,
        auth: AuthContext,
        acceptance_id: str,
    ) -> AcceptanceRecordResponse:
        self.calls.append(("revoke", auth.tenant_id))
        record = self._records.get((auth.tenant_id, acceptance_id))
        if record is None:
            raise AcceptanceNotFound
        if record.status == "available":
            record = record.model_copy(
                update={
                    "status": "revoked",
                    "revoked_at": "2026-07-12T11:30:00Z",
                    "updated_at": "2026-07-12T11:30:00Z",
                    "idempotent_replay": False,
                }
            )
            self._records[(auth.tenant_id, acceptance_id)] = record
        return record.model_copy(update={"idempotent_replay": False})


class _FakeAcquire:
    def __init__(self, connection: _FakeAuthConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _FakeAuthConnection:
        return self.connection

    async def __aexit__(self, *_args: object) -> bool:
        return False


class _FakePool:
    def __init__(self, connection: _FakeAuthConnection) -> None:
        self.connection = connection

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.connection)


class _FakeAuthConnection:
    def __init__(self, rows: dict[str, dict[str, object]]) -> None:
        self.rows = rows

    async def fetchrow(self, _query: str, key_hash: str) -> dict[str, object] | None:
        return self.rows.get(key_hash)

    async def execute(self, *_args: object) -> str:
        return "UPDATE 1"


@pytest.fixture
def fake_acceptance_service(
    monkeypatch: pytest.MonkeyPatch,
) -> _FakeAcceptanceService:
    service = _FakeAcceptanceService()
    try:
        router_module = importlib.import_module("src.routers.acceptance_records")
    except ModuleNotFoundError as exc:
        if exc.name != "src.routers.acceptance_records":
            raise
    else:
        monkeypatch.setattr(
            router_module,
            "get_artifact_acceptance_service",
            lambda: service,
        )
    return service


@pytest.fixture
def tenant_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, dict[str, str]]:
    from src.routers import _deps
    from src.storage import db

    raw_keys = {
        "reviewer_a": "router-reviewer-a-api-key",
        "reviewer_b": "router-reviewer-b-api-key",
        "provider_only": "router-provider-only-api-key",
    }
    permissions = {
        "reviewer_a": ["artifact:accept"],
        "reviewer_b": ["artifact:accept"],
        "provider_only": ["provider:submit"],
    }
    tenants = {
        "reviewer_a": "tenant-a",
        "reviewer_b": "tenant-b",
        "provider_only": "tenant-a",
    }
    rows = {
        hashlib.sha256(raw_key.encode()).hexdigest(): {
            "id": f"{name}-key-id",
            "tenant_id": tenants[name],
            "permissions": permissions[name],
            "revoked_at": None,
            "expires_at": datetime.now(UTC) + timedelta(hours=1),
        }
        for name, raw_key in raw_keys.items()
    }
    connection = _FakeAuthConnection(rows)

    async def fake_get_pool() -> _FakePool:
        return _FakePool(connection)

    monkeypatch.setattr(db, "is_pg_available", lambda: True)
    monkeypatch.setattr(db, "get_pool", fake_get_pool)
    monkeypatch.setattr(_deps, "API_KEY", "")
    monkeypatch.setattr(_deps, "TEST_BUNDLE_KEY", "")
    monkeypatch.setattr(_deps, "ENVIRONMENT", "test")

    return {
        name: {"X-API-Key": raw_key}
        for name, raw_key in raw_keys.items()
    }


@pytest.mark.asyncio
async def test_create_returns_201_and_replay_returns_200(
    auth_headers: dict[str, str],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    del fake_acceptance_service
    from src.api import app

    headers = {
        **auth_headers,
        "Idempotency-Key": "acceptance-action-key-0001",
        "X-Client-Trace-Id": "acceptance-http-trace",
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/acceptance-records",
            headers=headers,
            json=_valid_request(),
        )
        replay = await client.post(
            "/acceptance-records",
            headers=headers,
            json=_valid_request(),
        )

    assert first.status_code == 201, first.text
    assert replay.status_code == 200, replay.text
    assert first.json()["acceptance_id"] == replay.json()["acceptance_id"]
    assert replay.json()["idempotent_replay"] is True
    assert first.headers["X-Trace-Id"] == "acceptance-http-trace"
    assert set(first.json()["_meta"]) == {
        "trace_id",
        "duration_ms",
        "version",
        "timestamp",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/acceptance-records"),
        ("GET", "/acceptance-records/unknown-record"),
        ("POST", "/acceptance-records/unknown-record/revoke"),
    ],
)
async def test_every_acceptance_route_requires_api_key(
    method: str,
    path: str,
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    before = len(fake_acceptance_service.calls)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.request(
            method,
            path,
            headers={"Idempotency-Key": "unauthenticated-action-key-0001"},
            json=_valid_request(),
        )

    assert response.status_code == 401, response.text
    assert len(fake_acceptance_service.calls) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/acceptance-records"),
        ("GET", "/acceptance-records/unknown-record"),
        ("POST", "/acceptance-records/unknown-record/revoke"),
    ],
)
async def test_provider_submit_only_key_is_denied_before_route_processing(
    method: str,
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    before = len(fake_acceptance_service.calls)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.request(
            method,
            path,
            headers=tenant_auth_headers["provider_only"],
            content=b'{"credential":"must-not-be-parsed"',
        )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Insufficient permission"
    assert len(fake_acceptance_service.calls) == before


@pytest.mark.asyncio
async def test_missing_key_is_rejected_before_invalid_json(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Content-Type": "application/json",
            },
            content=b'{"credential":"must-not-be-parsed"',
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "acceptance_key_required"
    assert fake_acceptance_service.calls == []


@pytest.mark.asyncio
async def test_invalid_key_is_rejected_before_invalid_json(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": "short",
                "Content-Type": "application/json",
            },
            content=b'{"credential":"must-not-be-parsed"',
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "acceptance_key_invalid"
    assert fake_acceptance_service.calls == []


@pytest.mark.asyncio
async def test_duplicate_raw_key_headers_are_not_collapsed(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    headers = list(tenant_auth_headers["reviewer_a"].items()) + [
        ("Idempotency-Key", "duplicate-acceptance-key-0001"),
        ("Idempotency-Key", "duplicate-acceptance-key-0002"),
        ("Content-Type", "application/json"),
    ]
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/acceptance-records",
            headers=headers,
            content=b'{"credential":"must-not-be-parsed"',
        )

    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == "acceptance_key_invalid"
    assert fake_acceptance_service.calls == []


@pytest.mark.asyncio
async def test_validation_error_is_safe_and_never_echoes_credentials(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    raw_key = "safe-validation-action-key-0001"
    credential = "provider-credential-must-not-echo"
    payload = {
        **_valid_request(tenant_id="tenant-a"),
        "provider_credentials": {"POYO_API_KEY": credential},
    }
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": raw_key,
            },
            json=payload,
        )

    assert response.status_code == 422, response.text
    assert credential not in response.text
    assert raw_key not in response.text
    assert "POYO_API_KEY" not in response.text
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) <= {"type", "loc", "msg"} for error in errors)
    assert all("input" not in error and "ctx" not in error for error in errors)
    assert fake_acceptance_service.calls == []


@pytest.mark.asyncio
async def test_invalid_json_uses_safe_422_projection(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    credential = "malformed-json-credential-must-not-echo"
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": "invalid-json-action-key-0001",
                "Content-Type": "application/json",
            },
            content=f'{{"provider_credential":"{credential}"'.encode(),
        )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == [
        {"type": "json_invalid", "loc": ["body"], "msg": "Invalid JSON"}
    ]
    assert credential not in response.text
    assert fake_acceptance_service.calls == []


@pytest.mark.asyncio
async def test_cross_tenant_read_and_revoke_are_non_enumerating_404(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": "tenant-isolation-key-0001",
            },
            json=_valid_request(tenant_id="tenant-a"),
        )
        acceptance_id = created.json()["acceptance_id"]
        cross_read = await client.get(
            f"/acceptance-records/{acceptance_id}",
            headers=tenant_auth_headers["reviewer_b"],
        )
        unknown_read = await client.get(
            "/acceptance-records/unknown-record",
            headers=tenant_auth_headers["reviewer_b"],
        )
        cross_revoke = await client.post(
            f"/acceptance-records/{acceptance_id}/revoke",
            headers=tenant_auth_headers["reviewer_b"],
        )
        unknown_revoke = await client.post(
            "/acceptance-records/unknown-record/revoke",
            headers=tenant_auth_headers["reviewer_b"],
        )

    assert created.status_code == 201, created.text
    for response in (cross_read, unknown_read, cross_revoke, unknown_revoke):
        assert response.status_code == 404, response.text
        assert response.json()["detail"] == {"code": "acceptance_not_found"}


@pytest.mark.asyncio
async def test_revoke_replay_returns_the_same_revoked_record(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": "revoke-replay-action-key-0001",
            },
            json=_valid_request(tenant_id="tenant-a"),
        )
        acceptance_id = created.json()["acceptance_id"]
        first = await client.post(
            f"/acceptance-records/{acceptance_id}/revoke",
            headers=tenant_auth_headers["reviewer_a"],
        )
        replay = await client.post(
            f"/acceptance-records/{acceptance_id}/revoke",
            headers=tenant_auth_headers["reviewer_a"],
        )

    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert first.json()["status"] == replay.json()["status"] == "revoked"
    assert first.json()["acceptance_id"] == replay.json()["acceptance_id"]
    assert first.json()["revoked_at"] == replay.json()["revoked_at"]


@pytest.mark.asyncio
async def test_store_unavailable_maps_to_stable_503(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": "store-unavailable-key-0001",
            },
            json=_valid_request(
                tenant_id="tenant-a",
                source_resource_id="store_unavailable",
            ),
        )

    assert response.status_code == 503, response.text
    assert response.json()["detail"] == {"code": "acceptance_store_unavailable"}


@pytest.mark.asyncio
async def test_consume_is_not_exposed_over_http_and_never_calls_service(
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_acceptance_service: _FakeAcceptanceService,
) -> None:
    from src.api import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        created = await client.post(
            "/acceptance-records",
            headers={
                **tenant_auth_headers["reviewer_a"],
                "Idempotency-Key": "no-consume-action-key-0001",
            },
            json=_valid_request(tenant_id="tenant-a"),
        )
        acceptance_id = created.json()["acceptance_id"]
        before = len(fake_acceptance_service.calls)
        get_response = await client.get(
            f"/acceptance-records/{acceptance_id}/consume",
            headers=tenant_auth_headers["reviewer_a"],
        )
        post_response = await client.post(
            f"/acceptance-records/{acceptance_id}/consume",
            headers=tenant_auth_headers["reviewer_a"],
        )

    assert created.status_code == 201, created.text
    assert get_response.status_code in {404, 405}, get_response.text
    assert post_response.status_code in {404, 405}, post_response.text
    assert len(fake_acceptance_service.calls) == before


def test_openapi_documents_create_read_revoke_and_no_consume() -> None:
    from src.api import app

    paths = app.openapi()["paths"]
    assert "post" in paths["/acceptance-records"]
    assert "get" in paths["/acceptance-records/{acceptance_id}"]
    assert "post" in paths["/acceptance-records/{acceptance_id}/revoke"]
    create_operation = paths["/acceptance-records"]["post"]
    responses = create_operation["responses"]
    assert {"200", "201"} <= responses.keys()
    assert responses["200"]["description"] == (
        "Idempotent replay of the original acceptance record."
    )
    assert responses["200"]["content"]["application/json"]["schema"] == (
        responses["201"]["content"]["application/json"]["schema"]
    )
    parameters = create_operation["parameters"]
    action_key = next(
        parameter
        for parameter in parameters
        if parameter["name"] == "Idempotency-Key"
    )
    assert action_key["in"] == "header"
    assert action_key["required"] is True
    assert not any(path.endswith("/consume") for path in paths)


def test_openapi_create_request_body_is_required_and_matches_contract() -> None:
    from src.api import app

    operation = app.openapi()["paths"]["/acceptance-records"]["post"]
    request_body = operation["requestBody"]
    assert request_body["required"] is True
    assert set(request_body["content"]) == {"application/json"}

    schema = request_body["content"]["application/json"]["schema"]
    assert schema == AcceptanceCreateRequest.model_json_schema(mode="validation")
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "source_resource_type",
        "source_resource_id",
        "artifact_path",
        "decision",
        "review_notes",
    ]
    assert schema["properties"]["source_resource_type"]["enum"] == [
        "fast",
        "scenario",
    ]
    assert schema["properties"]["decision"]["enum"] == ["accepted", "rejected"]
    assert schema["properties"]["source_resource_id"]["minLength"] == 1
    assert schema["properties"]["source_resource_id"]["maxLength"] == 128
    assert schema["properties"]["artifact_path"]["minLength"] == 1
    assert schema["properties"]["artifact_path"]["maxLength"] == 1024
    assert schema["properties"]["review_notes"]["minLength"] == 1
    assert schema["properties"]["review_notes"]["maxLength"] == 2000
    assert schema["properties"]["expires_in_seconds"] == {
        "default": 3600,
        "maximum": 86400,
        "minimum": 300,
        "title": "Expires In Seconds",
        "type": "integer",
    }
