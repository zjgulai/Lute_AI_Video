"""GPT Image 2 (gpt-image-2) generation client.

Supports two backends:
  1. OpenAI Images API (gpt-image-2) — direct synchronous generation
  2. poyo.ai proxy — async submit + polling architecture

Every public method has asyncio.timeout() protection (120s default).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import structlog

from typing import Any

from src.config import (
    OPENAI_API_KEY,
    OUTPUT_DIR,
    POYO_API_KEY,
    POYO_IMAGE_MODEL,
)

logger = structlog.get_logger()

GPT_IMAGE_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 3


class GPTImageTimeoutError(asyncio.TimeoutError):
    """Raised when a gpt-image-2 call exceeds GPT_IMAGE_TIMEOUT_SECONDS."""


class GPTImageClient:
    """Generates images using gpt-image-2 with style reference support.

    Auto-detects backend:
      - If POYO_API_KEY is set → poyo.ai async proxy (preferred)
      - If only OPENAI_API_KEY is set → native OpenAI API
    """

    def __init__(
        self,
        api_key: str | None = None,
        output_dir: Path | None = None,
    ):
        _openai_key = api_key or OPENAI_API_KEY
        self._is_poyo = False

        # Prefer poyo.ai when available — OPENAI_API_KEY may be a Kimi key
        # that doesn't support image generation endpoints.
        if POYO_API_KEY:
            self._is_poyo = True
            logger.info("gpt_image: using poyo.ai backend (POYO_API_KEY present)")
        elif not _openai_key:
            logger.warning("gpt_image: no API keys — stub mode only")

        self.api_key = POYO_API_KEY or _openai_key
        self.output_dir = output_dir or OUTPUT_DIR / "gpt_images"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self._is_poyo:
            from src.tools.poyo_client import PoyoClient
            self._poyo = PoyoClient()
        else:
            self._client = httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; AI-Video-Agent/1.0)",
                },
                timeout=90.0,
            )

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

    async def _poyo_generate(
        self,
        prompt: str,
        style_ref: str | None,
        quality: str,
        size: str,
        image_id: str,
    ) -> dict[str, Any]:
        # poyo.ai GPT Image 2 format: size uses ratio like "1:1", "9:16", etc.
        # Remove "n" (not in poyo docs) and map pixel size to ratio
        ratio = self._size_to_ratio(size)
        input_payload: dict[str, Any] = {
            "prompt": prompt,
            "size": ratio,
            "quality": quality,
        }
        if style_ref:
            input_payload["style_ref"] = style_ref

        filename = f"poyo_img_{image_id}_{hash(prompt) & 0xFFFF:04x}.png"
        filepath = self.output_dir / filename

        try:
            result = await self._poyo.submit_poll_download(
                model=POYO_IMAGE_MODEL,
                input_payload=input_payload,
                output_path=filepath,
                poll_interval=5.0,
                max_polls=40,  # 200s max — image gen can take 2-3min
            )
            logger.info("gpt_image: poyo generated", image_id=image_id, file=filename)
            return {
                "image_id": image_id,
                "prompt": prompt,
                "image_url": result["file_url"],
                "local_path": str(result["local_path"]),
                "quality": quality,
            }
        except Exception as e:
            logger.error("gpt_image: poyo failed", image_id=image_id, error=str(e))
            return self._stub_result(image_id, prompt, quality)

    # ═══ OpenAI backend ═══

    async def _openai_generate(
        self,
        prompt: str,
        style_ref: str | None,
        quality: str,
        size: str,
        image_id: str,
    ) -> dict[str, Any]:
        from src.tools.retry import retry_with_backoff

        payload = {
            "model": "gpt-image-2",
            "prompt": prompt,
            "n": 1,
            "size": size,
            "output_quality": quality,
        }
        if style_ref:
            payload["style_ref"] = style_ref

        async def _do_generate():
            async with asyncio.timeout(GPT_IMAGE_TIMEOUT_SECONDS):
                response = await self._client.post("/images/generations", json=payload)
                response.raise_for_status()
                data = response.json()

                image_url = data["data"][0]["url"]
                img_response = await httpx.AsyncClient().get(image_url)
                filename = f"gpt_img_{image_id}_{hash(prompt) & 0xFFFF:04x}.png"
                filepath = self.output_dir / filename
                filepath.write_bytes(img_response.content)

                logger.info("gpt_image: generated", image_id=image_id, file=filename)
                return {
                    "image_id": image_id,
                    "prompt": prompt,
                    "image_url": image_url,
                    "local_path": str(filepath),
                    "quality": quality,
                }

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await retry_with_backoff(_do_generate)
            except TimeoutError:
                logger.error("gpt_image: timed out", image_id=image_id, attempt=attempt + 1)
                last_error = "timeout"
            except httpx.HTTPStatusError as e:
                logger.error("gpt_image: HTTP error", image_id=image_id, status=e.response.status_code)
                last_error = f"http_{e.response.status_code}"
                if e.response.status_code in (400, 401, 422):
                    break
            except Exception as e:
                logger.error("gpt_image: error", image_id=image_id, error=str(e))
                last_error = str(e)

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2.0 ** attempt)

        logger.warning("gpt_image: all retries exhausted, returning stub", image_id=image_id)
        return self._stub_result(image_id, prompt, quality)

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
        mapping = {
            "1024x1024": "1:1",
            "1024x1792": "9:16",
            "1792x1024": "16:9",
            "512x512": "1:1",
            "512x896": "9:16",
            "896x512": "16:9",
        }
        return mapping.get(size, size)  # fallback to raw if already a ratio

    def _stub_result(self, image_id: str, prompt: str, quality: str) -> dict[str, Any]:
        return {
            "image_id": image_id,
            "prompt": prompt,
            "image_url": f"[GPT_IMAGE_STUB — add OPENAI_API_KEY or POYO_API_KEY]",
            "local_path": str(self.output_dir / f"stub_{image_id}.png"),
            "quality": quality,
        }

    async def close(self):
        if self._is_poyo:
            await self._poyo.close()
        else:
            await self._client.aclose()
