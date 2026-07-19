"""W1-25 strict receipt and connector preflight vocabulary contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

OBSERVED_AT = "2026-07-14T08:00:00Z"


def _tiktok_receipt(**overrides: object) -> dict[str, object]:
    receipt: dict[str, object] = {
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
        "observed_at": OBSERVED_AT,
        "verified_by": "video_query",
        "simulated": False,
    }
    receipt.update(overrides)
    return receipt


def _shopify_receipt(**overrides: object) -> dict[str, object]:
    receipt: dict[str, object] = {
        "schema_version": "publish-receipt.v1",
        "platform": "shopify",
        "protocol_version": "shopify-admin-2026-07",
        "completion_scope": "shopify_product_media",
        "provider_operation_id": None,
        "provider_resource_id": "gid://shopify/Video/987654321",
        "target_id": "gid://shopify/Product/123456789",
        "provider_status": "READY",
        "post_id": None,
        "post_url": None,
        "public_visibility_verified": False,
        "observed_at": OBSERVED_AT,
        "verified_by": "file_query_and_product_readback",
        "simulated": False,
    }
    receipt.update(overrides)
    return receipt


def test_published_response_requires_exact_receipt_projection() -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    payload = {
        "publish_attempt_id": "91ec3593-cc3c-42bf-99ee-c98655c5826b",
        "acceptance_id": "7f947625-2898-4e9e-9e71-dce4309e5f4f",
        "platform": "tiktok",
        "status": "published",
        "success": True,
        "post_id": "7512345678901234567",
        "post_url": (
            "https://www.tiktok.com/@fixture_creator/video/7512345678901234567"
        ),
        "receipt": _tiktok_receipt(),
        "acceptance_consumed": True,
        "retry_allowed": False,
    }

    response = PublishAttemptResponse.model_validate(payload)

    assert response.receipt.validate_published() is response.receipt
    for contradictory in (
        {key: value for key, value in payload.items() if key != "receipt"},
        {**payload, "platform": "shopify"},
        {**payload, "post_id": "7512345678901234568"},
        {**payload, "post_url": None},
        {
            **payload,
            "receipt": _tiktok_receipt(
                provider_resource_id=None,
                provider_status="PROCESSING_UPLOAD",
                post_id=None,
                post_url=None,
                public_visibility_verified=False,
                verified_by=None,
            ),
        },
    ):
        with pytest.raises(ValidationError):
            PublishAttemptResponse.model_validate(contradictory)


def test_tiktok_published_receipt_is_strict_and_canonical() -> None:
    from src.models.publish_attempt import PublishReceiptV1

    receipt = PublishReceiptV1.model_validate(_tiktok_receipt())

    assert receipt.validate_published() is receipt
    assert receipt.platform == "tiktok"
    assert receipt.provider_operation_id != receipt.post_id
    assert receipt.canonical_json_bytes() == (
        receipt.canonical_json().encode("utf-8")
    )
    assert len(receipt.canonical_json_bytes()) <= 8 * 1024


def test_tiktok_published_receipt_can_have_no_public_post_id() -> None:
    from src.models.publish_attempt import PublishReceiptV1

    receipt = PublishReceiptV1.model_validate(
        _tiktok_receipt(
            provider_resource_id=None,
            post_id=None,
            post_url=None,
            public_visibility_verified=False,
            verified_by="status_fetch",
        )
    )

    assert receipt.validate_published() is receipt


def test_shopify_published_receipt_has_no_post_projection() -> None:
    from src.models.publish_attempt import PublishReceiptV1

    receipt = PublishReceiptV1.model_validate(_shopify_receipt())

    assert receipt.validate_published() is receipt
    assert receipt.provider_resource_id == "gid://shopify/Video/987654321"
    assert receipt.target_id == "gid://shopify/Product/123456789"
    assert receipt.post_id is None
    assert receipt.post_url is None


@pytest.mark.parametrize("value", [True, 0, 1, "false", None])
def test_receipt_requires_exact_simulated_false(value: object) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises(ValidationError):
        PublishReceiptV1.model_validate(_tiktok_receipt(simulated=value))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("provider_operation_id", "tt_mock_operation"),
        ("provider_resource_id", "mock-7512345678901234567"),
        ("post_id", "mock-post"),
        ("post_url", "https://www.tiktok.com/@creator/video/mock-post"),
        ("provider_operation_id", "contains\x00control"),
    ],
)
def test_receipt_rejects_mock_markers_and_control_characters(
    field: str,
    value: object,
) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises(ValidationError):
        PublishReceiptV1.model_validate(_tiktok_receipt(**{field: value}))


@pytest.mark.parametrize(
    "post_url",
    [
        "http://www.tiktok.com/@fixture_creator/video/7512345678901234567",
        "https://evil.example/@fixture_creator/video/7512345678901234567",
        "https://www.tiktok.com:443/@fixture_creator/video/7512345678901234567",
        "https://user@www.tiktok.com/@fixture_creator/video/7512345678901234567",
        "https://www.tiktok.com/@fixture_creator/video/7512345678901234567?x=1",
        "https://www.tiktok.com/@fixture_creator/video/7512345678901234567#x",
        "https://www.tiktok.com/video/7512345678901234567",
        "https://www.tiktok.com/@fixture_creator/video/9999999999999999999",
    ],
)
def test_tiktok_receipt_rejects_untrusted_share_urls(post_url: str) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises(ValidationError):
        PublishReceiptV1.model_validate(_tiktok_receipt(post_url=post_url))


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version": "shopify-admin-2026-07"},
        {"completion_scope": "shopify_product_media"},
        {"provider_status": "READY"},
        {"provider_status": "PROCESSING_DOWNLOAD"},
        {"target_id": "gid://shopify/Product/123"},
        {"provider_resource_id": "7512345678901234568"},
        {"public_visibility_verified": False},
        {"verified_by": "file_query_and_product_readback"},
    ],
)
def test_tiktok_receipt_rejects_platform_contradictions(
    changes: dict[str, object],
) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises((ValidationError, ValueError)):
        receipt = PublishReceiptV1.model_validate(_tiktok_receipt(**changes))
        receipt.validate_published()


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version": "tiktok-content-posting-v2"},
        {"completion_scope": "tiktok_direct_post"},
        {"provider_status": "PUBLISH_COMPLETE"},
        {"provider_resource_id": "gid://shopify/Product/987"},
        {"target_id": "gid://shopify/Video/123"},
        {"post_id": "987654321"},
        {"post_url": "https://www.tiktok.com/@creator/video/987654321"},
        {"public_visibility_verified": True},
        {"verified_by": "status_fetch"},
    ],
)
def test_shopify_receipt_rejects_platform_contradictions(
    changes: dict[str, object],
) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises((ValidationError, ValueError)):
        receipt = PublishReceiptV1.model_validate(_shopify_receipt(**changes))
        receipt.validate_published()


@pytest.mark.parametrize(
    "receipt_data",
    [
        _tiktok_receipt(
            provider_resource_id=None,
            provider_status="PROCESSING_UPLOAD",
            post_id=None,
            post_url=None,
            public_visibility_verified=False,
            verified_by=None,
        ),
        _tiktok_receipt(
            provider_resource_id=None,
            provider_status="FAILED",
            post_id=None,
            post_url=None,
            public_visibility_verified=False,
            verified_by=None,
        ),
        _shopify_receipt(
            provider_status="PROCESSING",
            post_id=None,
            post_url=None,
            public_visibility_verified=False,
            verified_by=None,
        ),
        _shopify_receipt(
            provider_status=None,
            post_id=None,
            post_url=None,
            public_visibility_verified=False,
            verified_by=None,
        ),
    ],
)
def test_safe_partial_receipts_parse_but_are_not_published(
    receipt_data: dict[str, object],
) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    receipt = PublishReceiptV1.model_validate(receipt_data)

    with pytest.raises(ValueError, match="published receipt"):
        receipt.validate_published()


def test_receipt_rejects_unknown_fields_and_oversized_identifiers() -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises(ValidationError):
        PublishReceiptV1.model_validate(
            {**_shopify_receipt(), "provider_payload": {"token": "forbidden"}}
        )
    with pytest.raises(ValidationError):
        PublishReceiptV1.model_validate(
            _tiktok_receipt(provider_operation_id="x" * (8 * 1024))
        )


@pytest.mark.parametrize(
    "observed_at",
    ["2026-07-14T08:00:00", "not-a-time", None],
)
def test_receipt_observation_time_is_timezone_aware_utc(observed_at: object) -> None:
    from src.models.publish_attempt import PublishReceiptV1

    with pytest.raises(ValidationError):
        PublishReceiptV1.model_validate(_shopify_receipt(observed_at=observed_at))


def test_preflight_vocabulary_is_typed_frozen_and_message_safe() -> None:
    from src.connectors.base import (
        ConnectorOutcomeAmbiguous,
        ConnectorPreflightRejected,
        ConnectorPreflightUnavailable,
        ShopifyPreflightSnapshot,
        TikTokPreflightSnapshot,
    )

    observed_at = datetime(2026, 7, 14, 8, tzinfo=UTC)
    tiktok = TikTokPreflightSnapshot(
        privacy_level="SELF_ONLY",
        disable_comment=True,
        disable_duet=True,
        disable_stitch=True,
        brand_content_toggle=False,
        brand_organic_toggle=False,
        max_video_post_duration_sec=600,
        media_duration_seconds=15.0,
        observed_at=observed_at,
    )
    shopify = ShopifyPreflightSnapshot(
        product_id="gid://shopify/Product/123456789",
        required_scopes_verified=True,
        media_duration_seconds=15.0,
        observed_at=observed_at,
    )

    assert tiktok.platform == "tiktok"
    assert shopify.platform == "shopify"
    with pytest.raises(FrozenInstanceError):
        tiktok.max_video_post_duration_sec = 601
    with pytest.raises(FrozenInstanceError):
        shopify.required_scopes_verified = False

    rejected = ConnectorPreflightRejected()
    unavailable = ConnectorPreflightUnavailable()
    ambiguous = ConnectorOutcomeAmbiguous(
        partial_receipt={"provider_operation_id": "safe-operation"}
    )
    assert str(rejected) == "connector_preflight_rejected"
    assert str(unavailable) == "connector_preflight_unavailable"
    assert str(ambiguous) == "connector_outcome_ambiguous"
    assert ambiguous.partial_receipt == {
        "provider_operation_id": "safe-operation"
    }


def test_publish_status_and_error_vocab_include_preflight_outcomes() -> None:
    from typing import get_args

    from src.models.publish_attempt import (
        PublishAttemptErrorCode,
        PublishAttemptStatus,
    )

    assert "preflight_failed" in get_args(PublishAttemptStatus)
    assert "publish_preflight_rejected" in get_args(PublishAttemptErrorCode)
    assert "publish_preflight_unavailable" in get_args(PublishAttemptErrorCode)
