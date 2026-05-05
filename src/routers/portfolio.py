"""Portfolio endpoint — expose all pipeline-generated media for browsing and reuse.

Scans OUTPUT_DIR subdirectories (renders/ seedance/ gpt_images/ audio/ fast_mode/
keyframes/ etc.) and returns a structured file listing that the frontend footage
page can render as a gallery. Complements /api/assets/ (upload-only) with the
full set of real pipeline outputs.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from src.config import OUTPUT_DIR

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

MEDIA_EXTS = {".mp4", ".mp3", ".wav", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".gif"}

CATEGORIES: dict[str, tuple[str, str]] = {
    "renders": ("renders", "remotion_assemble"),
    "seedance": ("seedance", "seedance_video_generate"),
    "gpt_images": ("gpt_images", "poyo_image_generate"),
    "audio": ("audio", "tts_synthesis"),
    "fast_mode": ("fast_mode", "fast_mode_pipeline"),
    "keyframes": ("keyframes", "keyframe_extract"),
    "character_identity": ("character_identity", "character_identity"),
    "quality-test": ("quality-test", "quality_test"),
    "demo": ("demo", "demo"),
    "assets": ("assets", "asset_storage"),
    "thumbnails": ("thumbnails", "thumbnail_generate"),
    "uploads": ("uploads", "user_uploads"),
}

LABEL_RE = re.compile(r"^(s\d)_(\d+)")

# Quality ranking: lower number = higher priority. Categories not listed get 99 (lowest).
# renders = 成片(remotion 完整组装),fast_mode = Fast Mode 直出。其余是中间产物。
QUALITY_PRIORITY: dict[str, int] = {
    "renders": 0,
    "fast_mode": 1,
}

# Thumbnail posters live alongside other thumbnails but in a dedicated subfolder so
# they're easy to identify, regenerate, and rsync. Naming: <category>__<filename>.jpg
# (slashes in original path replaced by `__` so a single flat directory works).
THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails" / "portfolio_posters"


def _thumbnail_path_for(rel_path: str) -> str | None:
    """Return relative thumbnail path (under OUTPUT_DIR) if the poster jpg exists.

    Naming convention: rel_path "seedance/s1_001.mp4" → poster
    "thumbnails/portfolio_posters/seedance__s1_001.jpg".
    """
    flat = rel_path.replace("/", "__").rsplit(".", 1)[0] + ".jpg"
    poster = THUMBNAIL_DIR / flat
    if poster.is_file():
        return str(poster.relative_to(OUTPUT_DIR))
    return None


class PortfolioFile(BaseModel):
    id: str
    filename: str
    path: str
    category: str
    scenario: str | None = None
    label: str | None = None
    produced_at: str
    size_bytes: int
    mime_type: str
    thumbnail_path: str | None = None  # relative to OUTPUT_DIR; None for non-video or missing poster


class PortfolioResponse(BaseModel):
    total: int
    by_category: dict[str, dict[str, int]]
    files: list[PortfolioFile]


def _guess_mime(ext: str) -> str:
    return {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
    }.get(ext.lower(), "application/octet-stream")


def _scan_portfolio() -> list[PortfolioFile]:
    """Walk OUTPUT_DIR subdirectories and build PortfolioFile list.

    Video / image: strictly larger than 1 MiB (same threshold as /api/files).
    Audio: any positive size (no floor).
    """
    files: list[PortfolioFile] = []
    min_bytes = 1024 * 1024
    for subdir_name, (category, _source) in CATEGORIES.items():
        subdir = OUTPUT_DIR / subdir_name
        if not subdir.is_dir():
            continue
        for path in sorted(subdir.rglob("*")):
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in MEDIA_EXTS:
                continue
            st = path.stat()
            if st.st_size <= 0:
                continue
            mime = _guess_mime(ext)
            # Skip tiny video/image files — likely generation failures or stubs
            if not mime.startswith("audio/") and st.st_size <= min_bytes:
                continue
            rel = path.relative_to(OUTPUT_DIR)
            m = LABEL_RE.match(path.stem)
            scenario = m.group(1) if m else None
            label = f"{scenario}_{m.group(2)}" if m else None
            thumb = _thumbnail_path_for(str(rel)) if mime.startswith("video/") else None
            files.append(
                PortfolioFile(
                    id=str(rel),
                    filename=path.name,
                    path=str(rel),
                    category=category,
                    scenario=scenario,
                    label=label,
                    produced_at=datetime.fromtimestamp(
                        st.st_mtime, tz=UTC
                    ).isoformat(timespec="seconds"),
                    size_bytes=st.st_size,
                    mime_type=mime,
                    thumbnail_path=thumb,
                )
            )
    return files


_CACHE: dict[str, tuple[list[PortfolioFile], float]] = {}
_CACHE_TTL = 30  # seconds


def _scan_portfolio_cached() -> list[PortfolioFile]:
    """Return cached scan result if within TTL, otherwise rescan."""
    key = "all"
    now = time.time()
    if key in _CACHE:
        files, cached_at = _CACHE[key]
        if now - cached_at < _CACHE_TTL:
            return files
    files = _scan_portfolio()
    _CACHE[key] = (files, now)
    return files


@router.get("/")
async def list_portfolio(
    category: str | None = None,
    limit: int | None = None,
    sort: str = "recent",
) -> PortfolioResponse:
    """Return pipeline-generated media files.

    Query params:
    - `category`: filter to a single category (renders, seedance, ...).
    - `limit`: cap number of files returned (after sort+filter).
    - `sort`: `recent` (default, by produced_at desc) or `quality` (renders+fast_mode first,
              then by produced_at desc — used by frontend footage TOP-N display).

    `by_category` aggregates the *unfiltered* full set so UI can show overall counts
    even when displaying a TOP-N slice.
    """
    all_files = _scan_portfolio_cached()

    # by_category aggregates over all files (pre-filter, pre-limit) so totals stay stable
    by_cat: dict[str, dict[str, int]] = {}
    for f in all_files:
        entry = by_cat.setdefault(f.category, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += f.size_bytes

    if category:
        all_files = [f for f in all_files if f.category == category]

    if sort == "quality":
        all_files = sorted(
            all_files,
            key=lambda f: (
                QUALITY_PRIORITY.get(f.category, 99),
                # produced_at is ISO-8601 UTC; lex desc == chronological desc
                _negate_iso(f.produced_at),
            ),
        )
    else:  # recent
        all_files = sorted(all_files, key=lambda f: f.produced_at, reverse=True)

    if limit is not None and limit > 0:
        all_files = all_files[:limit]

    return PortfolioResponse(
        total=len(all_files),
        by_category=by_cat,
        files=all_files,
    )


def _negate_iso(iso: str) -> str:
    """Return a sort key that yields desc order when paired with ascending sort.

    Python sorts strings lexically; for ISO-8601 dates we want most-recent first,
    so we map each char to its inverse ordinal. Stable across all valid ISO inputs.
    """
    return "".join(chr(0xFFFF - ord(c)) for c in iso)
