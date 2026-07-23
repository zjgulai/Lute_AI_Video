"""Seedance 2.0 video generation client.

The only enabled paid backend is the cataloged poyo.ai async submit/poll
path. Native Seedance mutation remains an explicit fail-closed legacy path.

Every public method has asyncio.timeout() protection (120s default).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import re
import socket
from collections.abc import Callable, Mapping
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import structlog

from src.config import (
    OUTPUT_DIR,
    POYO_API_BASE_URL,
    POYO_API_KEY,
    POYO_VIDEO_MODEL,
    SEEDANCE_API_BASE_URL,
    SEEDANCE_API_KEY,
)
from src.models.provider_cost import ProviderCostContractError, VideoDurationBillingFacts
from src.models.runtime_contracts import SeedanceVideoResult
from src.services.provider_cost import ProviderCostOperationDefinition, ProviderCostService
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.tools.llm_client import get_request_api_key

logger = structlog.get_logger()

SEEDANCE_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 3

# poyo.ai uses an async submit+poll architecture. Default model is driven by
# POYO_VIDEO_MODEL env var (Sprint 0 S0-1 default: seedance-2). Callers may
# override per-request via the `model` parameter on text_to_video /
# image_to_video — see ModelRouter.select_model(scenario) for the routing
# contract introduced in Sprint 1 P1-1.
POYO_MODEL_NAME = POYO_VIDEO_MODEL or "seedance-2"
POYO_VIDEO_OPERATION_KEY = "poyo.seedance"
POYO_GLOBAL_ENDPOINT = "https://api.poyo.ai"
_SAFE_OPERATION_INSTANCE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_SUPPORTED_POYO_MODELS = frozenset({"seedance-2", "seedance-2-fast"})
_SUPPORTED_RESOLUTIONS = frozenset({"480p", "720p", "1080p"})

ProviderCostServiceFactory = Callable[
    [Mapping[str, ProviderCostOperationDefinition]],
    ProviderCostService,
]


class SeedanceTimeoutError(asyncio.TimeoutError):
    """Raised when a Seedance call exceeds SEEDANCE_TIMEOUT_SECONDS."""


# Mapping from file extension to MIME type for base64 data URLs.
# POYO Happy Horse `image_urls[]` only accepts http(s) URLs or `data:image/...;base64,...`,
# so local paths must be inlined here before submit.
_IMAGE_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_IMAGE_MAX_BYTES = 32 * 1024 * 1024
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_WEBP_MAGIC = b"RIFF"
_GIF_MAGICS = (b"GIF87a", b"GIF89a")


def _validate_remote_image_ref(ref: str) -> tuple[str, str]:
    parsed = urlsplit(ref)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance reference image URL is not an approved HTTPS reference",
        )
    try:
        port = parsed.port
    except ValueError:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance reference image URL port is not approved",
        ) from None
    if port not in (None, 443):
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance reference image URL port is not approved",
        )
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata.google.internal", "169.254.169.254"}:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance reference image host is blocked",
        )
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_unspecified):
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance reference image host is blocked",
        )
    if address is None:
        try:
            resolved = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError:
            resolved = []
        for _, _, _, _, sockaddr in resolved:
            try:
                resolved_address = ip_address(sockaddr[0])
            except (ValueError, IndexError):
                continue
            if resolved_address.is_private or resolved_address.is_loopback or resolved_address.is_link_local or resolved_address.is_reserved or resolved_address.is_unspecified:
                raise ProviderCostContractError(
                    "provider_cost_rule_unavailable",
                    "PoYo Seedance reference image host is blocked",
                )
    return ref, hashlib.sha256(ref.encode("utf-8")).hexdigest()


def _to_poyo_image_url(ref: str, *, allowed_root: Path) -> tuple[str, str]:
    """Prepare one server-owned image reference and return URL plus byte digest."""

    if not isinstance(ref, str) or not ref:
        raise ProviderCostContractError(
            "provider_cost_usage_invalid",
            "PoYo Seedance reference image is invalid",
        )
    lowered = ref.lower()
    if lowered.startswith("data:image/"):
        header, separator, encoded = ref.partition(",")
        if not separator or ";base64" not in header.lower() or not encoded:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance data image reference is invalid",
            )
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance data image reference is invalid",
            ) from None
        if not raw or len(raw) > _IMAGE_MAX_BYTES:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance data image reference is too large",
            )
        return ref, hashlib.sha256(raw).hexdigest()
    if lowered.startswith(("http://", "https://")):
        return _validate_remote_image_ref(ref)

    candidate = Path(ref)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.exists() or not candidate.is_file():
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image reference is not a server-owned artifact",
        )
    try:
        resolved_root = allowed_root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
    except (OSError, ValueError):
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image reference is outside the artifact root",
        ) from None
    if resolved.is_symlink() or not resolved.is_file():
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image reference is not a regular artifact",
        )
    ext = resolved.suffix.lower()
    mime = _IMAGE_MIME_BY_EXT.get(ext)
    if mime is None:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image extension is not approved",
        )
    try:
        raw = resolved.read_bytes()
    except OSError:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image cannot be read",
        ) from None
    if not raw or len(raw) > _IMAGE_MAX_BYTES:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image size is not approved",
        )
    magic_ok = (
        (ext == ".png" and raw.startswith(_PNG_MAGIC))
        or (ext in {".jpg", ".jpeg"} and raw.startswith(_JPEG_MAGIC))
        or (ext == ".webp" and raw.startswith(_WEBP_MAGIC) and raw[8:12] == b"WEBP")
        or (ext == ".gif" and raw.startswith(_GIF_MAGICS))
    )
    if not magic_ok:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "PoYo Seedance local image type is not approved",
        )
    digest = hashlib.sha256(raw).hexdigest()
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}", digest

class SeedanceClient:
    """Generates videos using Seedance 2.0.

    Uses the cataloged poyo.ai backend when a PoYo key is available. A native
    Seedance key is retained only for stable zero-network legacy blocking.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        output_dir: Path | None = None,
        max_retries: int | None = None,
        *,
        price_catalog: ProviderPriceCatalog | None = None,
        cost_service_factory: ProviderCostServiceFactory | None = None,
    ):
        # Unified routing: poyo.ai preferred when POYO_API_KEY is set
        # P0-1: Read from request context first (contextvars) for multi-tenant isolation
        req_poyo = get_request_api_key("POYO_API_KEY")
        req_seedance = get_request_api_key("SEEDANCE_API_KEY")

        _seedance_key = api_key or req_seedance or SEEDANCE_API_KEY
        _seedance_url = base_url or SEEDANCE_API_BASE_URL
        self._is_poyo = False

        if req_poyo or POYO_API_KEY:
            self._is_poyo = True
            _seedance_key = api_key or req_poyo or POYO_API_KEY
            _seedance_url = base_url or POYO_API_BASE_URL
            logger.info("seedance: using poyo.ai backend (unified)")
        elif _seedance_key:
            logger.info("seedance: using native ByteDance API")
        else:
            logger.warning("seedance: no API keys — stub mode only")

        self.api_key = _seedance_key
        self.base_url = _seedance_url.rstrip("/")
        self.output_dir = output_dir or OUTPUT_DIR / "seedance"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max(1, int(max_retries) + 1) if max_retries is not None else MAX_RETRIES
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
        self._cost_service_factory = cost_service_factory
        self._poyo = None
        if not self._is_poyo and self.api_key:
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "native Seedance mutation is outside the frozen PoYo catalog",
            )

    def _get_poyo(self):
        if self._poyo is None:
            from src.tools.poyo_client import PoyoClient

            self._poyo = PoyoClient(
                api_key=self.api_key,
                base_url=self.base_url,
                price_catalog=self._price_catalog,
                cost_service_factory=self._cost_service_factory,
            )
        return self._poyo

    async def text_to_video(
        self,
        prompt: str,
        image_refs: list[str] | None = None,
        duration: int = 10,
        resolution: str = "720p",
        model: str | None = None,
        *,
        reference_video_urls: list[str] | None = None,
        reference_audio_urls: list[str] | None = None,
        operation_instance: str = "primary",
    ) -> SeedanceVideoResult:
        if not self.api_key:
            logger.warning("seedance: no API key — returning stub")
            return self._stub_result(prompt=prompt, mode="text_to_video")

        if self._is_poyo:
            return await self._poyo_submit_and_poll(
                prompt=prompt,
                image_refs=image_refs,
                duration=duration,
                resolution=resolution,
                model=model,
                reference_video_urls=reference_video_urls,
                reference_audio_urls=reference_audio_urls,
                operation_instance=operation_instance,
            )

        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "native Seedance mutation is outside the frozen PoYo catalog",
        )

    async def image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        duration: int = 10,
        style_preserve: bool = True,
        model: str | None = None,
        *,
        resolution: str = "720p",
        operation_instance: str = "primary",
    ) -> SeedanceVideoResult:
        if not self.api_key:
            return self._stub_result(prompt=prompt, mode="image_to_video")

        if self._is_poyo:
            # poyo.ai supports image refs via input.images
            return await self._poyo_submit_and_poll(
                prompt=prompt,
                image_refs=[image_url],
                duration=duration,
                resolution=resolution,
                model=model,
                operation_instance=operation_instance,
            )


        del image_url, prompt, duration, style_preserve, model, resolution
        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "native Seedance mutation is outside the frozen PoYo catalog",
        )

    # ═══ poyo.ai async backend ═══

    async def _poyo_submit_and_poll(
        self,
        prompt: str,
        image_refs: list[str] | None = None,
        duration: int = 10,
        resolution: str = "720p",
        model: str | None = None,
        reference_video_urls: list[str] | None = None,
        reference_audio_urls: list[str] | None = None,
        operation_instance: str = "primary",
    ) -> SeedanceVideoResult:
        """Run one exact PoYo Seedance async attempt; polling never resubmits."""

        if not isinstance(prompt, str) or not prompt:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "PoYo Seedance prompt must be non-empty text",
            )
        active_model = model or POYO_MODEL_NAME
        if not isinstance(active_model, str) or active_model not in _SUPPORTED_POYO_MODELS:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance model is not frozen",
            )
        if self.base_url != POYO_GLOBAL_ENDPOINT:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo billing endpoint is not exact",
            )
        if not isinstance(resolution, str) or resolution not in _SUPPORTED_RESOLUTIONS or (
            active_model == "seedance-2-fast" and resolution == "1080p"
        ):
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance resolution has no exact price rule",
            )
        if type(duration) is not int or duration < 4 or duration > 15:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "PoYo Seedance duration must be an integer from 4 to 15 seconds",
            )
        if reference_video_urls or reference_audio_urls:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance video/audio references are not cataloged",
            )
        if not isinstance(operation_instance, str) or _SAFE_OPERATION_INSTANCE_RE.fullmatch(operation_instance) is None:
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo Seedance operation instance is invalid",
            )
        if image_refs is not None:
            if not isinstance(image_refs, list) or len(image_refs) > 1:
                raise ProviderCostContractError(
                    "provider_cost_rule_unavailable",
                    "PoYo Seedance accepts one exact reference image",
                )
            if image_refs and (not isinstance(image_refs[0], str) or not image_refs[0]):
                raise ProviderCostContractError(
                    "provider_cost_usage_invalid",
                    "PoYo Seedance reference image is invalid",
                )

        from src.tools.poyo_safety import sanitize_for_poyo

        prompt = prompt[:2400] if len(prompt) > 2400 else prompt
        prompt, _ = sanitize_for_poyo(prompt)
        input_payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": "9:16",
            "resolution": resolution,
            "duration": duration,
        }
        image_digest: str | None = None
        if image_refs:
            image_url, image_digest = _to_poyo_image_url(
                image_refs[0],
                allowed_root=self.output_dir.resolve().parent,
            )
            input_payload["image_urls"] = [image_url]
        reference_kind = "image" if image_refs else "none"
        catalog_operation = "image_to_video" if image_refs else "text_to_video"
        fingerprint_payload = {
            "version": "poyo-seedance-mutation.v1",
            "operation_instance": operation_instance,
            "model": active_model,
            "resolution": resolution,
            "duration": duration,
            "reference_kind": reference_kind,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "image_bytes_sha256": image_digest,
        }
        attempt_fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        filename = f"seedance_{operation_instance}_{hash(prompt) & 0xFFFF:04x}.mp4"
        filepath = self.output_dir / filename

        def validate_terminal(task: dict[str, Any]) -> None:
            files = task.get("files")
            if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], Mapping):
                raise ValueError("PoYo Seedance result count is not exactly one")
            if not isinstance(files[0].get("file_url"), str) or not files[0]["file_url"]:
                raise ValueError("PoYo Seedance result URL is missing")
            reported_duration = task.get("duration_ms")
            if reported_duration is not None and reported_duration != duration * 1000:
                raise ValueError("PoYo Seedance duration conflicts with request")
            reported_seconds = task.get("duration")
            if reported_seconds is not None and reported_seconds != duration:
                raise ValueError("PoYo Seedance duration conflicts with request")

        result = await self._get_poyo().run_costed(
            model=active_model,
            input_payload=input_payload,
            output_path=filepath,
            operation_key=POYO_VIDEO_OPERATION_KEY,
            logical_operation=f"{POYO_VIDEO_OPERATION_KEY}.{operation_instance}",
            attempt_fingerprint=attempt_fingerprint,
            catalog_operation=catalog_operation,
            media_type="video",
            billing_fact_kind="video_duration.v1",
            dimensions={"reference_input_kind": reference_kind, "resolution": resolution},
            reservation_billing_facts=VideoDurationBillingFacts(
                schema_version="video_duration.v1",
                task_count=1,
                duration_ms=duration * 1000,
            ),
            settlement_facts_builder=lambda _task: VideoDurationBillingFacts(
                schema_version="video_duration.v1",
                task_count=1,
                duration_ms=duration * 1000,
            ),
            artifact_url_builder=lambda task: task["files"][0]["file_url"],
            terminal_task_validator=validate_terminal,
            poll_interval=5.0,
            max_polls=120,
        )
        if result.get("_poyo_state") == "released":
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "PoYo Seedance task was released without a paid artifact",
            )
        poyo_state = result.get("_poyo_state")
        if poyo_state not in {"submitted", "settled"}:
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "PoYo Seedance task returned an invalid durable state",
            )
        return {
            "video_url": result.get("file_url", ""),
            "local_path": result.get("local_path", ""),
            "prompt_used": prompt,
            "duration": duration,
            "_poyo_state": poyo_state,
            "task_id": result.get("task_id", ""),
            "simulated": False,
        }

    def _stub_result(self, prompt: str, mode: str = "unknown") -> SeedanceVideoResult:
        return {
            "video_url": "[SEEDANCE_STUB — add API key]",
            "local_path": str(self.output_dir / f"stub_{mode}_{hash(prompt) & 0xFFFF:04x}.mp4"),
            "prompt_used": prompt,
            "duration": 0,
            "_stub_mode": mode,
            "simulated": True,
        }

    async def close(self):
        if self._poyo is not None:
            await self._poyo.close()
            self._poyo = None
