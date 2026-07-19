"""GPT Image 2 (gpt-image-2) generation client.

The only enabled paid backend is the cataloged poyo.ai async submit/poll
path. Direct OpenAI image mutation remains an explicit fail-closed legacy path.

Every public method has asyncio.timeout() protection (120s default).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import structlog

from src.config import (
    OPENAI_API_KEY,
    OUTPUT_DIR,
    POYO_API_KEY,
    POYO_IMAGE_MODEL,
)
from src.models.provider_cost import ImageCountBillingFacts, ProviderCostContractError
from src.services.provider_cost import ProviderCostOperationDefinition, ProviderCostService
from src.services.provider_price_catalog import ProviderPriceCatalog
from src.tools.llm_client import get_request_api_key

logger = structlog.get_logger()

GPT_IMAGE_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 3
POYO_IMAGE_OPERATION_KEY = "poyo.gpt_image"
_SAFE_OPERATION_INSTANCE_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_LEGACY_SIZE_ALIASES = {
    "1024x1024": "1:1",
    "1024x1792": "9:16",
    "1792x1024": "16:9",
    "1536x1024": "3:2",
    "1024x1536": "2:3",
    "512x512": "1:1",
    "512x896": "9:16",
    "896x512": "16:9",
}

ProviderCostServiceFactory = Callable[
    [Mapping[str, ProviderCostOperationDefinition]],
    ProviderCostService,
]


@dataclass(frozen=True, slots=True)
class GPTImageResolution:
    requested_resolution: str
    effective_resolution: str
    wire_size: str


def resolve_gpt_image_resolution(size: object, *, quality: object) -> GPTImageResolution:
    """Freeze the approved GPT Image 2 requested/effective resolution truth."""

    if not isinstance(quality, str) or quality not in {"low", "medium", "high"}:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "GPT Image 2 quality is not frozen",
        )
    raw = "auto" if size is None or size == "" else size
    if not isinstance(raw, str):
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "GPT Image 2 size is not frozen",
        )
    raw = raw.strip()
    if raw.lower() == "auto":
        return GPTImageResolution("auto", "1K", "auto")
    if raw in {"1K", "2K", "4K"}:
        return GPTImageResolution(raw, raw, raw)
    if raw in {"1:1", "16:9", "9:16", "21:9", "9:21", "3:2", "2:3"}:
        return GPTImageResolution("auto", "1K", raw)
    if raw in _LEGACY_SIZE_ALIASES:
        return GPTImageResolution("auto", "1K", _LEGACY_SIZE_ALIASES[raw])

    match = re.fullmatch(r"([1-9][0-9]{2,4})x([1-9][0-9]{2,4})", raw)
    if match is None:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "GPT Image 2 size is not frozen",
        )
    width, height = (int(match.group(1)), int(match.group(2)))
    longest = max(width, height)
    if min(width, height) < 2048 or longest > 4096:
        raise ProviderCostContractError(
            "provider_cost_rule_unavailable",
            "GPT Image 2 custom size is outside the approved 2K/4K envelope",
        )
    if longest <= 3072:
        requested = "2K"
        effective = "2K"
    else:
        requested = "4K"
        ratio = width / height
        legal_ratio = any(abs(ratio - candidate) < 1e-6 for candidate in (16 / 9, 9 / 16, 21 / 9, 9 / 21))
        effective = "4K" if legal_ratio or width == 3840 or height == 3840 else "2K"
    return GPTImageResolution(requested, effective, GPTImageClient._size_to_ratio(raw))


def _poyo_image_max_polls() -> int:
    try:
        value = int(os.getenv("POYO_IMAGE_MAX_POLLS", "72"))
    except ValueError:
        value = 72
    return max(40, value)


class GPTImageTimeoutError(asyncio.TimeoutError):
    """Raised when a gpt-image-2 call exceeds GPT_IMAGE_TIMEOUT_SECONDS."""


class GPTImageClient:
    """Generates images using gpt-image-2 with style reference support.

    Uses the cataloged poyo.ai backend when a PoYo key is available. A direct
    OpenAI key is retained only for stable zero-network legacy blocking.
    """

    def __init__(
        self,
        api_key: str | None = None,
        output_dir: Path | None = None,
        max_retries: int | None = None,
        *,
        price_catalog: ProviderPriceCatalog | None = None,
        cost_service_factory: ProviderCostServiceFactory | None = None,
    ):
        _openai_key = api_key or get_request_api_key("OPENAI_API_KEY") or OPENAI_API_KEY
        _poyo_key = get_request_api_key("POYO_API_KEY") or POYO_API_KEY
        self._is_poyo = False

        # Prefer poyo.ai when available — OPENAI_API_KEY may be a Kimi key
        # that doesn't support image generation endpoints.
        if _poyo_key:
            self._is_poyo = True
            logger.info("gpt_image: using poyo.ai backend (POYO_API_KEY present)")
        elif not _openai_key:
            logger.warning("gpt_image: no API keys — stub mode only")

        self.api_key = _poyo_key or _openai_key
        self.output_dir = output_dir or OUTPUT_DIR / "gpt_images"
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
        self._client: httpx.AsyncClient | None = None

        if self._is_poyo:
            # Keep the provider client lazy: execution-context and catalog
            # guards must run before any HTTP client is constructed.
            return
        # Direct OpenAI/DALL-E is not part of the frozen PoYo catalog.  Keep the
        # instance construction side-effect free and reject on generate().

    async def generate(
        self,
        prompt: str,
        style_ref: str | None = None,
        quality: str = "high",
        size: str = "1024x1792",
        image_id: str = "img_001",
    ) -> dict[str, Any]:
        """Generate an image.

        Wrapped in asyncio.timeout() with retry and graceful fallback.
        """
        if not self.api_key:
            logger.warning("gpt_image: no API key — returning stub")
            return self._stub_result(image_id, prompt, quality)

        if self._is_poyo:
            return await self._poyo_generate(
                prompt=prompt,
                style_ref=style_ref,
                quality=quality,
                size=size,
                image_id=image_id,
            )

        return await self._openai_generate(
            prompt=prompt,
            style_ref=style_ref,
            quality=quality,
            size=size,
            image_id=image_id,
        )

    # ═══ poyo.ai backend ═══

    def _get_poyo(self):
        if self._poyo is None:
            from src.tools.poyo_client import PoyoClient

            self._poyo = PoyoClient(
                price_catalog=self._price_catalog,
                cost_service_factory=self._cost_service_factory,
            )
        return self._poyo

    async def _poyo_generate(
        self,
        prompt: str,
        style_ref: str | None,
        quality: str,
        size: str,
        image_id: str,
    ) -> dict[str, Any]:
        if not isinstance(prompt, str) or not prompt:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "GPT Image 2 prompt must be non-empty text",
            )
        if not isinstance(image_id, str) or not image_id:
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "GPT Image 2 image ID is invalid",
            )
        if style_ref is not None and not isinstance(style_ref, str):
            raise ProviderCostContractError(
                "provider_cost_usage_invalid",
                "GPT Image 2 style reference is invalid",
            )
        if POYO_IMAGE_MODEL != "gpt-image-2":
            raise ProviderCostContractError(
                "provider_cost_rule_unavailable",
                "PoYo image model is not frozen",
            )
        from src.tools.poyo_safety import sanitize_for_poyo

        prompt = prompt[:2400] if len(prompt) > 2400 else prompt
        prompt, _ = sanitize_for_poyo(prompt)
        frozen_size = resolve_gpt_image_resolution(size, quality=quality)
        input_payload: dict[str, Any] = {
            "prompt": prompt,
            "size": frozen_size.wire_size,
            "quality": quality,
        }
        if style_ref:
            input_payload["style_ref"] = style_ref

        operation_instance = (
            image_id
            if _SAFE_OPERATION_INSTANCE_RE.fullmatch(image_id)
            else f"id_{hashlib.sha256(image_id.encode('utf-8')).hexdigest()[:16]}"
        )
        filename = f"poyo_img_{operation_instance}_{hash(prompt) & 0xFFFF:04x}.png"
        filepath = self.output_dir / filename
        fingerprint_payload = {
            "version": "poyo-image-mutation.v1",
            "operation_instance": operation_instance,
            "model": POYO_IMAGE_MODEL,
            "quality": quality,
            "requested_resolution": frozen_size.requested_resolution,
            "effective_resolution": frozen_size.effective_resolution,
            "size": frozen_size.wire_size,
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "style_ref_sha256": (
                hashlib.sha256(style_ref.encode("utf-8")).hexdigest() if isinstance(style_ref, str) else None
            ),
        }
        attempt_fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        def validate_terminal(task: dict[str, Any]) -> None:
            files = task.get("files")
            if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], Mapping):
                raise ValueError("PoYo image result count is not exactly one")
            if not isinstance(files[0].get("file_url"), str) or not files[0]["file_url"]:
                raise ValueError("PoYo image result URL is missing")

        result = await self._get_poyo().run_costed(
            model=POYO_IMAGE_MODEL,
            input_payload=input_payload,
            output_path=filepath,
            operation_key=POYO_IMAGE_OPERATION_KEY,
            logical_operation=f"{POYO_IMAGE_OPERATION_KEY}.{operation_instance}",
            attempt_fingerprint=attempt_fingerprint,
            catalog_operation="image_generation",
            media_type="image",
            billing_fact_kind="image_count.v1",
            dimensions={
                "effective_resolution": frozen_size.effective_resolution,
                "quality": quality,
            },
            reservation_billing_facts=ImageCountBillingFacts(
                schema_version="image_count.v1",
                image_count=1,
            ),
            settlement_facts_builder=lambda _task: ImageCountBillingFacts(
                schema_version="image_count.v1",
                image_count=1,
            ),
            artifact_url_builder=lambda task: task["files"][0]["file_url"],
            terminal_task_validator=validate_terminal,
            poll_interval=5.0,
            max_polls=_poyo_image_max_polls(),
        )
        if result.get("_poyo_state") == "released":
            raise ProviderCostContractError(
                "provider_cost_attempt_conflict",
                "PoYo image task was released without a paid artifact",
            )
        logger.info("gpt_image: poyo result", image_id=image_id, state=result.get("_poyo_state"))
        return {
            "image_id": image_id,
            "prompt": prompt,
            "image_url": result.get("file_url", ""),
            "local_path": result.get("local_path", ""),
            "quality": quality,
            "requested_resolution": frozen_size.requested_resolution,
            "effective_resolution": frozen_size.effective_resolution,
            "_poyo_state": result.get("_poyo_state"),
        }

    # ═══ Legacy direct path (blocked) ═══

    async def _openai_generate(
        self,
        prompt: str,
        style_ref: str | None,
        quality: str,
        size: str,
        image_id: str,
    ) -> dict[str, Any]:
        del prompt, style_ref, quality, size, image_id
        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "direct OpenAI image mutation is outside the frozen PoYo catalog",
        )

    async def generate_thumbnail_set(
        self,
        prompts: list[dict[str, Any]],
        size: str = "1024x1792",
        style_ref: str | None = None,
    ) -> list[dict[str, Any]]:
        """Generate a set of thumbnail variants."""
        results = []
        quality = "high"
        for item in prompts:
            result = await self.generate(
                prompt=item["prompt"],
                style_ref=style_ref,
                quality=quality,
                size=size,
                image_id=item.get("image_id", "thumb"),
            )
            results.append(result)
        return results

    @staticmethod
    def _size_to_ratio(size: str) -> str:
        """Map pixel dimensions to poyo.ai ratio strings."""
        return _LEGACY_SIZE_ALIASES.get(size, size)  # fallback to raw if already a ratio

    def _stub_result(self, image_id: str, prompt: str, quality: str) -> dict[str, Any]:
        return {
            "image_id": image_id,
            "prompt": prompt,
            "image_url": "[GPT_IMAGE_STUB — add OPENAI_API_KEY or POYO_API_KEY]",
            "local_path": str(self.output_dir / f"stub_{image_id}.png"),
            "quality": quality,
        }

    async def close(self):
        if self._poyo is not None:
            await self._poyo.close()
            self._poyo = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None
