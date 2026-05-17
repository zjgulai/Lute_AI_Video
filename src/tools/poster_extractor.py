"""Poster (thumbnail) extractor shared by every code path that produces an .mp4.

Why this exists:
    Before 2026-05-17 the only producer of `output/thumbnails/portfolio_posters/*.jpg`
    was `portfolio_hook.rebuild_portfolio_listener`, which fires on
    `pipeline.completed`. Fast-mode runs and ad-hoc seedance/remotion calls do
    NOT emit that event, so /works and /library cards rendered as black tiles.

    This module centralises the ffmpeg poster extraction so every video-producing
    skill can call `ensure_poster(video_path)` immediately after writing its mp4
    and the portfolio router can synthesize one on-the-fly when listing files.

Contract:
    - Best-effort: ffmpeg missing, ffmpeg failure, write-permission errors → all
      return None silently. NEVER raises. NEVER blocks the caller.
    - Idempotent: if the poster already exists and is at-least-as-new as the
      source video, returns the existing path without touching ffmpeg.
    - Naming convention matches `src.routers.portfolio._thumbnail_path_for`:
      `output/seedance/foo.mp4` -> `output/thumbnails/portfolio_posters/seedance__foo.jpg`.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

POSTER_DIR = OUTPUT_DIR / "thumbnails" / "portfolio_posters"
_VIDEO_EXTS = {".mp4", ".mov", ".webm"}


def poster_path_for(video_path: Path) -> Path | None:
    """Return the canonical poster Path for a video under OUTPUT_DIR, or None.

    Returns None when the video is not under OUTPUT_DIR (the path scheme
    `seedance__foo.jpg` only makes sense for files inside OUTPUT_DIR).
    """
    try:
        rel = video_path.resolve().relative_to(OUTPUT_DIR.resolve())
    except (ValueError, OSError):
        return None
    flat = str(rel).replace("/", "__").rsplit(".", 1)[0] + ".jpg"
    return POSTER_DIR / flat


def ensure_poster(video_path: str | Path) -> Path | None:
    """Make sure a poster jpg exists for `video_path`. Return its Path or None.

    Safe to call from any code path including pipeline skills, request handlers
    inside the portfolio router, and post-write hooks. Errors are swallowed.

    Returns:
        Path to the poster on success (whether freshly created or already
        present), or None if generation could not be performed.
    """
    src = Path(video_path)
    if not src.is_file():
        return None
    if src.suffix.lower() not in _VIDEO_EXTS:
        return None

    poster = poster_path_for(src)
    if poster is None:
        return None

    try:
        src_mtime = src.stat().st_mtime
        if poster.is_file() and poster.stat().st_mtime >= src_mtime:
            return poster
    except OSError:
        return None

    if not shutil.which("ffmpeg"):
        # ffmpeg is in Dockerfile.backend, but local dev / minimal images may
        # lack it. Don't spam the log; one warning per process is enough.
        if not getattr(ensure_poster, "_warned_no_ffmpeg", False):
            logger.warning("poster_extractor: ffmpeg not found, skipping poster generation")
            ensure_poster._warned_no_ffmpeg = True  # type: ignore[attr-defined]
        return None

    try:
        POSTER_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("poster_extractor: cannot create %s: %s", POSTER_DIR, exc)
        return None

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss", "00:00:02",
                "-i", str(src),
                "-vframes", "1",
                "-vf", "scale=480:-2",
                "-q:v", "3",
                str(poster),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError) as exc:
        # Short videos (<2s) fail the seek; retry without the seek so we still
        # get a frame. Don't loop further on failure.
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i", str(src),
                    "-vframes", "1",
                    "-vf", "scale=480:-2",
                    "-q:v", "3",
                    str(poster),
                ],
                capture_output=True,
                timeout=30,
                check=True,
            )
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
            logger.debug("poster_extractor: ffmpeg failed for %s: %s", src, exc)
            return None

    return poster if poster.is_file() else None
