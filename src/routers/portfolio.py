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
async def list_portfolio(category: str | None = None) -> PortfolioResponse:
    """Return all pipeline-generated media files.

    Query param `category` filters to a single category (renders, seedance, ...).
    """
    all_files = _scan_portfolio_cached()
    if category:
        all_files = [f for f in all_files if f.category == category]

    by_cat: dict[str, dict[str, int]] = {}
    for f in all_files:
        entry = by_cat.setdefault(f.category, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += f.size_bytes

    return PortfolioResponse(
        total=len(all_files),
        by_category=by_cat,
        files=all_files,
    )
