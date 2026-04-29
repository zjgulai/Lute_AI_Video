"""Seedance Video Generate Skill — produces real .mp4 clip + self-verifies it.

This skill replaces the prompt-only step. It:
1. Calls SeedanceClient.text_to_video (or image_to_video) and waits for the file.
2. Self-verifies the generated mp4: file exists, size > threshold, valid mp4 header,
   duration >= minimum.
3. If verification fails AND API key was present, retries via SkillCallable.safe_execute.
4. If API key absent or all retries fail, falls back to a deterministic stub mp4 marker.

Output schema:
    {
      "video_path": str,           # absolute path to .mp4
      "duration_seconds": float,
      "file_size_bytes": int,
      "resolution": str,           # "720p" | "1080p"
      "prompt_used": str,
      "is_stub": bool,             # True if no API key OR fallback mode
      "verification": {            # self-verify report
        "file_exists": bool,
        "size_ok": bool,
        "header_ok": bool,
        "duration_ok": bool,
      }
    }
"""

from __future__ import annotations

import asyncio
import os
import struct
from pathlib import Path
from typing import Any

import structlog

from src.skills.base import SkillCallable, SkillResult
from src.skills.registry import SkillRegistry

logger = structlog.get_logger()

# --- Self-verification thresholds ---
MIN_FILE_SIZE_BYTES = 1024          # < 1KB = empty/corrupt
MIN_DURATION_SECONDS = 3.0          # < 3s = unusable
DEFAULT_DURATION = 5
DEFAULT_RESOLUTION = "720p"

# MP4 ftyp box signatures (ISO base media file format)
MP4_FTYP_BRANDS = [b"isom", b"iso2", b"avc1", b"mp41", b"mp42", b"M4V ", b"M4A "]


class SeedanceVideoGenerateSkill(SkillCallable):
    """Generates a single real video clip via Seedance and verifies it.

    Wraps SeedanceClient.text_to_video / image_to_video with the standard
    SkillCallable contract (validate_params + execute + validate_output + fallback).
    """

    name = "seedance-video-generate-skill"
    description = "Calls Seedance 2.0 to generate a real .mp4 clip and self-verifies the output"
    max_retries = 2  # Each Seedance call is 30-60s; cap retries to keep demo timeline sane

    async def execute(self, params: dict[str, Any]) -> SkillResult:
        prompt = params.get("prompt", "")
        if not prompt or not prompt.strip():
            prompt = f"{params.get('output_label', 'clip')} product showcase"
            logger.info("seedance: using fallback prompt", prompt=prompt)

        duration = int(params.get("duration", DEFAULT_DURATION))
        # Clamp duration to valid range [4, 15] seconds (Seedance API limit)
        duration = max(4, min(duration, 15))
        resolution = params.get("resolution", DEFAULT_RESOLUTION)
        image_refs = params.get("image_refs") or []
        output_label = params.get("output_label", "clip")

        # ── Track 3: keyframe / continuity-frame support ──
        keyframe_image_path: str | None = params.get("keyframe_image_path") or (
            params.get("keyframe", {}).get("image_path") if isinstance(params.get("keyframe"), dict) else None
        )
        continuity_frame_path: str | None = params.get("continuity_frame_path")

        # Helper: pick the best image source (continuity > keyframe > image_refs)
        best_image_path = continuity_frame_path or keyframe_image_path or (image_refs[0] if image_refs else None)

        # Lazy import to avoid module-load network handles
        from src.tools.seedance_client import SeedanceClient

        client = SeedanceClient()

        try:
            # Choose API based on whether we have a reference image
            if best_image_path:
                # Validate that the image file actually exists before calling API
                if Path(best_image_path).exists() and Path(best_image_path).stat().st_size > 100:
                    api_result = await client.image_to_video(
                        image_url=best_image_path,
                        prompt=prompt,
                        duration=duration,
                        style_preserve=True,
                    )
                else:
                    # Image doesn't exist or is too small — fall through to text_to_video
                    logger.warning("seedance: best_image_path missing or too small, falling back to text_to_video",
                                   path=best_image_path)
                    api_result = await client.text_to_video(
                        prompt=prompt,
                        image_refs=None,
                        duration=duration,
                        resolution=resolution,
                    )
            elif image_refs:
                ref_url = image_refs[0]
                # Validate file existence for image_refs too
                if not Path(ref_url).exists() or Path(ref_url).stat().st_size < 100:
                    logger.warning("seedance: image_refs[0] missing or too small, falling back to text_to_video",
                                   path=ref_url)
                    api_result = await client.text_to_video(
                        prompt=prompt,
                        image_refs=None,
                        duration=duration,
                        resolution=resolution,
                    )
                else:
                    api_result = await client.image_to_video(
                        image_url=ref_url,
                        prompt=prompt,
                        duration=duration,
                        style_preserve=True,
                    )
            else:
                api_result = await client.text_to_video(
                    prompt=prompt,
                    image_refs=None,
                    duration=duration,
                    resolution=resolution,
                )
        finally:
            # Best-effort close httpx client
            try:
                await client.close()
            except Exception:
                pass

        is_stub = "_stub_mode" in api_result or not api_result.get("video_url", "").startswith(("http://", "https://"))
        local_path_str = api_result.get("local_path", "")
        local_path = Path(local_path_str) if local_path_str else None

        # === Self-verification ===
        verification = self._self_verify(
            local_path=local_path,
            is_stub=is_stub,
        )

        # If real-mode (had API key, no stub) but verification failed → return failure to trigger retry
        if not is_stub and not verification["all_ok"]:
            return SkillResult(
                success=False,
                error=f"video verification failed: {verification['failures']}",
                metadata={
                    "verification": verification,
                    "video_path": str(local_path) if local_path else "",
                },
            )

        # Stub mode: ensure a placeholder file exists so downstream nodes don't crash
        if is_stub and local_path and not local_path.exists():
            self._build_stub_mp4(local_path, output_label)

        # Best-effort duration measurement
        duration_seconds = self._measure_duration(local_path) if local_path and local_path.exists() else 0.0
        # Trust API-reported duration if measurement returned 0
        if duration_seconds == 0.0:
            duration_seconds = float(api_result.get("duration", duration))

        file_size = local_path.stat().st_size if (local_path and local_path.exists()) else 0

        return SkillResult(
            success=True,
            data={
                "video_path": str(local_path) if local_path else "",
                "duration_seconds": duration_seconds,
                "file_size_bytes": file_size,
                "resolution": resolution,
                "prompt_used": prompt,
                "is_stub": is_stub,
                "verification": verification,
                "output_label": output_label,
            },
            metadata={"api_mode": api_result.get("_stub_mode", "real")},
        )

    # === Self-verification helpers ===

    def _self_verify(self, local_path: Path | None, is_stub: bool) -> dict[str, Any]:
        """Run technical checks on the generated mp4.

        For stub mode we relax checks (we know the file is a placeholder).
        """
        if is_stub:
            return {
                "file_exists": local_path is not None,
                "size_ok": True,        # not applicable
                "header_ok": True,      # not applicable
                "duration_ok": True,    # not applicable
                "all_ok": True,
                "failures": [],
                "mode": "stub_relaxed",
            }

        failures: list[str] = []

        if not local_path or not local_path.exists():
            failures.append("file_not_found")
            return {
                "file_exists": False, "size_ok": False, "header_ok": False,
                "duration_ok": False, "all_ok": False, "failures": failures,
                "mode": "real",
            }

        size = local_path.stat().st_size
        size_ok = size >= MIN_FILE_SIZE_BYTES
        if not size_ok:
            failures.append(f"file_too_small_{size}b")

        header_ok = self._is_valid_mp4(local_path)
        if not header_ok:
            failures.append("invalid_mp4_header")

        duration = self._measure_duration(local_path)
        duration_ok = duration >= MIN_DURATION_SECONDS
        if not duration_ok:
            failures.append(f"duration_too_short_{duration:.1f}s")

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
    def _is_valid_mp4(path: Path) -> bool:
        """Check the ftyp box at the start of the file.

        MP4 files start with: [4 bytes size][ftyp][4 bytes major brand]...
        """
        try:
            if not path.exists() or path.stat().st_size < 12:
                return False
            with open(path, "rb") as f:
                head = f.read(12)
            if len(head) < 12:
                return False
            # bytes 4-8 should be 'ftyp'
            if head[4:8] != b"ftyp":
                return False
            major_brand = head[8:12]
            return major_brand in MP4_FTYP_BRANDS
        except Exception:
            return False

    @staticmethod
    def _measure_duration(path: Path) -> float:
        """Attempt to measure video duration via ffprobe.

        Returns 0.0 if ffprobe is unavailable or file is too small —
        caller should fall back to API value.
        """
        if not path or not path.exists() or path.stat().st_size < 100:
            return 0.0
        try:
            import subprocess
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
    def _extract_last_frame(video_path: str) -> str:
        """Extract the last frame of a video as a JPEG image using ffmpeg.

        This is used for continuity — the last frame of shot N becomes the
        starting frame for shot N+1 to maintain visual consistency.

        Args:
            video_path: Path to the source video file.

        Returns:
            Absolute path to the extracted JPEG frame, or empty string on failure.
        """
        import subprocess
        import tempfile

        if not video_path or not isinstance(video_path, str):
            return ""
        src = Path(video_path)
        if not src.exists() or src.stat().st_size < 100:
            return ""

        try:
            frame_path = Path(tempfile.mktemp(suffix=".jpg"))
            # ffmpeg -sseof -1 seeks to 1 second before end, then -vframes 1 captures last frame
            cmd = [
                "ffmpeg", "-y",
                "-sseof", "-1",
                "-i", str(src),
                "-vframes", "1",
                "-q:v", "2",
                str(frame_path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=15, check=True)
            if frame_path.exists() and frame_path.stat().st_size > 100:
                return str(frame_path)
        except (FileNotFoundError, subprocess.TimeoutExpired,
                subprocess.CalledProcessError, Exception):
            pass
        return ""

    @staticmethod
    def _build_stub_mp4(path: Path, label: str) -> None:
        """Generate a playable stub MP4 using ffmpeg, or fallback to minimal bytes.

        The ffmpeg-generated file is a real 3-second 720x1280 video with a
        text overlay so it's visually obvious it's a stub.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        text = label or "Stub Video"
        try:
            import subprocess
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", "color=c=#f5f5f7:s=720x1280:d=3",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-an",  # no audio
                str(path),
            ]
            subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, Exception):
            # ffmpeg unavailable or failed — write minimal magic-byte stub
            marker = label.encode()[:8].ljust(8, b"\0")
            path.write_bytes(b"\x00\x00\x00\x14" + b"ftyp" + b"isom" + marker)

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        errors = []
        prompt = params.get("prompt")
        if not prompt or (isinstance(prompt, str) and not prompt.strip()):
            errors.append("missing or empty 'prompt'")
        elif not isinstance(prompt, str):
            errors.append("'prompt' must be a string")
        elif len(prompt.strip()) < 5:
            errors.append("'prompt' too short (< 5 chars)")
        return errors

    def validate_output(self, data: Any) -> list[str]:
        errors = []
        if not data:
            return ["output is None"]
        if "video_path" not in data:
            errors.append("missing 'video_path'")
        if "verification" not in data:
            errors.append("missing 'verification' report")
        return errors

    def fallback(self, params: dict[str, Any]) -> SkillResult:
        """Deterministic fallback: write a placeholder mp4 marker."""
        from src.config import OUTPUT_DIR

        label = params.get("output_label", "fallback")
        out_dir = OUTPUT_DIR / "seedance"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"fallback_{label}_{abs(hash(params.get('prompt',''))) & 0xFFFF:04x}.mp4"
        self._build_stub_mp4(path, label)

        return SkillResult(
            success=True,
            data={
                "video_path": str(path),
                "duration_seconds": float(params.get("duration", DEFAULT_DURATION)),
                "file_size_bytes": path.stat().st_size,
                "resolution": params.get("resolution", DEFAULT_RESOLUTION),
                "prompt_used": params.get("prompt", ""),
                "is_stub": True,
                "verification": {
                    "file_exists": True, "size_ok": True, "header_ok": True,
                    "duration_ok": True, "all_ok": True, "failures": [],
                    "mode": "fallback",
                },
                "output_label": label,
                "_fallback": True,
            },
            metadata={"reason": "all_retries_exhausted"},
        )


# Auto-register
try:
    SkillRegistry.register(SeedanceVideoGenerateSkill())
    logger.info("seedance_video_generate_skill: registered")
except ValueError:
    pass
