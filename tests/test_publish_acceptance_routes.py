"""HTTP contract for acceptance-backed canonical and legacy publish adapters."""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response

from src.models.publish_attempt import (
    PublishAttemptErrorResponse,
    PublishAttemptRequest,
    PublishAttemptResponse,
)
from src.routers._deps import AuthContext
from src.services.publish_attempt import PublishAttemptError

ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
ATTEMPT_ID = "91ec3593-cc3c-42bf-99ee-c98655c5826b"
SUCCESSOR_LINK = '</distribution/publish>; rel="successor-version"'
_MISSING = object()
_UNSAFE_LEGACY_PATHS = [
    "sk-secret-shaped-path.must-not-echo",
    "a" * 129,
]


def _published_receipt() -> dict[str, object]:
    return {
        "schema_version": "publish-receipt.v1",
        "platform": "tiktok",
        "protocol_version": "tiktok-content-posting-v2",
        "completion_scope": "tiktok_direct_post",
        "provider_operation_id": "v_pub_file_fixture_123",
        "provider_resource_id": "7512345678901234567",
        "target_id": None,
        "provider_status": "PUBLISH_COMPLETE",
        "post_id": "7512345678901234567",
        "post_url": (
            "https://www.tiktok.com/@fixture_creator/video/7512345678901234567"
        ),
        "public_visibility_verified": True,
        "observed_at": "2026-07-14T08:00:00Z",
        "verified_by": "video_query",
        "simulated": False,
    }


def _valid_body(*, platform: str = "tiktok") -> dict[str, object]:
    platform_options: dict[str, object]
    if platform == "tiktok":
        platform_options = {
            "platform": "tiktok",
            "privacy_level": "SELF_ONLY",
            "disable_comment": True,
            "disable_duet": True,
            "disable_stitch": True,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        }
    else:
        platform_options = {
            "platform": "shopify",
            "product_id": "gid://shopify/Product/123456789",
        }
    return {
        "acceptance_id": ACCEPTANCE_ID,
        "platform": platform,
        "platform_options": platform_options,
        "metadata": {"title": "Reviewed campaign"},
    }


class _FakePublishService:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error: PublishAttemptError | None = None

    async def execute(
        self,
        *,
        auth: AuthContext,
        request: PublishAttemptRequest,
        route_kind: str,
    ) -> PublishAttemptResponse:
        self.calls.append(
            {
                "tenant_id": auth.tenant_id,
                "key_id": auth.key_id,
                "request": request,
                "request_json": request.model_dump(mode="json"),
                "route_kind": route_kind,
            }
        )
        if self.error is not None:
            raise self.error
        return PublishAttemptResponse(
            publish_attempt_id=ATTEMPT_ID,
            acceptance_id=request.acceptance_id,
            platform=request.platform,
            status="published",
            success=True,
            post_id="7512345678901234567",
            post_url=(
                "https://www.tiktok.com/@fixture_creator/video/7512345678901234567"
            ),
            receipt=_published_receipt(),
            acceptance_consumed=True,
            retry_allowed=False,
        )


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
def fake_publish_service(monkeypatch: pytest.MonkeyPatch) -> _FakePublishService:
    service = _FakePublishService()
    router_module = importlib.import_module("src.routers.distribution")
    monkeypatch.setattr(
        router_module,
        "get_publish_attempt_service",
        lambda: service,
        raising=False,
    )
    return service


@pytest.fixture
def tenant_auth_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, dict[str, str]]:
    from src.routers import _deps
    from src.storage import db

    raw_keys = {
        "publisher": "publish-router-publisher-api-key",
        "reviewer": "publish-router-reviewer-api-key",
        "generator": "publish-router-generator-api-key",
        "all_access": "publish-router-all-access-api-key",
    }
    permissions = {
        "publisher": ["artifact:publish"],
        "reviewer": ["artifact:accept"],
        "generator": ["provider:submit"],
        "all_access": ["all"],
    }
    tenants = {
        "publisher": "tenant-a",
        "reviewer": "tenant-a",
        "generator": "tenant-a",
        "all_access": "tenant-a",
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

    return {name: {"X-API-Key": raw_key} for name, raw_key in raw_keys.items()}


async def _asgi_request(
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json_body: object = _MISSING,
    content: bytes | None = None,
) -> Response:
    from src.api import app

    kwargs: dict[str, object] = {"headers": headers or {}}
    if json_body is not _MISSING:
        kwargs["json"] = json_body
    if content is not None:
        kwargs["content"] = content
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        return await client.request(method, path, **kwargs)


def _assert_legacy_headers(response: Response) -> None:
    assert response.headers["Deprecation"] == "true"
    assert response.headers["Link"] == SUCCESSOR_LINK


def _iter_openapi_refs(value: object) -> Iterator[str]:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str):
            yield ref
        for nested in value.values():
            yield from _iter_openapi_refs(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _iter_openapi_refs(nested)


def _resolve_local_openapi_ref(document: dict[str, Any], ref: str) -> object:
    assert ref.startswith("#/"), f"non-local OpenAPI ref: {ref}"
    current: object = document
    for raw_token in ref[2:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict), f"non-object OpenAPI ref segment: {ref}"
        assert token in current, f"unresolved OpenAPI ref: {ref}"
        current = current[token]
    return current


@pytest.mark.asyncio
@pytest.mark.parametrize("principal", ["reviewer", "generator"])
@pytest.mark.parametrize(
    "path",
    [
        "/distribution/publish",
        "/publish/client-video-label",
        "/publish/sk-secret-shaped-path.must-not-echo",
    ],
)
async def test_non_publish_permissions_are_denied_before_body_parse(
    principal: str,
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    response = await _asgi_request(
        "POST",
        path,
        headers={
            **tenant_auth_headers[principal],
            "Content-Type": "application/json",
        },
        content=b'{"credential":"must-not-be-parsed"',
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Insufficient permission"
    assert fake_publish_service.calls == []
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "content"),
    [
        ("POST", "/distribution/publish", b'{"credential":"not-parsed"'),
        ("GET", "/distribution/status/tiktok/7512345678901234567", None),
        ("GET", f"/distribution/publish-attempts/{ATTEMPT_ID}", None),
        ("GET", "/distribution/platforms", None),
        ("POST", "/publish/client-video-label", b'{"credential":"not-parsed"'),
    ],
)
@pytest.mark.parametrize("credential", [None, "invalid-publish-router-key"])
async def test_all_distribution_routes_reject_missing_or_invalid_api_keys(
    method: str,
    path: str,
    content: bytes | None,
    credential: str | None,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    del tenant_auth_headers
    headers = {"Content-Type": "application/json"}
    if credential is not None:
        headers["X-API-Key"] = credential

    response = await _asgi_request(
        method,
        path,
        headers=headers,
        content=content,
    )

    assert response.status_code == 401, response.text
    assert fake_publish_service.calls == []
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)
    else:
        assert "Deprecation" not in response.headers
        assert "Link" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/distribution/status/tiktok/7512345678901234567",
        f"/distribution/publish-attempts/{ATTEMPT_ID}",
    ],
)
@pytest.mark.parametrize("principal", ["reviewer", "generator"])
async def test_publish_readback_routes_require_publish_permission(
    path: str,
    principal: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    response = await _asgi_request(
        "GET",
        path,
        headers=tenant_auth_headers[principal],
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permission"
    assert fake_publish_service.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "body", "raw_value"),
    [
        (
            "credential_field",
            {
                **_valid_body(),
                "provider_credentials": {
                    "POYO_API_KEY": "credential-field-value-must-not-echo"
                },
            },
            "credential-field-value-must-not-echo",
        ),
        (
            "credential_shaped_value",
            {**_valid_body(), "platform": "sk-secret-shaped-value-must-not-echo"},
            "sk-secret-shaped-value-must-not-echo",
        ),
        (
            "legacy_content",
            {
                **_valid_body(),
                "content": {"title": "legacy-content-value-must-not-echo"},
            },
            "legacy-content-value-must-not-echo",
        ),
        (
            "legacy_delivery_acceptance",
            {
                **_valid_body(),
                "delivery_acceptance": {
                    "source": "human",
                    "reviewer": "reviewer-value-must-not-echo",
                    "delivery_accepted": True,
                    "publish_allowed": True,
                },
            },
            "reviewer-value-must-not-echo",
        ),
        (
            "client_video_path",
            {
                **_valid_body(),
                "metadata": {
                    "title": "Reviewed campaign",
                    "video_path": "/private/path-value-must-not-echo.mp4",
                },
            },
            "/private/path-value-must-not-echo.mp4",
        ),
        (
            "platforms_array",
            {**_valid_body(), "platforms": ["tiktok", "shopify"]},
            "shopify",
        ),
        (
            "tenant_override",
            {**_valid_body(), "tenant_id": "cross-tenant-value-must-not-echo"},
            "cross-tenant-value-must-not-echo",
        ),
        (
            "reviewer_override",
            {**_valid_body(), "reviewer": "caller-reviewer-must-not-echo"},
            "caller-reviewer-must-not-echo",
        ),
        (
            "artifact_override",
            {
                **_valid_body(),
                "artifact_path": "tenants/other/private-path-must-not-echo.mp4",
            },
            "tenants/other/private-path-must-not-echo.mp4",
        ),
        (
            "authority_override",
            {**_valid_body(), "source": "human-authority-must-not-echo"},
            "human-authority-must-not-echo",
        ),
        (
            "url_override",
            {
                **_valid_body(),
                "video_url": "https://credential.invalid/raw-value-must-not-echo",
            },
            "https://credential.invalid/raw-value-must-not-echo",
        ),
        (
            "unknown_field",
            {**_valid_body(), "unexpected": "unknown-value-must-not-echo"},
            "unknown-value-must-not-echo",
        ),
    ],
)
@pytest.mark.parametrize(
    "path",
    ["/distribution/publish", "/publish/client-video-label"],
)
async def test_strict_validation_is_safe_and_runs_before_service(
    name: str,
    body: dict[str, object],
    raw_value: str,
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    del name
    response = await _asgi_request(
        "POST",
        path,
        headers=tenant_auth_headers["publisher"],
        json_body=body,
    )

    assert response.status_code == 422, response.text
    assert raw_value not in response.text
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    assert all(
        "input" not in error
        and "ctx" not in error
        and "url" not in error
        for error in errors
    )
    assert fake_publish_service.calls == []
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["title", "description", "hook", "product_name"])
@pytest.mark.parametrize(
    "path",
    ["/distribution/publish", "/publish/client-video-label"],
)
async def test_explicit_null_metadata_text_is_safely_rejected_before_service(
    field: str,
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    response = await _asgi_request(
        "POST",
        path,
        headers=tenant_auth_headers["publisher"],
        json_body={**_valid_body(), "metadata": {field: None}},
    )

    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    assert fake_publish_service.calls == []
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("metadata", "escaped_surrogate"),
    [
        ({"title": "\ud800"}, "\\ud800"),
        ({"tags": ["\udc00"]}, "\\udc00"),
    ],
)
@pytest.mark.parametrize(
    "path",
    ["/distribution/publish", "/publish/client-video-label"],
)
async def test_invalid_unicode_metadata_is_safely_rejected_before_service(
    metadata: dict[str, object],
    escaped_surrogate: str,
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    body = {**_valid_body(), "metadata": metadata}
    response = await _asgi_request(
        "POST",
        path,
        headers={
            **tenant_auth_headers["publisher"],
            "Content-Type": "application/json",
        },
        content=json.dumps(body, ensure_ascii=True).encode("utf-8"),
    )

    assert response.status_code == 422, response.text
    assert escaped_surrogate not in response.text
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    assert any(error["type"] == "string_unicode" for error in errors)
    assert fake_publish_service.calls == []
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/distribution/publish", "/publish/client-video-label"],
)
async def test_invalid_json_uses_safe_projection_without_echo(
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    raw_value = "malformed-json-credential-must-not-echo"
    response = await _asgi_request(
        "POST",
        path,
        headers={
            **tenant_auth_headers["publisher"],
            "Content-Type": "application/json",
        },
        content=f'{{"credential":"{raw_value}"'.encode(),
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == [
        {"type": "json_invalid", "loc": ["body"], "msg": "Invalid JSON"}
    ]
    assert raw_value not in response.text
    assert fake_publish_service.calls == []
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("principal", ["publisher", "all_access"])
@pytest.mark.parametrize(
    ("path", "route_kind"),
    [
        ("/distribution/publish", "canonical"),
        ("/publish/client-video-label", "legacy_adapter"),
    ],
)
async def test_publish_principals_call_only_shared_service_with_auth_tenant(
    principal: str,
    path: str,
    route_kind: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    response = await _asgi_request(
        "POST",
        path,
        headers=tenant_auth_headers[principal],
        json_body=_valid_body(),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["publish_attempt_id"] == ATTEMPT_ID
    assert payload["acceptance_id"] == ACCEPTANCE_ID
    assert payload["platform"] == "tiktok"
    assert payload["status"] == "published"
    assert payload["success"] is True
    assert payload["receipt"] == _published_receipt()
    assert not isinstance(payload, list)
    assert len(fake_publish_service.calls) == 1
    call = fake_publish_service.calls[0]
    assert call["tenant_id"] == "tenant-a"
    assert call["route_kind"] == route_kind
    assert isinstance(call["request"], PublishAttemptRequest)
    expected_request = PublishAttemptRequest.model_validate(_valid_body())
    assert call["request"] == expected_request
    assert call["request_json"] == expected_request.model_dump(mode="json")
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)
        assert "client-video-label" not in json.dumps(call["request_json"])
        assert "client-video-label" not in response.text
    else:
        assert "Deprecation" not in response.headers
        assert "Link" not in response.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_path_value",
    _UNSAFE_LEGACY_PATHS,
)
async def test_legacy_path_parameter_is_bounded_and_never_reaches_service(
    raw_path_value: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    response = await _asgi_request(
        "POST",
        f"/publish/{raw_path_value}",
        headers=tenant_auth_headers["publisher"],
        json_body=_valid_body(),
    )

    assert response.status_code == 422, response.text
    assert raw_path_value not in response.text
    errors = response.json()["detail"]
    assert errors
    assert all(set(error) == {"type", "loc", "msg"} for error in errors)
    assert all(
        "input" not in error
        and "ctx" not in error
        and "url" not in error
        for error in errors
    )
    assert fake_publish_service.calls == []
    _assert_legacy_headers(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_path_value", _UNSAFE_LEGACY_PATHS)
@pytest.mark.parametrize("credential", [None, "invalid-publish-router-key"])
async def test_legacy_path_validation_runs_only_after_api_key_authentication(
    raw_path_value: str,
    credential: str | None,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    del tenant_auth_headers
    headers: dict[str, str] = {}
    if credential is not None:
        headers["X-API-Key"] = credential

    response = await _asgi_request(
        "POST",
        f"/publish/{raw_path_value}",
        headers=headers,
        json_body=_valid_body(),
    )

    assert response.status_code == 401, response.text
    assert fake_publish_service.calls == []
    _assert_legacy_headers(response)


_ERROR_CASES = [
    ("publish_connector_not_ready", 503, None, False, True),
    ("publish_attempt_store_unavailable", 503, None, False, True),
    ("acceptance_not_found", 404, ATTEMPT_ID, False, False),
    ("acceptance_expired", 409, ATTEMPT_ID, False, False),
    ("acceptance_not_available", 409, ATTEMPT_ID, False, False),
    ("acceptance_artifact_integrity_mismatch", 409, ATTEMPT_ID, False, False),
    ("acceptance_store_unavailable", 503, ATTEMPT_ID, False, True),
    ("publish_artifact_unavailable_after_consume", 500, ATTEMPT_ID, True, False),
    ("publish_attempt_state_unknown", 500, ATTEMPT_ID, None, False),
    ("publish_connector_failed", 502, ATTEMPT_ID, True, False),
    ("publish_outcome_ambiguous", 502, ATTEMPT_ID, True, False),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "status_code", "attempt_id", "acceptance_consumed", "retry_allowed"),
    _ERROR_CASES,
)
@pytest.mark.parametrize(
    "path",
    ["/distribution/publish", "/publish/client-video-label"],
)
async def test_typed_service_errors_preserve_only_stable_http_detail(
    code: str,
    status_code: int,
    attempt_id: str | None,
    acceptance_consumed: bool | None,
    retry_allowed: bool,
    path: str,
    tenant_auth_headers: dict[str, dict[str, str]],
    fake_publish_service: _FakePublishService,
) -> None:
    raw_exception = "connector-credential-and-exception-must-not-echo"
    error = PublishAttemptError(
        status_code=status_code,
        code=code,  # type: ignore[arg-type]
        publish_attempt_id=attempt_id,
        acceptance_consumed=acceptance_consumed,
        retry_allowed=retry_allowed,
    )
    error.raw_exception = raw_exception  # type: ignore[attr-defined]
    fake_publish_service.error = error

    response = await _asgi_request(
        "POST",
        path,
        headers=tenant_auth_headers["publisher"],
        json_body=_valid_body(),
    )

    assert response.status_code == status_code, response.text
    assert response.json()["detail"] == {
        "code": code,
        "publish_attempt_id": attempt_id,
        "acceptance_consumed": acceptance_consumed,
        "retry_allowed": retry_allowed,
    }
    assert raw_exception not in response.text
    assert len(fake_publish_service.calls) == 1
    if path.startswith("/publish/"):
        _assert_legacy_headers(response)


@pytest.mark.asyncio
async def test_deprecation_headers_do_not_leak_to_unrelated_routes(
    fake_publish_service: _FakePublishService,
) -> None:
    response = await _asgi_request("GET", "/health")

    assert response.status_code == 200, response.text
    assert fake_publish_service.calls == []
    assert "Deprecation" not in response.headers
    assert "Link" not in response.headers


def test_openapi_documents_identical_strict_bodies_and_legacy_path() -> None:
    from src.api import app

    document = app.openapi()
    paths = document["paths"]
    canonical = paths["/distribution/publish"]["post"]
    legacy = paths["/publish/{video_id}"]["post"]

    assert canonical["requestBody"]["required"] is True
    assert legacy["requestBody"]["required"] is True
    assert legacy["deprecated"] is True
    assert canonical["requestBody"] == legacy["requestBody"]
    publish_schema = canonical["requestBody"]["content"]["application/json"][
        "schema"
    ]
    model_schema = PublishAttemptRequest.model_json_schema(mode="validation")
    model_definitions = model_schema.pop("$defs")
    model_schema["properties"]["metadata"]["$ref"] = (
        "#/components/schemas/PublishMetadata"
    )
    platform_options = model_schema["properties"]["platform_options"]
    platform_options["discriminator"]["mapping"] = {
        key: value.replace("#/$defs/", "#/components/schemas/")
        for key, value in platform_options["discriminator"]["mapping"].items()
    }
    for variant in platform_options["oneOf"]:
        variant["$ref"] = variant["$ref"].replace(
            "#/$defs/", "#/components/schemas/"
        )
    assert publish_schema == model_schema
    assert document["components"]["schemas"]["PublishMetadata"] == (
        model_definitions["PublishMetadata"]
    )
    for name in ("TikTokPublishOptions", "ShopifyPublishOptions"):
        assert document["components"]["schemas"][name] == model_definitions[name]
    legacy_path = next(
        parameter
        for parameter in legacy["parameters"]
        if parameter["in"] == "path" and parameter["name"] == "video_id"
    )
    assert legacy_path["required"] is True
    assert legacy_path["schema"]["minLength"] == 1
    assert legacy_path["schema"]["maxLength"] == 128
    assert legacy_path["schema"]["pattern"] == "^[A-Za-z0-9_-]+$"
    assert not any(path.endswith("/consume") for path in paths)


def test_openapi_declares_safe_success_and_error_responses() -> None:
    from src.api import app

    paths = app.openapi()["paths"]
    expected_statuses = {"200", "401", "403", "404", "409", "422", "500", "502", "503"}
    success_schema = {"$ref": "#/components/schemas/PublishAttemptResponse"}
    error_schema = {"$ref": "#/components/schemas/PublishAttemptErrorResponse"}

    for route_path in ("/distribution/publish", "/publish/{video_id}"):
        responses = paths[route_path]["post"]["responses"]
        assert expected_statuses <= responses.keys()
        assert responses["200"]["content"]["application/json"]["schema"] == success_schema
        for status in ("404", "409", "500", "502", "503"):
            assert responses[status]["content"]["application/json"]["schema"] == error_schema
        assert responses["422"]["description"] == "Safe validation projection"

    assert PublishAttemptResponse.model_json_schema(mode="validation")
    assert PublishAttemptErrorResponse.model_json_schema(mode="validation")


def test_publish_request_schema_refs_resolve_from_openapi_root() -> None:
    from src.api import app

    document = app.openapi()
    for route_path in ("/distribution/publish", "/publish/{video_id}"):
        request_schema = document["paths"][route_path]["post"]["requestBody"][
            "content"
        ]["application/json"]["schema"]
        for ref in _iter_openapi_refs(request_schema):
            _resolve_local_openapi_ref(document, ref)


def test_publish_openapi_component_collision_fails_without_partial_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api_module = importlib.import_module("src.api")
    request_body = {
        "required": True,
        "description": "sentinel request body",
        "content": {
            "application/json": {
                "schema": {"type": "object", "title": "sentinel request"},
                "examples": {"sentinel": {"value": {"platform": "tiktok"}}},
            }
        },
    }
    document = {
        "components": {
            "schemas": {
                "PublishMetadata": {"type": "string", "title": "collision"}
            }
        },
        "paths": {
            "/distribution/publish": {
                "post": {"requestBody": deepcopy(request_body)}
            },
            "/publish/{video_id}": {
                "post": {"requestBody": deepcopy(request_body)}
            },
        },
    }
    original = deepcopy(document)
    monkeypatch.setattr(api_module, "_fastapi_openapi", lambda: document)

    with pytest.raises(
        RuntimeError,
        match="OpenAPI component collision: PublishMetadata",
    ):
        api_module._openapi_with_exact_publish_request_schema()

    assert document == original
