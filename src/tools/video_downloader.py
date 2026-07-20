"""Video download and transcription service.

Downloads videos from social platforms (Douyin, Xiaohongshu, TikTok)
and transcribes audio to timestamped text segments.

Uses yt-dlp for video download and Whisper for transcription.
Graceful fallback to mock when external tools unavailable.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog
from pydantic import BaseModel

from src.config import OUTPUT_DIR
from src.tools.safe_media import UnsafeMediaError, validate_media_file

logger = structlog.get_logger()

DOWNLOAD_TIMEOUT_SECONDS = 120.0
TRANSCRIBE_TIMEOUT_SECONDS = 300.0
YTDLP_SAFE_FORMAT = (
    "best[ext=mp4][protocol=http][vcodec!=?none][acodec!=?none]/"
    "best[ext=mp4][protocol=https][vcodec!=?none][acodec!=?none]/"
    "best[protocol=http][vcodec!=?none][acodec!=?none]/"
    "best[protocol=https][vcodec!=?none][acodec!=?none]"
)


class VideoDownloadError(Exception):
    """Raised when video download fails."""


class TranscriptionError(Exception):
    """Raised when transcription fails."""


class UnsafeUrlError(Exception):
    """Raised when a URL points to a private/internal address."""


class TranscribeSegment(BaseModel):
    """A single transcribed segment with timing."""
    start: float
    end: float
    text: str


class VideoMetadata(BaseModel):
    """Metadata extracted from a downloaded video."""
    title: str = ""
    author: str = ""
    duration: float = 0.0
    source_url: str = ""
    platform: str = ""
    local_path: str = ""


class VideoDownloader:
    """Downloads and transcribes videos from social platforms.

    Two modes:
    1. Real: yt-dlp + Whisper (requires system installation)
    2. Mock: returns synthetic segments for testing
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or OUTPUT_DIR / "downloaded_videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._ytdlp_available = self._check_ytdlp()
        self._whisper_available = self._check_whisper()

    # ── Public API ──

    async def download(self, url: str) -> VideoMetadata:
        """Download a video from any supported platform.

        Falls back to mock if yt-dlp is not available.

        Args:
            url: Video URL from Douyin, Xiaohongshu, TikTok, etc.

        Returns:
            VideoMetadata with local_path pointing to downloaded file.
        """
        try:
            self._validate_url(url)
        except UnsafeUrlError as exc:
            logger.error("video_downloader: unsafe URL rejected", url=url, error=str(exc))
            return self._mock_metadata(url)

        if not self._ytdlp_available:
            logger.warning("video_downloader: yt-dlp not available, using mock")
            return self._mock_metadata(url)

        try:
            return await self._real_download(url)
        except (VideoDownloadError, subprocess.TimeoutExpired) as e:
            logger.error("video_downloader: download failed", url=url, error=str(e))
            return self._mock_metadata(url)

    async def transcribe(self, video_path: str) -> list[TranscribeSegment]:
        """Transcribe audio from a video file to timestamped text.

        Falls back to mock if Whisper is not available.

        Args:
            video_path: Path to local video file.

        Returns:
            List of TranscribeSegment with start, end, and text.
        """
        if self._is_mock_download_path(video_path):
            logger.info("video_downloader: mock download, skipping transcription")
            return self._mock_transcription()

        if not self._whisper_available:
            logger.warning("video_downloader: whisper not available, using mock")
            return self._mock_transcription()

        try:
            return await self._real_transcribe(video_path)
        except (TranscriptionError, subprocess.TimeoutExpired) as e:
            logger.error("video_downloader: transcribe failed", path=video_path, error=str(e))
            return self._mock_transcription()

    async def download_and_transcribe(self, url: str) -> dict[str, Any]:
        """Convenience: download then transcribe in one call.

        Returns:
            {metadata: VideoMetadata, segments: list[TranscribeSegment]}
        """
        metadata = await self.download(url)
        if not metadata.local_path or self._is_mock_download_path(metadata.local_path):
            logger.info("video_downloader: mock mode, skipping transcription")
            return {
                "metadata": metadata.model_dump(),
                "segments": [s.model_dump() for s in self._mock_transcription()],
            }

        segments = await self.transcribe(metadata.local_path)
        return {
            "metadata": metadata.model_dump(),
            "segments": [s.model_dump() for s in segments],
        }

    # ── Real implementations ──

    async def _real_download(self, url: str) -> VideoMetadata:
        """Download video using yt-dlp."""
        output_template = str(self.output_dir / "%(title).50s_%(id)s.%(ext)s")

        async def _do_download():
            async with asyncio.timeout(DOWNLOAD_TIMEOUT_SECONDS):
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "yt-dlp",
                        "--ignore-config",
                        "--no-playlist",
                        "--concat-playlist", "never",
                        "--format", YTDLP_SAFE_FORMAT,
                        "--downloader", "native",
                        "--fixup", "never",
                        "--output", output_template,
                        "--no-simulate",
                        "--print", "after_move:filepath",
                        "--restrict-filenames",
                        url,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                    env={**os.environ, "YTDLP_NO_PLUGINS": "1"},
                )
                if result.returncode != 0:
                    raise VideoDownloadError(f"yt-dlp failed: {result.stderr[:500]}")

                local_path = result.stdout.strip()
                if not local_path or not Path(local_path).exists():
                    raise VideoDownloadError(f"yt-dlp returned no output for {url}")
                try:
                    validate_media_file(local_path)
                except UnsafeMediaError as exc:
                    Path(local_path).unlink(missing_ok=True)
                    raise VideoDownloadError("yt-dlp returned an unsafe media container") from exc

                logger.info("video_downloader: downloaded", path=local_path)
                return VideoMetadata(
                    local_path=local_path,
                    source_url=url,
                    platform=self._detect_platform(url),
                )

        return await _do_download()

    async def _real_transcribe(self, video_path: str) -> list[TranscribeSegment]:
        """Transcribe using faster-whisper (Python API, preferred) or whisper CLI (fallback).

        faster-whisper is ~200 MB vs openai-whisper+torch ~1.8 GB — we install
        it as the primary transcription backend. The CLI subprocess path is kept
        as a fallback for environments that installed openai-whisper directly.
        """
        validate_media_file(video_path)

        async def _do_transcribe():
            async with asyncio.timeout(TRANSCRIBE_TIMEOUT_SECONDS):
                try:
                    from faster_whisper import WhisperModel
                except ImportError:
                    return await self._cli_whisper_transcribe(video_path)

                def _run_faster_whisper() -> list[TranscribeSegment]:
                    model = WhisperModel("base", device="cpu", compute_type="int8")
                    segments_iter, _info = model.transcribe(
                        video_path, language="en", beam_size=1
                    )
                    return [
                        TranscribeSegment(
                            start=float(s.start),
                            end=float(s.end),
                            text=(s.text or "").strip(),
                        )
                        for s in segments_iter
                    ]

                segments = await asyncio.to_thread(_run_faster_whisper)
                logger.info(
                    "video_downloader: transcribed",
                    segments=len(segments),
                    backend="faster-whisper",
                )
                return segments

        return await _do_transcribe()

    async def _cli_whisper_transcribe(self, video_path: str) -> list[TranscribeSegment]:
        """Fallback: shell out to the `whisper` CLI (openai-whisper package)."""
        async with asyncio.timeout(TRANSCRIBE_TIMEOUT_SECONDS):
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "whisper",
                    video_path,
                    "--model", "base",
                    "--output_format", "json",
                    "--language", "en",
                ],
                capture_output=True, text=True, timeout=TRANSCRIBE_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                raise TranscriptionError(f"whisper failed: {result.stderr[:500]}")

            data = json.loads(result.stdout)
            segments = [
                TranscribeSegment(
                    start=seg.get("start", 0.0),
                    end=seg.get("end", 0.0),
                    text=seg.get("text", "").strip(),
                )
                for seg in data.get("segments", [])
            ]
            logger.info(
                "video_downloader: transcribed",
                segments=len(segments),
                backend="whisper-cli",
            )
            return segments


    # ── Mock implementations ──

    def _mock_metadata(self, url: str) -> VideoMetadata:
        """Return mock metadata when yt-dlp unavailable."""
        plat = self._detect_platform(url)
        return VideoMetadata(
            title=f"[MOCK] Video from {plat}",
            author="mock_creator",
            duration=30.0,
            source_url=url,
            platform=plat,
            local_path="[MOCK_DOWNLOAD — add yt-dlp]",
        )

    def _is_mock_download_path(self, path: str) -> bool:
        """Detect synthetic paths returned by `_mock_metadata`."""
        return path.startswith("[MOCK_DOWNLOAD")

    def _mock_transcription(self) -> list[TranscribeSegment]:
        """Return mock transcription when Whisper unavailable."""
        return [
            TranscribeSegment(start=0.0, end=3.5, text="Hey everyone, welcome back to my channel."),
            TranscribeSegment(start=3.5, end=8.2, text="Today I'm going to show you something really exciting."),
            TranscribeSegment(start=8.2, end=14.0, text="I've been using this product for the past two weeks."),
            TranscribeSegment(start=14.0, end=20.5, text="And honestly, it has completely changed my daily routine."),
            TranscribeSegment(start=20.5, end=26.0, text="Let me show you how it works and why I love it."),
            TranscribeSegment(start=26.0, end=30.0, text="Link in the description if you want to try it yourself."),
        ]

    # ── Helpers ──

    def _detect_platform(self, url: str) -> str:
        url_lower = url.lower()
        if "douyin" in url_lower:
            return "douyin"
        elif "xiaohongshu" in url_lower or "xhslink" in url_lower:
            return "xiaohongshu"
        elif "tiktok" in url_lower:
            return "tiktok"
        elif "youtube" in url_lower or "youtu.be" in url_lower:
            return "youtube"
        else:
            return "unknown"

    def _check_ytdlp(self) -> bool:
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_whisper(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            result = subprocess.run(
                ["whisper", "--help"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _validate_url(self, url: str) -> None:
        """Validate that the URL is safe to pass to yt-dlp.

        Rejects:
          - Non-http(s) protocols (file://, ftp://, etc.)
          - Private / loopback / link-local IP addresses
          - URLs without a hostname

        Raises:
            UnsafeUrlError: If the URL is deemed unsafe.
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise UnsafeUrlError(f"URL scheme '{parsed.scheme}' is not allowed")
        if not parsed.hostname:
            raise UnsafeUrlError("URL has no hostname")

        hostname = parsed.hostname
        # Check for IP-based URLs
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                raise UnsafeUrlError(f"URL resolves to a private/internal IP: {hostname}")
        except ValueError:
            # Not an IP address — assume DNS name; allow public domains.
            # If needed, A-record resolution could be added here in the future.
            pass
