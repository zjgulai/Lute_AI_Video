"""Fast Mode Service — direct text-to-video generation without pipeline.

Used for testing the LLM + video generation matrix capability.
Completely independent from pipelines, scenarios, and LangGraph.

Flow:
  user_prompt → LLM enhancement → Seedance video → optional TTS → result
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import structlog

from src.config import DEFAULT_LLM_PROVIDER, OUTPUT_DIR
from src.tools.llm_client import LLMClient
from src.tools.seedance_client import SeedanceClient
from src.tools.cosyvoice_client import CosyVoiceClient

logger = structlog.get_logger()

FAST_MODE_OUTPUT_DIR = OUTPUT_DIR / "fast_mode"
FAST_MODE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Module-level singleton instance — avoids rebuilding clients per request
_fast_mode_service_instance: FastModeService | None = None


def get_fast_mode_service() -> FastModeService:
    """Return the singleton FastModeService instance."""
    global _fast_mode_service_instance
    if _fast_mode_service_instance is None:
        _fast_mode_service_instance = FastModeService()
    return _fast_mode_service_instance

# System prompt for converting user's simple description into a professional
# Seedance video generation prompt.
_PROMPT_ENHANCE_SYSTEM = """You are an expert AI video generation prompt engineer.
Your task is to convert the user's simple description into a high-quality,
professional video generation prompt optimized for Seedance / Happy Horse
AI video models.

Requirements:
- Output MUST be in English (the video model requires English prompts)
- Include: scene description, camera angles, lighting, movement, atmosphere
- Be vivid and specific — describe exactly what the viewer sees
- Length: STRICTLY 200-400 words, MAX 1800 characters total
- Do NOT include any product showcase / 360 rotation / turntable patterns
- Focus on cinematic, lifestyle, or narrative shots

HARD CONSTRAINT: The video_prompt field MUST be a string of <= 1800 characters.
The downstream POYO/Happy Horse API rejects prompts > 2500 chars; we leave a 700-char safety margin.

Respond in strict JSON format:
{
  "video_prompt": "the full professional prompt (200-400 words, <= 1800 chars)...",
  "scene_description": "a 1-sentence summary of the scene"
}
"""


class FastModeService:
    """Fast Mode: text → LLM prompt → video (10-15s).

    Completely independent from pipelines, scenarios, and LangGraph.
    """

    def __init__(self):
        self.llm = LLMClient()
        self.seedance = SeedanceClient(output_dir=FAST_MODE_OUTPUT_DIR)
        self.cosyvoice = CosyVoiceClient(output_dir=FAST_MODE_OUTPUT_DIR / "audio")
        # P2: Cache model metadata once at init — avoids per-request reflection
        self._llm_model = self._resolve_llm_model()
        self._video_model = "poyo-happy-horse" if self.seedance._is_poyo else "seedance-2.0"

    def _resolve_llm_model(self) -> str:
        """Resolve the actual LLM model name once at initialization."""
        try:
            client = self.llm._get_client()
            # langchain clients expose model name via different attrs
            for attr in ("model_name", "model", "model_id"):
                if hasattr(client, attr):
                    return str(getattr(client, attr))
        except Exception:
            pass
        return DEFAULT_LLM_PROVIDER

    async def generate(
        self,
        user_prompt: str,
        duration: int = 15,
        enable_tts: bool = False,
    ) -> dict[str, Any]:
        """Generate a short video from simple text input.

        Args:
            user_prompt: User's simple description (can be any language).
            duration: Video duration in seconds (10 or 15).
            enable_tts: Whether to generate voiceover with CosyVoice.

        Returns:
            Dict with video_path, debug info, and timing.
        """
        total_start = time.perf_counter()
        duration = max(10, min(15, duration))

        # ── Step 1: LLM prompt enhancement ──
        llm_start = time.perf_counter()
        logger.info("fast_mode: enhancing prompt", user_prompt=user_prompt[:100])

        try:
            enhanced = await self.llm.invoke_json(
                system_prompt=_PROMPT_ENHANCE_SYSTEM,
                user_message=f"User description:\n{user_prompt}\n\nGenerate a professional video prompt in English.",
            )
            video_prompt = enhanced.get("video_prompt", "")
            scene_description = enhanced.get("scene_description", "")
        except Exception as e:
            logger.error("fast_mode: LLM enhancement failed, using raw prompt", error=str(e))
            video_prompt = user_prompt
            scene_description = user_prompt

        llm_time_ms = int((time.perf_counter() - llm_start) * 1000)
        logger.info(
            "fast_mode: prompt enhanced",
            llm_time_ms=llm_time_ms,
            prompt_length=len(video_prompt),
        )

        # ── Step 2: Video + optional TTS in parallel ──
        video_start = time.perf_counter()
        logger.info("fast_mode: generating video", duration=duration, enable_tts=enable_tts)

        video_future = self.seedance.text_to_video(
            prompt=video_prompt,
            duration=duration,
            resolution="720p",
        )

        tts_future = None
        if enable_tts and scene_description:
            tts_future = self.cosyvoice.synthesize(
                text=scene_description,
                language="en",
            )

        if tts_future is not None:
            results = await asyncio.gather(video_future, tts_future, return_exceptions=True)
            video_result = results[0]
            tts_result = results[1]

            # TTS failure is non-fatal — log and continue
            tts_path = None
            tts_time_ms = 0
            if isinstance(tts_result, Exception):
                logger.warning("fast_mode: TTS generation failed", error=str(tts_result))
            elif tts_result:
                tts_path = str(tts_result)
                tts_time_ms = int((time.perf_counter() - video_start) * 1000)
                logger.info("fast_mode: TTS generated", tts_path=tts_path)
        else:
            try:
                video_result = await video_future
            except Exception as e:
                logger.error("fast_mode: video generation failed", error=str(e))
                raise RuntimeError(f"Video generation failed: {e}") from e
            tts_path = None
            tts_time_ms = 0

        video_time_ms = int((time.perf_counter() - video_start) * 1000)

        # Video failure is fatal
        if isinstance(video_result, Exception):
            logger.error("fast_mode: video generation failed", error=str(video_result))
            raise RuntimeError(f"Video generation failed: {video_result}") from video_result

        local_path = video_result.get("local_path", "")
        video_url = video_result.get("video_url", "")
        is_stub = bool(video_result.get("_stub_mode"))

        # Get file info
        file_size = 0
        if local_path and Path(local_path).exists():
            file_size = Path(local_path).stat().st_size

        logger.info(
            "fast_mode: video generated",
            video_time_ms=video_time_ms,
            is_stub=is_stub,
            file_size=file_size,
        )

        # ── Step 3: Build result ──
        total_time_ms = int((time.perf_counter() - total_start) * 1000)

        # Extract filename for media serving
        filename = Path(local_path).name if local_path else ""

        model_info = {
            "llm": DEFAULT_LLM_PROVIDER,
            "llm_model": self._llm_model,
            "video": self._video_model,
            "tts": "cosyvoice2" if enable_tts else None,
        }

        # If stub mode (video generation failed), mark as failure and do not
        # return a non-existent filename that would cause a 404 on media fetch.
        if is_stub:
            logger.warning(
                "fast_mode: video generation failed (stub mode)",
                mode=video_result.get("_stub_mode", "unknown"),
                total_time_ms=total_time_ms,
            )
            return {
                "success": False,
                "error": f"Video generation failed: {video_result.get('_stub_mode', 'unknown')}",
                "video_path": "",
                "video_url": "",
                "filename": "",
                "llm_prompt": video_prompt,
                "scene_description": scene_description,
                "user_prompt": user_prompt,
                "duration_seconds": duration,
                "file_size_bytes": 0,
                "generation_time_ms": total_time_ms,
                "timing": {
                    "llm_ms": llm_time_ms,
                    "video_ms": video_time_ms,
                    "tts_ms": tts_time_ms,
                },
                "model_info": model_info,
                "is_stub": True,
                "tts_path": None,
            }

        result = {
            "success": True,
            "video_path": local_path,
            "video_url": video_url,
            "filename": filename,
            "llm_prompt": video_prompt,
            "scene_description": scene_description,
            "user_prompt": user_prompt,
            "duration_seconds": duration,
            "file_size_bytes": file_size,
            "generation_time_ms": total_time_ms,
            "timing": {
                "llm_ms": llm_time_ms,
                "video_ms": video_time_ms,
                "tts_ms": tts_time_ms,
            },
            "model_info": model_info,
            "is_stub": False,
            "tts_path": tts_path,
        }

        logger.info(
            "fast_mode: complete",
            total_time_ms=total_time_ms,
            is_stub=False,
            filename=filename,
        )
        return result
