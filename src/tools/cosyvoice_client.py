"""CosyVoice TTS client — SiliconFlow API.

Compatible with OpenAI /audio/speech format:
  POST /v1/audio/speech
  Returns binary audio data (mp3/opus/wav/pcm).

Reference: https://docs.siliconflow.cn/cn/api-reference/audio/create-speech
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import httpx
import structlog

from src.config import (
    COSYVOICE_MODEL,
    COSYVOICE_VOICE,
    OUTPUT_DIR,
    SILICONFLOW_API_BASE,
    SILICONFLOW_API_KEY,
)

logger = structlog.get_logger()

BASE_URL = SILICONFLOW_API_BASE or "https://api.siliconflow.cn/v1"
DEFAULT_MODEL = COSYVOICE_MODEL or "FunAudioLLM/CosyVoice2-0.5B"
DEFAULT_VOICE = COSYVOICE_VOICE or "FunAudioLLM/CosyVoice2-0.5B:alex"

# Timeout per TTS call in seconds
TTS_TIMEOUT_SECONDS = 60.0

# Preset voices for different languages / use cases.
# These are SiliconFlow CosyVoice2 built-in speaker IDs.
VOICE_PRESETS = {
    "en": DEFAULT_VOICE,                       # English — warm male (alex)
    "zh": "FunAudioLLM/CosyVoice2-0.5B:diana", # Chinese — warm female (diana)
    "es": DEFAULT_VOICE,
    "fr": DEFAULT_VOICE,
    "de": DEFAULT_VOICE,
}


class CosyVoiceClient:
    """Synthesizes speech via SiliconFlow CosyVoice2 API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        output_dir: Path | None = None,
    ):
        self.api_key = api_key or SILICONFLOW_API_KEY
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.output_dir = output_dir or OUTPUT_DIR / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self.api_key:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "AI-Video-Agent/1.0",
                },
                timeout=60.0,
            )
        else:
            self._client = None

    async def synthesize(
        self,
        text: str,
        voice: str | None = None,
        language: str = "en",
        response_format: str = "mp3",
        speed: float = 1.0,
    ) -> Path:
        """Generate speech audio for a text segment.

        Wrapped in asyncio.timeout() to prevent pipeline hangs.
        Falls back to silent MP3 on timeout or any error.
        """
        if not self.api_key or not self._client:
            logger.warning(
                "cosyvoice: no API key, using silent MP3 fallback "
                "(set SILICONFLOW_API_KEY for real TTS)"
            )
            return self._build_silent_mp3(output_label=f"tts_{language}_fallback")

        selected_voice = voice or VOICE_PRESETS.get(language, VOICE_PRESETS["en"])

        try:
            async with asyncio.timeout(TTS_TIMEOUT_SECONDS):
                resp = await self._client.post(
                    "/audio/speech",
                    json={
                        "model": DEFAULT_MODEL,
                        "input": text,
                        "voice": selected_voice,
                        "response_format": response_format,
                        "speed": speed,
                    },
                )
                resp.raise_for_status()

                text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
                filename = f"cosyvoice_{language}_{text_hash}.{response_format}"
                filepath = self.output_dir / filename
                filepath.write_bytes(resp.content)

                logger.info(
                    "cosyvoice: synthesized",
                    file=filename,
                    chars=len(text),
                    size_bytes=len(resp.content),
                    voice=selected_voice,
                )
                return filepath

        except asyncio.TimeoutError:
            logger.error(
                "cosyvoice: synthesis timed out",
                timeout=TTS_TIMEOUT_SECONDS,
                chars=len(text),
            )
        except Exception as e:
            logger.error(
                "cosyvoice: synthesis failed",
                error=str(e),
                chars=len(text),
            )

        return self._build_silent_mp3(output_label=f"tts_{language}_fallback")

    async def synthesize_script(
        self,
        segments: list[dict],
        language: str = "en",
    ) -> list[dict]:
        """Synthesize all segments of a script."""
        results = []
        for seg in segments:
            path = await self.synthesize(
                text=seg.get("text", ""),
                language=language,
            )
            results.append({
                "start_time": seg.get("start_time", 0.0),
                "end_time": seg.get("end_time", 0.0),
                "file_path": str(path),
                "text": seg.get("text", ""),
            })
        return results

    # ── Fallback helpers ──

    def _build_silent_mp3(self, output_label: str = "tts") -> Path:
        """Produce a silent but valid MP3 file using ffmpeg."""
        import subprocess

        out_dir = self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{output_label}.mp3"
        try:
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "3",
                    "-acodec", "libmp3lame", "-b:a", "64k",
                    str(out_path),
                ],
                capture_output=True, check=True, timeout=15,
            )
        except Exception:
            # Minimal valid MP3 header bytes as last resort
            out_path.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 512)
        return out_path

    async def close(self):
        if self._client:
            await self._client.aclose()
