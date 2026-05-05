#!/usr/bin/env python3
"""Generate poster JPEGs for all video files in OUTPUT_DIR.

Scans the same subdirectories as /api/portfolio/, runs ffprobe to verify
each file is a valid video, then ffmpeg to extract 1 frame at t=2 s.

Naming convention (matches _thumbnail_path_for in portfolio.py):
  source  : "seedance/s1_001.mp4"
  poster  : "thumbnails/portfolio_posters/seedance__s1_001.jpg"

Resolution: 480 x 270 (16:9), quality ~85.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import OUTPUT_DIR

MEDIA_EXTS = {".mp4", ".mov", ".webm"}

CATEGORIES = [
    "renders",
    "seedance",
    "fast_mode",
    "keyframes",
    "demo",
    "quality-test",
]

POSTER_DIR = OUTPUT_DIR / "thumbnails" / "portfolio_posters"


def _thumbnail_path(rel: str) -> Path:
    flat = rel.replace("/", "__").rsplit(".", 1)[0] + ".jpg"
    return POSTER_DIR / flat


def _ffprobe_valid(path: Path) -> bool:
    """Return True if ffprobe reports a non-zero width and height."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return False
        dims = result.stdout.strip()
        if "N/A" in dims:
            return False
        w, _, h = dims.partition("x")
        return int(w) > 0 and int(h) > 0
    except (ValueError, subprocess.TimeoutExpired, OSError):
        return False


def _extract_poster(source: Path, dest: Path) -> bool:
    """Use ffmpeg to grab a single frame at 2 s, scale to 480x270."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",                          # overwrite if needed
                "-ss", "00:00:02",             # seek to 2 s (keyframe-aware fast)
                "-i", str(source),
                "-vframes", "1",               # single frame
                "-vf", "scale=480:-2",         # 480 px wide, height auto-even
                "-q:v", "3",                   # quality (2-5 is good)
                str(dest),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        return dest.is_file()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
        return False


def rebuild_thumbnails() -> dict[str, int]:
    stats = {"created": 0, "skipped": 0, "failed": 0, "scanned": 0}
    POSTER_DIR.mkdir(parents=True, exist_ok=True)

    for cat in CATEGORIES:
        subdir = OUTPUT_DIR / cat
        if not subdir.is_dir():
            continue
        for path in subdir.rglob("*"):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in MEDIA_EXTS:
                continue
            stats["scanned"] += 1
            rel = path.relative_to(OUTPUT_DIR)
            poster = _thumbnail_path(str(rel))
            src_mtime = path.stat().st_mtime
            if poster.is_file() and poster.stat().st_mtime >= src_mtime:
                stats["skipped"] += 1
                continue
            if not _ffprobe_valid(path):
                stats["failed"] += 1
                continue
            if _extract_poster(path, poster):
                stats["created"] += 1
            else:
                stats["failed"] += 1

    return stats


def main() -> int:
    print("Portfolio poster thumbnail generator")
    print("-" * 40)
    print(f"OUTPUT_DIR : {OUTPUT_DIR}")
    print(f"POSTER_DIR : {POSTER_DIR}")
    print(f"ffprobe    : {'available' if _cmd_exists('ffprobe') else 'NOT FOUND'}")
    print()
    if not _cmd_exists("ffprobe") or not _cmd_exists("ffmpeg"):
        print("ERROR: ffmpeg / ffprobe not found in PATH.")
        print("Install with: brew install ffmpeg   # macOS")
        print("Or:          apt-get install ffmpeg # Debian/Ubuntu")
        return 1

    stats = rebuild_thumbnails()
    print(f"Scanned : {stats['scanned']}")
    print(f"Created : {stats['created']}")
    print(f"Skipped : {stats['skipped']}  (already up-to-date)")
    print(f"Failed  : {stats['failed']}")
    print()
    print(f"Done. Posters in: {POSTER_DIR}")
    return 0


def _cmd_exists(cmd: str) -> bool:
    import shutil
    return shutil.which(cmd) is not None


if __name__ == "__main__":
    sys.exit(main())
