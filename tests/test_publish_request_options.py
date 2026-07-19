"""W1-25 strict publish options and canonical runtime configuration."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from pydantic import ValidationError

ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"

_PUBLISH_ENV_NAMES = (
    "TIKTOK_ACCESS_TOKEN",
    "TIKTOK_PUBLISH_ENABLED",
    "TIKTOK_USERNAME",
    "TIKTOK_API_UPLOAD_URL",
    "TIKTOK_API_BASE_URL",
    "SHOPIFY_ACCESS_TOKEN",
    "SHOPIFY_STORE_URL",
    "SHOPIFY_PUBLISH_ENABLED",
    "SHOPIFY_API_KEY",
    "SHOPIFY_ADMIN_TOKEN",
    "SHOPIFY_API_PASSWORD",
    "SHOPIFY_GRAPHQL_URL_TEMPLATE",
)


@pytest.fixture(autouse=True)
def clear_publish_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in _PUBLISH_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    yield


def _base_request(*, platform: str) -> dict[str, object]:
    return {
        "acceptance_id": ACCEPTANCE_ID,
        "platform": platform,
        "metadata": {"title": "Reviewed campaign"},
    }


def _tiktok_options(**overrides: object) -> dict[str, object]:
    options: dict[str, object] = {
        "platform": "tiktok",
        "privacy_level": "SELF_ONLY",
        "disable_comment": True,
        "disable_duet": True,
        "disable_stitch": True,
        "brand_content_toggle": False,
        "brand_organic_toggle": False,
    }
    options.update(overrides)
    return options


def _shopify_options(**overrides: object) -> dict[str, object]:
    options: dict[str, object] = {
        "platform": "shopify",
        "product_id": "gid://shopify/Product/123456789",
    }
    options.update(overrides)
    return options


def test_tiktok_publish_options_are_required_and_strict() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    body = {
        **_base_request(platform="tiktok"),
        "platform_options": _tiktok_options(),
    }

    request = PublishAttemptRequest.model_validate(body)

    assert request.platform == "tiktok"
    assert request.platform_options.platform == "tiktok"
    assert request.platform_options.privacy_level == "SELF_ONLY"
    assert request.platform_options.disable_comment is True
    assert request.model_dump(mode="json")["platform_options"] == _tiktok_options()


def test_shopify_publish_options_require_exact_product_gid() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    body = {
        **_base_request(platform="shopify"),
        "platform_options": _shopify_options(),
    }

    request = PublishAttemptRequest.model_validate(body)

    assert request.platform == "shopify"
    assert request.platform_options.platform == "shopify"
    assert request.platform_options.product_id == "gid://shopify/Product/123456789"


def test_publish_options_are_required_without_a_silent_default() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(_base_request(platform="tiktok"))


def test_top_level_platform_must_match_discriminated_options() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError, match="platform_options"):
        PublishAttemptRequest.model_validate(
            {
                **_base_request(platform="tiktok"),
                "platform_options": _shopify_options(),
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("disable_comment", 1),
        ("disable_duet", 0),
        ("disable_stitch", "true"),
        ("brand_content_toggle", "false"),
        ("brand_organic_toggle", None),
    ],
)
def test_tiktok_boolean_options_reject_coercion(field: str, value: object) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {
                **_base_request(platform="tiktok"),
                "platform_options": _tiktok_options(**{field: value}),
            }
        )


@pytest.mark.parametrize(
    "privacy_level",
    ["", "PUBLIC", "FRIENDS", "public_to_everyone", 1, None],
)
def test_tiktok_privacy_uses_the_official_allowlist(privacy_level: object) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {
                **_base_request(platform="tiktok"),
                "platform_options": _tiktok_options(privacy_level=privacy_level),
            }
        )


@pytest.mark.parametrize(
    "product_id",
    [
        "",
        "123",
        "gid://shopify/Video/123",
        "gid://shopify/Product/0",
        "gid://shopify/Product/-1",
        "gid://shopify/Product/01",
        "gid://shopify/Product/123/extra",
        123,
        None,
    ],
)
def test_shopify_product_gid_is_exact_and_positive(product_id: object) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {
                **_base_request(platform="shopify"),
                "platform_options": _shopify_options(product_id=product_id),
            }
        )


@pytest.mark.parametrize("platform", ["tiktok", "shopify"])
def test_platform_options_reject_unknown_fields(platform: str) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    options = (
        _tiktok_options(credential="must-not-be-accepted")
        if platform == "tiktok"
        else _shopify_options(product_name="must-not-be-authority")
    )
    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {
                **_base_request(platform=platform),
                "platform_options": options,
            }
        )


@pytest.mark.parametrize(
    ("value", "enabled"),
    [
        (None, False),
        ("", False),
        ("   ", False),
        ("0", False),
        ("false", False),
        ("no", False),
        ("off", False),
        ("invalid", False),
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("yes", True),
        ("on", True),
    ],
)
@pytest.mark.parametrize(
    ("platform", "flag_name", "token_name"),
    [
        ("tiktok", "TIKTOK_PUBLISH_ENABLED", "TIKTOK_ACCESS_TOKEN"),
        ("shopify", "SHOPIFY_PUBLISH_ENABLED", "SHOPIFY_ACCESS_TOKEN"),
    ],
)
def test_publish_flags_are_explicit_and_default_off(
    value: str | None,
    enabled: bool,
    platform: str,
    flag_name: str,
    token_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness

    monkeypatch.setenv(token_name, "fixture-token")
    if platform == "shopify":
        monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.com")
    if value is not None:
        monkeypatch.setenv(flag_name, value)

    readiness = inspect_publish_readiness(platform)

    assert readiness.ready is enabled
    assert readiness.reason is (None if enabled else "publishing_disabled")


@pytest.mark.parametrize(
    "legacy_name",
    [
        "SHOPIFY_API_KEY",
        "SHOPIFY_ADMIN_TOKEN",
        "SHOPIFY_API_PASSWORD",
        "SHOPIFY_GRAPHQL_URL_TEMPLATE",
    ],
)
def test_shopify_legacy_configuration_fails_closed(
    legacy_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness

    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "canonical-fixture")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.com")
    monkeypatch.setenv(legacy_name, "legacy-fixture-must-not-be-read")

    readiness = inspect_publish_readiness("shopify")

    assert readiness.ready is False
    assert readiness.reason == "invalid_configuration"
    assert "fixture" not in repr(readiness)


@pytest.mark.parametrize(
    "legacy_name",
    ["TIKTOK_USERNAME", "TIKTOK_API_UPLOAD_URL", "TIKTOK_API_BASE_URL"],
)
def test_tiktok_publish_overrides_fail_closed(
    legacy_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness

    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", "canonical-fixture")
    monkeypatch.setenv(legacy_name, "legacy-fixture-must-not-be-read")

    readiness = inspect_publish_readiness("tiktok")

    assert readiness.ready is False
    assert readiness.reason == "invalid_configuration"
    assert "fixture" not in repr(readiness)


@pytest.mark.parametrize(
    "store",
    [
        "fixture-store.myshopify.invalid",
        "Fixture-Store.myshopify.com",
        "https://fixture-store.myshopify.com",
        "fixture-store.myshopify.com/path",
        "fixture-store.myshopify.com:443",
        "user@fixture-store.myshopify.com",
        "fixture-store.myshopify.com?x=1",
        "fixture-store.myshopify.com#x",
        "127.0.0.1",
        "localhost",
    ],
)
def test_shopify_store_is_one_canonical_myshopify_host(
    store: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness

    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", "fixture-token")
    monkeypatch.setenv("SHOPIFY_STORE_URL", store)

    readiness = inspect_publish_readiness("shopify")

    assert readiness.ready is False
    assert readiness.reason == "invalid_configuration"


def test_canonical_shopify_configuration_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.shopify_connector import _require_credentials

    monkeypatch.setenv("SHOPIFY_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("SHOPIFY_ACCESS_TOKEN", " canonical-fixture ")
    monkeypatch.setenv("SHOPIFY_STORE_URL", "fixture-store.myshopify.com")

    assert _require_credentials() == (
        "canonical-fixture",
        "fixture-store.myshopify.com",
    )
    assert inspect_publish_readiness("shopify").ready is True


def test_canonical_tiktok_configuration_is_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.connectors.registry import inspect_publish_readiness
    from src.connectors.tiktok_connector import _require_access_token

    monkeypatch.setenv("TIKTOK_PUBLISH_ENABLED", "true")
    monkeypatch.setenv("TIKTOK_ACCESS_TOKEN", " canonical-fixture ")

    assert _require_access_token() == "canonical-fixture"
    assert inspect_publish_readiness("tiktok").ready is True


def test_publish_protocol_endpoints_are_fixed_constants() -> None:
    from src.connectors.shopify_connector import _graphql_url
    from src.connectors.tiktok_connector import (
        _TIKTOK_CREATOR_INFO_URL,
        _TIKTOK_DIRECT_POST_INIT_URL,
        _TIKTOK_STATUS_FETCH_URL,
        _TIKTOK_VIDEO_QUERY_URL,
    )

    assert _TIKTOK_CREATOR_INFO_URL == (
        "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
    )
    assert _TIKTOK_DIRECT_POST_INIT_URL == (
        "https://open.tiktokapis.com/v2/post/publish/video/init/"
    )
    assert _TIKTOK_STATUS_FETCH_URL == (
        "https://open.tiktokapis.com/v2/post/publish/status/fetch/"
    )
    assert _TIKTOK_VIDEO_QUERY_URL == (
        "https://open.tiktokapis.com/v2/video/query/"
    )
    assert _graphql_url("fixture-store.myshopify.com") == (
        "https://fixture-store.myshopify.com/admin/api/2026-07/graphql.json"
    )
