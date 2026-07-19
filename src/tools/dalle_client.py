"""Retired DALL-E thumbnail compatibility client.

The unpriced DALL-E 3 mutation path is blocked before HTTP client construction.
No-key callers retain an explicit local stub for legacy no-media flows.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from src.config import OPENAI_API_KEY, OUTPUT_DIR
from src.models.provider_cost import ProviderCostContractError
from src.tools.llm_client import get_request_api_key

logger = structlog.get_logger()

DALLE_TIMEOUT_SECONDS = 120.0


class DalleTimeoutError(asyncio.TimeoutError):
    """Raised when a DALL-E call exceeds DALLE_TIMEOUT_SECONDS."""


class DalleClient:
    """Expose only the no-key stub; direct DALL-E mutation is blocked."""

    def __init__(self, api_key: str | None = None, output_dir: Path | None = None):
        self.api_key = api_key or get_request_api_key("OPENAI_API_KEY") or OPENAI_API_KEY
        if self.api_key:
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "direct DALL-E mutation is outside the frozen provider catalog",
            )
        self.output_dir = output_dir or OUTPUT_DIR / "thumbnails"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._client = None

    async def generate(
        self,
        prompt: str,
        variant_id: str = "A",
        size: str = "1024x1792",  # Vertical 9:16 for TikTok/Shorts
        quality: str = "standard",
    ) -> dict[str, Any]:
        """Return a local no-attempt stub; paid DALL-E is not cataloged.

        Args:
            prompt: DALL-E generation prompt.
            variant_id: A/B/C/D identifier.
            size: Image size (1024x1792 for vertical).
            quality: 'standard' or 'hd'.

        Returns:
            ``{variant_id, prompt, image_url, local_path}`` stub metadata.
        """
        del size, quality
        logger.warning("dalle: legacy provider path disabled — returning zero-attempt stub")
        return self._stub_result(variant_id, prompt)

    async def generate_variants(
        self,
        variants: list[dict[str, Any]],
        size: str = "1024x1792",
    ) -> list[dict[str, Any]]:
        """Generate all thumbnail variants for a video.

        Args:
            variants: List of {variant_id, prompt} dicts.
            size: Image size.

        Returns:
            List of {variant_id, prompt, image_url, local_path} dicts.
        """
        results = []
        for v in variants:
            result = await self.generate(
                prompt=v.get("prompt", ""),
                variant_id=v.get("variant_id", "A"),
                size=size,
            )
            results.append(result)
        return results

    def _stub_result(self, variant_id: str, prompt: str) -> dict[str, Any]:
        return {
            "variant_id": variant_id,
            "prompt": prompt,
            "image_url": "[DALL-E_STUB — add OPENAI_API_KEY]",
            "local_path": str(self.output_dir / f"stub_{variant_id}.png"),
        }

    @property
    def cost_estimate(self) -> dict[str, Any]:
        return {
            "status": "blocked",
            "reason": "provider_cost_legacy_path_blocked",
        }
