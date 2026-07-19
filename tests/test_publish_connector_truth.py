from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest

from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorPreflightRejected,
    ConnectorStatusUnavailable,
)

_CREDENTIAL_ENV = (
    "TIKTOK_ACCESS_TOKEN",
    "TIKTOK_PUBLISH_ENABLED",
    "TIKTOK_USERNAME",
    "TIKTOK_API_UPLOAD_URL",
    "TIKTOK_API_BASE_URL",
    "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_PUBLISH_ENABLED",
    "SHOPIFY_API_KEY",
    "SHOPIFY_ADMIN_TOKEN",
    "SHOPIFY_API_PASSWORD",
    "SHOPIFY_GRAPHQL_URL_TEMPLATE",
    "SHOPIFY_STORE_URL",
)


class ForbiddenAsyncClient:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("network client construction is forbidden")


@pytest.fixture(autouse=True)
def forbid_real_http(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.connectors.shopify_connector as shopify_module
    import src.connectors.tiktok_connector as tiktok_module

    monkeypatch.setattr(tiktok_module.httpx, "AsyncClient", ForbiddenAsyncClient)
    monkeypatch.setattr(shopify_module.httpx, "AsyncClient", ForbiddenAsyncClient)
    for name in (
        "TIKTOK_USERNAME",
        "TIKTOK_API_UPLOAD_URL",
        "TIKTOK_API_BASE_URL",
        "SHOPIFY_API_KEY",
        "SHOPIFY_ADMIN_TOKEN",
        "SHOPIFY_API_PASSWORD",
        "SHOPIFY_GRAPHQL_URL_TEMPLATE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")


def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _CREDENTIAL_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")


@pytest.mark.parametrize("token", [None, "", "   ", "\t\n"])
def test_tiktok_readiness_rejects_missing_or_blank_token(
    token: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.tiktok_connector import _credential_state

    _clear_credentials(monkeypatch)
    if token is not None:
        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", token)

    state = _credential_state()
    readiness = inspect_publish_readiness("tiktok")

    assert state.ready is False
    assert state.reason == "missing_credentials"
    assert readiness.platform == "tiktok"
    assert readiness.ready is False
    assert readiness.reason == state.reason


def test_tiktok_readiness_accepts_trimmed_nonempty_fixture_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.tiktok_connector import _require_access_token

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "  fixture-tiktok-token  ")

    assert _require_access_token() == "fixture-tiktok-token"
    assert inspect_publish_readiness("tiktok").ready is True


@pytest.mark.parametrize(
    ("access_token", "legacy_token", "store", "reason"),
    [
        (None, None, None, "missing_credentials"),
        ("", "", "fixture-store.myshopify.com", "missing_credentials"),
        ("   ", None, "fixture-store.myshopify.com", "missing_credentials"),
        ("fixture-token", None, None, "missing_credentials"),
        (None, "fixture-legacy", "", "invalid_configuration"),
        (
            "fixture-token",
            None,
            "https://fixture.myshopify.com",
            "invalid_configuration",
        ),
        (
            "fixture-token",
            None,
            "fixture.myshopify.com/path",
            "invalid_configuration",
        ),
        (
            "fixture-token",
            None,
            "user@fixture.myshopify.com",
            "invalid_configuration",
        ),
        (
            "fixture-token",
            None,
            "fixture.myshopify.com?x=1",
            "invalid_configuration",
        ),
        (
            "fixture-token",
            None,
            "fixture.myshopify.com#x",
            "invalid_configuration",
        ),
        (
            "fixture-token",
            None,
            " fixture.myshopify.com",
            "invalid_configuration",
        ),
        (
            "fixture-token",
            None,
            "fixture_store.myshopify.com",
            "invalid_configuration",
        ),
    ],
)
def test_shopify_readiness_rejects_partial_or_invalid_configuration(
    access_token: str | None,
    legacy_token: str | None,
    store: str | None,
    reason: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.shopify_connector import _credential_state

    _clear_credentials(monkeypatch)
    for name, value in (
        ("SHOPIFY_ACCESS_TOKEN", access_token),
        ("SHOPIFY_API_KEY", legacy_token),
        ("SHOPIFY_STORE_URL", store),
    ):
        if value is not None:
            monkeypatch.setenv(name, value)

    state = _credential_state()
    readiness = inspect_publish_readiness("shopify")

    assert state.ready is False
    assert state.reason == reason
    assert readiness.ready is False
    assert readiness.reason == reason


def test_shopify_legacy_token_invalidates_canonical_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.base import ConnectorCredentialNotReady
    from src.connectors.shopify_connector import _require_credentials

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", " canonical-fixture ")
    monkeypatch.setenv("SHOPIFY_API_KEY", "legacy-fixture")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.com")

    with pytest.raises(ConnectorCredentialNotReady) as error:
        _require_credentials()

    assert error.value.reason == "invalid_configuration"


@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
def test_allow_mock_mode_never_changes_publish_readiness(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("ALLOW_MOCK_MODE", "1")
    first = inspect_publish_readiness(platform)
    monkeypatch.setenv("ALLOW_MOCK_MODE", "0")
    second = inspect_publish_readiness(platform)
    assert (first.ready, first.reason) == (False, "missing_credentials")
    assert (second.ready, second.reason) == (False, "missing_credentials")


def test_readiness_rejects_unsupported_platform_without_connector_construction() -> None:
    from src.connectors.registry import inspect_publish_readiness

    with pytest.raises(ValueError, match="Unsupported platform"):
        inspect_publish_readiness("instagram")


@pytest.mark.asyncio
async def test_tiktok_missing_credentials_block_publish_and_status_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.tiktok_connector as module
    from src.connectors.tiktok_connector import TikTokConnector

    _clear_credentials(monkeypatch)
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)
    connector = TikTokConnector()

    with pytest.raises(ConnectorCredentialNotReady) as publish_error:
        await connector.publish({"video_path": "/not/read.mp4"})
    with pytest.raises(ConnectorCredentialNotReady) as status_error:
        await connector.get_status("post-fixture")

    assert publish_error.value.reason == "missing_credentials"
    assert status_error.value.reason == "missing_credentials"


@pytest.mark.asyncio
async def test_tiktok_missing_video_is_rejected_during_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.tiktok_connector as module
    from src.connectors.tiktok_connector import TikTokConnector

    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)

    with pytest.raises(ConnectorPreflightRejected):
        await TikTokConnector().preflight(
            {
                "video_path": str(tmp_path / "missing.mp4"),
                "description": "Reviewed",
                "platform_options": {
                    "platform": "tiktok",
                    "privacy_level": "SELF_ONLY",
                    "disable_comment": True,
                    "disable_duet": True,
                    "disable_stitch": True,
                    "brand_content_toggle": False,
                    "brand_organic_toggle": False,
                },
            }
        )


def test_tiktok_runtime_source_has_no_publish_or_status_mock() -> None:
    import src.connectors.tiktok_connector as module

    source = inspect.getsource(module)
    for forbidden in (
        "_mock_publish",
        "_mock_status",
        "tt_mock_",
        "tiktok_mock_publish",
        "_upload_video",
        "_publish_video",
    ):
        assert forbidden not in source
    assert "https://open.tiktokapis.com" in source


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: Any,
        *,
        error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload
        self.error = error

    def json(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.payload


class OneResponseClient:
    def __init__(
        self,
        response: FakeResponse | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "store",
    [None, "", "https://fixture.myshopify.com", "fixture.myshopify.com/path"],
)
async def test_shopify_invalid_credentials_block_publish_and_status_before_network(
    store: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.shopify_connector as module
    from src.connectors.shopify_connector import ShopifyConnector

    _clear_credentials(monkeypatch)
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
    if store is not None:
        monkeypatch.setenv("SHOPIFY_STORE_URL", store)
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)
    connector = ShopifyConnector()

    with pytest.raises(ConnectorCredentialNotReady):
        await connector.publish({"video_path": "/not/read.mp4"})
    with pytest.raises(ConnectorCredentialNotReady):
        await connector.get_status("gid://shopify/MediaFile/fixture")


@pytest.mark.asyncio
async def test_shopify_missing_video_is_rejected_during_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.connectors.shopify_connector as module
    from src.connectors.shopify_connector import ShopifyConnector

    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.com")
    monkeypatch.setattr(module.httpx, "AsyncClient", ForbiddenAsyncClient)

    with pytest.raises(ConnectorPreflightRejected):
        await ShopifyConnector().preflight(
            {
                "video_path": str(tmp_path / "missing.mp4"),
                "title": "Reviewed",
                "platform_options": {
                    "platform": "shopify",
                    "product_id": "gid://shopify/Product/123456789",
                },
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
async def test_direct_connector_status_is_disabled_without_network(
    platform: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_credentials(monkeypatch)
    client = OneResponseClient(FakeResponse(200, {}))
    if platform == "tiktok":
        from src.connectors.tiktok_connector import TikTokConnector

        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
        connector = TikTokConnector(http_client=client)  # type: ignore[arg-type]
    else:
        from src.connectors.shopify_connector import ShopifyConnector

        monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
        monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.com")
        connector = ShopifyConnector(http_client=client)  # type: ignore[arg-type]
    with pytest.raises(ConnectorStatusUnavailable):
        await connector.get_status("post-fixture")
    assert client.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
@pytest.mark.parametrize("failure_kind", ["http", "json", "timeout"])
async def test_direct_status_failure_is_typed_and_message_free(
    platform: str,
    failure_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_credentials(monkeypatch)
    if failure_kind == "http":
        client = OneResponseClient(FakeResponse(503, {}))
    elif failure_kind == "json":
        client = OneResponseClient(FakeResponse(200, {}, error=ValueError("raw-body")))
    else:
        client = OneResponseClient(error=TimeoutError("raw-timeout"))
    if platform == "tiktok":
        from src.connectors.tiktok_connector import TikTokConnector

        monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "fixture-token")
        connector = TikTokConnector(http_client=client)  # type: ignore[arg-type]
    else:
        from src.connectors.shopify_connector import ShopifyConnector

        monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
        monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture.myshopify.com")
        connector = ShopifyConnector(http_client=client)  # type: ignore[arg-type]

    with pytest.raises(ConnectorStatusUnavailable) as error:
        await connector.get_status("post-fixture")
    assert "raw-" not in repr(error.value)


def test_shopify_runtime_source_has_no_publish_or_status_mock() -> None:
    import src.connectors.shopify_connector as module

    source = inspect.getsource(module)
    for forbidden in (
        "_mock_publish",
        "_mock_status",
        "sp_mock_",
        "shopify_mock_publish",
        "mock-store.myshopify.com",
    ):
        assert forbidden not in source


def test_runtime_publish_and_status_sources_have_no_mock_or_retry_escape_hatch() -> None:
    import src.connectors.registry as registry_module
    import src.connectors.shopify_connector as shopify_module
    import src.connectors.tiktok_connector as tiktok_module

    sources = "\n".join(
        inspect.getsource(module)
        for module in (registry_module, tiktok_module, shopify_module)
    )
    for forbidden in (
        "_mock_publish",
        "_mock_status",
        "tt_mock_",
        "sp_mock_",
        "mock-store.myshopify.com",
        "missing_credentials_or_mock_mode",
    ):
        assert forbidden not in sources
    publish_and_status = "\n".join(
        (
            inspect.getsource(tiktok_module.TikTokConnector.publish),
            inspect.getsource(tiktok_module.TikTokConnector.get_status),
            inspect.getsource(shopify_module.ShopifyConnector.publish),
            inspect.getsource(shopify_module.ShopifyConnector.get_status),
        )
    )
    assert "ALLOW_MOCK_MODE" not in publish_and_status
    assert "retry" not in publish_and_status.lower()


def test_w1_25_adds_only_the_preflight_attempt_status() -> None:
    from typing import get_args

    from src.models.publish_attempt import PublishAttemptStatus

    assert get_args(PublishAttemptStatus) == (
        "prepared",
        "authorization_failed",
        "preflight_failed",
        "acceptance_consumed",
        "published",
        "failed",
        "ambiguous",
    )
