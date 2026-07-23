from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
    model_validator,
)
from pydantic import (
    ValidationError as PydanticValidationError,
)
from pydantic.json_schema import SkipJsonSchema

PublishPlatform = Literal["tiktok", "shopify"]
TikTokPrivacyLevel = Literal[
    "PUBLIC_TO_EVERYONE",
    "MUTUAL_FOLLOW_FRIENDS",
    "FOLLOWER_OF_CREATOR",
    "SELF_ONLY",
]
PublishAttemptStatus = Literal[
    "prepared",
    "authorization_failed",
    "preflight_failed",
    "acceptance_consumed",
    "published",
    "failed",
    "ambiguous",
]
PublishAttemptErrorCode = Literal[
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
]

PublishReceiptProviderStatus = Literal[
    "PROCESSING_UPLOAD",
    "PUBLISH_COMPLETE",
    "FAILED",
    "UPLOADED",
    "PROCESSING",
    "READY",
]
PublishReceiptVerifier = Literal[
    "status_fetch",
    "video_query",
    "file_query_and_product_readback",
]

_UUID4_PATTERN = (
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_UUID4_RE = re.compile(_UUID4_PATTERN)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_METADATA_LIMIT_BYTES = 16 * 1024
_RECEIPT_LIMIT_BYTES = 8 * 1024
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_TIKTOK_POST_ID_RE = re.compile(r"^[1-9][0-9]*$")
_SHOPIFY_VIDEO_GID_RE = re.compile(r"^gid://shopify/Video/[1-9][0-9]*$")
_SHOPIFY_PRODUCT_GID_RE = re.compile(r"^gid://shopify/Product/[1-9][0-9]*$")
AI_GENERATED_DISCLOSURE_TEXT = "AI-generated content."
AI_GENERATED_TITLE_PREFIX = "[AI-generated] "


def _validate_tiktok_post_url(
    *,
    post_id: str,
    post_url: str | None,
    verified_by: str | None,
) -> None:
    if post_url is None:
        if verified_by == "video_query":
            raise ValueError("TikTok video query requires a share URL")
        return
    try:
        parsed = urlsplit(post_url)
        parsed_port = parsed.port
    except ValueError as exc:
        raise ValueError("TikTok share URL is invalid") from exc
    expected_path = re.compile(rf"^/@[^/]+/video/{re.escape(post_id)}/?$")
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"www.tiktok.com", "tiktok.com"}
        or parsed.netloc != parsed.hostname
        or parsed_port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or expected_path.fullmatch(parsed.path) is None
    ):
        raise ValueError("TikTok share URL is invalid")
    if verified_by != "video_query":
        raise ValueError("TikTok share URL requires video query")


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class PublishMetadata(_StrictModel):
    title: str | SkipJsonSchema[None] = Field(
        default_factory=lambda: None,
        min_length=1,
        max_length=300,
    )
    description: str | SkipJsonSchema[None] = Field(
        default_factory=lambda: None,
        min_length=1,
        max_length=5000,
    )
    hook: str | SkipJsonSchema[None] = Field(
        default_factory=lambda: None,
        min_length=1,
        max_length=1000,
    )
    product_name: str | SkipJsonSchema[None] = Field(
        default_factory=lambda: None,
        min_length=1,
        max_length=300,
    )
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("title", "description", "hook", "product_name", mode="before")
    @classmethod
    def reject_explicit_null_text(cls, value: object) -> object:
        if value is None:
            raise ValueError("metadata text must be omitted instead of null")
        return value

    @field_validator("title", "description", "hook", "product_name")
    @classmethod
    def reject_control_text(cls, value: str) -> str:
        if _CONTROL_RE.search(value):
            raise ValueError("metadata text contains control characters")
        return value

    @field_validator("hashtags", "tags")
    @classmethod
    def validate_tag_list(cls, values: list[str]) -> list[str]:
        if any(
            not value
            or len(value) > 100
            or value.startswith("#")
            or _CONTROL_RE.search(value)
            for value in values
        ):
            raise ValueError("tag values are invalid")
        if len(set(values)) != len(values):
            raise ValueError("tag values must be unique")
        return values

    @model_validator(mode="after")
    def enforce_serialized_size(self) -> PublishMetadata:
        encoded = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(encoded) > _METADATA_LIMIT_BYTES:
            raise ValueError("metadata exceeds 16 KiB")
        return self


class PublishDisclosureV1(_StrictModel):
    schema_version: Literal["publish-disclosure.v1"] = "publish-disclosure.v1"
    label: Literal["AI-generated"] = "AI-generated"
    visible_text: Literal["AI-generated content."] = AI_GENERATED_DISCLOSURE_TEXT
    sidecar_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_artifact_c2pa_status: Literal["signed_local_readback"]
    verification_scope: Literal["local_reader_only"] = "local_reader_only"
    independently_validated: Literal[False] = False


def effective_tiktok_metadata(
    metadata: PublishMetadata,
) -> tuple[str, str, list[str]]:
    title = metadata.title or metadata.hook or "AI-generated video"
    description = metadata.description or metadata.hook or title
    tags = list(metadata.hashtags or metadata.tags)
    if tags:
        description = description + "\n" + " ".join(f"#{tag}" for tag in tags)
    lines = [
        line
        for line in description.splitlines()
        if line.strip() != AI_GENERATED_DISCLOSURE_TEXT
    ]
    body = "\n".join(lines).strip()
    effective = (
        f"{body}\n{AI_GENERATED_DISCLOSURE_TEXT}"
        if body
        else AI_GENERATED_DISCLOSURE_TEXT
    )
    if len(effective) > 2200:
        raise ValueError("TikTok metadata exceeds limit after AI disclosure")
    return title, effective, tags


def effective_shopify_title(metadata: PublishMetadata) -> str:
    title = metadata.title or metadata.hook or "AI-generated video"
    while title.startswith(AI_GENERATED_TITLE_PREFIX):
        title = title[len(AI_GENERATED_TITLE_PREFIX) :].lstrip()
    effective = f"{AI_GENERATED_TITLE_PREFIX}{title}"
    if len(effective) > 300:
        raise ValueError("Shopify metadata exceeds limit after AI disclosure")
    return effective


class TikTokPublishOptions(_StrictModel):
    platform: Literal["tiktok"]
    privacy_level: TikTokPrivacyLevel
    disable_comment: bool
    disable_duet: bool
    disable_stitch: bool
    brand_content_toggle: bool
    brand_organic_toggle: bool

    @field_validator(
        "disable_comment",
        "disable_duet",
        "disable_stitch",
        "brand_content_toggle",
        "brand_organic_toggle",
        mode="before",
    )
    @classmethod
    def validate_boolean_literals(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("publish option boolean must be exact")
        return value


class ShopifyPublishOptions(_StrictModel):
    platform: Literal["shopify"]
    product_id: str = Field(pattern=r"^gid://shopify/Product/[1-9][0-9]*$")

    @field_validator("product_id", mode="before")
    @classmethod
    def validate_product_id_type(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("product_id must be an exact Product GID")
        return value


PublishPlatformOptions = Annotated[
    TikTokPublishOptions | ShopifyPublishOptions,
    Field(discriminator="platform"),
]


class PublishAttemptRequest(_StrictModel):
    acceptance_id: str = Field(pattern=_UUID4_PATTERN)
    platform: PublishPlatform
    metadata: PublishMetadata
    platform_options: PublishPlatformOptions

    @field_validator("acceptance_id", mode="before")
    @classmethod
    def validate_acceptance_id(cls, value: object) -> object:
        if not isinstance(value, str) or _UUID4_RE.fullmatch(value) is None:
            raise ValueError("acceptance_id is invalid")
        return value

    @model_validator(mode="after")
    def validate_platform_options_match(self) -> PublishAttemptRequest:
        if self.platform_options.platform != self.platform:
            raise ValueError("platform_options must match platform")
        if self.platform == "tiktok":
            effective_tiktok_metadata(self.metadata)
        else:
            effective_shopify_title(self.metadata)
        return self


class PublishReceiptV1(_StrictModel):
    schema_version: Literal["publish-receipt.v1"]
    platform: PublishPlatform
    protocol_version: Literal[
        "tiktok-content-posting-v2",
        "shopify-admin-2026-07",
    ]
    completion_scope: Literal[
        "tiktok_direct_post",
        "shopify_product_media",
    ]
    provider_operation_id: str | None = Field(max_length=64)
    provider_resource_id: str | None = Field(max_length=256)
    target_id: str | None = Field(max_length=256)
    provider_status: PublishReceiptProviderStatus | None
    post_id: str | None = Field(max_length=128)
    post_url: str | None = Field(max_length=2048)
    public_visibility_verified: bool
    observed_at: datetime
    verified_by: PublishReceiptVerifier | None
    simulated: Literal[False]

    @field_validator("simulated", "public_visibility_verified", mode="before")
    @classmethod
    def validate_receipt_boolean_literals(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("receipt boolean must be exact")
        return value

    @field_validator("observed_at", mode="before")
    @classmethod
    def parse_observed_at(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            try:
                return datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError("receipt observed_at is invalid") from exc
        return value

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("receipt observed_at must be UTC")
        return value.astimezone(UTC)

    @field_validator(
        "provider_operation_id",
        "provider_resource_id",
        "target_id",
        "post_id",
        "post_url",
    )
    @classmethod
    def validate_safe_receipt_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if (
            not value
            or value != value.strip()
            or _CONTROL_RE.search(value)
            or "mock" in value.lower()
        ):
            raise ValueError("receipt text is unsafe")
        return value

    @model_validator(mode="after")
    def validate_platform_receipt(self) -> PublishReceiptV1:
        if not any(
            value is not None
            for value in (
                self.provider_operation_id,
                self.provider_resource_id,
                self.provider_status,
            )
        ):
            raise ValueError("receipt has no provider observation")
        if self.platform == "tiktok":
            self._validate_tiktok_receipt()
        else:
            self._validate_shopify_receipt()
        if len(self.canonical_json_bytes()) > _RECEIPT_LIMIT_BYTES:
            raise ValueError("receipt exceeds 8 KiB")
        return self

    def _validate_tiktok_receipt(self) -> None:
        if (
            self.protocol_version != "tiktok-content-posting-v2"
            or self.completion_scope != "tiktok_direct_post"
            or self.target_id is not None
            or self.provider_status
            not in {None, "PROCESSING_UPLOAD", "PUBLISH_COMPLETE", "FAILED"}
        ):
            raise ValueError("TikTok receipt fields are contradictory")
        if self.provider_operation_id is None:
            raise ValueError("TikTok receipt requires an operation ID")
        if self.provider_resource_id is not None and not _TIKTOK_POST_ID_RE.fullmatch(
            self.provider_resource_id
        ):
            raise ValueError("TikTok resource ID is invalid")
        if self.post_id is not None and not _TIKTOK_POST_ID_RE.fullmatch(self.post_id):
            raise ValueError("TikTok post ID is invalid")
        if self.provider_resource_id != self.post_id:
            raise ValueError("TikTok resource and post IDs must match")
        if self.public_visibility_verified is (self.post_id is None):
            raise ValueError("TikTok public visibility is contradictory")
        if self.provider_status != "PUBLISH_COMPLETE" and (
            self.post_id is not None
            or self.post_url is not None
            or self.verified_by is not None
            or self.public_visibility_verified
        ):
            raise ValueError("nonterminal TikTok receipt claims completion")
        if self.verified_by not in {None, "status_fetch", "video_query"}:
            raise ValueError("TikTok verifier is invalid")
        if self.post_url is not None:
            self._validate_tiktok_share_url()
            if self.verified_by != "video_query":
                raise ValueError("TikTok share URL requires video query")
        elif self.verified_by == "video_query":
            raise ValueError("TikTok video query requires a share URL")

    def _validate_tiktok_share_url(self) -> None:
        assert self.post_url is not None
        assert self.post_id is not None
        _validate_tiktok_post_url(
            post_id=self.post_id,
            post_url=self.post_url,
            verified_by=self.verified_by,
        )

    def _validate_shopify_receipt(self) -> None:
        if (
            self.protocol_version != "shopify-admin-2026-07"
            or self.completion_scope != "shopify_product_media"
            or self.provider_operation_id is not None
            or self.provider_status
            not in {None, "UPLOADED", "PROCESSING", "READY", "FAILED"}
            or self.post_id is not None
            or self.post_url is not None
            or self.public_visibility_verified
        ):
            raise ValueError("Shopify receipt fields are contradictory")
        if (
            self.target_id is None
            or _SHOPIFY_PRODUCT_GID_RE.fullmatch(self.target_id) is None
        ):
            raise ValueError("Shopify target ID is invalid")
        if self.provider_resource_id is not None and _SHOPIFY_VIDEO_GID_RE.fullmatch(
            self.provider_resource_id
        ) is None:
            raise ValueError("Shopify resource ID is invalid")
        if self.verified_by not in {None, "file_query_and_product_readback"}:
            raise ValueError("Shopify verifier is invalid")
        if self.verified_by is not None and (
            self.provider_status != "READY" or self.provider_resource_id is None
        ):
            raise ValueError("Shopify verifier requires a ready video")

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def canonical_json_bytes(self) -> bytes:
        return self.canonical_json().encode("utf-8")

    def validate_published(self) -> PublishReceiptV1:
        valid = False
        if self.platform == "tiktok":
            valid = (
                self.provider_status == "PUBLISH_COMPLETE"
                and self.provider_operation_id is not None
                and self.verified_by in {"status_fetch", "video_query"}
            )
        elif self.platform == "shopify":
            valid = (
                self.provider_status == "READY"
                and self.provider_resource_id is not None
                and self.target_id is not None
                and self.verified_by == "file_query_and_product_readback"
            )
        if not valid:
            raise ValueError("published receipt is invalid")
        return self


class PublishAttemptResponse(_StrictModel):
    publish_attempt_id: str = Field(pattern=_UUID4_PATTERN)
    acceptance_id: str = Field(pattern=_UUID4_PATTERN)
    platform: PublishPlatform
    status: Literal["published"]
    success: Literal[True]
    post_id: str | None = Field(default=None, max_length=256)
    post_url: str | None = Field(default=None, max_length=2048)
    receipt: PublishReceiptV1
    acceptance_consumed: Literal[True]
    retry_allowed: Literal[False]

    @field_validator("success", "acceptance_consumed", "retry_allowed", mode="before")
    @classmethod
    def validate_boolean_literals(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("boolean literal is invalid")
        return value

    @field_validator("publish_attempt_id", "acceptance_id", mode="before")
    @classmethod
    def validate_ids(cls, value: object) -> object:
        if not isinstance(value, str) or _UUID4_RE.fullmatch(value) is None:
            raise ValueError("identifier is invalid")
        return value

    @field_validator("post_id")
    @classmethod
    def validate_post_id(cls, value: str | None) -> str | None:
        if value is not None and (_CONTROL_RE.search(value) or not value):
            raise ValueError("post_id is invalid")
        return value

    @field_validator("post_url", mode="before")
    @classmethod
    def validate_post_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        if _CONTROL_RE.search(value) or any(character.isspace() for character in value):
            raise ValueError("post_url is invalid")
        try:
            _HTTP_URL_ADAPTER.validate_python(value, strict=True)
            parsed = urlsplit(value)
            hostname = parsed.hostname
            parsed.port
        except (PydanticValidationError, ValueError) as exc:
            raise ValueError("post_url is invalid") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("post_url is invalid")
        return value

    @model_validator(mode="after")
    def validate_receipt_projection(self) -> PublishAttemptResponse:
        self.receipt.validate_published()
        if (
            self.receipt.platform != self.platform
            or self.receipt.post_id != self.post_id
            or self.receipt.post_url != self.post_url
        ):
            raise ValueError("published receipt projection is contradictory")
        return self


class PublishAttemptReadbackResponse(_StrictModel):
    publish_attempt_id: str = Field(pattern=_UUID4_PATTERN)
    acceptance_id: str = Field(pattern=_UUID4_PATTERN)
    platform: PublishPlatform
    status: PublishAttemptStatus
    error_code: PublishAttemptErrorCode | None
    post_id: str | None = Field(default=None, max_length=256)
    post_url: str | None = Field(default=None, max_length=2048)
    receipt: PublishReceiptV1 | None
    acceptance_consumed: bool | None
    retry_allowed: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("publish_attempt_id", "acceptance_id", mode="before")
    @classmethod
    def validate_ids(cls, value: object) -> object:
        if not isinstance(value, str) or _UUID4_RE.fullmatch(value) is None:
            raise ValueError("identifier is invalid")
        return value

    @field_validator("acceptance_consumed", "retry_allowed", mode="before")
    @classmethod
    def validate_readback_boolean_literals(cls, value: object) -> object:
        if value is not None and type(value) is not bool:
            raise ValueError("readback boolean must be exact")
        return value

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def parse_readback_timestamp(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
            try:
                return datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError("attempt timestamp is invalid") from exc
        return value

    @field_validator("post_id")
    @classmethod
    def validate_post_id(cls, value: str | None) -> str | None:
        if value is not None and (
            not value or value != value.strip() or _CONTROL_RE.search(value)
        ):
            raise ValueError("post_id is invalid")
        return value

    @field_validator("post_url", mode="before")
    @classmethod
    def validate_post_url(cls, value: object) -> object:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        if _CONTROL_RE.search(value) or any(character.isspace() for character in value):
            raise ValueError("post_url is invalid")
        try:
            _HTTP_URL_ADAPTER.validate_python(value, strict=True)
            parsed = urlsplit(value)
            hostname = parsed.hostname
            parsed.port
        except (PydanticValidationError, ValueError) as exc:
            raise ValueError("post_url is invalid") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("post_url is invalid")
        return value

    @model_validator(mode="after")
    def validate_state_projection(self) -> PublishAttemptReadbackResponse:
        consumed_statuses = {"acceptance_consumed", "published", "failed", "ambiguous"}
        preconsume_terminal = {"authorization_failed", "preflight_failed"}
        if self.status in consumed_statuses:
            if self.acceptance_consumed is not True or self.retry_allowed:
                raise ValueError("post-consume readback projection is invalid")
        elif self.status in preconsume_terminal:
            if self.acceptance_consumed is not False:
                raise ValueError("pre-consume readback projection is invalid")
        elif self.acceptance_consumed is not None or self.retry_allowed:
            raise ValueError("active readback projection is invalid")

        if self.status == "preflight_failed" and not self.retry_allowed:
            raise ValueError("preflight failure retry projection is invalid")
        if self.status == "authorization_failed":
            expected_retry = self.error_code == "acceptance_store_unavailable"
            if self.retry_allowed is not expected_retry:
                raise ValueError("authorization retry projection is invalid")

        terminal_errors = {
            "authorization_failed",
            "preflight_failed",
            "failed",
            "ambiguous",
        }
        if (self.status in terminal_errors) is (self.error_code is None):
            raise ValueError("attempt error projection is invalid")

        if self.status == "published":
            if self.receipt is not None:
                self.receipt.validate_published()
                if (
                    self.receipt.platform != self.platform
                    or self.receipt.post_id != self.post_id
                    or self.receipt.post_url != self.post_url
                ):
                    raise ValueError("published readback receipt is contradictory")
            return self

        if self.post_id is not None or self.post_url is not None:
            raise ValueError("non-published readback cannot carry a post")
        if self.receipt is not None:
            if (
                self.status not in {"failed", "ambiguous"}
                or self.receipt.platform != self.platform
                or self.receipt.post_id is not None
                or self.receipt.post_url is not None
                or self.receipt.public_visibility_verified
            ):
                raise ValueError("readback partial receipt is contradictory")
            try:
                self.receipt.validate_published()
            except ValueError:
                receipt_claims_completion = False
            else:
                receipt_claims_completion = True
            if receipt_claims_completion:
                raise ValueError("readback partial receipt claims completion")
        return self


class DurableTikTokStatusResponse(_StrictModel):
    platform: Literal["tiktok"]
    post_id: str = Field(pattern=r"^[1-9][0-9]*$", max_length=128)
    status: Literal["PUBLISH_COMPLETE"]
    post_url: str | None = Field(default=None, max_length=2048)
    simulated: Literal[False]
    observed_at: datetime
    verified_by: Literal["status_fetch", "video_query"]

    @field_validator("simulated", mode="before")
    @classmethod
    def validate_simulated(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("simulated must be exact")
        return value

    @model_validator(mode="after")
    def validate_status_url(self) -> DurableTikTokStatusResponse:
        _validate_tiktok_post_url(
            post_id=self.post_id,
            post_url=self.post_url,
            verified_by=self.verified_by,
        )
        return self


class PublishAttemptErrorDetail(_StrictModel):
    code: PublishAttemptErrorCode
    publish_attempt_id: str | None = Field(default=None, pattern=_UUID4_PATTERN)
    acceptance_consumed: bool | None
    retry_allowed: bool

    @field_validator("publish_attempt_id", mode="before")
    @classmethod
    def validate_attempt_id(cls, value: object) -> object:
        if value is not None and (
            not isinstance(value, str) or _UUID4_RE.fullmatch(value) is None
        ):
            raise ValueError("publish_attempt_id is invalid")
        return value

    @model_validator(mode="after")
    def enforce_retry_invariant(self) -> PublishAttemptErrorDetail:
        if self.retry_allowed and self.acceptance_consumed is not False:
            raise ValueError("retry requires a known unconsumed acceptance")
        return self


class PublishAttemptErrorResponse(_StrictModel):
    detail: PublishAttemptErrorDetail
