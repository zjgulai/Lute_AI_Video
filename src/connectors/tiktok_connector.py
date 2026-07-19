"""Strict TikTok Content Posting API v2 Direct Post connector."""

import asyncio
import inspect
import logging
import math
import os
import re
import subprocess
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorCredentialState,
    ConnectorOutcomeAmbiguous,
    ConnectorPreflightRejected,
    ConnectorPreflightUnavailable,
    ConnectorStatusUnavailable,
    PlatformConnector,
    TikTokPreflightSnapshot,
)
from src.models.publish_attempt import PublishReceiptV1, TikTokPublishOptions
from src.tasks.metrics_poller import PlatformMetricsError, classify_platform_http_status

logger = logging.getLogger(__name__)

# TikTok Content Posting API v2 endpoints are intentionally not configurable.
_TIKTOK_ORIGIN = "https://open.tiktokapis.com"
_TIKTOK_CREATOR_INFO_URL = (
    f"{_TIKTOK_ORIGIN}/v2/post/publish/creator_info/query/"
)
_TIKTOK_DIRECT_POST_INIT_URL = f"{_TIKTOK_ORIGIN}/v2/post/publish/video/init/"
_TIKTOK_STATUS_FETCH_URL = f"{_TIKTOK_ORIGIN}/v2/post/publish/status/fetch/"
_TIKTOK_VIDEO_QUERY_URL = f"{_TIKTOK_ORIGIN}/v2/video/query/"
_TIKTOK_METRICS_QUERY_URL = _TIKTOK_VIDEO_QUERY_URL
_TIKTOK_METRIC_FIELDS = "id,view_count,like_count,comment_count,share_count"
_TIKTOK_SHARE_FIELDS = "id,share_url"

_PUBLISH_OVERRIDE_ENV_NAMES = (
    "TIKTOK_USERNAME",
    "TIKTOK_API_UPLOAD_URL",
    "TIKTOK_API_BASE_URL",
)
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}
_MAX_VIDEO_BYTES = 4 * 1024 * 1024 * 1024
_MIN_CHUNK_BYTES = 5 * 1024 * 1024
_MAX_CHUNK_BYTES = 64 * 1024 * 1024
_MAX_FINAL_CHUNK_BYTES = 128 * 1024 * 1024
_MAX_CHUNK_COUNT = 1000
_MAX_TITLE_CHARACTERS = 2200
_PUBLISH_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{1,64}$")
_POST_ID_RE = re.compile(r"^[1-9][0-9]*$")
_UNSAFE_TITLE_RE = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")

MediaProbe: TypeAlias = Callable[[Path], float | Awaitable[float]]
Sleep: TypeAlias = Callable[[float], Awaitable[None]]
Clock: TypeAlias = Callable[[], float]
Now: TypeAlias = Callable[[], datetime]


class _TikTokDeterministicFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _TikTokMedia:
    path: Path
    size_bytes: int
    mime_type: str
    duration_seconds: float
    chunks: tuple[tuple[int, int], ...]


def _build_chunk_plan(size_bytes: int) -> tuple[tuple[int, int], ...]:
    if (
        isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes <= 0
        or size_bytes > _MAX_VIDEO_BYTES
    ):
        raise ValueError("TikTok video size is invalid")
    chunk_size = size_bytes if size_bytes < _MIN_CHUNK_BYTES else _MAX_CHUNK_BYTES
    chunks: list[tuple[int, int]] = []
    start = 0
    while start < size_bytes:
        end = min(start + chunk_size, size_bytes) - 1
        chunks.append((start, end))
        start = end + 1
    if not chunks or len(chunks) > _MAX_CHUNK_COUNT:
        raise ValueError("TikTok chunk count is invalid")
    for index, (start, end) in enumerate(chunks):
        length = end - start + 1
        if start < 0 or end < start:
            raise ValueError("TikTok chunk plan is invalid")
        if index < len(chunks) - 1 and not (
            _MIN_CHUNK_BYTES <= length <= _MAX_CHUNK_BYTES
        ):
            raise ValueError("TikTok chunk size is invalid")
        if index == len(chunks) - 1 and length > _MAX_FINAL_CHUNK_BYTES:
            raise ValueError("TikTok final chunk is invalid")
    return tuple(chunks)


def _default_media_probe(path: Path) -> float:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError("media probe unavailable")
    value = float(completed.stdout.strip())
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError("media probe unavailable")
    return value


def _read_nonempty_env(name: str) -> str | None:
    raw = os.environ.get(name)
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    return value or None


def _publish_enabled() -> bool:
    raw = os.environ.get("TIKTOK_PUBLISH_ENABLED")
    return isinstance(raw, str) and raw.strip().lower() in _TRUTHY_VALUES


def _credential_state() -> ConnectorCredentialState:
    if any(_read_nonempty_env(name) is not None for name in _PUBLISH_OVERRIDE_ENV_NAMES):
        return ConnectorCredentialState(False, "invalid_configuration")
    if not _publish_enabled():
        return ConnectorCredentialState(False, "publishing_disabled")
    if _read_nonempty_env("TIKTOK_ACCESS_TOKEN") is None:
        return ConnectorCredentialState(False, "missing_credentials")
    return ConnectorCredentialState(True, None)


def _require_access_token() -> str:
    state = _credential_state()
    token = _read_nonempty_env("TIKTOK_ACCESS_TOKEN")
    if not state.ready or token is None:
        raise ConnectorCredentialNotReady(state.reason or "missing_credentials")
    return token


def _classify_tiktok_error(code: str, message: str) -> str:
    value = f"{code} {message}".lower()
    if any(marker in value for marker in ("auth", "token", "scope", "permission")):
        return "auth"
    if any(marker in value for marker in ("rate", "quota", "too many")):
        return "rate_limit"
    if any(marker in value for marker in ("not_found", "not found", "does not exist")):
        return "not_found"
    if any(marker in value for marker in ("invalid", "field", "schema", "param")):
        return "schema_drift"
    return "transient"


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_tiktok_video_metrics(video: dict[str, Any]) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    field_map = {
        "view_count": "views",
        "like_count": "likes",
        "comment_count": "comments",
        "share_count": "shares",
    }
    for source, target in field_map.items():
        value = _coerce_int(video.get(source))
        if value is not None:
            metrics[target] = value
    return metrics


class TikTokConnector(PlatformConnector):
    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        media_probe: MediaProbe | None = None,
        sleep: Sleep = asyncio.sleep,
        monotonic: Clock = time.monotonic,
        now: Now | None = None,
        max_status_polls: int = 6,
        poll_interval_seconds: float = 2.0,
        poll_deadline_seconds: float = 30.0,
    ) -> None:
        if (
            isinstance(max_status_polls, bool)
            or not isinstance(max_status_polls, int)
            or max_status_polls <= 0
            or not math.isfinite(poll_interval_seconds)
            or poll_interval_seconds < 0
            or not math.isfinite(poll_deadline_seconds)
            or poll_deadline_seconds <= 0
        ):
            raise ValueError("TikTok polling configuration is invalid")
        self._http_client = http_client
        self._media_probe = media_probe or _default_media_probe
        self._sleep = sleep
        self._monotonic = monotonic
        self._now = now or (lambda: datetime.now(UTC))
        self._max_status_polls = max_status_polls
        self._poll_interval_seconds = poll_interval_seconds
        self._poll_deadline_seconds = poll_deadline_seconds

    async def _post(
        self,
        url: str,
        *,
        timeout_seconds: float,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(
                url,
                follow_redirects=False,
                **kwargs,
            )
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
        ) as client:
            return await client.post(url, **kwargs)

    async def _put(
        self,
        url: str,
        *,
        timeout_seconds: float,
        **kwargs: Any,
    ) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.put(
                url,
                follow_redirects=False,
                **kwargs,
            )
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=False,
        ) as client:
            return await client.put(url, **kwargs)

    async def fetch_metrics(self, post_id: str) -> dict[str, Any]:
        """Fetch performance metrics for a TikTok post.

        Uses TikTok's official `/v2/video/query/` endpoint. The endpoint
        verifies ownership of the requested video for the authorized user and
        returns the requested video object fields.
        """
        token = os.environ.get("TIKTOK_ACCESS_TOKEN", "")
        if not token:
            raise PlatformMetricsError(
                "auth",
                "TIKTOK_ACCESS_TOKEN is required for TikTok metrics",
            )

        resp = await self._post_metrics_query(token, post_id)
        if resp.status_code != 200:
            raise PlatformMetricsError(
                classify_platform_http_status(resp.status_code),
                f"TikTok metrics HTTP {resp.status_code}",
            )

        data = resp.json()
        error = data.get("error") or {}
        error_code = str(error.get("code") or "").lower()
        if error and error_code not in {"", "ok", "0"}:
            raise PlatformMetricsError(
                _classify_tiktok_error(error_code, str(error.get("message") or "")),
                f"TikTok metrics error {error_code}: {error.get('message', '')}",
            )

        videos = data.get("data", {}).get("videos")
        if not isinstance(videos, list):
            raise PlatformMetricsError(
                "schema_drift",
                "TikTok metrics response missing data.videos list",
            )
        video = next(
            (item for item in videos if str(item.get("id")) == str(post_id)),
            videos[0] if videos else None,
        )
        if not isinstance(video, dict):
            raise PlatformMetricsError(
                "not_found",
                f"TikTok video {post_id} was not returned by metrics query",
            )

        metrics = _normalize_tiktok_video_metrics(video)
        if not metrics:
            raise PlatformMetricsError(
                "schema_drift",
                "TikTok video object has no supported metric fields",
            )
        return metrics

    async def _post_metrics_query(self, token: str, post_id: str) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {"filters": {"video_ids": [str(post_id)]}}
        params = {"fields": _TIKTOK_METRIC_FIELDS}
        if self._http_client is not None:
            return await self._http_client.post(
                _TIKTOK_METRICS_QUERY_URL,
                headers=headers,
                params=params,
                json=payload,
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(
                _TIKTOK_METRICS_QUERY_URL,
                headers=headers,
                params=params,
                json=payload,
            )

    async def preflight(self, content: dict[str, Any]) -> TikTokPreflightSnapshot:
        token = _require_access_token()
        media, options, _ = await self._validate_local_content(content)
        creator = await self._query_creator_info(token)
        privacy_options = creator.get("privacy_level_options")
        comment_disabled = creator.get("comment_disabled")
        duet_disabled = creator.get("duet_disabled")
        stitch_disabled = creator.get("stitch_disabled")
        max_duration = creator.get("max_video_post_duration_sec")
        if (
            not isinstance(privacy_options, list)
            or not privacy_options
            or any(not isinstance(value, str) for value in privacy_options)
            or type(comment_disabled) is not bool
            or type(duet_disabled) is not bool
            or type(stitch_disabled) is not bool
            or isinstance(max_duration, bool)
            or not isinstance(max_duration, int)
            or max_duration <= 0
        ):
            raise ConnectorPreflightUnavailable
        if (
            options.privacy_level not in privacy_options
            or (comment_disabled and not options.disable_comment)
            or (duet_disabled and not options.disable_duet)
            or (stitch_disabled and not options.disable_stitch)
            or media.duration_seconds > max_duration
        ):
            raise ConnectorPreflightRejected
        return TikTokPreflightSnapshot(
            privacy_level=options.privacy_level,
            disable_comment=options.disable_comment,
            disable_duet=options.disable_duet,
            disable_stitch=options.disable_stitch,
            brand_content_toggle=options.brand_content_toggle,
            brand_organic_toggle=options.brand_organic_toggle,
            max_video_post_duration_sec=max_duration,
            media_duration_seconds=media.duration_seconds,
            observed_at=self._utc_now(),
        )

    async def publish(
        self,
        content: dict[str, Any],
        *,
        preflight: TikTokPreflightSnapshot | None = None,
    ) -> dict[str, Any]:
        token = _require_access_token()
        if not isinstance(preflight, TikTokPreflightSnapshot):
            raise ConnectorPreflightUnavailable
        publish_id: str | None = None
        last_status: str | None = None
        try:
            media, options, title = await self._validate_local_content(content)
            if not self._snapshot_matches(
                preflight=preflight,
                options=options,
                duration_seconds=media.duration_seconds,
            ):
                raise ConnectorOutcomeAmbiguous
            publish_id, upload_url = await self._initialize_direct_post(
                token=token,
                media=media,
                options=options,
                title=title,
            )
            await self._upload_chunks(upload_url=upload_url, media=media)
            status, post_ids = await self._poll_publish_status(
                token=token,
                publish_id=publish_id,
            )
            last_status = status
            if status == "FAILED":
                return self._failure_result(
                    receipt=self._receipt(
                        publish_id=publish_id,
                        provider_status="FAILED",
                    )
                )
            post_id = post_ids[0] if post_ids else None
            receipt = self._receipt(
                publish_id=publish_id,
                provider_status="PUBLISH_COMPLETE",
                post_id=post_id,
                public_visibility_verified=post_id is not None,
                verified_by="status_fetch",
            )
            if post_id is not None:
                try:
                    share_url = await self._query_share_url(
                        token=token,
                        post_id=post_id,
                    )
                    if share_url is not None:
                        receipt = self._receipt(
                            publish_id=publish_id,
                            provider_status="PUBLISH_COMPLETE",
                            post_id=post_id,
                            post_url=share_url,
                            public_visibility_verified=True,
                            verified_by="video_query",
                        )
                except ConnectorOutcomeAmbiguous:
                    raise ConnectorOutcomeAmbiguous(
                        partial_receipt=self._receipt(
                            publish_id=publish_id,
                            provider_status="PUBLISH_COMPLETE",
                        ).model_dump(mode="json")
                    ) from None
            receipt.validate_published()
            return {
                "success": True,
                "simulated": False,
                "platform": "tiktok",
                "status": "published",
                "post_id": receipt.post_id,
                "url": receipt.post_url,
                "receipt": receipt.model_dump(mode="json"),
            }
        except _TikTokDeterministicFailure:
            receipt = (
                self._receipt(
                    publish_id=publish_id,
                    provider_status=last_status or "PROCESSING_UPLOAD",
                )
                if publish_id is not None
                else None
            )
            return self._failure_result(receipt=receipt)
        except ConnectorOutcomeAmbiguous as exc:
            if exc.partial_receipt is not None:
                raise
            receipt = (
                self._receipt(
                    publish_id=publish_id,
                    provider_status=last_status,
                )
                if publish_id is not None
                else None
            )
            raise ConnectorOutcomeAmbiguous(
                partial_receipt=(
                    receipt.model_dump(mode="json") if receipt is not None else None
                )
            ) from None
        except ConnectorPreflightUnavailable as exc:
            logger.warning(
                "tiktok_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        except Exception as exc:
            logger.warning(
                "tiktok_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            receipt = (
                self._receipt(
                    publish_id=publish_id,
                    provider_status=last_status,
                )
                if publish_id is not None
                else None
            )
            raise ConnectorOutcomeAmbiguous(
                partial_receipt=(
                    receipt.model_dump(mode="json") if receipt is not None else None
                )
            ) from None

    async def _validate_local_content(
        self,
        content: Mapping[str, Any],
    ) -> tuple[_TikTokMedia, TikTokPublishOptions, str]:
        video_path = content.get("video_path")
        title = content.get("description", content.get("title"))
        try:
            options = TikTokPublishOptions.model_validate(
                content.get("platform_options")
            )
        except ValidationError:
            raise ConnectorPreflightRejected from None
        if (
            not isinstance(video_path, str)
            or not video_path
            or not isinstance(title, str)
            or not title
            or len(title) > _MAX_TITLE_CHARACTERS
            or _UNSAFE_TITLE_RE.search(title)
        ):
            raise ConnectorPreflightRejected
        path = Path(video_path)
        mime_type = _MIME_BY_SUFFIX.get(path.suffix.lower())
        try:
            size_bytes = path.stat().st_size
        except OSError:
            raise ConnectorPreflightRejected from None
        if mime_type is None:
            raise ConnectorPreflightRejected
        try:
            chunks = _build_chunk_plan(size_bytes)
        except ValueError:
            raise ConnectorPreflightRejected from None
        try:
            duration = self._media_probe(path)
            if inspect.isawaitable(duration):
                duration = await duration
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int | float)
                or not math.isfinite(float(duration))
                or duration <= 0
            ):
                raise ValueError("duration is invalid")
        except Exception:
            raise ConnectorPreflightUnavailable from None
        return (
            _TikTokMedia(
                path=path,
                size_bytes=size_bytes,
                mime_type=mime_type,
                duration_seconds=float(duration),
                chunks=chunks,
            ),
            options,
            title,
        )

    async def _query_creator_info(self, token: str) -> Mapping[str, Any]:
        try:
            response = await self._post(
                _TIKTOK_CREATOR_INFO_URL,
                timeout_seconds=30.0,
                headers=self._json_headers(token),
                json={},
            )
        except Exception as exc:
            logger.warning(
                "tiktok_preflight_unavailable error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorPreflightUnavailable from None
        if 400 <= response.status_code < 500:
            raise ConnectorPreflightRejected
        if response.status_code != 200:
            raise ConnectorPreflightUnavailable
        try:
            payload = response.json()
        except Exception:
            raise ConnectorPreflightUnavailable from None
        if not isinstance(payload, Mapping):
            raise ConnectorPreflightUnavailable
        error = payload.get("error")
        if not isinstance(error, Mapping) or not isinstance(error.get("code"), str):
            raise ConnectorPreflightUnavailable
        if error["code"] != "ok":
            raise ConnectorPreflightRejected
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ConnectorPreflightUnavailable
        return data

    async def _initialize_direct_post(
        self,
        *,
        token: str,
        media: _TikTokMedia,
        options: TikTokPublishOptions,
        title: str,
    ) -> tuple[str, str]:
        chunk_size = media.chunks[0][1] - media.chunks[0][0] + 1
        payload = {
            "post_info": {
                "title": title,
                "privacy_level": options.privacy_level,
                "disable_duet": options.disable_duet,
                "disable_comment": options.disable_comment,
                "disable_stitch": options.disable_stitch,
                "brand_content_toggle": options.brand_content_toggle,
                "brand_organic_toggle": options.brand_organic_toggle,
                "is_aigc": True,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": media.size_bytes,
                "chunk_size": chunk_size,
                "total_chunk_count": len(media.chunks),
            },
        }
        try:
            response = await self._post(
                _TIKTOK_DIRECT_POST_INIT_URL,
                timeout_seconds=30.0,
                headers=self._json_headers(token),
                json=payload,
            )
        except Exception as exc:
            logger.warning(
                "tiktok_publish_init_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        if 400 <= response.status_code < 500:
            raise _TikTokDeterministicFailure
        if response.status_code != 200:
            raise ConnectorOutcomeAmbiguous
        data = self._mutation_data(response)
        publish_id = data.get("publish_id")
        upload_url = data.get("upload_url")
        if (
            not isinstance(publish_id, str)
            or _PUBLISH_ID_RE.fullmatch(publish_id) is None
            or not isinstance(upload_url, str)
            or not self._is_safe_upload_url(upload_url)
        ):
            raise ConnectorOutcomeAmbiguous
        return publish_id, upload_url

    async def _upload_chunks(
        self,
        *,
        upload_url: str,
        media: _TikTokMedia,
    ) -> None:
        try:
            with media.path.open("rb") as video_file:
                for index, (start, end) in enumerate(media.chunks):
                    length = end - start + 1
                    chunk = video_file.read(length)
                    if len(chunk) != length:
                        raise ConnectorOutcomeAmbiguous
                    response = await self._put(
                        upload_url,
                        timeout_seconds=300.0,
                        headers={
                            "Content-Type": media.mime_type,
                            "Content-Length": str(length),
                            "Content-Range": (
                                f"bytes {start}-{end}/{media.size_bytes}"
                            ),
                        },
                        content=chunk,
                    )
                    expected_status = 201 if index == len(media.chunks) - 1 else 206
                    if 400 <= response.status_code < 500:
                        raise _TikTokDeterministicFailure
                    if response.status_code != expected_status:
                        raise ConnectorOutcomeAmbiguous
                if video_file.read(1):
                    raise ConnectorOutcomeAmbiguous
        except (_TikTokDeterministicFailure, ConnectorOutcomeAmbiguous):
            raise
        except Exception as exc:
            logger.warning(
                "tiktok_upload_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None

    async def _poll_publish_status(
        self,
        *,
        token: str,
        publish_id: str,
    ) -> tuple[str, tuple[str, ...]]:
        started = self._monotonic()
        last_status: str | None = None
        for index in range(self._max_status_polls):
            status, post_ids = await self._fetch_publish_status(
                token=token,
                publish_id=publish_id,
            )
            last_status = status
            if status in {"PUBLISH_COMPLETE", "FAILED"}:
                return status, post_ids
            if index == self._max_status_polls - 1:
                break
            if self._monotonic() - started >= self._poll_deadline_seconds:
                break
            await self._sleep(self._poll_interval_seconds)
        raise ConnectorOutcomeAmbiguous(
            partial_receipt=self._receipt(
                publish_id=publish_id,
                provider_status=last_status,
            ).model_dump(mode="json")
        )

    async def _fetch_publish_status(
        self,
        *,
        token: str,
        publish_id: str,
    ) -> tuple[str, tuple[str, ...]]:
        try:
            response = await self._post(
                _TIKTOK_STATUS_FETCH_URL,
                timeout_seconds=30.0,
                headers=self._json_headers(token),
                json={"publish_id": publish_id},
            )
        except Exception as exc:
            logger.warning(
                "tiktok_status_observation_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        if response.status_code != 200:
            raise ConnectorOutcomeAmbiguous
        data = self._observation_data(response)
        status = data.get("status")
        raw_post_ids = data.get("publicaly_available_post_id")
        if (
            status not in {"PROCESSING_UPLOAD", "PUBLISH_COMPLETE", "FAILED"}
            or not isinstance(raw_post_ids, list)
            or any(
                not isinstance(value, str)
                or _POST_ID_RE.fullmatch(value) is None
                for value in raw_post_ids
            )
            or len(raw_post_ids) != len(set(raw_post_ids))
            or len(raw_post_ids) > 1
            or (status != "PUBLISH_COMPLETE" and raw_post_ids)
        ):
            provider_status = status if isinstance(status, str) else None
            raise ConnectorOutcomeAmbiguous(
                partial_receipt=self._receipt(
                    publish_id=publish_id,
                    provider_status=(
                        provider_status
                        if provider_status
                        in {"PROCESSING_UPLOAD", "PUBLISH_COMPLETE", "FAILED"}
                        else None
                    ),
                ).model_dump(mode="json")
            )
        return status, tuple(raw_post_ids)

    async def _query_share_url(self, *, token: str, post_id: str) -> str | None:
        try:
            response = await self._post(
                _TIKTOK_VIDEO_QUERY_URL,
                timeout_seconds=30.0,
                headers=self._json_headers(token),
                params={"fields": _TIKTOK_SHARE_FIELDS},
                json={"filters": {"video_ids": [post_id]}},
            )
        except Exception:
            return None
        if response.status_code != 200:
            return None
        try:
            payload = response.json()
        except Exception:
            raise ConnectorOutcomeAmbiguous from None
        if not isinstance(payload, Mapping):
            raise ConnectorOutcomeAmbiguous
        error = payload.get("error")
        if not isinstance(error, Mapping) or not isinstance(error.get("code"), str):
            raise ConnectorOutcomeAmbiguous
        if error["code"] != "ok":
            return None
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ConnectorOutcomeAmbiguous
        videos = data.get("videos")
        if videos == []:
            return None
        if (
            not isinstance(videos, list)
            or len(videos) != 1
            or not isinstance(videos[0], Mapping)
            or videos[0].get("id") != post_id
            or not isinstance(videos[0].get("share_url"), str)
        ):
            raise ConnectorOutcomeAmbiguous
        return videos[0]["share_url"]

    @staticmethod
    def _mutation_data(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except Exception:
            raise ConnectorOutcomeAmbiguous from None
        if not isinstance(payload, Mapping):
            raise ConnectorOutcomeAmbiguous
        error = payload.get("error")
        if not isinstance(error, Mapping) or not isinstance(error.get("code"), str):
            raise ConnectorOutcomeAmbiguous
        if error["code"] != "ok":
            raise _TikTokDeterministicFailure
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ConnectorOutcomeAmbiguous
        return data

    @staticmethod
    def _observation_data(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except Exception:
            raise ConnectorOutcomeAmbiguous from None
        if not isinstance(payload, Mapping):
            raise ConnectorOutcomeAmbiguous
        error = payload.get("error")
        if (
            not isinstance(error, Mapping)
            or error.get("code") != "ok"
            or not isinstance(payload.get("data"), Mapping)
        ):
            raise ConnectorOutcomeAmbiguous
        return payload["data"]

    def _receipt(
        self,
        *,
        publish_id: str,
        provider_status: str | None,
        post_id: str | None = None,
        post_url: str | None = None,
        public_visibility_verified: bool = False,
        verified_by: str | None = None,
    ) -> PublishReceiptV1:
        return PublishReceiptV1.model_validate(
            {
                "schema_version": "publish-receipt.v1",
                "platform": "tiktok",
                "protocol_version": "tiktok-content-posting-v2",
                "completion_scope": "tiktok_direct_post",
                "provider_operation_id": publish_id,
                "provider_resource_id": post_id,
                "target_id": None,
                "provider_status": provider_status,
                "post_id": post_id,
                "post_url": post_url,
                "public_visibility_verified": public_visibility_verified,
                "observed_at": self._utc_now(),
                "verified_by": verified_by,
                "simulated": False,
            }
        )

    @staticmethod
    def _failure_result(
        *,
        receipt: PublishReceiptV1 | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "success": False,
            "simulated": False,
            "error": "tiktok_publish_failed",
            "status": "failed",
            "platform": "tiktok",
        }
        if receipt is not None:
            result["receipt"] = receipt.model_dump(mode="json")
        return result

    @staticmethod
    def _snapshot_matches(
        *,
        preflight: TikTokPreflightSnapshot,
        options: TikTokPublishOptions,
        duration_seconds: float,
    ) -> bool:
        return (
            preflight.platform == "tiktok"
            and preflight.privacy_level == options.privacy_level
            and preflight.disable_comment is options.disable_comment
            and preflight.disable_duet is options.disable_duet
            and preflight.disable_stitch is options.disable_stitch
            and preflight.brand_content_toggle is options.brand_content_toggle
            and preflight.brand_organic_toggle is options.brand_organic_toggle
            and duration_seconds == preflight.media_duration_seconds
            and duration_seconds <= preflight.max_video_post_duration_sec
        )

    @staticmethod
    def _is_safe_upload_url(value: str) -> bool:
        if any(character.isspace() for character in value):
            return False
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and (
                parsed.hostname == "tiktokapis.com"
                or parsed.hostname.endswith(".tiktokapis.com")
            )
            and port is None
            and parsed.username is None
            and parsed.password is None
            and not parsed.fragment
            and bool(parsed.path)
        )

    @staticmethod
    def _json_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("TikTok observation time must be UTC")
        return value.astimezone(UTC)

    async def get_status(self, post_id: str) -> dict[str, Any]:
        del post_id
        _require_access_token()
        raise ConnectorStatusUnavailable
