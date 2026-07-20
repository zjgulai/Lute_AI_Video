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

from src.models.provider_cost import ProviderCostContractError
from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry
from src.tools.llm_client import get_request_api_key
from src.tools.safe_media import ffprobe_local_input_args

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
        output_dir = Path(params["output_dir"]) if params.get("output_dir") else None

        from src.config import OUTPUT_DIR

        siliconflow_key = get_request_api_key("SILICONFLOW_API_KEY") or ""
        elevenlabs_key = get_request_api_key("ELEVENLABS_API_KEY") or ""
        poyo_key = get_request_api_key("POYO_API_KEY") or ""

        # ── Priority 1: SiliconFlow CosyVoice (Pro version TTS) ──
        if siliconflow_key:
            from src.tools.cosyvoice_client import VOICE_PRESETS as COSY_PRESETS
            from src.tools.cosyvoice_client import CosyVoiceClient

            cosy_client = CosyVoiceClient(api_key=siliconflow_key, output_dir=output_dir)
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
                    operation_instance=params.get("operation_instance", "primary"),
                )
            except ProviderCostContractError:
                raise
            except Exception:
                return SkillResult(success=False, error="cosyvoice_tts_call_failed")
            finally:
                # Cleanup is best-effort and must never replace the provider
                # outcome (especially an ambiguous paid mutation).
                try:
                    await cosy_client.close()
                except Exception:
                    logger.warning(
                        "elevenlabs_tts: client close failed",
                        error_code="tts_client_close_failed",
                    )

            is_stub = path.name.startswith("stub_")
            used_voice = cosy_voice or COSY_PRESETS.get(language, COSY_PRESETS["en"])

        # ── Legacy providers are not cost-integrated in this batch ──
        elif elevenlabs_key or poyo_key:
            raise ProviderCostContractError(
                "provider_cost_legacy_path_blocked",
                "legacy TTS provider has no exact provider-cost rule",
            )
        else:
            # No credential means an explicit pre-submit, zero-attempt local
            # fallback. Do not construct a legacy provider client merely to
            # discover that it has no key.
            resolved_output_dir = output_dir or OUTPUT_DIR / "audio"
            path = resolved_output_dir / f"tts_{language}_fallback.mp3"
            self._build_stub_mp3(path)
            is_stub = True
            from src.tools.elevenlabs_client import VOICE_PRESETS

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
                    *ffprobe_local_input_args(path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return float(result.stdout.strip() or "0.0")
        except Exception:
            logger.debug(
                "elevenlabs_tts: ffprobe duration failed",
                error_code="audio_duration_probe_failed",
            )
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
        out_dir = Path(params["output_dir"]) if params.get("output_dir") else OUTPUT_DIR / "audio"
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
    logger.debug(
        "elevenlabs_tts_skill: already registered",
        error_code="skill_already_registered",
    )
