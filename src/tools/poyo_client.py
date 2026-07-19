"""Generic poyo.ai async client — submit + poll + download.

poyo.ai uses a unified async architecture for all media types:
  1. POST /api/generate/submit  → {code, data: {task_id, status}}
  2. GET  /api/generate/status/{task_id} → poll until finished / failed
  3. Download from data.files[0].file_url

This module provides the low-level transport. Higher-level clients
(GPTImageClient, ElevenLabsClient, SeedanceClient) decide the model
name and input payload shape.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import tempfile
from collections.abc import Callable, Mapping
from ipaddress import ip_address
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
import structlog

from src.config import POYO_API_BASE_URL, POYO_API_KEY
from src.models.provider_cost import (
    BillingFactKind,
    CatalogOperation,
    MediaType,
    ProviderBillingFacts,
    ProviderCostContractError,
    parse_billing_facts,
)
from src.services.provider_cost import (
    ProviderCostOperationDefinition,
    ProviderCostService,
    build_provider_cost_service,
)
from src.services.provider_execution import (
    ProviderExecutionContext,
    get_provider_execution_context,
)
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.tools.llm_client import get_request_api_key

logger = structlog.get_logger()

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_MAX_POLLS = 60  # 5s * 60 = 300s max
POYO_GLOBAL_ENDPOINT = "https://api.poyo.ai"
POYO_RESERVATION_TTL_SECONDS = 900
_ARTIFACT_MAX_BYTES = {
    ".png": 32 * 1024 * 1024,
    ".jpg": 32 * 1024 * 1024,
    ".jpeg": 32 * 1024 * 1024,
    ".webp": 32 * 1024 * 1024,
    ".gif": 64 * 1024 * 1024,
    ".mp3": 128 * 1024 * 1024,
    ".wav": 512 * 1024 * 1024,
    ".mp4": 512 * 1024 * 1024,
}
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_LEDGER_SUBMIT_PERMIT = object()

ProviderCostServiceFactory = Callable[
    [Mapping[str, ProviderCostOperationDefinition]],
    ProviderCostService,
]


class PoyoPollExhausted(RuntimeError):
    """The accepted task remains durable ``submitted`` after bounded polling."""


class PoyoProtocolAmbiguous(RuntimeError):
    """The provider response cannot prove one durable async outcome."""


class _NonCanonicalJsonNumber(str):
    """Lexical JSON number marker that is never coerced to binary float."""


def _reject_json_number(value: str) -> _NonCanonicalJsonNumber:
    return _NonCanonicalJsonNumber(value)


def _strict_response_payload(response: Any) -> object:
    """Decode JSON while preserving non-canonical numbers as non-numeric markers."""

    raw = getattr(response, "content", None)
    if isinstance(raw, (bytes, bytearray)):
        return json.loads(
            bytes(raw).decode("utf-8"),
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    payload = response.json()
    if isinstance(payload, Mapping):
        return dict(payload)
    return payload


def parse_poyo_credits_amount(value: object) -> int:
    """Parse charged credits as strict, bounded integer microcredits."""

    from src.models.provider_cost import MAX_SIGNED_BIGINT

    if type(value) is not int or value < 0 or value > MAX_SIGNED_BIGINT:
        raise ValueError("credits_amount must be a bounded integer")
    return value


def _resolve_public_artifact_addresses(host: str) -> tuple[str, ...]:
    """Resolve an artifact hostname and require only globally routable IPs."""

    try:
        resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise ValueError("artifact URL host could not be resolved") from None

    addresses: set[str] = set()
    for _, _, _, _, sockaddr in resolved:
        try:
            resolved_address = ip_address(sockaddr[0])
        except (ValueError, IndexError, TypeError):
            raise ValueError("artifact URL host resolution is invalid") from None
        if not resolved_address.is_global:
            raise ValueError("artifact URL host is not globally routable")
        addresses.add(str(resolved_address))
    if not addresses:
        raise ValueError("artifact URL host could not be resolved")
    return tuple(sorted(addresses))


def _validate_artifact_url(file_url: str) -> tuple[str, ...]:
    parsed = urlsplit(file_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("artifact URL is not an approved HTTPS URL")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("artifact URL port is not approved") from None
    if port not in (None, 443):
        raise ValueError("artifact URL port is not approved")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal", "169.254.169.254"}:
        raise ValueError("artifact URL host is blocked")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if not address.is_global:
            raise ValueError("artifact URL host is blocked")
        return (str(address),)
    return _resolve_public_artifact_addresses(host)


def _pinned_artifact_request(
    file_url: str,
    *,
    host: str,
    address: str,
) -> tuple[str, dict[str, str], dict[str, str]]:
    """Build an IP-pinned URL while preserving provider TLS/HTTP identity."""

    parsed = urlsplit(file_url)
    pinned_host = f"[{address}]" if ":" in address else address
    pinned_url = parsed._replace(netloc=pinned_host).geturl()
    return pinned_url, {"Host": host}, {"sni_hostname": host}


def _artifact_content_limit(output_path: Path) -> int:
    return _ARTIFACT_MAX_BYTES.get(output_path.suffix.lower(), 64 * 1024 * 1024)


def _content_type_allowed(output_path: Path, content_type: str | None) -> bool:
    if not content_type:
        return True
    normalized = content_type.split(";", 1)[0].strip().lower()
    suffix = output_path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return normalized.startswith("image/") or normalized == "application/octet-stream"
    if suffix == ".mp4":
        return normalized in {"video/mp4", "application/mp4", "application/octet-stream"}
    if suffix in {".mp3", ".wav"}:
        return normalized.startswith("audio/") or normalized == "application/octet-stream"
    return normalized == "application/octet-stream"


class PoyoClient:
    """Low-level poyo.ai submit+poll client.

    Args:
        api_key: poyo.ai API key. Defaults to POYO_API_KEY.
        base_url: poyo.ai base URL. Defaults to POYO_API_BASE_URL.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        *,
        price_catalog: ProviderPriceCatalog | None = None,
        cost_service_factory: ProviderCostServiceFactory | None = None,
    ):
        self.api_key = api_key or get_request_api_key("POYO_API_KEY") or POYO_API_KEY
        self.base_url = (base_url or POYO_API_BASE_URL).rstrip("/")
        if not self.api_key:
            raise RuntimeError("PoyoClient requires POYO_API_KEY")
        if price_catalog is not None and not isinstance(price_catalog, ProviderPriceCatalog):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "provider price catalog injection is invalid",
            )
        if cost_service_factory is not None and not callable(cost_service_factory):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost service factory is invalid",
            )
        self._price_catalog = price_catalog or ProviderPriceCatalog.load_default()
        self._cost_service_factory = cost_service_factory or self._build_cost_service
        self._client: httpx.AsyncClient | None = None

    def _build_cost_service(
        self,
        registry: Mapping[str, ProviderCostOperationDefinition],
    ) -> ProviderCostService:
        return build_provider_cost_service(
            operation_registry=registry,
            price_catalog=self._price_catalog,
        )

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        limits = httpx.Limits(max_keepalive_connections=0, max_connections=50)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            http2=False,
            limits=limits,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "AI-Video-Platform/1.0",
            },
            timeout=90.0,
        )
        return self._client

    async def submit(
        self,
        model: str,
        input_payload: dict[str, Any],
        *,
        _ledger_permit: object | None = None,
    ) -> str:
        """Submit a generation task and return task_id.

        Raises:
            httpx.HTTPStatusError: on non-2xx from submit endpoint.
            RuntimeError: if submit response indicates failure.
        """
        if _ledger_permit is not _LEDGER_SUBMIT_PERMIT:
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "PoYo submit requires the durable cost ledger",
            )
        body = {"model": model, "input": input_payload}
        logger.info("poyo: submitting", model=model, keys=list(input_payload.keys()))
        resp = await self._get_client().post(
            "/api/generate/submit",
            content=json.dumps(body).encode(),
        )
        resp.raise_for_status()
        data = _strict_response_payload(resp)
        if not isinstance(data, Mapping):
            raise RuntimeError("poyo submit response is invalid")

        if data.get("code") != 200:
            raise RuntimeError("poyo submit failed")

        response_data = data.get("data")
        task_id = response_data.get("task_id", "") if isinstance(response_data, Mapping) else ""
        if not isinstance(task_id, str) or _SAFE_TASK_ID_RE.fullmatch(task_id) is None:
            raise RuntimeError("poyo submit missing task_id")

        logger.info("poyo: submitted", task_id=task_id, model=model)
        return task_id

    async def poll(
        self,
        task_id: str,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
    ) -> dict[str, Any]:
        """Poll until task finishes or fails.

        Returns:
            The finished task dict (data field from status response).

        Raises:
            RuntimeError: on task failure or polling timeout.
        """
        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            resp = await self._get_client().get(f"/api/generate/status/{task_id}")
            resp.raise_for_status()
            status_data = _strict_response_payload(resp)
            if not isinstance(status_data, Mapping):
                raise RuntimeError("poyo status response is invalid")

            task = status_data.get("data", {})
            if not isinstance(task, Mapping):
                raise RuntimeError("poyo status task is invalid")
            task = dict(task)
            status = task.get("status", "")
            logger.info("poyo: polling", task_id=task_id, status=status, attempt=i + 1)

            if status == "finished":
                return task
            if status == "failed":
                logger.error("poyo: task failed", task_id=task_id)
                raise RuntimeError("poyo task failed")

        raise RuntimeError(f"poyo polling timed out after {max_polls * poll_interval}s")

    async def download(
        self,
        task: dict[str, Any],
        output_path: Path,
        *,
        max_retries: int = 3,
    ) -> Path:
        """Download the first file_url from a finished task.

        Returns:
            Path to the saved file.

        Raises:
            RuntimeError: if no file_url found.
        """
        files = task.get("files", [])
        if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], Mapping):
            raise RuntimeError("poyo task finished but no files returned")

        file_url = files[0].get("file_url", "") or files[0].get("audio_url", "")
        if not isinstance(file_url, str) or not file_url:
            raise RuntimeError("poyo task finished but file_url is empty")
        resolved_addresses = _validate_artifact_url(file_url)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        last_error: BaseException | None = None
        max_bytes = _artifact_content_limit(output_path)
        for attempt_index in range(max(1, max_retries)):
            temp_path: Path | None = None
            try:
                # Re-resolve immediately before opening the client.  A changed
                # or newly non-global answer is rejected before any request;
                # this closes the practical DNS-rebinding window between URL
                # validation and the HTTP connection.
                if _validate_artifact_url(file_url) != resolved_addresses:
                    raise RuntimeError("provider artifact host resolution changed")
                request_url, request_headers, request_extensions = _pinned_artifact_request(
                    file_url,
                    host=urlsplit(file_url).hostname or "",
                    address=resolved_addresses[attempt_index % len(resolved_addresses)],
                )
                fd, temp_name = tempfile.mkstemp(
                    dir=str(output_path.parent),
                    prefix=f".{output_path.name}.",
                    suffix=".part",
                )
                os.close(fd)
                temp_path = Path(temp_name)
                async with httpx.AsyncClient(
                    http2=False,
                    follow_redirects=False,
                    timeout=90.0,
                    trust_env=False,
                ) as dl:
                    stream = cast(Any, getattr(dl, "stream", None))
                    if callable(stream):
                        stream_response = cast(
                            Any,
                            stream(
                                "GET",
                                request_url,
                                headers=request_headers,
                                extensions=request_extensions,
                                follow_redirects=False,
                            ),
                        )
                        async with stream_response as dl_resp:
                            await self._write_download_response(
                                dl_resp,
                                temp_path,
                                output_path,
                                max_bytes,
                            )
                    else:
                        dl_resp = await dl.get(
                            request_url,
                            headers=request_headers,
                            extensions=request_extensions,
                            follow_redirects=False,
                        )
                        await self._write_download_response(
                            dl_resp,
                            temp_path,
                            output_path,
                            max_bytes,
                        )
                os.replace(temp_path, output_path)
                temp_path = None
                last_error = None
                break
            except Exception as exc:
                last_error = exc
            finally:
                if temp_path is not None:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        logger.warning(
                            "poyo: artifact cleanup failed",
                            artifact_name=temp_path.name,
                            error_code="poyo_artifact_cleanup_failed",
                        )
        if last_error is not None:
            raise RuntimeError("poyo artifact download failed") from None

        logger.info("poyo: downloaded", file=output_path.name, size=output_path.stat().st_size)
        return output_path

    @staticmethod
    async def _write_download_response(
        response: Any,
        temp_path: Path,
        output_path: Path,
        max_bytes: int,
    ) -> None:
        response.raise_for_status()
        headers = getattr(response, "headers", {}) or {}
        if headers.get("location"):
            raise RuntimeError("provider artifact redirect is not allowed")
        content_type = headers.get("content-type")
        if not _content_type_allowed(output_path, content_type):
            raise RuntimeError("provider artifact content type is not approved")
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    raise RuntimeError("provider artifact is too large")
            except (TypeError, ValueError):
                raise RuntimeError("provider artifact content length is invalid") from None

        total = 0
        with temp_path.open("wb") as handle:
            iterator = cast(Any, getattr(response, "aiter_bytes", None))
            if callable(iterator):
                async for chunk in cast(Any, iterator(chunk_size=64 * 1024)):
                    if not isinstance(chunk, (bytes, bytearray)):
                        raise RuntimeError("provider artifact stream is invalid")
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError("provider artifact is too large")
                    handle.write(chunk)
            else:
                content = getattr(response, "content", b"")
                if not isinstance(content, (bytes, bytearray)) or len(content) > max_bytes:
                    raise RuntimeError("provider artifact is too large")
                total = len(content)
                handle.write(content)
        if total <= 0:
            raise RuntimeError("provider artifact is empty")

    async def submit_poll_download(
        self,
        model: str,
        input_payload: dict[str, Any],
        output_path: Path,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
    ) -> dict[str, Any]:
        """Reject the legacy unaccounted mutation entry point."""
        del model, input_payload, output_path, poll_interval, max_polls
        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "PoYo one-shot submit/poll/download requires the durable cost ledger",
        )

    async def _poll_until_terminal(
        self,
        task_id: str,
        *,
        poll_interval: float,
        max_polls: int,
    ) -> dict[str, Any]:
        """Read one accepted task with bounded status retries and no resubmit."""

        for attempt in range(max(1, max_polls)):
            if poll_interval > 0:
                await asyncio.sleep(poll_interval)
            try:
                response = await self._get_client().get(f"/api/generate/status/{task_id}")
                response.raise_for_status()
                payload = _strict_response_payload(response)
            except json.JSONDecodeError:
                if attempt + 1 >= max(1, max_polls):
                    raise PoyoPollExhausted from None
                continue
            except ValueError:
                # A syntactically valid HTTP response with non-canonical billing
                # numbers is an accounting failure, not a retryable read error.
                raise
            except PoyoProtocolAmbiguous:
                raise
            except Exception as exc:
                if attempt + 1 >= max(1, max_polls):
                    raise PoyoPollExhausted from None
                continue

            if not isinstance(payload, Mapping):
                raise PoyoProtocolAmbiguous
            if payload.get("code") != 200:
                raise PoyoProtocolAmbiguous
            task = payload.get("data")
            if not isinstance(task, Mapping):
                raise PoyoProtocolAmbiguous
            task = dict(task)
            response_task_id = task.get("task_id")
            if response_task_id is not None and response_task_id != task_id:
                raise PoyoProtocolAmbiguous
            status = task.get("status")
            if status in {"finished", "failed"}:
                return task
        raise PoyoPollExhausted

    @staticmethod
    def _cost_error_for_attempt(attempt: Mapping[str, Any]) -> ProviderCostContractError:
        state = attempt.get("state")
        if state == "ambiguous":
            return ProviderCostContractError(
                "provider_cost_outcome_ambiguous",
                "durable PoYo attempt has uncertain outcome",
            )
        if state == "accounting_error":
            return ProviderCostContractError(
                "provider_cost_accounting_error",
                "durable PoYo attempt has invalid accounting facts",
            )
        if state == "released":
            return ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "durable PoYo attempt was released",
            )
        return ProviderCostContractError(
            "provider_cost_attempt_conflict",
            "durable PoYo attempt cannot be resubmitted",
        )

    async def run_costed(
        self,
        *,
        model: str,
        input_payload: dict[str, Any],
        output_path: Path,
        operation_key: str,
        logical_operation: str,
        attempt_fingerprint: str,
        catalog_operation: CatalogOperation,
        media_type: MediaType,
        billing_fact_kind: BillingFactKind,
        dimensions: Mapping[str, str],
        reservation_billing_facts: ProviderBillingFacts,
        settlement_facts_builder: Callable[[dict[str, Any]], object],
        artifact_url_builder: Callable[[dict[str, Any]], str],
        terminal_task_validator: Callable[[dict[str, Any]], None] | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
    ) -> dict[str, Any]:
        """Run one ledger-authorized PoYo async mutation.

        The method deliberately separates submit, durable ``submitted`` transition,
        read-only polling, strict terminal accounting, and artifact download.  Only
        the submit is a provider mutation; status/download retries never allocate a
        second attempt.
        """

        context = get_provider_execution_context()
        if not isinstance(context, ProviderExecutionContext):
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "paid PoYo mutation requires a bound provider execution context",
            )
        if context.provider_max_retries != 0:
            raise ProviderCostContractError(
                "provider_execution_context_missing",
                "paid PoYo mutation retry authority is invalid",
            )
        if self.base_url != POYO_GLOBAL_ENDPOINT:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo billing endpoint is not exact",
            )

        definition = ProviderCostOperationDefinition(
            registry_key=operation_key,
            logical_operation=logical_operation,
            provider="poyo",
            canonical_model=model,
            provider_billing_region="poyo_global_usd",
            catalog_operation=catalog_operation,
            media_type=media_type,
            billing_fact_kind=billing_fact_kind,
            dimensions=tuple(sorted((str(k), str(v)) for k, v in dimensions.items())),
            reservation_billing_facts=reservation_billing_facts,
            reservation_ttl_seconds=POYO_RESERVATION_TTL_SECONDS,
        )
        service = self._cost_service_factory({operation_key: definition})
        if not isinstance(service, ProviderCostService):
            raise ProviderCostContractError(
                "provider_cost_store_unavailable",
                "provider cost service injection is invalid",
            )

        reservation = await service.reserve_or_replay(
            tenant_id=context.tenant_id,
            account_id=context.account_id,
            operation_key=operation_key,
            attempt_fingerprint=attempt_fingerprint,
            regeneration_epoch=context.regeneration_epoch,
        )
        attempt = reservation.attempt
        state = str(attempt.get("state"))
        already_settled = state == "settled"
        if reservation.outcome == "replay":
            if state in {"ambiguous", "accounting_error", "released"}:
                raise self._cost_error_for_attempt(attempt)
            if state == "settled" and not attempt.get("external_task_id"):
                raise ProviderCostContractError(
                    "provider_cost_attempt_conflict",
                    "settled PoYo attempt has no external task ID",
                )
            if state == "submission_started":
                # A prior process may have reached the mutation boundary. Never
                # resubmit it after restart; hold it for explicit recovery.
                await service.mark_ambiguous(
                    tenant_id=context.tenant_id,
                    attempt_id=str(attempt["attempt_id"]),
                    expected_state="submission_started",
                )
                raise ProviderCostContractError(
                    "provider_cost_outcome_ambiguous",
                    "PoYo submission acknowledgement is uncertain",
                )
            task_id = str(attempt.get("external_task_id") or "")
            if state == "reserved":
                await service.mark_submission_started(
                    tenant_id=context.tenant_id,
                    attempt_id=str(attempt["attempt_id"]),
                )
                state = "submission_started"
        else:
            await service.mark_submission_started(
                tenant_id=context.tenant_id,
                attempt_id=str(attempt["attempt_id"]),
            )
            state = "submission_started"
            task_id = ""

        attempt_id = str(attempt["attempt_id"])
        if not task_id:
            try:
                self._get_client()
            except Exception:
                await service.release(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submission_started",
                )
                raise ProviderCostContractError(
                    "provider_cost_legacy_path_blocked",
                    "PoYo HTTP client construction failed before submit",
                ) from None
            try:
                task_id = await self.submit(
                    model,
                    input_payload,
                    _ledger_permit=_LEDGER_SUBMIT_PERMIT,
                )
            except asyncio.CancelledError:
                await asyncio.shield(
                    service.mark_ambiguous(
                        tenant_id=context.tenant_id,
                        attempt_id=attempt_id,
                        expected_state="submission_started",
                    )
                )
                raise
            except Exception:
                await service.mark_ambiguous(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submission_started",
                )
                raise ProviderCostContractError(
                    "provider_cost_outcome_ambiguous",
                    "PoYo submission acknowledgement is uncertain",
                ) from None
            if not isinstance(task_id, str) or _SAFE_TASK_ID_RE.fullmatch(task_id) is None:
                await service.mark_ambiguous(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submission_started",
                )
                raise ProviderCostContractError(
                    "provider_cost_outcome_ambiguous",
                    "PoYo task identifier is invalid or missing",
                )
            await service.mark_submitted(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                external_task_id=task_id,
            )
            state = "submitted"

        try:
            task = await self._poll_until_terminal(
                task_id,
                poll_interval=poll_interval,
                max_polls=max_polls,
            )
        except PoyoPollExhausted:
            if already_settled:
                raise ProviderCostContractError(
                    "provider_cost_artifact_failed",
                    "settled PoYo attempt needs artifact recovery",
                ) from None
            return {
                "task_id": task_id,
                "file_url": "",
                "local_path": "",
                "task": {},
                "_poyo_state": "submitted",
            }
        except ValueError:
            if already_settled:
                raise ProviderCostContractError(
                    "provider_cost_artifact_failed",
                    "settled PoYo attempt returned invalid recovery facts",
                ) from None
            if state == "submitted":
                await service.mark_accounting_error(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submitted",
                    external_task_id=task_id,
                )
            raise ProviderCostContractError(
                "provider_cost_accounting_error",
                "PoYo status JSON contains invalid accounting numbers",
            ) from None
        except PoyoProtocolAmbiguous:
            if already_settled:
                raise ProviderCostContractError(
                    "provider_cost_artifact_failed",
                    "settled PoYo attempt has ambiguous artifact recovery",
                ) from None
            if state == "submitted":
                await service.mark_ambiguous(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submitted",
                    external_task_id=task_id,
                )
            raise ProviderCostContractError(
                "provider_cost_outcome_ambiguous",
                "PoYo status response is ambiguous",
            ) from None

        status = task.get("status")
        if status == "failed":
            if already_settled:
                raise ProviderCostContractError(
                    "provider_cost_artifact_failed",
                    "settled PoYo attempt returned a failed recovery status",
                ) from None
            try:
                credits = parse_poyo_credits_amount(task.get("credits_amount"))
            except ValueError:
                await service.mark_ambiguous(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submitted",
                    external_task_id=task_id,
                )
                raise ProviderCostContractError(
                    "provider_cost_outcome_ambiguous",
                    "PoYo failed task charge is unknown",
                ) from None
            if credits == 0:
                await service.release(
                    tenant_id=context.tenant_id,
                    attempt_id=attempt_id,
                    expected_state="submitted",
                    external_task_id=task_id,
                )
                return {
                    "task_id": task_id,
                    "file_url": "",
                    "local_path": "",
                    "task": task,
                    "_poyo_state": "released",
                }
            await service.mark_accounting_error(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submitted",
                provider_reported_credit_micro_units=credits,
                external_task_id=task_id,
            )
            raise ProviderCostContractError(
                "provider_cost_accounting_error",
                "PoYo failed task reports charged credits",
            )

        try:
            credits = parse_poyo_credits_amount(task.get("credits_amount"))
            if terminal_task_validator is not None:
                terminal_task_validator(task)
            facts = parse_billing_facts(settlement_facts_builder(task))
            rule = self._price_catalog.require_rule(
                provider="poyo",
                canonical_model=model,
                provider_billing_region="poyo_global_usd",
                catalog_operation=catalog_operation,
                media_type=media_type,
                billing_fact_kind=billing_fact_kind,
                dimensions=dict(dimensions),
            )
            expected_credits = self._price_catalog.calculate_expected_provider_credit_micro_units(rule, facts)
            if expected_credits is None or credits != expected_credits:
                raise ValueError("provider credits do not match frozen rule")
        except Exception:
            if already_settled:
                raise ProviderCostContractError(
                    "provider_cost_artifact_failed",
                    "settled PoYo attempt has invalid recovery facts",
                ) from None
            await service.mark_accounting_error(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submitted",
                external_task_id=task_id,
            )
            raise ProviderCostContractError(
                "provider_cost_accounting_error",
                "PoYo terminal success facts are invalid",
            ) from None

        if not already_settled:
            transition = await service.settle(
                tenant_id=context.tenant_id,
                attempt_id=attempt_id,
                expected_state="submitted",
                settlement_billing_facts=facts,
                provider_reported_credit_micro_units=credits,
                external_task_id=task_id,
            )
            settled_attempt = transition["attempt"]
            if settled_attempt.get("state") != "settled":
                raise ProviderCostContractError(
                    "provider_cost_accounting_error",
                    "PoYo terminal success could not be settled",
                )

        try:
            file_url = artifact_url_builder(task)
            if not isinstance(file_url, str) or not file_url:
                raise ValueError("artifact URL is missing")
            local_path = await self.download(task, output_path)
        except Exception:
            raise ProviderCostContractError(
                "provider_cost_artifact_failed",
                "PoYo paid artifact download failed after settlement",
            ) from None
        return {
            "task_id": task_id,
            "file_url": file_url,
            "local_path": str(local_path),
            "task": task,
            "_poyo_state": "settled",
        }

    async def test_connectivity(self) -> dict[str, Any]:
        """Quick health check — verify poyo.ai API is reachable.

        Sends a lightweight HEAD to the base URL. Does not submit a job.

        Returns:
            {"reachable": bool, "status_code": int | None, "detail": str}
        """
        try:
            async with httpx.AsyncClient(http2=False) as c:
                resp = await c.get(
                    f"{self.base_url}/api/generate/status/dummy",
                    headers={"User-Agent": "AI-Video-Platform/1.0"},
                    timeout=15.0,
                )
                # Expected: 404 or similar (endpoint exists but dummy task)
                # Even a 404 means the API is reachable.
                return {"reachable": True, "status_code": resp.status_code, "detail": "API responded"}
        except httpx.ConnectError:
            return {"reachable": False, "status_code": None, "detail": "connection_failed"}
        except httpx.TimeoutException:
            return {"reachable": False, "status_code": None, "detail": "timeout"}
        except Exception:
            return {"reachable": False, "status_code": None, "detail": "connectivity_check_failed"}

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
