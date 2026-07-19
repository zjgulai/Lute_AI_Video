"""Retired ElevenLabs/PoYo TTS compatibility client.

Both legacy paid backends are blocked before client construction. No-key
callers retain an explicit local silent-audio fallback for no-media flows.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import structlog

from src.config import OUTPUT_DIR
from src.models.provider_cost import ProviderCostContractError
from src.tools.llm_client import get_request_api_key

logger = structlog.get_logger()

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
    """Expose only the no-key fallback; legacy paid TTS is blocked."""

    def __init__(self, api_key: str | None = None, output_dir: Path | None = None):
        _eleven_key = api_key if api_key is not None else (get_request_api_key("ELEVENLABS_API_KEY") or "")
        _poyo_key = get_request_api_key("POYO_API_KEY") or ""

        if _eleven_key or _poyo_key:
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "legacy TTS provider has no exact provider-cost rule",
            )

        self._is_poyo = False
        logger.warning("tts: no API keys — stub mode only")
        self.api_key = ""
        self.output_dir = output_dir or OUTPUT_DIR / "audio"
        self.output_dir.mkdir(parents=True, exist_ok=True)


    async def synthesize(
        self,
        text: str,
        voice_id: str | None = None,
        language: str = "en",
        stability: float = 0.5,
        similarity_boost: float = 0.75,
    ) -> Path:
        """Generate local fallback audio; configured legacy providers are blocked."""
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
        del text, language
        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "PoYo music and lyrics TTS are outside the frozen provider catalog",
        )

    # ═══ ElevenLabs backend ═══

    async def _elevenlabs_synthesize(
        self,
        text: str,
        voice_id: str | None,
        language: str,
        stability: float,
        similarity_boost: float,
    ) -> Path:
        del text, voice_id, language, stability, similarity_boost
        raise ProviderCostContractError(
            "provider_cost_legacy_path_blocked",
            "ElevenLabs TTS is outside the frozen provider catalog",
        )

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
        """Report that this compatibility client has no catalog authority."""
        return {
            "status": "blocked",
            "reason": "provider_cost_legacy_path_blocked",
            "voice_presets": list(VOICE_PRESETS.keys()),
        }

    async def close(self) -> None:
        """Keep the legacy async cleanup contract without opening a client."""
        return
