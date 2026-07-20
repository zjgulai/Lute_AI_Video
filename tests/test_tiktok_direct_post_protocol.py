"""W1-25 hermetic TikTok Content Posting API v2 protocol contracts."""

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
    TikTokPreflightSnapshot,
)
from src.connectors.tiktok_connector import (
    _TIKTOK_CREATOR_INFO_URL,
    _TIKTOK_DIRECT_POST_INIT_URL,
    _TIKTOK_STATUS_FETCH_URL,
    _TIKTOK_VIDEO_QUERY_URL,
    TikTokConnector,
    _build_chunk_plan,
    _default_media_probe,
)
from src.models.publish_attempt import PublishReceiptV1

NOW = datetime(2026, 7, 14, 8, 0, tzinfo=UTC)
PUBLISH_ID = "v_pub_file_fixture_123"
POST_ID = "7512345678901234567"
UPLOAD_URL = (
    "https://open-upload.tiktokapis.com/video/"
    "?upload_id=fixture&upload_token=fixture-signed-value"
)


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
        return self._next("POST", url, kwargs)

    async def put(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._next("PUT", url, kwargs)

    def _next(self, method: str, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        queued = self.responses[(method, url)]
        if not queued:
            raise AssertionError(f"unexpected {method} request")
        value = queued.popleft()
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, FakeResponse)
        return value


def _ok(data: object) -> FakeResponse:
    return FakeResponse(
        200,
        {
            "data": data,
            "error": {"code": "ok", "message": "", "log_id": "fixture"},
        },
    )


def _creator_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "creator_avatar_url": "https://pii.invalid/avatar",
        "creator_username": "private-creator",
        "creator_nickname": "Private Creator",
        "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
        "comment_disabled": False,
        "duet_disabled": False,
        "stitch_disabled": False,
        "max_video_post_duration_sec": 300,
    }
    data.update(overrides)
    return data


def _content(video: Path, **overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "video_path": str(video),
        "title": "Reviewed title",
        "description": "Reviewed caption",
        "tags": [],
        "platform_options": {
            "platform": "tiktok",
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_comment": False,
            "disable_duet": False,
            "disable_stitch": False,
            "brand_content_toggle": True,
            "brand_organic_toggle": False,
        },
    }
    content.update(overrides)
    return content


@pytest.fixture(autouse=True)
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-tiktok-token")
    for name in (
        "TIKTOK_USERNAME",
        "TIKTOK_API_UPLOAD_URL",
        "TIKTOK_API_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "reviewed.mp4"
    path.write_bytes(b"0123456789")
    return path


def _connector(client: ProtocolClient, *, duration: float = 12.5) -> TikTokConnector:
    async def no_sleep(_: float) -> None:
        return None

    return TikTokConnector(
        http_client=client,  # type: ignore[arg-type]
        media_probe=lambda _: duration,
        sleep=no_sleep,
        monotonic=lambda: 0.0,
        now=lambda: NOW,
        max_status_polls=3,
        poll_interval_seconds=0.0,
        poll_deadline_seconds=30.0,
    )


@pytest.mark.asyncio
async def test_preflight_validates_creator_options_and_keeps_no_pii(
    video: Path,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    connector = _connector(client)

    snapshot = await connector.preflight(_content(video))

    assert snapshot == TikTokPreflightSnapshot(
        privacy_level="PUBLIC_TO_EVERYONE",
        disable_comment=False,
        disable_duet=False,
        disable_stitch=False,
        brand_content_toggle=True,
        brand_organic_toggle=False,
        max_video_post_duration_sec=300,
        media_duration_seconds=12.5,
        observed_at=NOW,
    )
    assert "private-creator" not in repr(snapshot)
    assert [call["url"] for call in client.calls] == [_TIKTOK_CREATOR_INFO_URL]
    assert client.calls[0]["json"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("creator_overrides", "content_overrides"),
    [
        ({"privacy_level_options": ["SELF_ONLY"]}, {}),
        ({"comment_disabled": True}, {}),
        ({"duet_disabled": True}, {}),
        ({"stitch_disabled": True}, {}),
        ({"max_video_post_duration_sec": 10}, {}),
        ({}, {"description": "x" * 2201}),
    ],
)
async def test_preflight_rejects_incompatible_creator_or_caption_contract(
    video: Path,
    creator_overrides: dict[str, object],
    content_overrides: dict[str, object],
) -> None:
    client = ProtocolClient()
    client.queue(
        "POST",
        _TIKTOK_CREATOR_INFO_URL,
        _ok(_creator_data(**creator_overrides)),
    )

    with pytest.raises(ConnectorPreflightRejected):
        await _connector(client).preflight(_content(video, **content_overrides))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        TimeoutError("secret-provider-timeout"),
        FakeResponse(503, {}),
        FakeResponse(200, {}, json_error=ValueError("raw-body")),
        _ok({"privacy_level_options": "PUBLIC_TO_EVERYONE"}),
    ],
)
async def test_preflight_uncertainty_is_unavailable(
    video: Path,
    response: object,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, response)

    with pytest.raises(ConnectorPreflightUnavailable):
        await _connector(client).preflight(_content(video))


@pytest.mark.asyncio
async def test_media_probe_failure_is_unavailable_before_network(video: Path) -> None:
    client = ProtocolClient()

    def broken_probe(_: Path) -> float:
        raise RuntimeError("private-local-path")

    connector = _connector(client)
    connector._media_probe = broken_probe

    with pytest.raises(ConnectorPreflightUnavailable):
        await connector.preflight(_content(video))
    assert client.calls == []


@pytest.mark.asyncio
async def test_unsafe_media_is_rejected_before_network(video: Path) -> None:
    client = ProtocolClient()
    connector = _connector(client)
    connector._media_probe = _default_media_probe

    with pytest.raises(ConnectorPreflightRejected):
        await connector.preflight(_content(video))
    assert client.calls == []


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (1, ((0, 0),)),
        (5 * 1024 * 1024 - 1, ((0, 5 * 1024 * 1024 - 2),)),
        (5 * 1024 * 1024, ((0, 5 * 1024 * 1024 - 1),)),
        (
            64 * 1024 * 1024 + 7,
            ((0, 64 * 1024 * 1024 - 1), (64 * 1024 * 1024, 64 * 1024 * 1024 + 6)),
        ),
    ],
)
def test_chunk_plan_is_ordered_and_bounded(
    size: int,
    expected: tuple[tuple[int, int], ...],
) -> None:
    assert _build_chunk_plan(size) == expected


@pytest.mark.asyncio
async def test_direct_post_success_uses_one_init_ordered_upload_and_exact_receipt(
    video: Path,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue(
        "POST",
        _TIKTOK_STATUS_FETCH_URL,
        _ok(
            {
                "status": "PROCESSING_UPLOAD",
                "publicaly_available_post_id": [],
            }
        ),
        _ok(
            {
                "status": "PUBLISH_COMPLETE",
                "publicaly_available_post_id": [POST_ID],
            }
        ),
    )
    client.queue(
        "POST",
        _TIKTOK_VIDEO_QUERY_URL,
        _ok(
            {
                "videos": [
                    {
                        "id": POST_ID,
                        "share_url": (
                            f"https://www.tiktok.com/@fixture/video/{POST_ID}"
                        ),
                    }
                ]
            }
        ),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    result = await connector.publish(content, preflight=preflight)

    assert [call["url"] for call in client.calls] == [
        _TIKTOK_CREATOR_INFO_URL,
        _TIKTOK_DIRECT_POST_INIT_URL,
        UPLOAD_URL,
        _TIKTOK_STATUS_FETCH_URL,
        _TIKTOK_STATUS_FETCH_URL,
        _TIKTOK_VIDEO_QUERY_URL,
    ]
    init = client.calls[1]["json"]
    assert init["source_info"] == {
        "source": "FILE_UPLOAD",
        "video_size": 10,
        "chunk_size": 10,
        "total_chunk_count": 1,
    }
    assert init["post_info"]["is_aigc"] is True
    assert init["post_info"]["privacy_level"] == "PUBLIC_TO_EVERYONE"
    upload = client.calls[2]
    assert upload["content"] == b"0123456789"
    assert upload["headers"]["Content-Range"] == "bytes 0-9/10"
    assert upload["headers"]["Content-Length"] == "10"
    assert upload["follow_redirects"] is False
    assert result["success"] is True
    assert result["simulated"] is False
    assert result["post_id"] == POST_ID
    receipt = PublishReceiptV1.model_validate(result["receipt"])
    receipt.validate_published()
    assert receipt.provider_operation_id == PUBLISH_ID
    assert receipt.post_url == f"https://www.tiktok.com/@fixture/video/{POST_ID}"


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
async def test_provider_failed_status_is_deterministic_with_partial_receipt(
    video: Path,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue(
        "POST",
        _TIKTOK_STATUS_FETCH_URL,
        _ok({"status": "FAILED", "publicaly_available_post_id": []}),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    result = await connector.publish(content, preflight=preflight)

    assert result["success"] is False
    assert result["error"] == "tiktok_publish_failed"
    receipt = PublishReceiptV1.model_validate(result["receipt"])
    assert receipt.provider_status == "FAILED"
    assert receipt.post_id is None
    assert [call["url"] for call in client.calls].count(
        _TIKTOK_DIRECT_POST_INIT_URL
    ) == 1


@pytest.mark.asyncio
async def test_poll_budget_exhaustion_is_ambiguous_without_reinitialization(
    video: Path,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue(
        "POST",
        _TIKTOK_STATUS_FETCH_URL,
        *[
            _ok(
                {
                    "status": "PROCESSING_UPLOAD",
                    "publicaly_available_post_id": [],
                }
            )
            for _ in range(3)
        ],
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous) as exc_info:
        await connector.publish(content, preflight=preflight)

    assert exc_info.value.partial_receipt is not None
    partial = PublishReceiptV1.model_validate(dict(exc_info.value.partial_receipt))
    assert partial.provider_operation_id == PUBLISH_ID
    assert partial.provider_status == "PROCESSING_UPLOAD"
    assert [call["url"] for call in client.calls].count(
        _TIKTOK_DIRECT_POST_INIT_URL
    ) == 1
    assert [call["url"] for call in client.calls].count(
        _TIKTOK_STATUS_FETCH_URL
    ) == 3


@pytest.mark.asyncio
async def test_unsafe_upload_url_is_ambiguous_and_never_uploaded(video: Path) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok(
            {
                "publish_id": PUBLISH_ID,
                "upload_url": "https://169.254.169.254/private",
            }
        ),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await connector.publish(content, preflight=preflight)
    assert all(call["method"] != "PUT" for call in client.calls)


@pytest.mark.asyncio
async def test_provider_failure_logs_do_not_expose_token_path_or_raw_message(
    video: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        TimeoutError("raw-provider-secret-shaped-sentinel"),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous):
        await connector.publish(content, preflight=preflight)

    assert "raw-provider-secret-shaped-sentinel" not in caplog.text
    assert "fixture-tiktok-token" not in caplog.text
    assert str(video) not in caplog.text
    assert "private-creator" not in caplog.text


@pytest.mark.asyncio
async def test_conflicting_public_ids_are_ambiguous_with_sanitized_receipt(
    video: Path,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue(
        "POST",
        _TIKTOK_STATUS_FETCH_URL,
        _ok(
            {
                "status": "PUBLISH_COMPLETE",
                "publicaly_available_post_id": [POST_ID, "7512345678901234568"],
            }
        ),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous) as exc_info:
        await connector.publish(content, preflight=preflight)

    partial = PublishReceiptV1.model_validate(dict(exc_info.value.partial_receipt))
    assert partial.provider_status == "PUBLISH_COMPLETE"
    assert partial.post_id is None
    assert partial.verified_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status_payload",
    [
        {"status": "UNKNOWN", "publicaly_available_post_id": []},
        {"status": "PROCESSING_UPLOAD"},
        {"status": "PROCESSING_UPLOAD", "publicaly_available_post_id": ""},
    ],
)
async def test_unknown_or_drifted_status_is_ambiguous(
    video: Path,
    status_payload: dict[str, object],
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue("POST", _TIKTOK_STATUS_FETCH_URL, _ok(status_payload))
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous) as exc_info:
        await connector.publish(content, preflight=preflight)

    assert exc_info.value.partial_receipt is not None
    assert [call["url"] for call in client.calls].count(
        _TIKTOK_DIRECT_POST_INIT_URL
    ) == 1


@pytest.mark.asyncio
async def test_unsafe_video_query_share_url_makes_receipt_ambiguous(
    video: Path,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue(
        "POST",
        _TIKTOK_STATUS_FETCH_URL,
        _ok(
            {
                "status": "PUBLISH_COMPLETE",
                "publicaly_available_post_id": [POST_ID],
            }
        ),
    )
    client.queue(
        "POST",
        _TIKTOK_VIDEO_QUERY_URL,
        _ok(
            {
                "videos": [
                    {
                        "id": POST_ID,
                        "share_url": (
                            f"https://www.tiktok.com/@fixture/video/{POST_ID}"
                            "?token=unsafe"
                        ),
                    }
                ]
            }
        ),
    )
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    with pytest.raises(ConnectorOutcomeAmbiguous) as exc_info:
        await connector.publish(content, preflight=preflight)

    partial = PublishReceiptV1.model_validate(dict(exc_info.value.partial_receipt))
    assert partial.provider_status == "PUBLISH_COMPLETE"
    assert partial.post_id is None
    assert partial.post_url is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query_response",
    [
        FakeResponse(403, {}),
        FakeResponse(
            200,
            {
                "data": {},
                "error": {
                    "code": "scope_not_authorized",
                    "message": "private provider message",
                    "log_id": "fixture",
                },
            },
        ),
    ],
)
async def test_video_query_scope_failure_keeps_status_verified_receipt(
    video: Path,
    query_response: FakeResponse,
) -> None:
    client = ProtocolClient()
    client.queue("POST", _TIKTOK_CREATOR_INFO_URL, _ok(_creator_data()))
    client.queue(
        "POST",
        _TIKTOK_DIRECT_POST_INIT_URL,
        _ok({"publish_id": PUBLISH_ID, "upload_url": UPLOAD_URL}),
    )
    client.queue("PUT", UPLOAD_URL, FakeResponse(201, {}))
    client.queue(
        "POST",
        _TIKTOK_STATUS_FETCH_URL,
        _ok(
            {
                "status": "PUBLISH_COMPLETE",
                "publicaly_available_post_id": [POST_ID],
            }
        ),
    )
    client.queue("POST", _TIKTOK_VIDEO_QUERY_URL, query_response)
    connector = _connector(client)
    content = _content(video)
    preflight = await connector.preflight(content)

    result = await connector.publish(content, preflight=preflight)

    receipt = PublishReceiptV1.model_validate(result["receipt"])
    assert receipt.verified_by == "status_fetch"
    assert receipt.post_id == POST_ID
    assert receipt.post_url is None
