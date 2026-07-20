"""Strict Shopify Admin GraphQL 2026-07 product-video connector."""

import asyncio
import inspect
import ipaddress
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

from src.config import SHOPIFY_METRICS_SHOPIFYQL_QUERY
from src.connectors.base import (
    ConnectorCredentialNotReady,
    ConnectorCredentialState,
    ConnectorOutcomeAmbiguous,
    ConnectorPreflightRejected,
    ConnectorPreflightUnavailable,
    ConnectorStatusUnavailable,
    PlatformConnector,
    ShopifyPreflightSnapshot,
)
from src.models.publish_attempt import PublishReceiptV1, ShopifyPublishOptions
from src.tasks.metrics_poller import PlatformMetricsError, classify_platform_http_status
from src.tools.safe_media import ffprobe_local_input_args

logger = logging.getLogger(__name__)

_SHOPIFY_ADMIN_API_VERSION = "2026-07"

_STORE_HOST_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.myshopify\.com$"
)
_LEGACY_PUBLISH_ENV_NAMES = (
    "SHOPIFY_API_KEY",
    "SHOPIFY_ADMIN_TOKEN",
    "SHOPIFY_API_PASSWORD",
    "SHOPIFY_GRAPHQL_URL_TEMPLATE",
)
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
}
_MAX_VIDEO_BYTES = 1024 * 1024 * 1024
_MAX_VIDEO_DURATION_SECONDS = 600.0
_VIDEO_GID_RE = re.compile(r"^gid://shopify/Video/[1-9][0-9]*$")
_PARAMETER_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_REQUIRED_SCOPES = frozenset({"read_products", "write_products", "write_files"})

MediaProbe: TypeAlias = Callable[[Path], float | Awaitable[float]]
Sleep: TypeAlias = Callable[[float], Awaitable[None]]
Clock: TypeAlias = Callable[[], float]
Now: TypeAlias = Callable[[], datetime]

_PREFLIGHT_QUERY = """
query PublishPreflight($productId: ID!) {
  product(id: $productId) { id }
  currentAppInstallation { accessScopes { handle } }
}
"""
_STAGED_UPLOADS_MUTATION = """
mutation StagedUploadsCreate($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } }
    userErrors { field message }
  }
}
"""
_FILE_CREATE_MUTATION = """
mutation FileCreate($files: [FileCreateInput!]!) {
  fileCreate(files: $files) {
    files { ... on Video { id fileStatus } }
    userErrors { field message }
  }
}
"""
_VIDEO_STATUS_QUERY = """
query VideoStatus($id: ID!) {
  node(id: $id) { ... on Video { id fileStatus } }
}
"""
_FILE_UPDATE_MUTATION = """
mutation FileUpdate($files: [FileUpdateInput!]!) {
  fileUpdate(files: $files) {
    files { ... on Video { id fileStatus } }
    userErrors { field message }
  }
}
"""
_PRODUCT_MEDIA_READBACK_QUERY = """
query ProductMediaReadback($productId: ID!) {
  product(id: $productId) {
    id
    media(first: 250) { nodes { ... on Video { id } } }
  }
}
"""


class _ShopifyDeterministicFailure(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _ShopifyMedia:
    path: Path
    size_bytes: int
    mime_type: str
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class _StagedTarget:
    upload_url: str
    resource_url: str
    parameters: Mapping[str, str]


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
            *ffprobe_local_input_args(path),
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


def _selected_token() -> str | None:
    return _read_nonempty_env("SHOPIFY_ACCESS_TOKEN")


def _publish_enabled() -> bool:
    raw = os.environ.get("SHOPIFY_PUBLISH_ENABLED")
    return isinstance(raw, str) and raw.strip().lower() in _TRUTHY_VALUES


def _valid_store_host(value: str) -> bool:
    if not value or any(character.isspace() for character in value):
        return False
    try:
        parsed = urlsplit(f"//{value}")
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme == ""
        and parsed.path == ""
        and parsed.query == ""
        and parsed.fragment == ""
        and parsed.username is None
        and parsed.password is None
        and parsed.port is None
        and parsed.hostname is not None
        and parsed.netloc == value
        and parsed.hostname == value
        and value == value.lower()
        and _STORE_HOST_RE.fullmatch(value) is not None
    )


def _credential_state() -> ConnectorCredentialState:
    if any(_read_nonempty_env(name) is not None for name in _LEGACY_PUBLISH_ENV_NAMES):
        return ConnectorCredentialState(False, "invalid_configuration")
    if not _publish_enabled():
        return ConnectorCredentialState(False, "publishing_disabled")
    token = _selected_token()
    store = os.environ.get("SHOPIFY_STORE_URL")
    if token is None or not isinstance(store, str) or not store:
        return ConnectorCredentialState(False, "missing_credentials")
    if not _valid_store_host(store):
        return ConnectorCredentialState(False, "invalid_configuration")
    return ConnectorCredentialState(True, None)


def _require_credentials() -> tuple[str, str]:
    state = _credential_state()
    token = _selected_token()
    store = os.environ.get("SHOPIFY_STORE_URL")
    if (
        not state.ready
        or token is None
        or not isinstance(store, str)
        or not _valid_store_host(store)
    ):
        raise ConnectorCredentialNotReady(state.reason or "invalid_configuration")
    return token, store


def _graphql_url(store: str) -> str:
    if not _valid_store_host(store):
        raise ValueError("Shopify store host is invalid")
    return f"https://{store}/admin/api/{_SHOPIFY_ADMIN_API_VERSION}/graphql.json"


def _headers(token: str) -> dict[str, str]:
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

def _shopify_metrics_query(post_id: str) -> str:
    template = os.environ.get(
        "SHOPIFY_METRICS_SHOPIFYQL_QUERY",
        SHOPIFY_METRICS_SHOPIFYQL_QUERY,
    )
    safe_post_id = str(post_id).replace("\\", "\\\\").replace("'", "\\'")
    return template.replace("{post_id}", safe_post_id)


def _summarize_graphql_errors(errors: Any) -> str:
    if not isinstance(errors, list):
        return str(errors)
    messages = [
        str(error.get("message", error)) if isinstance(error, dict) else str(error)
        for error in errors
    ]
    return "; ".join(messages)


def _classify_shopify_error(errors: Any) -> str:
    value = _summarize_graphql_errors(errors).lower()
    if any(marker in value for marker in ("access denied", "scope", "permission", "protected customer", "token")):
        return "auth"
    if any(marker in value for marker in ("throttle", "rate limit", "too many")):
        return "rate_limit"
    if "not found" in value:
        return "not_found"
    if any(marker in value for marker in ("parse", "syntax", "field", "schema")):
        return "schema_drift"
    return "transient"


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, dict):
        amount = value.get("amount")
        return _to_number(amount)
    if isinstance(value, str):
        normalized = value.replace(",", "").replace("$", "").strip()
        try:
            return float(normalized)
        except ValueError:
            return None
    return None


def _iter_shopifyql_rows(table_data: Any) -> list[dict[str, Any]]:
    if not isinstance(table_data, dict):
        raise PlatformMetricsError("schema_drift", "ShopifyQL tableData is missing")
    columns = table_data.get("columns")
    rows = table_data.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise PlatformMetricsError(
            "schema_drift",
            "ShopifyQL tableData missing columns or rows list",
        )
    column_names = [
        str(column.get("name") or column.get("displayName") or "")
        for column in columns
        if isinstance(column, dict)
    ]
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            normalized_rows.append(row)
            continue
        if isinstance(row, list):
            normalized_rows.append(
                {
                    column_names[index]: value
                    for index, value in enumerate(row)
                    if index < len(column_names) and column_names[index]
                }
            )
    return normalized_rows


def _normalize_shopifyql_metrics(table_data: Any) -> dict[str, Any]:
    rows = _iter_shopifyql_rows(table_data)
    if not rows:
        raise PlatformMetricsError("not_found", "ShopifyQL returned no metric rows")

    totals: dict[str, float] = {}
    for row in rows:
        for key, value in row.items():
            number = _to_number(value)
            if number is not None:
                totals[str(key)] = totals.get(str(key), 0.0) + number

    metrics: dict[str, Any] = {}
    revenue = (
        totals.get("total_sales")
        or totals.get("gross_sales")
        or totals.get("net_sales")
        or totals.get("revenue")
    )
    orders = totals.get("orders")
    sessions = totals.get("sessions")
    if revenue is not None:
        metrics["revenue"] = revenue
    if orders is not None:
        metrics["orders"] = int(orders)
        metrics["sales"] = int(orders)
    if sessions is not None:
        metrics["views"] = int(sessions)
    if orders is not None and sessions:
        metrics["cvr"] = orders / sessions
    return metrics


class ShopifyConnector(PlatformConnector):
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
            raise ValueError("Shopify polling configuration is invalid")
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

    async def fetch_metrics(self, post_id: str) -> dict[str, Any]:
        """Fetch performance metrics for a Shopify media/post id.

        Uses Shopify Admin GraphQL `shopifyqlQuery`. The default query returns
        store/reporting analytics rather than media-file analytics; deployments
        that need stricter post-level filtering should set
        `SHOPIFY_METRICS_SHOPIFYQL_QUERY` with a `{post_id}` placeholder once
        the selected Shopify dimension is confirmed for the pilot.
        """
        token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")
        store_url = os.environ.get("SHOPIFY_STORE_URL", "")
        if not token or not store_url:
            raise PlatformMetricsError(
                "auth",
                "SHOPIFY_ACCESS_TOKEN and SHOPIFY_STORE_URL are required for Shopify metrics",
            )

        query = _shopify_metrics_query(post_id)
        response = await self._post_shopifyql_query(store_url, token, query)
        if response.status_code != 200:
            raise PlatformMetricsError(
                classify_platform_http_status(response.status_code),
                f"Shopify metrics HTTP {response.status_code}",
            )

        data = response.json()
        errors = data.get("errors")
        if errors:
            raise PlatformMetricsError(
                _classify_shopify_error(errors),
                f"Shopify metrics GraphQL errors: {_summarize_graphql_errors(errors)}",
            )
        response = data.get("data", {}).get("shopifyqlQuery")
        if not isinstance(response, dict):
            raise PlatformMetricsError(
                "schema_drift",
                "Shopify metrics response missing data.shopifyqlQuery",
            )
        parse_errors = response.get("parseErrors") or []
        if parse_errors:
            raise PlatformMetricsError(
                "schema_drift",
                f"ShopifyQL parse errors: {parse_errors}",
            )
        table_data = response.get("tableData")
        metrics = _normalize_shopifyql_metrics(table_data)
        if not metrics:
            raise PlatformMetricsError(
                "schema_drift",
                "ShopifyQL tableData has no supported metric columns",
            )
        return metrics

    async def _post_shopifyql_query(
        self,
        store_url: str,
        token: str,
        shopifyql: str,
    ) -> httpx.Response:
        graphql_url = _graphql_url(store_url)
        graphql_query = """
        query ShopifyMetrics($query: String!) {
            shopifyqlQuery(query: $query) {
                tableData {
                    columns {
                        name
                        dataType
                        displayName
                    }
                    rows
                }
                parseErrors
            }
        }
        """
        payload = {"query": graphql_query, "variables": {"query": shopifyql}}
        if self._http_client is not None:
            return await self._http_client.post(
                graphql_url,
                headers=_headers(token),
                json=payload,
            )
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(
                graphql_url,
                headers=_headers(token),
                json=payload,
            )

    async def preflight(self, content: dict[str, Any]) -> ShopifyPreflightSnapshot:
        token, store = _require_credentials()
        media, options, _ = await self._validate_local_content(content)
        data = await self._preflight_query(
            store=store,
            token=token,
            product_id=options.product_id,
        )
        product = data.get("product")
        installation = data.get("currentAppInstallation")
        if product is None or product is False:
            raise ConnectorPreflightRejected
        if not isinstance(product, Mapping):
            raise ConnectorPreflightUnavailable
        if product.get("id") != options.product_id:
            raise ConnectorPreflightRejected
        if not isinstance(installation, Mapping):
            raise ConnectorPreflightUnavailable
        raw_scopes = installation.get("accessScopes")
        if (
            not isinstance(raw_scopes, list)
            or any(
                not isinstance(item, Mapping)
                or not isinstance(item.get("handle"), str)
                for item in raw_scopes
            )
        ):
            raise ConnectorPreflightUnavailable
        scopes = {item["handle"] for item in raw_scopes}
        if not _REQUIRED_SCOPES <= scopes:
            raise ConnectorPreflightRejected
        return ShopifyPreflightSnapshot(
            product_id=options.product_id,
            required_scopes_verified=True,
            media_duration_seconds=media.duration_seconds,
            observed_at=self._utc_now(),
        )

    async def publish(
        self,
        content: dict[str, Any],
        *,
        preflight: ShopifyPreflightSnapshot | None = None,
    ) -> dict[str, Any]:
        token, store = _require_credentials()
        if not isinstance(preflight, ShopifyPreflightSnapshot):
            raise ConnectorPreflightUnavailable
        video_id: str | None = None
        provider_status: str | None = None
        product_id = preflight.product_id
        try:
            media, options, title = await self._validate_local_content(content)
            if not self._snapshot_matches(
                preflight=preflight,
                options=options,
                duration_seconds=media.duration_seconds,
            ):
                raise ConnectorOutcomeAmbiguous
            target = await self._create_staged_target(
                store=store,
                token=token,
                media=media,
            )
            await self._upload_staged_target(target=target, media=media)
            video_id, provider_status = await self._create_video_file(
                store=store,
                token=token,
                resource_url=target.resource_url,
                title=title,
            )
            if provider_status == "FAILED":
                return self._failure_result(
                    receipt=self._receipt(
                        video_id=video_id,
                        product_id=product_id,
                        provider_status="FAILED",
                    )
                )
            provider_status = await self._poll_video_status(
                store=store,
                token=token,
                video_id=video_id,
                product_id=product_id,
            )
            if provider_status == "FAILED":
                return self._failure_result(
                    receipt=self._receipt(
                        video_id=video_id,
                        product_id=product_id,
                        provider_status="FAILED",
                    )
                )
            await self._add_product_reference(
                store=store,
                token=token,
                video_id=video_id,
                product_id=product_id,
            )
            await self._verify_product_reference(
                store=store,
                token=token,
                video_id=video_id,
                product_id=product_id,
            )
            receipt = self._receipt(
                video_id=video_id,
                product_id=product_id,
                provider_status="READY",
                verified_by="file_query_and_product_readback",
            )
            receipt.validate_published()
            return {
                "success": True,
                "simulated": False,
                "platform": "shopify",
                "status": "published",
                "post_id": None,
                "url": None,
                "receipt": receipt.model_dump(mode="json"),
            }
        except _ShopifyDeterministicFailure:
            receipt = (
                self._receipt(
                    video_id=video_id,
                    product_id=product_id,
                    provider_status=provider_status,
                )
                if video_id is not None
                else None
            )
            return self._failure_result(receipt=receipt)
        except ConnectorOutcomeAmbiguous as exc:
            if exc.partial_receipt is not None:
                raise
            receipt = (
                self._receipt(
                    video_id=video_id,
                    product_id=product_id,
                    provider_status=provider_status,
                )
                if video_id is not None
                else None
            )
            raise ConnectorOutcomeAmbiguous(
                partial_receipt=(
                    receipt.model_dump(mode="json") if receipt is not None else None
                )
            ) from None
        except (ConnectorPreflightRejected, ConnectorPreflightUnavailable) as exc:
            logger.warning(
                "shopify_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        except Exception as exc:
            logger.warning(
                "shopify_publish_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            receipt = (
                self._receipt(
                    video_id=video_id,
                    product_id=product_id,
                    provider_status=provider_status,
                )
                if video_id is not None
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
    ) -> tuple[_ShopifyMedia, ShopifyPublishOptions, str]:
        video_path = content.get("video_path")
        title = content.get("title")
        try:
            options = ShopifyPublishOptions.model_validate(
                content.get("platform_options")
            )
        except ValidationError:
            raise ConnectorPreflightRejected from None
        if (
            not isinstance(video_path, str)
            or not video_path
            or not isinstance(title, str)
            or not title
            or len(title) > 300
            or _CONTROL_RE.search(title)
        ):
            raise ConnectorPreflightRejected
        path = Path(video_path)
        mime_type = _MIME_BY_SUFFIX.get(path.suffix.lower())
        try:
            size_bytes = path.stat().st_size
        except OSError:
            raise ConnectorPreflightRejected from None
        if (
            mime_type is None
            or size_bytes <= 0
            or size_bytes > _MAX_VIDEO_BYTES
        ):
            raise ConnectorPreflightRejected
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
        if duration > _MAX_VIDEO_DURATION_SECONDS:
            raise ConnectorPreflightRejected
        return (
            _ShopifyMedia(
                path=path,
                size_bytes=size_bytes,
                mime_type=mime_type,
                duration_seconds=float(duration),
            ),
            options,
            title,
        )

    async def _preflight_query(
        self,
        *,
        store: str,
        token: str,
        product_id: str,
    ) -> Mapping[str, Any]:
        try:
            response = await self._post(
                _graphql_url(store),
                timeout_seconds=30.0,
                headers=_headers(token),
                json={
                    "query": _PREFLIGHT_QUERY,
                    "variables": {"productId": product_id},
                },
            )
        except Exception as exc:
            logger.warning(
                "shopify_preflight_unavailable error_class=%s",
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
        errors = payload.get("errors")
        if errors:
            raise ConnectorPreflightRejected
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ConnectorPreflightUnavailable
        return data

    async def _create_staged_target(
        self,
        *,
        store: str,
        token: str,
        media: _ShopifyMedia,
    ) -> _StagedTarget:
        response = await self._graphql_post(
            store=store,
            token=token,
            query=_STAGED_UPLOADS_MUTATION,
            variables={
                "input": [
                    {
                        "resource": "VIDEO",
                        "filename": media.path.name,
                        "mimeType": media.mime_type,
                        "fileSize": str(media.size_bytes),
                    }
                ]
            },
            timeout_seconds=60.0,
        )
        mutation = self._mutation_result(response, "stagedUploadsCreate")
        targets = mutation.get("stagedTargets")
        if (
            not isinstance(targets, list)
            or len(targets) != 1
            or not isinstance(targets[0], Mapping)
        ):
            raise ConnectorOutcomeAmbiguous
        target = targets[0]
        upload_url = target.get("url")
        resource_url = target.get("resourceUrl")
        raw_parameters = target.get("parameters")
        if (
            not isinstance(upload_url, str)
            or not isinstance(resource_url, str)
            or not self._is_safe_staged_url(upload_url)
            or not self._is_safe_staged_url(resource_url)
            or not isinstance(raw_parameters, list)
            or not raw_parameters
            or len(raw_parameters) > 64
        ):
            raise ConnectorOutcomeAmbiguous
        parameters: dict[str, str] = {}
        for item in raw_parameters:
            if not isinstance(item, Mapping):
                raise ConnectorOutcomeAmbiguous
            name = item.get("name")
            value = item.get("value")
            if (
                not isinstance(name, str)
                or _PARAMETER_NAME_RE.fullmatch(name) is None
                or name in parameters
                or not isinstance(value, str)
                or not value
                or len(value) > 8192
                or _CONTROL_RE.search(value)
            ):
                raise ConnectorOutcomeAmbiguous
            parameters[name] = value
        return _StagedTarget(
            upload_url=upload_url,
            resource_url=resource_url,
            parameters=parameters,
        )

    async def _upload_staged_target(
        self,
        *,
        target: _StagedTarget,
        media: _ShopifyMedia,
    ) -> None:
        try:
            with media.path.open("rb") as video_file:
                response = await self._post(
                    target.upload_url,
                    timeout_seconds=300.0,
                    data=dict(target.parameters),
                    files={
                        "file": (media.path.name, video_file, media.mime_type),
                    },
                )
        except Exception as exc:
            logger.warning(
                "shopify_staged_upload_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None
        if 400 <= response.status_code < 500:
            raise _ShopifyDeterministicFailure
        if response.status_code not in {200, 201, 204}:
            raise ConnectorOutcomeAmbiguous

    async def _create_video_file(
        self,
        *,
        store: str,
        token: str,
        resource_url: str,
        title: str,
    ) -> tuple[str, str]:
        response = await self._graphql_post(
            store=store,
            token=token,
            query=_FILE_CREATE_MUTATION,
            variables={
                "files": [
                    {
                        "alt": title,
                        "contentType": "VIDEO",
                        "originalSource": resource_url,
                    }
                ]
            },
            timeout_seconds=60.0,
        )
        mutation = self._mutation_result(response, "fileCreate")
        files = mutation.get("files")
        if (
            not isinstance(files, list)
            or len(files) != 1
            or not isinstance(files[0], Mapping)
        ):
            raise ConnectorOutcomeAmbiguous
        video_id = files[0].get("id")
        status = files[0].get("fileStatus")
        if (
            not isinstance(video_id, str)
            or _VIDEO_GID_RE.fullmatch(video_id) is None
            or status not in {"UPLOADED", "PROCESSING", "READY", "FAILED"}
        ):
            raise ConnectorOutcomeAmbiguous
        return video_id, status

    async def _poll_video_status(
        self,
        *,
        store: str,
        token: str,
        video_id: str,
        product_id: str,
    ) -> str:
        started = self._monotonic()
        last_status: str | None = None
        for index in range(self._max_status_polls):
            last_status = await self._fetch_video_status(
                store=store,
                token=token,
                video_id=video_id,
            )
            if last_status in {"READY", "FAILED"}:
                return last_status
            if index == self._max_status_polls - 1:
                break
            if self._monotonic() - started >= self._poll_deadline_seconds:
                break
            await self._sleep(self._poll_interval_seconds)
        raise ConnectorOutcomeAmbiguous(
            partial_receipt=self._receipt(
                video_id=video_id,
                product_id=product_id,
                provider_status=last_status,
            ).model_dump(mode="json")
        )

    async def _fetch_video_status(
        self,
        *,
        store: str,
        token: str,
        video_id: str,
    ) -> str:
        response = await self._graphql_post(
            store=store,
            token=token,
            query=_VIDEO_STATUS_QUERY,
            variables={"id": video_id},
            timeout_seconds=30.0,
        )
        data = self._query_result(response)
        node = data.get("node")
        if not isinstance(node, Mapping):
            raise ConnectorOutcomeAmbiguous
        status = node.get("fileStatus")
        if (
            node.get("id") != video_id
            or status not in {"UPLOADED", "PROCESSING", "READY", "FAILED"}
        ):
            raise ConnectorOutcomeAmbiguous
        return status

    async def _add_product_reference(
        self,
        *,
        store: str,
        token: str,
        video_id: str,
        product_id: str,
    ) -> None:
        response = await self._graphql_post(
            store=store,
            token=token,
            query=_FILE_UPDATE_MUTATION,
            variables={
                "files": [
                    {
                        "id": video_id,
                        "referencesToAdd": [product_id],
                    }
                ]
            },
            timeout_seconds=60.0,
        )
        mutation = self._mutation_result(response, "fileUpdate")
        files = mutation.get("files")
        if (
            not isinstance(files, list)
            or len(files) != 1
            or not isinstance(files[0], Mapping)
            or files[0].get("id") != video_id
        ):
            raise ConnectorOutcomeAmbiguous

    async def _verify_product_reference(
        self,
        *,
        store: str,
        token: str,
        video_id: str,
        product_id: str,
    ) -> None:
        response = await self._graphql_post(
            store=store,
            token=token,
            query=_PRODUCT_MEDIA_READBACK_QUERY,
            variables={"productId": product_id},
            timeout_seconds=30.0,
        )
        data = self._query_result(response)
        product = data.get("product")
        if not isinstance(product, Mapping) or product.get("id") != product_id:
            raise ConnectorOutcomeAmbiguous
        media = product.get("media")
        nodes = media.get("nodes") if isinstance(media, Mapping) else None
        if not isinstance(nodes, list):
            raise ConnectorOutcomeAmbiguous
        matching = [
            node
            for node in nodes
            if isinstance(node, Mapping) and node.get("id") == video_id
        ]
        if len(matching) != 1:
            raise ConnectorOutcomeAmbiguous

    async def _graphql_post(
        self,
        *,
        store: str,
        token: str,
        query: str,
        variables: Mapping[str, Any],
        timeout_seconds: float,
    ) -> httpx.Response:
        try:
            return await self._post(
                _graphql_url(store),
                timeout_seconds=timeout_seconds,
                headers=_headers(token),
                json={"query": query, "variables": dict(variables)},
            )
        except Exception as exc:
            logger.warning(
                "shopify_graphql_outcome_ambiguous error_class=%s",
                type(exc).__name__,
            )
            raise ConnectorOutcomeAmbiguous from None

    @staticmethod
    def _mutation_result(
        response: httpx.Response,
        field: str,
    ) -> Mapping[str, Any]:
        if 400 <= response.status_code < 500:
            raise _ShopifyDeterministicFailure
        if response.status_code != 200:
            raise ConnectorOutcomeAmbiguous
        data = ShopifyConnector._query_result(response)
        mutation = data.get(field)
        if not isinstance(mutation, Mapping):
            raise ConnectorOutcomeAmbiguous
        user_errors = mutation.get("userErrors")
        if not isinstance(user_errors, list):
            raise ConnectorOutcomeAmbiguous
        if user_errors:
            raise _ShopifyDeterministicFailure
        return mutation

    @staticmethod
    def _query_result(response: httpx.Response) -> Mapping[str, Any]:
        if response.status_code != 200:
            raise ConnectorOutcomeAmbiguous
        try:
            payload = response.json()
        except Exception:
            raise ConnectorOutcomeAmbiguous from None
        if not isinstance(payload, Mapping) or payload.get("errors"):
            raise ConnectorOutcomeAmbiguous
        data = payload.get("data")
        if not isinstance(data, Mapping):
            raise ConnectorOutcomeAmbiguous
        return data

    def _receipt(
        self,
        *,
        video_id: str,
        product_id: str,
        provider_status: str | None,
        verified_by: str | None = None,
    ) -> PublishReceiptV1:
        return PublishReceiptV1.model_validate(
            {
                "schema_version": "publish-receipt.v1",
                "platform": "shopify",
                "protocol_version": "shopify-admin-2026-07",
                "completion_scope": "shopify_product_media",
                "provider_operation_id": None,
                "provider_resource_id": video_id,
                "target_id": product_id,
                "provider_status": provider_status,
                "post_id": None,
                "post_url": None,
                "public_visibility_verified": False,
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
            "error": "shopify_publish_failed",
            "status": "failed",
            "platform": "shopify",
        }
        if receipt is not None:
            result["receipt"] = receipt.model_dump(mode="json")
        return result

    @staticmethod
    def _snapshot_matches(
        *,
        preflight: ShopifyPreflightSnapshot,
        options: ShopifyPublishOptions,
        duration_seconds: float,
    ) -> bool:
        return (
            preflight.platform == "shopify"
            and preflight.product_id == options.product_id
            and preflight.required_scopes_verified is True
            and preflight.media_duration_seconds == duration_seconds
        )

    @staticmethod
    def _is_safe_staged_url(value: str) -> bool:
        if any(character.isspace() for character in value):
            return False
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError:
            return False
        hostname = parsed.hostname
        if (
            parsed.scheme != "https"
            or hostname is None
            or hostname != hostname.lower()
            or port is not None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or not parsed.path
            or "." not in hostname
            or hostname == "localhost"
            or hostname.endswith(".local")
        ):
            return False
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            return True
        return False

    def _utc_now(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("Shopify observation time must be UTC")
        return value.astimezone(UTC)

    async def get_status(self, post_id: str) -> dict[str, Any]:
        del post_id
        _require_credentials()
        raise ConnectorStatusUnavailable
