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
from src.pipeline.model_router import select_model
from src.tools.cosyvoice_client import CosyVoiceClient
from src.tools.llm_client import LLMClient
from src.tools.seedance_client import SeedanceClient

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
Convert the user's simple description into a high-quality, professional
video prompt optimized for Seedance / Happy Horse AI video models.

Requirements:
- Output MUST be in English
- Include: scene, camera angle, lighting, movement, atmosphere
- Be vivid and specific
- Length: STRICTLY 80-150 words, MAX 1000 characters total
- No product showcase / 360 rotation / turntable patterns
- Focus on cinematic, lifestyle, or narrative shots

CONTENT SAFETY (POYO/Seedance content filter rejects prompts that imply):
- Real human faces, especially children, public figures, or recognizable identities
- Brand logos, trademarked characters, or copyrighted IP
- Violence, blood, weapons, gore, war scenes
- Explicit/sexual content, nudity, suggestive poses
- Drugs, alcohol abuse, smoking
- Political figures, religious symbols, cultural sensitive topics
- Medical procedures, surgical content, injuries

If the user prompt is borderline (e.g. mentions a person, child, or product),
REWRITE to remove these elements: replace people with abstract figures or
silhouettes, products with generic stand-ins, brand names with neutral terms.
Default to nature/landscape/abstract/object-focused safe imagery.

HARD CONSTRAINT: video_prompt MUST be <= 1000 characters.
The downstream POYO API rejects prompts > 2500 chars.

Respond in strict JSON:
{
  "video_prompt": "the professional prompt (80-150 words, <= 1000 chars)",
  "scene_description": "1-sentence summary"
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
        # Phase 2 prereq (Oracle review #4): fast_mode is the equivalent of an
        # S1 product-direct shortcut, so use ModelRouter's S1 chain
        # (preferred=seedance-2). Falls back to env POYO_VIDEO_MODEL only if
        # we're not on poyo (native seedance-2.0 path).
        self._video_model = (
            f"poyo-{select_model('s1')}" if self.seedance._is_poyo else "seedance-2.0"
        )

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
        on_stage: "callable | None" = None,
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

        def _stage(s: str) -> None:
            if on_stage is not None:
                try:
                    on_stage(s)
                except Exception:
                    pass

        _stage("llm")
        llm_start = time.perf_counter()
        logger.info("fast_mode: enhancing prompt", user_prompt=user_prompt[:100])

        try:
            # `deepseek-chat` (V3) returns in ~2-5s for this task; the default
            # `deepseek-v4-pro` does extended reasoning and can take 60-150s,
            # which is unacceptable for Fast Mode UX.
            enhanced = await self.llm.invoke_json(
                system_prompt=_PROMPT_ENHANCE_SYSTEM,
                user_message=f"User description:\n{user_prompt}\n\nGenerate a professional video prompt in English.",
                model="deepseek-chat" if DEFAULT_LLM_PROVIDER == "deepseek" else None,
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
        _stage("video")
        logger.info("fast_mode: generating video", duration=duration, enable_tts=enable_tts)

        video_future = self.seedance.text_to_video(
            prompt=video_prompt,
            duration=duration,
            resolution="720p",
            model=select_model("s1") if self.seedance._is_poyo else None,
        )

        tts_future = None
        if enable_tts and scene_description:
            _stage("tts")
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
                from src.tools.error_classifier import classify_error
                structured = classify_error(e, context="fast_mode.video")
                logger.error(
                    "fast_mode: video generation failed",
                    error=str(e),
                    error_code=structured.code.value,
                    recoverable=structured.recoverable,
                )
                raise RuntimeError(f"Video generation failed: {e}") from e
            tts_path = None
            tts_time_ms = 0

        video_time_ms = int((time.perf_counter() - video_start) * 1000)

        # Video failure is fatal
        if isinstance(video_result, BaseException):
            logger.error("fast_mode: video generation failed", error=str(video_result))
            raise RuntimeError(f"Video generation failed: {video_result}") from video_result

        local_path = video_result.get("local_path", "")  # type: ignore[union-attr]
        video_url = video_result.get("video_url", "")  # type: ignore[union-attr]
        is_stub = bool(video_result.get("_stub_mode"))  # type: ignore[union-attr]

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
            stub_mode = video_result.get("_stub_mode", "unknown")  # type: ignore[union-attr]
            logger.warning(
                "fast_mode: video generation failed (stub mode)",
                mode=stub_mode,
                total_time_ms=total_time_ms,
            )
            return {
                "success": False,
                "error": f"Video generation failed: {stub_mode}",
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

        if local_path:
            try:
                from src.tools.poster_extractor import ensure_poster
                ensure_poster(local_path)
            except Exception:
                pass

        logger.info(
            "fast_mode: complete",
            total_time_ms=total_time_ms,
            is_stub=False,
            filename=filename,
        )
        return result
