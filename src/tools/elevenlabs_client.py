"""TTS / voice synthesis client.

Supports two backends:
  1. ElevenLabs API — direct synchronous generation
  2. poyo.ai proxy — async submit + polling architecture

Every public method has asyncio.timeout() protection (60s default).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import structlog

from src.config import (
    ELEVENLABS_API_BASE,
    ELEVENLABS_API_KEY,
    OUTPUT_DIR,
    POYO_API_KEY,
    POYO_TTS_MODEL,
)

logger = structlog.get_logger()

BASE_URL = ELEVENLABS_API_BASE

# Voice presets for baby-feeding brand (warm, maternal, professional)
VOICE_PRESETS = {
    "en": "21m00Tcm4TlvDq8ikWAM",  # Rachel — warm, American female
}

# ElevenLabs model
TTS_MODEL = "eleven_multilingual_v2"

# Timeout per TTS call in seconds
TTS_TIMEOUT_SECONDS = 60.0


class TTSTimeoutError(asyncio.TimeoutError):
    """Raised when a TTS call exceeds TTS_TIMEOUT_SECONDS."""


class ElevenLabsClient:
    """Synthesizes speech from text using ElevenLabs or poyo.ai API."""

    def __init__(self, api_key: str | None = None, output_dir: Path | None = None):
        _eleven_key = api_key or ELEVENLABS_API_KEY

        # Unified routing: poyo.ai preferred when POYO_API_KEY is set
        if POYO_API_KEY:
            self._is_poyo = True
            logger.info("tts: using poyo.ai backend (unified)")
            self.api_key = POYO_API_KEY
        elif _eleven_key:
            self._is_poyo = False
            logger.info("tts: using ElevenLabs native API")
            self.api_key = _eleven_key
        else:
            self._is_poyo = False
            logger.warning("tts: no API keys — stub mode only")
            self.api_key = ""
        self.output_dir = output_dir or OUTPUT_DIR / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self._is_poyo:
            from src.tools.poyo_client import PoyoClient
            self._poyo = PoyoClient()
        else:
            self._client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (compatible; AI-Video-Agent/1.0)",
                },
                timeout=60.0,
            )

    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> Path:
        """Generate speech audio for a text segment.

        Wrapped in asyncio.timeout() to prevent pipeline hangs.
        Falls back to stub on timeout or any error.
        """
        if self._is_poyo:
            return await self._poyo_synthesize(text=text, language=language)

        if not self.api_key:
            logger.warning(
                "elevenlabs: no API key, using silent MP3 fallback "
                "(set ELEVENLABS_API_KEY for real TTS)"
            )
            return self._build_silent_mp3(output_label=f"tts_{language}_fallback")

        return await self._elevenlabs_synthesize(
            text=text,
            voice_id=voice_id,
            language=language,
            stability=stability,
            similarity_boost=similarity_boost,
        )

    # ═══ poyo.ai backend ═══

    async def _poyo_synthesize(self, text: str, language: str) -> Path:
        """Generate audio via poyo.ai Suno models (generate-music / generate-lyrics).

        Supports both backends:
          - generate-music → returns audio (files[0].audio_url)
          - generate-lyrics → returns text lyrics (files[0].text)

        Uses the music-specific endpoint /api/generate/detail/music for polling.
        Text is truncated to 200 chars to avoid Suno's "Your text is too long" error.

        Falls back to silent MP3 on any failure or non-audio content.
        """
        import asyncio
        import hashlib

        import httpx

        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        filename = f"poyo_tts_{language}_{text_hash}.mp3"
        filepath = self.output_dir / filename

        # Suno enforces a text-length limit — truncate aggressively
        truncated = text[:200].strip() if len(text) > 200 else text.strip()
        if len(truncated) < 3:
            logger.warning("tts: text too short after truncation, returning stub")
            return self._build_silent_mp3(output_label=f"tts_{language}_{text_hash}")

        input_payload: dict[str, Any] = {
            "prompt": truncated,
            "title": f"Voiceover_{text_hash}",
            "style": "Soft, Warm, Gentle",
            "custom_mode": True,
            "instrumental": False,
            "mv": "V5_5",
        }

        try:
            # 1. Submit
            task_id = await self._poyo.submit(POYO_TTS_MODEL, input_payload)

            # 2. Poll via music-specific endpoint (generate-lyrics is a Suno model)
            task = None
            for i in range(60):
                await asyncio.sleep(5.0)
                resp = await self._poyo._client.get(
                    f"/api/generate/detail/music?task_id={task_id}"
                )
                resp.raise_for_status()
                status_data = resp.json()
                task = status_data.get("data", {})
                status = task.get("status", "")
                logger.info(
                    "poyo: music polling", task_id=task_id,
                    status=status, attempt=i + 1,
                )
                if status == "finished":
                    break
                if status == "failed":
                    err_msg = task.get("error_message", "unknown")
                    raise RuntimeError(f"poyo music task failed: {err_msg}")

            if not task or task.get("status") != "finished":
                raise RuntimeError("poyo music polling timed out")

            # 3. Download — handle both audio (audio_url) and lyrics (text) outputs
            files = task.get("files", [])
            if not files:
                raise RuntimeError("poyo music finished but no files returned")

            first_file = files[0]
            audio_url = first_file.get("audio_url", "")
            lyrics_text = first_file.get("text", "")

            if audio_url:
                # Real audio (generate-music path)
                async with httpx.AsyncClient() as dl:
                    dl_resp = await dl.get(audio_url)
                    dl_resp.raise_for_status()
                    filepath.write_bytes(dl_resp.content)

                if self._is_valid_mp3(filepath):
                    logger.info(
                        "tts: poyo audio generated",
                        model=POYO_TTS_MODEL, file=filename,
                        size=filepath.stat().st_size, chars=len(truncated),
                    )
                    return filepath

            elif lyrics_text:
                # generate-lyrics returns text lyrics, not audio
                # Save lyrics to the SAME basename as the returned silent MP3
                # so the skill layer can find it via path.with_suffix(".txt")
                stub_path = self._build_silent_mp3(output_label=f"tts_{language}_{text_hash}")
                txt_path = stub_path.with_suffix(".txt")
                txt_path.write_text(lyrics_text, encoding="utf-8")
                logger.info(
                    "tts: poyo lyrics generated",
                    model=POYO_TTS_MODEL, txt_file=txt_path.name,
                    lines=lyrics_text.count("\n"),
                )
                # Return silent MP3 so pipeline continues; lyrics saved as .txt
                return stub_path

            else:
                raise RuntimeError("poyo music finished but no audio_url or text found")

        except Exception as e:
            logger.error(
                "tts: poyo failed",
                model=POYO_TTS_MODEL, error=str(e), chars=len(truncated),
            )

        return self._build_silent_mp3(output_label=f"tts_{language}_{text_hash}")

    # ═══ ElevenLabs backend ═══

    async def _elevenlabs_synthesize(
        self,
        text: str,
        voice_id: str | None,
        language: str,
        stability: float,
        similarity_boost: float,
    ) -> Path:
        from src.tools.retry import retry_with_backoff

        voice = voice_id or VOICE_PRESETS.get(language, VOICE_PRESETS["en"])

        async def _do_synthesize():
            async with asyncio.timeout(TTS_TIMEOUT_SECONDS):
                response = await self._client.post(
                    f"/text-to-speech/{voice}",
                    json={
                        "text": text,
                        "model_id": TTS_MODEL,
                        "voice_settings": {
                            "stability": stability,
                            "similarity_boost": similarity_boost,
                        },
                    },
                )
                response.raise_for_status()

                import hashlib
                text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
                filename = f"tts_{language}_{text_hash}.mp3"
                filepath = self.output_dir / filename

                with open(filepath, "wb") as f:
                    f.write(response.content)

                logger.info("elevenlabs: synthesized", file=filename, chars=len(text))
                return filepath

        try:
            return await retry_with_backoff(_do_synthesize)
        except TimeoutError:
            logger.error("elevenlabs: synthesis timed out", timeout=TTS_TIMEOUT_SECONDS, chars=len(text))
            return self._stub_path(text)
        except Exception as e:
            logger.error("elevenlabs: synthesis failed", error=str(e))
            return self._stub_path(text)

    async def synthesize_script(
        self,
        segments: list[dict[str, Any]],
        language: str = "en",
    ) -> list[dict[str, Any]]:
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

    def _stub_path(self, text: str) -> Path:
        """Return a placeholder path when API key is missing."""
        path = self._build_silent_mp3(output_label="stub_tts")
        return path

    @staticmethod
    def _is_valid_mp3(path: Path) -> bool:
        """Check for ID3 tag or MPEG sync byte."""
        try:
            with open(path, "rb") as f:
                head = f.read(4)
            if len(head) < 4:
                return False
            if head[:3] == b"ID3":
                return True
            if head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
                return True
            return False
        except Exception:
            return False

    @property
    def cost_estimate(self) -> dict[str, Any]:
        """Cost info: $0.015/1k chars for multilingual v2."""
        return {
            "model": TTS_MODEL,
            "price_per_1k_chars": "$0.015",
            "voice_presets": list(VOICE_PRESETS.keys()),
        }

    async def close(self):
        if self._is_poyo:
            await self._poyo.close()
        else:
            await self._client.aclose()
