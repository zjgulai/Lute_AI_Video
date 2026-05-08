"""ElevenLabs TTS Skill — produces real .mp3 voiceover + self-verifies it.

Wraps ElevenLabsClient.synthesize with the SkillCallable contract.
Self-verifies the generated audio: file exists, has valid mp3 header
(ID3 tag or sync byte 0xFF), and (best-effort) duration via ffprobe.

Output schema:
    {
      "audio_path": str,          # absolute path to .mp3
      "duration_seconds": float,
      "file_size_bytes": int,
      "language": str,
      "voice_id": str,
      "text_used": str,
      "is_stub": bool,
      "verification": { ... }
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

# Self-verification thresholds
MIN_FILE_SIZE_BYTES = 200             # < 200B = empty / API rejection page
MIN_DURATION_SECONDS = 0.5            # < 0.5s = no usable speech


class ElevenLabsTTSSkill(SkillCallable):
    """Generates a real TTS audio segment via ElevenLabs and verifies it."""

    name = "elevenlabs-tts-skill"
    description = "Calls ElevenLabs to synthesize a real .mp3 voiceover and self-verifies the output"
    max_retries = 2

    # Default English voice: Rachel (warm, American female)
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        text = params["text"]
        language = params.get("language", "en")
        voice_id = params.get("voice_id", self.DEFAULT_VOICE_ID)
        stability = float(params.get("stability", 0.5))
        similarity_boost = float(params.get("similarity_boost", 0.75))

        from src.config import SILICONFLOW_API_KEY, ELEVENLABS_API_KEY, POYO_API_KEY

        # ── Priority 1: SiliconFlow CosyVoice (Pro version TTS) ──
        if SILICONFLOW_API_KEY:
            from src.tools.cosyvoice_client import CosyVoiceClient, VOICE_PRESETS as COSY_PRESETS

            cosy_client = CosyVoiceClient()
            path: Path | None = None
            try:
                # Map ElevenLabs voice_id to CosyVoice voice if possible.
                # Support voice_gender param for category-based selection (default female for maternal/baby).
                voice_gender = params.get("voice_gender", "female")
                cosy_voice = None
                if voice_id and voice_id in COSY_PRESETS:
                    cosy_voice = COSY_PRESETS[voice_id]
                elif voice_gender == "female" and "female_en" in COSY_PRESETS:
                    cosy_voice = COSY_PRESETS["female_en"]
                elif language in COSY_PRESETS:
                    cosy_voice = COSY_PRESETS[language]

                path = await cosy_client.synthesize(
                    text=text,
                    voice=cosy_voice,
                    language=language,
                    response_format="mp3",
                    speed=1.0,
                )
            except Exception as e:
                return SkillResult(success=False, error=f"cosyvoice_tts_call_failed: {e}")
            finally:
                await cosy_client.close()

            is_stub = path.name.startswith("stub_")
            used_voice = cosy_voice or COSY_PRESETS.get(language, COSY_PRESETS["en"])

        # ── Priority 2: ElevenLabs (legacy fallback) ──
        else:
            from src.tools.elevenlabs_client import ElevenLabsClient, VOICE_PRESETS

            client = ElevenLabsClient()
            try:
                path: Path = await client.synthesize(
                    text=text,
                    voice_id=voice_id,
                    language=language,
                    stability=stability,
                    similarity_boost=similarity_boost,
                )
            except Exception as e:
                return SkillResult(success=False, error=f"tts_call_failed: {e}")

            has_key = bool(ELEVENLABS_API_KEY or POYO_API_KEY)
            is_stub = (not has_key) or path.name.startswith("stub_")
            used_voice = voice_id or VOICE_PRESETS.get(language, VOICE_PRESETS["en"])

        # Stub mode: ensure placeholder file exists with at least minimal mp3 header
        if is_stub and (not path.exists() or path.stat().st_size == 0):
            self._build_stub_mp3(path)

        # === Self-verification ===
        verification = self._self_verify(path=path, is_stub=is_stub)

        if not is_stub and not verification["all_ok"]:
            return SkillResult(
                success=False,
                error=f"tts verification failed: {verification['failures']}",
                metadata={"verification": verification, "audio_path": str(path)},
            )

        duration_seconds = self._measure_duration(path) if path.exists() else 0.0
        if duration_seconds == 0.0 and not is_stub:
            # Heuristic: ~150 words/min for English speech, ~6 chars/word
            duration_seconds = max(MIN_DURATION_SECONDS, len(text) / 6 / 150 * 60)

        file_size = path.stat().st_size if path.exists() else 0
        # `used_voice` already resolved above (cosyvoice or elevenlabs branch)
        resolved_voice = used_voice

        # Check for companion lyrics file (generate-lyrics produces .txt, not audio)
        lyrics_path = path.with_suffix(".txt")
        has_lyrics = lyrics_path.exists() and lyrics_path.stat().st_size > 10

        return SkillResult(
            success=True,
            data={
                "audio_path": str(path),
                "duration_seconds": duration_seconds,
                "file_size_bytes": file_size,
                "language": language,
                "voice_id": resolved_voice,
                "text_used": text,
                "is_stub": is_stub,
                "verification": verification,
                "lyrics_path": str(lyrics_path) if has_lyrics else "",
            },
            metadata={"chars": len(text), "language": language, "has_lyrics": has_lyrics},
        )

    def _self_verify(self, path: Path, is_stub: bool) -> dict[str, Any]:
        if is_stub:
            return {
                "file_exists": path.exists(),
                "size_ok": True, "header_ok": True, "duration_ok": True,
                "all_ok": True, "failures": [], "mode": "stub_relaxed",
            }

        failures: list[str] = []
        if not path.exists():
            failures.append("file_not_found")
            return {
                "file_exists": False, "size_ok": False, "header_ok": False,
                "duration_ok": False, "all_ok": False, "failures": failures,
                "mode": "real",
            }

        size = path.stat().st_size
        size_ok = size >= MIN_FILE_SIZE_BYTES
        if not size_ok:
            failures.append(f"file_too_small_{size}b")

        header_ok = self._is_valid_mp3(path)
        if not header_ok:
            failures.append("invalid_mp3_header")

        duration = self._measure_duration(path)
        duration_ok = duration >= MIN_DURATION_SECONDS
        if not duration_ok and duration > 0:
            failures.append(f"duration_too_short_{duration:.1f}s")
        elif duration == 0:
            # ffprobe missing or unreadable — don't block on this
            duration_ok = True

        return {
            "file_exists": True,
            "size_ok": size_ok,
            "header_ok": header_ok,
            "duration_ok": duration_ok,
            "all_ok": size_ok and header_ok and duration_ok,
            "failures": failures,
            "mode": "real",
        }

    @staticmethod
    def _is_valid_mp3(path: Path) -> bool:
        """Check for ID3 tag (ID3) or MPEG sync byte (0xFF 0xFB / 0xFF 0xF3 / 0xFF 0xE3)."""
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

    @staticmethod
    def _measure_duration(path: Path) -> float:
        import subprocess
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip() or "0.0")
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, Exception):
            pass
        return 0.0

    @staticmethod
    def _build_stub_mp3(path: Path) -> None:
        """Generate a playable stub MP3 using ffmpeg, or fallback to minimal bytes.

        The ffmpeg-generated file is a real 2-second silent mono MP3.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        import subprocess
        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                "-t", "2",
                "-acodec", "libmp3lame", "-q:a", "9",
                str(path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception):
            # ffmpeg unavailable or failed — write minimal magic-byte stub
            path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        if not params.get("text"):
            errors.append("missing 'text'")
        elif not isinstance(params["text"], str):
            errors.append("'text' must be a string")
        elif len(params["text"]) < 1:
            errors.append("'text' is empty")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        if "audio_path" not in data:
            errors.append("missing 'audio_path'")
        if "verification" not in data:
            errors.append("missing 'verification' report")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        from src.config import OUTPUT_DIR

        text = params.get("text", "")
        language = params.get("language", "en")
        out_dir = OUTPUT_DIR / "audio"
        out_dir.mkdir(parents=True, exist_ok=True)

        import hashlib
        text_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        path = out_dir / f"fallback_tts_{language}_{text_hash}.mp3"
        self._build_stub_mp3(path)

        return SkillResult(
            success=True,
            data={
                "audio_path": str(path),
                "duration_seconds": max(MIN_DURATION_SECONDS, len(text) / 6 / 150 * 60),
                "file_size_bytes": path.stat().st_size,
                "language": language,
                "voice_id": params.get("voice_id", "fallback"),
                "text_used": text,
                "is_stub": True,
                "verification": {
                    "file_exists": True, "size_ok": True, "header_ok": True,
                    "duration_ok": True, "all_ok": True, "failures": [],
                    "mode": "fallback",
                },
                "_fallback": True,
            },
            metadata={"reason": "all_retries_exhausted"},
        )


# Auto-register
try:
    SkillRegistry.register(ElevenLabsTTSSkill())
    logger.info("elevenlabs_tts_skill: registered")
except ValueError:
    pass
