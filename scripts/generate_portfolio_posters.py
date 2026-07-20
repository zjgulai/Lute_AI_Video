#!/usr/bin/env python3
"""Generate JPEG poster thumbnails for every video in output/ that lacks one.

Mirrors the path-mapping convention in src/routers/portfolio.py:
  rel_path "seedance/s1_001.mp4" -> "thumbnails/portfolio_posters/seedance__s1_001.jpg"

Run inside the backend container (ffmpeg available there):
  docker exec -it ai_video_backend python /app/scripts/generate_portfolio_posters.py

Idempotent: skips files whose poster already exists and is non-empty.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from src.tools.safe_media import UnsafeMediaError, ffmpeg_local_input_args

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".m4v"}

OUTPUT_DIR = Path(os.environ.get("VIDEO_OUTPUT_DIR", "/app/output")).resolve()
THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails" / "portfolio_posters"


def poster_path_for(video_rel: str) -> Path:
    flat = video_rel.replace("/", "__").rsplit(".", 1)[0] + ".jpg"
    return THUMBNAIL_DIR / flat


def extract_poster(video: Path, poster: Path, *, seek_seconds: float = 1.0) -> bool:
    poster.parent.mkdir(parents=True, exist_ok=True)
    try:
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-y",
            "-ss", f"{seek_seconds}",
            *ffmpeg_local_input_args(video),
            "-frames:v", "1",
            "-q:v", "3",
            "-vf", "scale='min(1280,iw)':-2",
            str(poster),
        ]
        subprocess.run(cmd, check=True, timeout=60)
    except subprocess.CalledProcessError as exc:
        print(f"  [skip seek={seek_seconds}s] ffmpeg failed: {exc}", file=sys.stderr)
        return False
    except subprocess.TimeoutExpired:
        print("  [skip] ffmpeg timeout", file=sys.stderr)
        return False
    except UnsafeMediaError:
        print("  [skip] unsafe media container", file=sys.stderr)
        return False
    return poster.is_file() and poster.stat().st_size > 1024


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(OUTPUT_DIR), help="Output dir (default: $VIDEO_OUTPUT_DIR or /app/output)")
    parser.add_argument("--force", action="store_true", help="Regenerate even if poster exists")
    parser.add_argument("--dry-run", action="store_true", help="List candidates without invoking ffmpeg")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: root {root} is not a directory", file=sys.stderr)
        return 2

    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)

    skip_dirs = {"thumbnails", "tmp", "ai_video.db-journal"}
    candidates: list[tuple[Path, str]] = []
    for video in root.rglob("*"):
        if not video.is_file():
            continue
        if video.suffix.lower() not in VIDEO_EXTS:
            continue
        if any(part in skip_dirs for part in video.parts):
            continue
        rel = video.relative_to(root).as_posix()
        candidates.append((video, rel))

    print(f"Scanned: {len(candidates)} videos under {root}")

    generated = 0
    skipped = 0
    failed = 0
    for video, rel in candidates:
        poster = poster_path_for(rel)
        if poster.is_file() and poster.stat().st_size > 1024 and not args.force:
            skipped += 1
            continue
        if args.dry_run:
            print(f"  would generate: {rel} -> {poster.relative_to(OUTPUT_DIR)}")
            generated += 1
            continue
        ok = extract_poster(video, poster, seek_seconds=1.0)
        if not ok:
            ok = extract_poster(video, poster, seek_seconds=0.0)
        if ok:
            generated += 1
            print(f"  ok  {rel}")
        else:
            failed += 1
            print(f"  FAIL {rel}", file=sys.stderr)

    print(f"\nResult: generated={generated} skipped_existing={skipped} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
