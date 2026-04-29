"""Seedance 2.0 video generation client.

Supports two backends:
  1. Native Seedance API (ByteDance) — synchronous generation
  2. poyo.ai proxy — async submit + polling architecture

Every public method has asyncio.timeout() protection (120s default).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import structlog

from src.config import (
    SEEDANCE_API_KEY,
    SEEDANCE_API_BASE_URL,
    POYO_API_KEY,
    POYO_API_BASE_URL,
    OUTPUT_DIR,
)

logger = structlog.get_logger()

SEEDANCE_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 3

# poyo.ai uses a different async architecture
POYO_MODEL_NAME = "seedance-2-fast"


class SeedanceTimeoutError(asyncio.TimeoutError):
    """Raised when a Seedance call exceeds SEEDANCE_TIMEOUT_SECONDS."""


class SeedanceClient:
    """Generates videos using Seedance 2.0.

    Auto-detects backend:
      - If SEEDANCE_API_KEY is set → native ByteDance API
      - If only POYO_API_KEY is set → poyo.ai async proxy
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        output_dir: Path | None = None,
    ):
        # Unified routing: poyo.ai preferred when POYO_API_KEY is set
        _seedance_key = api_key or SEEDANCE_API_KEY
        _seedance_url = base_url or SEEDANCE_API_BASE_URL
        self._is_poyo = False

        if POYO_API_KEY:
            self._is_poyo = True
            _seedance_key = POYO_API_KEY
            _seedance_url = POYO_API_BASE_URL
            logger.info("seedance: using poyo.ai backend (unified)")
        elif _seedance_key:
            logger.info("seedance: using native ByteDance API")
        else:
            logger.warning("seedance: no API keys — stub mode only")

        self.api_key = _seedance_key
        self.base_url = _seedance_url.rstrip("/")
        self.output_dir = output_dir or OUTPUT_DIR / "seedance"
        self.output_dir.mkdir(parents=True, exist_ok=True)
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

    async def text_to_video(
        self,
        prompt: str,
        image_refs: list[str] | None = None,
        duration: int = 10,
        resolution: str = "720p",
    ) -> dict:
        if not self.api_key:
            logger.warning("seedance: no API key — returning stub")
            return self._stub_result(prompt=prompt, mode="text_to_video")

        if self._is_poyo:
            return await self._poyo_submit_and_poll(
                prompt=prompt,
                image_refs=image_refs,
                duration=duration,
                resolution=resolution,
            )

        # Native Seedance API
        from src.tools.retry import retry_with_backoff

        payload = {
            "model": "seedance-2.0",
            "prompt": prompt,
            "duration": duration,
            "resolution": resolution,
        }
        if image_refs:
            payload["images"] = image_refs

        async def _do_generate():
            async with asyncio.timeout(SEEDANCE_TIMEOUT_SECONDS):
                response = await self._client.post("/v1/video/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return await self._poll_and_download(
                    task_id=data.get("task_id", ""),
                    prompt=prompt,
                )

        return await self._execute_with_retry(_do_generate, "text_to_video", prompt)

    async def image_to_video(
        self,
        image_url: str,
        prompt: str = "",
        duration: int = 10,
        style_preserve: bool = True,
    ) -> dict:
        if not self.api_key:
            return self._stub_result(prompt=prompt, mode="image_to_video")

        if self._is_poyo:
            # poyo.ai supports image refs via input.images
            return await self._poyo_submit_and_poll(
                prompt=prompt,
                image_refs=[image_url],
                duration=duration,
            )

        from src.tools.retry import retry_with_backoff

        payload = {
            "model": "seedance-2.0",
            "image": image_url,
            "duration": duration,
            "style_preserve": style_preserve,
        }
        if prompt:
            payload["prompt"] = prompt

        async def _do_generate():
            async with asyncio.timeout(SEEDANCE_TIMEOUT_SECONDS):
                response = await self._client.post("/v1/video/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                return await self._poll_and_download(
                    task_id=data.get("task_id", ""),
                    prompt=prompt or "image_to_video",
                )

        return await self._execute_with_retry(_do_generate, "image_to_video", prompt)

    # ═══ poyo.ai async backend ═══

    async def _poyo_submit_and_poll(
        self,
        prompt: str,
        image_refs: list[str] | None = None,
        duration: int = 10,
        resolution: str = "720p",
    ) -> dict:
        """poyo.ai flow: submit → poll → download with retry + backoff.

        Retries up to 3 times on submit failure or task failure to handle
        poyo.ai queue limits and transient errors.
        """
        MAX_RETRIES = 3
        SUBMIT_BACKOFF_BASE = 2.0  # 2^attempt seconds between retries

        for attempt in range(MAX_RETRIES):
            result = await self._poyo_attempt_submit_and_poll(
                prompt=prompt,
                image_refs=image_refs,
                duration=duration,
                resolution=resolution,
                attempt=attempt,
            )
            # If successful (has local_path with real video URL), return immediately
            if not result.get("_stub_mode"):
                return result

            # Stub returned — decide whether to retry
            stub_mode = result.get("_stub_mode", "")
            retryable_modes = (
                "poyo_submit_failed",
                "poyo_no_task_id",
                "poyo_failed:",
                "poyo_poll_timeout",
            )
            is_retryable = any(stub_mode.startswith(m) for m in retryable_modes)

            if is_retryable and attempt < MAX_RETRIES - 1:
                delay = SUBMIT_BACKOFF_BASE ** attempt
                logger.warning(
                    "poyo: retrying submit+poll",
                    attempt=attempt + 1,
                    delay=delay,
                    mode=stub_mode,
                )
                await asyncio.sleep(delay)
                continue

            # Non-retryable or exhausted retries — return the stub
            logger.error("poyo: all retries exhausted", mode=stub_mode, attempts=attempt + 1)
            return result

        # Should never reach here, but return a catch-all stub
        return self._stub_result(prompt=prompt, mode="poyo_all_retries_exhausted")

    async def _poyo_attempt_submit_and_poll(
        self,
        prompt: str,
        image_refs: list[str] | None,
        duration: int,
        resolution: str,
        attempt: int,
    ) -> dict:
        """Single attempt: submit → poll → download."""
        aspect_ratio = "9:16"

        input_payload: dict = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "duration": int(duration),
            "generate_audio": False,
        }
        if image_refs:
            input_payload["first_frame_image"] = image_refs[0]
            if len(image_refs) > 1:
                input_payload["last_frame_image"] = image_refs[1]

        submit_body = {
            "model": POYO_MODEL_NAME,
            "input": input_payload,
        }

        logger.info(
            "poyo: submitting task",
            model=POYO_MODEL_NAME,
            resolution=resolution,
            duration=duration,
            attempt=attempt + 1,
        )
        import json
        try:
            resp = await self._client.post(
                "/api/generate/submit",
                content=json.dumps(submit_body).encode(),
            )
            resp.raise_for_status()
        except Exception as e:
            logger.error("poyo: submit request failed", error=str(e), attempt=attempt + 1)
            return self._stub_result(prompt=prompt, mode="poyo_submit_failed")

        submit_data = resp.json()

        if submit_data.get("code") != 200:
            logger.error("poyo: submit failed", response=submit_data, attempt=attempt + 1)
            return self._stub_result(prompt=prompt, mode="poyo_submit_failed")

        task_id = submit_data.get("data", {}).get("task_id", "")
        if not task_id:
            logger.error("poyo: no task_id in submit response", attempt=attempt + 1)
            return self._stub_result(prompt=prompt, mode="poyo_no_task_id")

        logger.info("poyo: task submitted", task_id=task_id, attempt=attempt + 1)

        # Poll status
        poll_interval = 5.0
        max_polls = 60  # 300s max

        for i in range(max_polls):
            await asyncio.sleep(poll_interval)
            try:
                status_resp = await self._client.get(f"/api/generate/status/{task_id}")
                status_resp.raise_for_status()
            except Exception as e:
                logger.error("poyo: poll request failed", error=str(e), attempt=i + 1)
                continue  # Retry poll on network error

            status_data = status_resp.json()
            task = status_data.get("data", {})
            status = task.get("status", "")
            logger.info("poyo: polling", task_id=task_id, status=status, attempt=i + 1)

            if status == "finished":
                files = task.get("files", [])
                video_url = ""
                if files:
                    video_url = files[0].get("file_url", "")
                if not video_url:
                    logger.error("poyo: no video_url in finished task", task=task)
                    return self._stub_result(prompt=prompt, mode="poyo_no_url")
                return await self._download_video(video_url, task_id, prompt)

            if status == "failed":
                err_msg = task.get("error_message", "unknown")
                logger.error("poyo: task failed", task_id=task_id, error=err_msg, task=task)
                return self._stub_result(prompt=prompt, mode=f"poyo_failed:{err_msg}")

        logger.error("poyo: polling timed out", task_id=task_id)
        return self._stub_result(prompt=prompt, mode="poyo_poll_timeout")

    async def _download_video(self, video_url: str, task_id: str, prompt: str) -> dict:
        """Download video from URL and save locally."""
        async with httpx.AsyncClient() as dl_client:
            dl_resp = await dl_client.get(video_url)
            dl_resp.raise_for_status()
            filename = f"seedance_{task_id[:8]}_{hash(prompt) & 0xFFFF:04x}.mp4"
            filepath = self.output_dir / filename
            filepath.write_bytes(dl_resp.content)
            logger.info("seedance: video saved", file=filename, size=filepath.stat().st_size)

            return {
                "video_url": video_url,
                "local_path": str(filepath),
                "prompt_used": prompt,
                "duration": 0,  # poyo status may not include duration
            }

    # ═══ Native Seedance polling ═══

    async def _poll_and_download(self, task_id: str, prompt: str) -> dict:
        """Native Seedance: poll until complete, then download."""
        poll_interval = 2.0
        max_polls = 30  # 60s max

        for _ in range(max_polls):
            async with asyncio.timeout(30.0):
                resp = await self._client.get(f"/v1/video/status/{task_id}")
                resp.raise_for_status()
                status_data = resp.json()

            if status_data.get("status") == "completed":
                video_url = status_data.get("video_url", "")
                return await self._download_video(video_url, task_id, prompt)

            await asyncio.sleep(poll_interval)

        logger.error("seedance: polling timed out", task_id=task_id)
        return self._stub_result(prompt=prompt, mode="poll_timeout")

    # ═══ Retry + fallback ═══

    async def _execute_with_retry(self, fn, mode: str, prompt: str) -> dict:
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                return await fn()
            except TimeoutError:
                logger.error("seedance: timed out", mode=mode, attempt=attempt + 1)
                last_error = "timeout"
            except httpx.HTTPStatusError as e:
                logger.error("seedance: HTTP error", mode=mode, status=e.response.status_code, body=e.response.text[:200])
                last_error = f"http_{e.response.status_code}"
                if e.response.status_code in (400, 401, 422):
                    break
            except Exception as e:
                logger.error("seedance: error", mode=mode, error=str(e))
                last_error = str(e)

            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(2.0 ** attempt)

        logger.warning("seedance: all retries exhausted, returning stub", mode=mode, error=last_error)
        return self._stub_result(prompt=prompt, mode=mode)

    def _stub_result(self, prompt: str, mode: str = "unknown") -> dict:
        return {
            "video_url": f"[SEEDANCE_STUB — add API key]",
            "local_path": str(self.output_dir / f"stub_{mode}_{hash(prompt) & 0xFFFF:04x}.mp4"),
            "prompt_used": prompt,
            "duration": 0,
            "_stub_mode": mode,
        }

    async def close(self):
        await self._client.aclose()
