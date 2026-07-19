from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from types import MappingProxyType
from typing import Any, Literal

ConnectorCredentialReason = Literal[
    "missing_credentials",
    "invalid_configuration",
    "publishing_disabled",
]


@dataclass(frozen=True, slots=True)
class ConnectorCredentialState:
    ready: bool
    reason: ConnectorCredentialReason | None

    def __post_init__(self) -> None:
        if self.ready is (self.reason is not None):
            raise ValueError("connector credential state is inconsistent")


class ConnectorCredentialNotReady(RuntimeError):
    def __init__(self, reason: ConnectorCredentialReason) -> None:
        self.reason = reason
        super().__init__(reason)


class ConnectorPreflightRejected(RuntimeError):
    def __init__(self) -> None:
        super().__init__("connector_preflight_rejected")


class ConnectorPreflightUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("connector_preflight_unavailable")


class ConnectorOutcomeAmbiguous(RuntimeError):
    def __init__(
        self,
        *,
        partial_receipt: Mapping[str, Any] | None = None,
    ) -> None:
        self.partial_receipt = (
            None
            if partial_receipt is None
            else MappingProxyType(dict(partial_receipt))
        )
        super().__init__("connector_outcome_ambiguous")


class ConnectorStatusUnavailable(RuntimeError):
    def __init__(self) -> None:
        super().__init__("connector_status_unavailable")


def _validate_snapshot_time(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("preflight observation time must be UTC")


def _validate_media_duration(value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("preflight media duration is invalid")
    if not isfinite(float(value)) or value <= 0:
        raise ValueError("preflight media duration is invalid")


@dataclass(frozen=True, slots=True)
class TikTokPreflightSnapshot:
    privacy_level: str
    disable_comment: bool
    disable_duet: bool
    disable_stitch: bool
    brand_content_toggle: bool
    brand_organic_toggle: bool
    max_video_post_duration_sec: int
    media_duration_seconds: float
    observed_at: datetime
    platform: Literal["tiktok"] = "tiktok"

    def __post_init__(self) -> None:
        if (
            not self.privacy_level
            or type(self.disable_comment) is not bool
            or type(self.disable_duet) is not bool
            or type(self.disable_stitch) is not bool
            or type(self.brand_content_toggle) is not bool
            or type(self.brand_organic_toggle) is not bool
            or isinstance(self.max_video_post_duration_sec, bool)
            or not isinstance(self.max_video_post_duration_sec, int)
            or self.max_video_post_duration_sec <= 0
        ):
            raise ValueError("TikTok preflight snapshot is invalid")
        _validate_media_duration(self.media_duration_seconds)
        _validate_snapshot_time(self.observed_at)


@dataclass(frozen=True, slots=True)
class ShopifyPreflightSnapshot:
    product_id: str
    required_scopes_verified: bool
    media_duration_seconds: float
    observed_at: datetime
    platform: Literal["shopify"] = "shopify"

    def __post_init__(self) -> None:
        if (
            not self.product_id
            or type(self.required_scopes_verified) is not bool
            or not self.required_scopes_verified
        ):
            raise ValueError("Shopify preflight snapshot is invalid")
        _validate_media_duration(self.media_duration_seconds)
        _validate_snapshot_time(self.observed_at)


ConnectorPreflightSnapshot = TikTokPreflightSnapshot | ShopifyPreflightSnapshot


class PlatformConnector(ABC):
    async def preflight(
        self,
        content: dict[str, Any],
    ) -> ConnectorPreflightSnapshot:
        """Perform read-only provider checks before publish authority is spent."""

        del content
        raise ConnectorPreflightUnavailable

    @abstractmethod
    async def publish(
        self,
        content: dict[str, Any],
        *,
        preflight: ConnectorPreflightSnapshot | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic mapping with exact success/simulated truth."""
        raise NotImplementedError

    @abstractmethod
    async def get_status(self, post_id: str) -> dict[str, Any]:
        """Return a trusted real status mapping or raise a typed error."""
        raise NotImplementedError
