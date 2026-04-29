"""DALL-E image generation client — thumbnail production.

Replaces the thumbnail stub with real AI image generation.
Generates 4 variants per video.

API: OpenAI Images API (DALL-E 3)

Every public method has asyncio.timeout() protection (120s default).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import structlog

from src.config import OPENAI_API_KEY, OUTPUT_DIR

logger = structlog.get_logger()

DALLE_TIMEOUT_SECONDS = 120.0


class DalleTimeoutError(asyncio.TimeoutError):
    """Raised when a DALL-E call exceeds DALLE_TIMEOUT_SECONDS."""


class DalleClient:
    """Generates thumbnail images using DALL-E 3."""

    def __init__(self, api_key: str | None = None, output_dir: Path | None = None):
        self.api_key = api_key or OPENAI_API_KEY
        self.output_dir = output_dir or OUTPUT_DIR / "thumbnails"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=90.0,
        )

    async def generate(
        self,
        prompt: str,
        variant_id: str = "A",
        size: str = "1024x1792",  # Vertical 9:16 for TikTok/Shorts
        quality: str = "standard",
    ) -> dict:
        """Generate a single thumbnail image.

        Wrapped in asyncio.timeout() to prevent pipeline hangs.
        Falls back to stub on timeout or any error.

        Args:
            prompt: DALL-E generation prompt.
            variant_id: A/B/C/D identifier.
            size: Image size (1024x1792 for vertical).
            quality: 'standard' or 'hd'.

        Returns:
            {variant_id, prompt, image_url, local_path}
        """
        if not self.api_key:
            logger.warning("dalle: no API key — returning stub")
            return self._stub_result(variant_id, prompt)

        from src.tools.retry import retry_with_backoff

        async def _do_generate():
            async with asyncio.timeout(DALLE_TIMEOUT_SECONDS):
                response = await self._client.post(
                    "/images/generations",
                    json={
                        "model": "dall-e-3",
                        "prompt": prompt,
                        "n": 1,
                        "size": size,
                        "quality": quality,
                    },
                )
                response.raise_for_status()
                data = response.json()

                image_url = data["data"][0]["url"]

                # Download and save locally
                img_response = await httpx.AsyncClient().get(image_url)
                filename = f"thumb_{variant_id}_{hash(prompt) & 0xFFFF:04x}.png"
                filepath = self.output_dir / filename
                filepath.write_bytes(img_response.content)

                logger.info("dalle: generated", variant=variant_id, file=filename)
                return {
                    "variant_id": variant_id,
                    "prompt": prompt,
                    "image_url": image_url,
                    "local_path": str(filepath),
                }

        try:
            return await retry_with_backoff(_do_generate)
        except TimeoutError:
            logger.error(
                "dalle: generation timed out",
                variant=variant_id,
                timeout=DALLE_TIMEOUT_SECONDS,
            )
            return self._stub_result(variant_id, prompt)
        except Exception as e:
            logger.error("dalle: generation failed", variant=variant_id, error=str(e))
            return self._stub_result(variant_id, prompt)

    async def generate_variants(
        self,
        variants: list[dict],
        size: str = "1024x1792",
    ) -> list[dict]:
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

    def _stub_result(self, variant_id: str, prompt: str) -> dict:
        return {
            "variant_id": variant_id,
            "prompt": prompt,
            "image_url": "[DALL-E_STUB — add OPENAI_API_KEY]",
            "local_path": str(self.output_dir / f"stub_{variant_id}.png"),
        }

    @property
    def cost_estimate(self) -> dict:
        return {
            "model": "dall-e-3",
            "price_per_image_standard": "$0.04",
            "price_per_image_hd": "$0.08",
            "sizes": ["1024x1024", "1024x1792", "1792x1024"],
        }
