from __future__ import annotations

import json
from typing import get_args, get_type_hints

import pytest
from pydantic import ValidationError

VALID_ACCEPTANCE_ID = "7f947625-2898-4e9e-9e71-dce4309e5f4f"
VALID_ATTEMPT_ID = "91ec3593-cc3c-42bf-99ee-c98655c5826b"
UUID4_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def _annotation_allows_none(annotation: object) -> bool:
    if annotation is type(None):
        return True
    return any(_annotation_allows_none(arg) for arg in get_args(annotation))


def _valid_request() -> dict[str, object]:
    return {
        "acceptance_id": VALID_ACCEPTANCE_ID,
        "platform": "tiktok",
        "metadata": {
            "title": "Reviewed campaign video",
            "description": "Final approved creative.",
            "hashtags": ["momlife", "wearablepump"],
            "product_name": "Wearable Breast Pump",
        },
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


def _valid_receipt(**overrides: object) -> dict[str, object]:
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
        "observed_at": "2026-07-14T08:00:00Z",
        "verified_by": "video_query",
        "simulated": False,
    }
    receipt.update(overrides)
    return receipt


def _valid_response() -> dict[str, object]:
    return {
        "publish_attempt_id": VALID_ATTEMPT_ID,
        "acceptance_id": VALID_ACCEPTANCE_ID,
        "platform": "tiktok",
        "status": "published",
        "success": True,
        "post_id": "7512345678901234567",
        "post_url": (
            "https://www.tiktok.com/@fixture_creator/video/7512345678901234567"
        ),
        "receipt": _valid_receipt(),
        "acceptance_consumed": True,
        "retry_allowed": False,
    }


def test_publish_request_is_strict_and_single_platform() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    parsed = PublishAttemptRequest.model_validate(_valid_request())
    assert parsed.platform == "tiktok"
    assert parsed.acceptance_id == VALID_ACCEPTANCE_ID

    shopify = PublishAttemptRequest.model_validate(
        {
            **_valid_request(),
            "platform": "shopify",
            "platform_options": {
                "platform": "shopify",
                "product_id": "gid://shopify/Product/123456789",
            },
        }
    )
    assert shopify.platform == "shopify"

    for value in ("TIKTOK", "instagram", ["tiktok"], 1):
        with pytest.raises(ValidationError):
            PublishAttemptRequest.model_validate(
                {**_valid_request(), "platform": value}
            )


def test_publish_request_requires_metadata_but_allows_an_empty_object() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    request = _valid_request()
    request.pop("metadata")
    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(request)

    parsed = PublishAttemptRequest.model_validate(
        {**_valid_request(), "metadata": {}}
    )
    assert parsed.metadata.hashtags == []
    assert parsed.metadata.tags == []


def test_publish_metadata_omits_text_but_rejects_explicit_null() -> None:
    from src.models.publish_attempt import PublishMetadata

    parsed = PublishMetadata.model_validate({})
    assert parsed.model_dump(mode="json") == {
        "title": None,
        "description": None,
        "hook": None,
        "product_name": None,
        "hashtags": [],
        "tags": [],
    }

    for field in ("title", "description", "hook", "product_name"):
        with pytest.raises(ValidationError):
            PublishMetadata.model_validate({field: None})


def test_publish_metadata_schema_has_optional_nonnullable_text_fields() -> None:
    from src.models.publish_attempt import PublishMetadata

    schema = PublishMetadata.model_json_schema(mode="validation")
    required = set(schema.get("required", []))
    for field in ("title", "description", "hook", "product_name"):
        assert field not in required
        field_schema = schema["properties"][field]
        assert field_schema["type"] == "string"
        assert "anyOf" not in field_schema
        assert "default" not in field_schema


def test_publish_metadata_python_annotations_honestly_include_missing_none() -> None:
    from src.models.publish_attempt import PublishMetadata

    type_hints = get_type_hints(PublishMetadata, include_extras=True)
    for field in ("title", "description", "hook", "product_name"):
        assert _annotation_allows_none(type_hints[field])
        assert _annotation_allows_none(PublishMetadata.model_fields[field].annotation)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("platforms", ["tiktok"]),
        ("content", {"title": "legacy"}),
        ("video_path", "/tmp/client.mp4"),
        ("video_url", "https://client.invalid/video.mp4"),
        ("delivery_acceptance", {"source": "human"}),
        ("tenant_id", "attacker"),
        ("reviewer", "self-asserted"),
        ("publish_allowed", True),
    ],
)
def test_publish_request_forbids_legacy_and_server_authority_fields(
    field: str,
    value: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate({**_valid_request(), field: value})


@pytest.mark.parametrize(
    "metadata",
    [
        {"title": 42},
        {"description": True},
        {"hashtags": "momlife"},
        {"hashtags": ["#momlife"]},
        {"hashtags": ["momlife", "momlife"]},
        {"tags": ["ok", "bad\x00tag"]},
        {"video_path": "/tmp/client.mp4"},
        {"thumbnail_url": "https://client.invalid/thumb.jpg"},
        {"title": "x" * 301},
        {"description": "x" * 5001},
        {"hashtags": [f"tag-{index}" for index in range(31)]},
    ],
)
def test_publish_metadata_rejects_unsafe_or_unbounded_values(
    metadata: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "metadata": metadata}
        )


def test_publish_metadata_trims_text_and_tag_items() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    parsed = PublishAttemptRequest.model_validate(
        {
            **_valid_request(),
            "metadata": {
                "title": "  Reviewed title  ",
                "description": "  Reviewed description  ",
                "hook": "  Opening hook  ",
                "product_name": "  Product name  ",
                "hashtags": ["  momlife  "],
                "tags": ["  campaign  "],
            },
        }
    )

    assert parsed.metadata.model_dump() == {
        "title": "Reviewed title",
        "description": "Reviewed description",
        "hook": "Opening hook",
        "product_name": "Product name",
        "hashtags": ["momlife"],
        "tags": ["campaign"],
    }


@pytest.mark.parametrize("field", ["title", "description", "hook", "product_name"])
@pytest.mark.parametrize("value", ["safe\x00unsafe", "safe\nunsafe", "safe\x7funsafe", "   "])
def test_publish_metadata_text_rejects_control_characters_and_empty_values(
    field: str,
    value: str,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "metadata": {field: value}}
        )


@pytest.mark.parametrize(
    "values",
    [
        [1],
        [True],
        [["nested"]],
        ["   "],
        ["  #momlife  "],
        ["momlife", "  momlife  "],
        ["safe\tunsafe"],
        ["x" * 101],
    ],
)
def test_publish_metadata_tag_items_are_strict_and_bounded(values: object) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "metadata": {"tags": values}}
        )


def test_publish_metadata_accepts_exact_tag_count_and_length_boundaries() -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    boundary_tags = [f"{index:02d}" + "x" * 98 for index in range(30)]
    parsed = PublishAttemptRequest.model_validate(
        {**_valid_request(), "metadata": {"tags": boundary_tags}}
    )

    assert parsed.metadata.tags == boundary_tags
    assert all(len(value) == 100 for value in parsed.metadata.tags)


def test_publish_metadata_counts_unicode_code_points_and_rejects_surrogates() -> None:
    from src.models.publish_attempt import PublishMetadata

    emoji = "😀"
    parsed = PublishMetadata.model_validate(
        {
            "title": emoji * 300,
            "description": emoji * 300,
            "hook": emoji * 300,
            "product_name": emoji * 300,
            "hashtags": [emoji * 100],
            "tags": [emoji * 100],
        }
    )
    assert len(parsed.title) == 300
    assert len(parsed.product_name) == 300
    assert len(parsed.tags[0]) == 100

    for metadata in (
        {"title": emoji * 301},
        {"tags": [emoji * 101]},
        {"title": "\ud800"},
        {"description": "\udc00"},
        {"hook": "safe\ud800unsafe"},
        {"product_name": "safe\udc00unsafe"},
        {"hashtags": ["\ud800"]},
        {"tags": ["\udc00"]},
    ):
        with pytest.raises(ValidationError):
            PublishMetadata.model_validate(metadata)


def test_publish_metadata_compact_utf8_matches_escaped_astral_boundary() -> None:
    from src.models.publish_attempt import PublishMetadata

    exact_payload = {
        "title": '"\\😀' + "x" * 297,
        "description": "界" * 5000,
        "hook": "x" * 996,
    }
    oversized_payload = {**exact_payload, "hook": "x" * 997}

    exact = PublishMetadata.model_validate(exact_payload)
    exact_bytes = len(
        json.dumps(
            exact.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    assert len(exact.title) == 300
    assert exact_bytes == 16 * 1024

    oversized_projection = {
        "title": oversized_payload["title"],
        "description": oversized_payload["description"],
        "hook": oversized_payload["hook"],
        "product_name": None,
        "hashtags": [],
        "tags": [],
    }
    oversized_bytes = len(
        json.dumps(
            oversized_projection,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    assert oversized_bytes == 16 * 1024 + 1
    with pytest.raises(ValidationError):
        PublishMetadata.model_validate(oversized_payload)


def test_publish_metadata_enforces_canonical_utf8_16_kib_limit() -> None:
    from src.models.publish_attempt import PublishAttemptRequest, PublishMetadata

    utf8_tags = [f"{index:02d}" + "界" * 98 for index in range(30)]
    within_limit = PublishMetadata.model_validate({"tags": utf8_tags})
    within_bytes = len(
        json.dumps(
            within_limit.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    assert within_bytes <= 16 * 1024

    oversized_payload = {"tags": utf8_tags, "hashtags": utf8_tags}
    oversized_projection = {
        "title": None,
        "description": None,
        "hook": None,
        "product_name": None,
        **oversized_payload,
    }
    oversized_bytes = len(
        json.dumps(
            oversized_projection,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    assert oversized_bytes > 16 * 1024

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "metadata": oversized_payload}
        )


@pytest.mark.parametrize(
    "acceptance_id",
    [
        "not-a-uuid",
        "7F947625-2898-4E9E-9E71-DCE4309E5F4F",
        "7f947625-2898-1e9e-9e71-dce4309e5f4f",
        "7f947625-2898-4e9e-7e71-dce4309e5f4f",
        f" {VALID_ACCEPTANCE_ID}",
        f"{VALID_ACCEPTANCE_ID} ",
        f"\n{VALID_ACCEPTANCE_ID}",
        True,
        123,
    ],
)
def test_acceptance_id_is_a_strict_lowercase_uuid4(
    acceptance_id: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptRequest

    with pytest.raises(ValidationError):
        PublishAttemptRequest.model_validate(
            {**_valid_request(), "acceptance_id": acceptance_id}
        )


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.invalid/post",
        "https:///post",
        "https://user:secret@example.invalid/post",
        "https://example.invalid/post?token=secret",
        "https://example.invalid/post#secret",
        "https://example.invalid/post\x00unsafe",
        "https://example.invalid/post\nunsafe",
        " https://example.invalid/post",
        "https://example.invalid/post ",
        "https://exa mple.invalid/post",
        "https://example.invalid:invalid/post",
        "https://example.invalid:65536/post",
        "https://[::1/post",
        "https://%zz/post",
        "https://example.invalid\\evil/post",
    ],
)
def test_success_projection_rejects_credential_shaped_or_unsafe_urls(
    url: str,
) -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    valid = _valid_response()
    assert PublishAttemptResponse.model_validate(valid).status == "published"

    with pytest.raises(ValidationError):
        PublishAttemptResponse.model_validate({**valid, "post_url": url})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "failed"),
        ("success", 1),
        ("success", False),
        ("acceptance_consumed", 1),
        ("acceptance_consumed", False),
        ("retry_allowed", 0),
        ("retry_allowed", True),
        ("platform", "TIKTOK"),
    ],
)
def test_success_projection_has_strict_success_only_literals(
    field: str,
    value: object,
) -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    with pytest.raises(ValidationError):
        PublishAttemptResponse.model_validate({**_valid_response(), field: value})


@pytest.mark.parametrize(
    "post_id",
    ["   ", "unsafe\x00id", "x" * 257, 123, True],
)
def test_success_projection_rejects_unsafe_post_ids(post_id: object) -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    with pytest.raises(ValidationError):
        PublishAttemptResponse.model_validate(
            {**_valid_response(), "post_id": post_id}
        )


def test_success_projection_accepts_optional_safe_post_fields() -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    valid = _valid_response()
    valid["post_id"] = None
    valid["post_url"] = None
    valid["receipt"] = _valid_receipt(
        provider_resource_id=None,
        post_id=None,
        post_url=None,
        public_visibility_verified=False,
        verified_by="status_fetch",
    )
    parsed = PublishAttemptResponse.model_validate(valid)
    assert parsed.post_id is None
    assert parsed.post_url is None


def test_success_projection_requires_exact_receipt_url() -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    parsed = PublishAttemptResponse.model_validate(_valid_response())
    assert parsed.post_url == parsed.receipt.post_url

    with pytest.raises(ValidationError):
        PublishAttemptResponse.model_validate(
            {
                **_valid_response(),
                "post_url": "https://www.tiktok.com/@other/video/7512345678901234567",
            }
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("publish_attempt_id", f" {VALID_ATTEMPT_ID}"),
        ("publish_attempt_id", f"{VALID_ATTEMPT_ID}\n"),
        ("acceptance_id", f" {VALID_ACCEPTANCE_ID}"),
        ("acceptance_id", f"{VALID_ACCEPTANCE_ID}\n"),
    ],
)
def test_success_projection_rejects_padded_uuid_inputs(
    field: str,
    value: str,
) -> None:
    from src.models.publish_attempt import PublishAttemptResponse

    with pytest.raises(ValidationError):
        PublishAttemptResponse.model_validate({**_valid_response(), field: value})


def test_error_projection_rejects_unknown_code_and_malformed_attempt_id() -> None:
    from src.models.publish_attempt import PublishAttemptErrorDetail

    valid = {
        "code": "publish_connector_failed",
        "publish_attempt_id": VALID_ATTEMPT_ID,
        "acceptance_consumed": True,
        "retry_allowed": False,
    }
    assert PublishAttemptErrorDetail.model_validate(valid).retry_allowed is False
    for invalid in (
        {**valid, "code": "raw_connector_exception"},
        {**valid, "publish_attempt_id": "/host/path"},
        {**valid, "publish_attempt_id": VALID_ATTEMPT_ID.upper()},
    ):
        with pytest.raises(ValidationError):
            PublishAttemptErrorDetail.model_validate(invalid)


def test_error_projection_requires_explicit_retry_and_consume_truth() -> None:
    from src.models.publish_attempt import (
        PublishAttemptErrorDetail,
        PublishAttemptErrorResponse,
    )

    valid = {
        "code": "acceptance_not_found",
        "acceptance_consumed": None,
        "retry_allowed": False,
    }
    assert PublishAttemptErrorDetail.model_validate(valid).acceptance_consumed is None
    assert PublishAttemptErrorResponse.model_validate({"detail": valid}).detail.code == (
        "acceptance_not_found"
    )

    for field in ("acceptance_consumed", "retry_allowed"):
        incomplete = dict(valid)
        incomplete.pop(field)
        with pytest.raises(ValidationError):
            PublishAttemptErrorDetail.model_validate(incomplete)

    for invalid in (
        {**valid, "acceptance_consumed": 0},
        {**valid, "retry_allowed": 0},
    ):
        with pytest.raises(ValidationError):
            PublishAttemptErrorDetail.model_validate(invalid)

    with pytest.raises(ValidationError):
        PublishAttemptErrorResponse.model_validate({})


@pytest.mark.parametrize(
    ("acceptance_consumed", "retry_allowed"),
    [
        (None, True),
        (True, True),
    ],
)
def test_error_projection_forbids_retry_without_known_unconsumed_acceptance(
    acceptance_consumed: bool | None,
    retry_allowed: bool,
) -> None:
    from src.models.publish_attempt import PublishAttemptErrorDetail

    with pytest.raises(ValidationError):
        PublishAttemptErrorDetail.model_validate(
            {
                "code": "acceptance_store_unavailable",
                "acceptance_consumed": acceptance_consumed,
                "retry_allowed": retry_allowed,
            }
        )


def test_error_projection_allows_retry_for_known_unconsumed_acceptance() -> None:
    from src.models.publish_attempt import PublishAttemptErrorDetail

    parsed = PublishAttemptErrorDetail.model_validate(
        {
            "code": "publish_connector_not_ready",
            "acceptance_consumed": False,
            "retry_allowed": True,
        }
    )

    assert parsed.acceptance_consumed is False
    assert parsed.retry_allowed is True


@pytest.mark.parametrize(
    "publish_attempt_id",
    [f" {VALID_ATTEMPT_ID}", f"{VALID_ATTEMPT_ID} ", f"{VALID_ATTEMPT_ID}\n"],
)
def test_error_projection_rejects_padded_attempt_ids(
    publish_attempt_id: str,
) -> None:
    from src.models.publish_attempt import PublishAttemptErrorDetail

    with pytest.raises(ValidationError):
        PublishAttemptErrorDetail.model_validate(
            {
                "code": "publish_connector_failed",
                "publish_attempt_id": publish_attempt_id,
                "acceptance_consumed": True,
                "retry_allowed": False,
            }
        )


def test_publish_attempt_aliases_are_exact() -> None:
    from src.models.publish_attempt import (
        PublishAttemptErrorCode,
        PublishAttemptStatus,
        PublishPlatform,
    )

    assert get_args(PublishPlatform) == ("tiktok", "shopify")
    assert get_args(PublishAttemptStatus) == (
        "prepared",
        "authorization_failed",
        "preflight_failed",
        "acceptance_consumed",
        "published",
        "failed",
        "ambiguous",
    )
    assert get_args(PublishAttemptErrorCode) == (
        "publish_connector_not_ready",
        "publish_connector_not_ready_after_consume",
        "publish_connector_simulated",
        "publish_attempt_store_unavailable",
        "acceptance_not_found",
        "acceptance_expired",
        "acceptance_not_available",
        "acceptance_artifact_integrity_mismatch",
        "acceptance_store_unavailable",
        "publish_artifact_unavailable_after_consume",
        "publish_attempt_state_unknown",
        "publish_connector_failed",
        "publish_outcome_ambiguous",
        "publish_preflight_rejected",
        "publish_preflight_unavailable",
    )


def test_all_publish_models_share_the_strict_configuration() -> None:
    from src.models.publish_attempt import (
        PublishAttemptErrorDetail,
        PublishAttemptErrorResponse,
        PublishAttemptRequest,
        PublishAttemptResponse,
        PublishMetadata,
    )

    for model in (
        PublishMetadata,
        PublishAttemptRequest,
        PublishAttemptResponse,
        PublishAttemptErrorDetail,
        PublishAttemptErrorResponse,
    ):
        assert model.model_config["extra"] == "forbid"
        assert model.model_config["strict"] is True
        assert model.model_config["str_strip_whitespace"] is True


def test_publish_request_validation_schema_locks_authority_boundary() -> None:
    from src.models.publish_attempt import (
        PublishAttemptErrorDetail,
        PublishAttemptRequest,
        PublishAttemptResponse,
        PublishMetadata,
    )

    def string_pattern(schema: dict[str, object], field: str) -> object:
        properties = schema["properties"]
        assert isinstance(properties, dict)
        field_schema = properties[field]
        assert isinstance(field_schema, dict)
        if "pattern" in field_schema:
            return field_schema["pattern"]
        variants = field_schema.get("anyOf")
        assert isinstance(variants, list)
        return next(
            variant["pattern"]
            for variant in variants
            if isinstance(variant, dict) and variant.get("type") == "string"
        )

    request_schema = PublishAttemptRequest.model_json_schema(mode="validation")
    metadata_schema = PublishMetadata.model_json_schema(mode="validation")
    response_schema = PublishAttemptResponse.model_json_schema(mode="validation")
    error_schema = PublishAttemptErrorDetail.model_json_schema(mode="validation")

    assert request_schema["additionalProperties"] is False
    assert request_schema["properties"]["platform"]["enum"] == [
        "tiktok",
        "shopify",
    ]
    assert request_schema["required"] == [
        "acceptance_id",
        "platform",
        "metadata",
        "platform_options",
    ]
    assert metadata_schema["additionalProperties"] is False
    assert set(metadata_schema["properties"]) == {
        "title",
        "description",
        "hook",
        "product_name",
        "hashtags",
        "tags",
    }
    assert metadata_schema["properties"]["hashtags"]["maxItems"] == 30
    assert metadata_schema["properties"]["tags"]["maxItems"] == 30
    assert string_pattern(request_schema, "acceptance_id") == UUID4_PATTERN
    assert string_pattern(response_schema, "publish_attempt_id") == UUID4_PATTERN
    assert string_pattern(response_schema, "acceptance_id") == UUID4_PATTERN
    assert string_pattern(error_schema, "publish_attempt_id") == UUID4_PATTERN
