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
from pathlib import Path
from typing import Any

import httpx
import structlog

from src.config import POYO_API_KEY, POYO_API_BASE_URL
from src.tools.llm_client import get_request_api_key

logger = structlog.get_logger()

DEFAULT_POLL_INTERVAL = 5.0
DEFAULT_MAX_POLLS = 60  # 5s * 60 = 300s max


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
    ):
        self.api_key = api_key or get_request_api_key("POYO_API_KEY") or POYO_API_KEY
        self.base_url = (base_url or POYO_API_BASE_URL).rstrip("/")
        if not self.api_key:
            raise RuntimeError("PoyoClient requires POYO_API_KEY")
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

    async def submit(
        self,
        model: str,
        input_payload: dict[str, Any],
    ) -> str:
        """Submit a generation task and return task_id.

        Raises:
            httpx.HTTPStatusError: on non-2xx from submit endpoint.
            RuntimeError: if submit response indicates failure.
        """
        # Apply content-moderation sanitization to any prompt-bearing key.
        # POYO rejects common maternal/baby terms ("breast pump", "lactation",
        # "吸奶器") with a 'content does not comply' error; sanitizer maps them
        # to neutral product-equivalent phrases that preserve visual intent.
        from src.tools.poyo_safety import sanitize_for_poyo

        for key in ("prompt",):
            val = input_payload.get(key)
            if isinstance(val, str) and val:
                cleaned, subs = sanitize_for_poyo(val)
                if subs:
                    logger.info(
                        "poyo_safety: prompt sanitized",
                        key=key,
                        substitutions=subs,
                    )
                    input_payload = {**input_payload, key: cleaned}

        body = {"model": model, "input": input_payload}
        logger.info("poyo: submitting", model=model, keys=list(input_payload.keys()))
        import json as _json
        resp = await self._client.post(
            "/api/generate/submit",
            content=_json.dumps(body).encode(),
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            raise RuntimeError(f"poyo submit failed: {data}")

        task_id = data.get("data", {}).get("task_id", "")
        if not task_id:
            raise RuntimeError(f"poyo submit missing task_id: {data}")

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
            resp = await self._client.get(f"/api/generate/status/{task_id}")
            resp.raise_for_status()
            status_data = resp.json()

            task = status_data.get("data", {})
            status = task.get("status", "")
            logger.info("poyo: polling", task_id=task_id, status=status, attempt=i + 1)

            if status == "finished":
                return task
            if status == "failed":
                err_msg = task.get("error_message", "unknown")
                raise RuntimeError(f"poyo task failed: {err_msg}")

        raise RuntimeError(f"poyo polling timed out after {max_polls * poll_interval}s")

    async def download(
        self,
        task: dict[str, Any],
        output_path: Path,
    ) -> Path:
        """Download the first file_url from a finished task.

        Returns:
            Path to the saved file.

        Raises:
            RuntimeError: if no file_url found.
        """
        files = task.get("files", [])
        if not files:
            raise RuntimeError("poyo task finished but no files returned")

        file_url = files[0].get("file_url", "") or files[0].get("audio_url", "")
        if not file_url:
            raise RuntimeError("poyo task finished but file_url is empty")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient() as dl:
            dl_resp = await dl.get(file_url)
            dl_resp.raise_for_status()
            output_path.write_bytes(dl_resp.content)

        logger.info("poyo: downloaded", file=output_path.name, size=output_path.stat().st_size)
        return output_path

    async def submit_poll_download(
        self,
        model: str,
        input_payload: dict[str, Any],
        output_path: Path,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        max_polls: int = DEFAULT_MAX_POLLS,
    ) -> dict[str, Any]:
        """One-shot: submit → poll → download.

        Returns:
            {"task_id": str, "file_url": str, "local_path": str, "task": dict}
        """
        task_id = await self.submit(model, input_payload)
        task = await self.poll(task_id, poll_interval, max_polls)
        local_path = await self.download(task, output_path)
        files = task.get("files", [])
        file_url = files[0].get("file_url", "") if files else ""
        from src.tools.cost_tracker import track
        track(api="poyo_video", units=1)
        return {
            "task_id": task_id,
            "file_url": file_url,
            "local_path": str(local_path),
            "task": task,
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
        except httpx.ConnectError as e:
            return {"reachable": False, "status_code": None, "detail": f"Connection failed: {e}"}
        except httpx.TimeoutException as e:
            return {"reachable": False, "status_code": None, "detail": f"Timeout: {e}"}
        except Exception as e:
            return {"reachable": False, "status_code": None, "detail": f"Error: {e}"}

    async def close(self) -> None:
        await self._client.aclose()
