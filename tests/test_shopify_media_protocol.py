"""W1-25 hermetic Shopify Admin GraphQL 2026-07 video protocol contracts."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.connectors.base import (
    ConnectorOutcomeAmbiguous,
    ConnectorPreflightRejected,
    ConnectorPreflightUnavailable,
    ShopifyPreflightSnapshot,
)
from src.connectors.shopify_connector import (
    ShopifyConnector,
    _default_media_probe,
    _graphql_url,
)
from src.models.publish_attempt import PublishReceiptV1

NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
STORE = "fixture-store.myshopify.com"
GRAPHQL_URL = f"https://{STORE}/admin/api/2026-07/graphql.json"
PRODUCT_ID = "gid://shopify/Product/1234567890"
VIDEO_ID = "gid://shopify/Video/7512345678901234567"
STAGED_URL = "https://shopify-staged-uploads.storage.googleapis.com/"
RESOURCE_URL = "https://shopify-video-production-core-originals.storage.googleapis.com/video"


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: object,
        *,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> object:
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class ProtocolClient:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, str], deque[object]] = defaultdict(deque)
        self.calls: list[dict[str, Any]] = []

    def queue(self, method: str, url: str, *responses: object) -> None:
        self.responses[(method, url)].extend(responses)

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": "POST", "url": url, **kwargs})
        queued = self.responses[("POST", url)]
        if not queued:
            raise AssertionError("unexpected POST request")
        value = queued.popleft()
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, FakeResponse)
        for file_value in (kwargs.get("files") or {}).values():
            if (
                isinstance(file_value, tuple)
                and len(file_value) >= 2
                and hasattr(file_value[1], "close")
            ):
                file_value[1].close()
        return value


def _data(data: object) -> FakeResponse:
    return FakeResponse(200, {"data": data})


def _mutation(field: str, body: dict[str, object]) -> FakeResponse:
    return _data({field: {**body, "userErrors": []}})


def _preflight_data(
    *,
    product: object = None,
    scopes: tuple[str, ...] = ("read_products", "write_products", "write_files"),
) -> FakeResponse:
    if product is None:
        product = {"id": PRODUCT_ID}
    return _data(
        {
            "product": product,
            "currentAppInstallation": {
                "accessScopes": [{"handle": scope} for scope in scopes]
            },
        }
    )


def _content(video: Path, **overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "video_path": str(video),
        "title": "Reviewed title",
        "product_name": "Display only product name",
        "platform_options": {
            "platform": "shopify",
            "product_id": PRODUCT_ID,
        },
    }
    content.update(overrides)
    return content


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-shopify-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", STORE)
    for name in (
        "SHOPIFY_API_KEY",
        "SHOPIFY_ADMIN_TOKEN",
        "SHOPIFY_API_PASSWORD",
        "SHOPIFY_GRAPHQL_URL_TEMPLATE",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "reviewed.mp4"
    path.write_bytes(b"0123456789")
    return path


def _connector(client: ProtocolClient, *, duration: float = 12.5) -> ShopifyConnector:
    async def no_sleep(_: float) -> None:
        return None

    return ShopifyConnector(
        http_client=client,  # type: ignore[arg-type]
        media_probe=lambda _: duration,
        sleep=no_sleep,
        monotonic=lambda: 0.0,
        now=lambda: NOW,
        max_status_polls=3,
        poll_interval_seconds=0.0,
        poll_deadline_seconds=30.0,
    )


def _queue_preflight(client: ProtocolClient, response: object | None = None) -> None:
    client.queue("POST", GRAPHQL_URL, response or _preflight_data())


def _queue_staged(client: ProtocolClient, *, url: str = STAGED_URL) -> None:
    client.queue(
        "POST",
        GRAPHQL_URL,
        _mutation(
            "stagedUploadsCreate",
            {
                "stagedTargets": [
                    {
                        "url": url,
                        "resourceUrl": RESOURCE_URL,
                        "parameters": [
                            {"name": "key", "value": "fixture-key"},
                            {"name": "policy", "value": "fixture-policy"},
                        ],
                    }
                ]
            },
        ),
    )


def _queue_file_create(client: ProtocolClient, *, video_id: str = VIDEO_ID) -> None:
    client.queue(
        "POST",
        GRAPHQL_URL,
        _mutation(
            "fileCreate",
            {"files": [{"id": video_id, "fileStatus": "UPLOADED"}]},
        ),
    )


def _queue_ready_and_association(client: ProtocolClient) -> None:
    client.queue(
        "POST",
        GRAPHQL_URL,
        _data({"node": {"id": VIDEO_ID, "fileStatus": "PROCESSING"}}),
        _data({"node": {"id": VIDEO_ID, "fileStatus": "READY"}}),
        _mutation("fileUpdate", {"files": [{"id": VIDEO_ID}]}),
        _data(
            {
                "product": {
                    "id": PRODUCT_ID,
                    "media": {"nodes": [{"id": VIDEO_ID}]},
                }
            }
        ),
    )


@pytest.mark.asyncio
async def test_preflight_checks_exact_product_scopes_and_media(video: Path) -> None:
    client = ProtocolClient()
    _queue_preflight(client)

    snapshot = await _connector(client).preflight(_content(video))

    assert snapshot == ShopifyPreflightSnapshot(
        product_id=PRODUCT_ID,
        required_scopes_verified=True,
        media_duration_seconds=12.5,
        observed_at=NOW,
    )
    call = client.calls[0]
    assert call["url"] == GRAPHQL_URL
    assert "PublishPreflight" in call["json"]["query"]
    assert call["json"]["variables"] == {"productId": PRODUCT_ID}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _preflight_data(product=False),
        _preflight_data(scopes=("read_products", "write_products")),
        FakeResponse(403, {}),
        _data(
            {
                "product": {"id": "gid://shopify/Product/999"},
                "currentAppInstallation": {
                    "accessScopes": [
                        {"handle": "read_products"},
                        {"handle": "write_products"},
                        {"handle": "write_files"},
                    ]
                },
            }
        ),
    ],
)
async def test_preflight_deterministic_product_or_scope_rejection(
    video: Path,
    response: FakeResponse,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client, response)

    with pytest.raises(ConnectorPreflightRejected):
        await _connector(client).preflight(_content(video))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        TimeoutError("raw-timeout"),
        FakeResponse(503, {}),
        FakeResponse(200, {}, json_error=ValueError("raw-json")),
        _data({"product": {"id": PRODUCT_ID}}),
    ],
)
async def test_preflight_uncertainty_is_unavailable(
    video: Path,
    response: object,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client, response)

    with pytest.raises(ConnectorPreflightUnavailable):
        await _connector(client).preflight(_content(video))


@pytest.mark.asyncio
async def test_media_limit_rejects_more_than_ten_minutes(video: Path) -> None:
    client = ProtocolClient()

    with pytest.raises(ConnectorPreflightRejected):
        await _connector(client, duration=600.001).preflight(_content(video))
    assert client.calls == []


@pytest.mark.asyncio
async def test_unsafe_media_is_rejected_before_network(
    video: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = ProtocolClient()
    connector = _connector(client)
    connector._media_probe = _default_media_probe
    subprocess_calls: list[object] = []

    def fail_if_called(*args: object, **kwargs: object) -> None:
        subprocess_calls.append((args, kwargs))
        raise AssertionError("unsafe media reached ffprobe")

    monkeypatch.setattr("src.connectors.shopify_connector.subprocess.run", fail_if_called)

    with pytest.raises(ConnectorPreflightRejected):
        await connector.preflight(_content(video))
    assert client.calls == []
    assert subprocess_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["oversized", "unsupported_suffix"])
async def test_media_size_and_format_reject_before_network(
    video: Path,
    kind: str,
) -> None:
    client = ProtocolClient()
    if kind == "oversized":
        candidate = video.parent / "oversized.mp4"
        with candidate.open("wb") as stream:
            stream.truncate(1024 * 1024 * 1024 + 1)
    else:
        candidate = video.with_suffix(".avi")
        candidate.write_bytes(b"fixture")

    with pytest.raises(ConnectorPreflightRejected):
        await _connector(client).preflight(_content(candidate))
    assert client.calls == []


@pytest.mark.asyncio
async def test_success_protocol_is_exact_order_and_returns_scoped_receipt(
    video: Path,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client)
    client.queue("POST", STAGED_URL, FakeResponse(201, {}))
    _queue_file_create(client)
    _queue_ready_and_association(client)
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    result = await connector.publish(content, preflight=preflight)

    assert [call["url"] for call in client.calls] == [
        GRAPHQL_URL,
        GRAPHQL_URL,
        STAGED_URL,
        GRAPHQL_URL,
        GRAPHQL_URL,
        GRAPHQL_URL,
        GRAPHQL_URL,
        GRAPHQL_URL,
    ]
    graphql_calls = [call for call in client.calls if call["url"] == GRAPHQL_URL]
    assert [
        next(
            name
            for name in (
                "PublishPreflight",
                "StagedUploadsCreate",
                "FileCreate",
                "VideoStatus",
                "FileUpdate",
                "ProductMediaReadback",
            )
            if name in call["json"]["query"]
        )
        for call in graphql_calls
    ] == [
        "PublishPreflight",
        "StagedUploadsCreate",
        "FileCreate",
        "VideoStatus",
        "VideoStatus",
        "FileUpdate",
        "ProductMediaReadback",
    ]
    staged_variables = graphql_calls[1]["json"]["variables"]
    assert staged_variables == {
        "input": [
            {
                "resource": "VIDEO",
                "filename": "reviewed.mp4",
                "mimeType": "video/mp4",
                "fileSize": "10",
            }
        ]
    }
    upload = client.calls[2]
    assert upload["follow_redirects"] is False
    assert "headers" not in upload
    assert upload["data"] == {"key": "fixture-key", "policy": "fixture-policy"}
    assert upload["files"]["file"][0] == "reviewed.mp4"
    assert "fixture-shopify-token" not in repr(upload)
    assert "Display only product name" not in repr(client.calls)
    assert graphql_calls[2]["json"]["variables"] == {
        "files": [
            {
                "alt": "Reviewed title",
                "contentType": "VIDEO",
                "originalSource": RESOURCE_URL,
            }
        ]
    }
    assert graphql_calls[5]["json"]["variables"] == {
        "files": [{"id": VIDEO_ID, "referencesToAdd": [PRODUCT_ID]}]
    }
    assert graphql_calls[6]["json"]["variables"] == {"productId": PRODUCT_ID}
    receipt = PublishReceiptV1.model_validate(result["receipt"])
    receipt.validate_published()
    assert receipt.provider_resource_id == VIDEO_ID
    assert receipt.target_id == PRODUCT_ID
    assert receipt.post_id is None
    assert receipt.post_url is None
    assert receipt.public_visibility_verified is False


@pytest.mark.asyncio
async def test_publish_requires_retained_matching_preflight_without_network(
    video: Path,
) -> None:
    client = ProtocolClient()
    connector = _connector(client)

    with pytest.raises(ConnectorPreflightUnavailable):
        await connector.publish(_content(video), preflight=None)
    assert client.calls == []


@pytest.mark.asyncio
async def test_failed_file_status_is_deterministic_with_partial_receipt(
    video: Path,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client)
    client.queue("POST", STAGED_URL, FakeResponse(201, {}))
    _queue_file_create(client)
    client.queue(
        "POST",
        GRAPHQL_URL,
        _data({"node": {"id": VIDEO_ID, "fileStatus": "FAILED"}}),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    result = await connector.publish(content, preflight=preflight)

    assert result["success"] is False
    assert result["error"] == "shopify_publish_failed"
    receipt = PublishReceiptV1.model_validate(result["receipt"])
    assert receipt.provider_status == "FAILED"
    assert receipt.provider_resource_id == VIDEO_ID


@pytest.mark.asyncio
async def test_poll_timeout_is_ambiguous_without_recreating_file(video: Path) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client)
    client.queue("POST", STAGED_URL, FakeResponse(201, {}))
    _queue_file_create(client)
    client.queue(
        "POST",
        GRAPHQL_URL,
        *[
            _data({"node": {"id": VIDEO_ID, "fileStatus": "PROCESSING"}})
            for _ in range(3)
        ],
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous) as exc_info:
        await connector.publish(content, preflight=preflight)

    partial = PublishReceiptV1.model_validate(dict(exc_info.value.partial_receipt))
    assert partial.provider_status == "PROCESSING"
    assert sum(
        "FileCreate" in call.get("json", {}).get("query", "")
        for call in client.calls
    ) == 1


@pytest.mark.asyncio
async def test_unsafe_staged_target_is_ambiguous_without_upload(video: Path) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client, url="https://127.0.0.1/private")
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await connector.publish(content, preflight=preflight)

    assert [call["url"] for call in client.calls] == [GRAPHQL_URL, GRAPHQL_URL]


@pytest.mark.asyncio
async def test_file_create_requires_exact_video_gid(video: Path) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client)
    client.queue("POST", STAGED_URL, FakeResponse(201, {}))
    _queue_file_create(client, video_id="gid://shopify/MediaImage/123")
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await connector.publish(content, preflight=preflight)


@pytest.mark.asyncio
async def test_missing_association_readback_is_ambiguous_and_not_retried(
    video: Path,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client)
    client.queue("POST", STAGED_URL, FakeResponse(201, {}))
    _queue_file_create(client)
    client.queue(
        "POST",
        GRAPHQL_URL,
        _data({"node": {"id": VIDEO_ID, "fileStatus": "READY"}}),
        _mutation("fileUpdate", {"files": [{"id": VIDEO_ID}]}),
        _data({"product": {"id": PRODUCT_ID, "media": {"nodes": []}}}),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous) as exc_info:
        await connector.publish(content, preflight=preflight)

    partial = PublishReceiptV1.model_validate(dict(exc_info.value.partial_receipt))
    assert partial.provider_status == "READY"
    assert partial.verified_by is None
    assert sum(
        "FileUpdate" in call.get("json", {}).get("query", "")
        for call in client.calls
    ) == 1


@pytest.mark.asyncio
async def test_file_update_user_error_is_deterministic_without_readback(
    video: Path,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    _queue_staged(client)
    client.queue("POST", STAGED_URL, FakeResponse(201, {}))
    _queue_file_create(client)
    client.queue(
        "POST",
        GRAPHQL_URL,
        _data({"node": {"id": VIDEO_ID, "fileStatus": "READY"}}),
        _data(
            {
                "fileUpdate": {
                    "files": [],
                    "userErrors": [
                        {"field": ["files"], "message": "private provider text"}
                    ],
                }
            }
        ),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    result = await connector.publish(content, preflight=preflight)

    assert result["success"] is False
    receipt = PublishReceiptV1.model_validate(result["receipt"])
    assert receipt.provider_status == "READY"
    assert receipt.verified_by is None
    assert all(
        "ProductMediaReadback" not in call.get("json", {}).get("query", "")
        for call in client.calls
    )
    assert "private provider text" not in repr(result)


@pytest.mark.asyncio
async def test_failure_logs_hide_token_path_product_and_staged_values(
    video: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = ProtocolClient()
    _queue_preflight(client)
    client.queue(
        "POST",
        GRAPHQL_URL,
        TimeoutError("raw-provider-secret-shaped-sentinel"),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await connector.publish(content, preflight=preflight)

    assert "raw-provider-secret-shaped-sentinel" not in caplog.text
    assert "fixture-shopify-token" not in caplog.text
    assert "Display only product name" not in caplog.text
    assert str(video) not in caplog.text


def test_graphql_url_is_pinned_and_rejects_noncanonical_store_hosts() -> None:
    assert _graphql_url(STORE) == GRAPHQL_URL
    for value in (
        "https://fixture-store.myshopify.com",
        "fixture-store.myshopify.com/path",
        "FIXTURE-STORE.myshopify.com",
        "127.0.0.1",
    ):
        with pytest.raises(ValueError):
            _graphql_url(value)
