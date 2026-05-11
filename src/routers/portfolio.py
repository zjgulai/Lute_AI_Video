"""Portfolio endpoint — expose all pipeline-generated media for browsing and reuse.

Scans OUTPUT_DIR subdirectories (renders/ seedance/ gpt_images/ audio/ fast_mode/
keyframes/ etc.) and returns a structured file listing that the frontend footage
page can render as a gallery. Complements /api/assets/ (upload-only) with the
full set of real pipeline outputs.
"""

from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import OUTPUT_DIR

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

MEDIA_EXTS = {".mp4", ".mp3", ".wav", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".gif", ".webp"}

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
    "brand_assets": ("brand_assets", "external_scrape"),
}

LABEL_RE = re.compile(r"^(s\d)_(\d+)")

QUALITY_PRIORITY: dict[str, int] = {
    "renders": 0,
    "fast_mode": 1,
}

AssetKind = Literal["final_work", "creation_intermediate", "brand_kit"]

KIND_BY_CATEGORY: dict[str, AssetKind] = {
    "renders": "final_work",
    "fast_mode": "final_work",
    "seedance": "creation_intermediate",
    "gpt_images": "creation_intermediate",
    "audio": "creation_intermediate",
    "keyframes": "creation_intermediate",
    "thumbnails": "creation_intermediate",
    "character_identity": "creation_intermediate",
    "uploads": "creation_intermediate",
    "assets": "creation_intermediate",
    "demo": "creation_intermediate",
    "quality-test": "creation_intermediate",
    "brand_assets": "brand_kit",
}

def _derive_kind(category: str, mime: str) -> AssetKind:
    """Map (storage category, mime type) to lifecycle kind.

    `final_work` is reserved for deliverable video outputs only; audio or image
    artifacts inside `renders/` or `fast_mode/` remain `creation_intermediate`.
    """
    base = KIND_BY_CATEGORY.get(category, "creation_intermediate")
    if base == "final_work" and not mime.startswith("video/"):
        return "creation_intermediate"
    return base


THUMBNAIL_DIR = OUTPUT_DIR / "thumbnails" / "portfolio_posters"

BRAND_PATH_RE = re.compile(r"^brand_assets/([^/]+)/([^/]+)/images/")


@lru_cache(maxsize=128)
def _load_brand_info(brand: str, slug: str) -> dict | None:
    """Read brand_assets/<brand>/<slug>/info.json with LRU cache.

    Cache keyed by (brand, slug); invalidated by process restart (info.json is
    only written by scrape_momcozy.py, which is run out-of-band).
    """
    info_path = OUTPUT_DIR / "brand_assets" / brand / slug / "info.json"
    if not info_path.is_file():
        return None
    try:
        return json.loads(info_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _brand_meta_for(rel_path: str) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None]:
    """Return (title, slug, brand, source_url, description, price) for a brand asset path.

    Returns (None, ...) tuple for non-brand paths or when info.json is missing.
    """
    m = BRAND_PATH_RE.match(rel_path)
    if not m:
        return (None, None, None, None, None, None)
    brand, slug = m.group(1), m.group(2)
    info = _load_brand_info(brand, slug)
    if info is None:
        return (None, slug, brand, None, None, None)
    return (
        info.get("title") or None,
        info.get("slug") or slug,
        info.get("vendor") or brand,
        info.get("source_url") or None,
        info.get("description") or None,
        info.get("price") or None,
    )


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
    kind: AssetKind = "creation_intermediate"
    scenario: str | None = None
    label: str | None = None
    produced_at: str
    size_bytes: int
    mime_type: str
    thumbnail_path: str | None = None
    product_title: str | None = None
    product_slug: str | None = None
    product_brand: str | None = None
    product_source_url: str | None = None
    product_description: str | None = None
    product_price: str | None = None


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
        ".webp": "image/webp",
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
            # Skip tiny video/image files — likely generation failures or stubs.
            # Brand assets are exempt: scraped Shopify CDN images are 60-300KB.
            if not mime.startswith("audio/") and st.st_size <= min_bytes:
                if category != "brand_assets":
                    continue
            rel = path.relative_to(OUTPUT_DIR)
            m = LABEL_RE.match(path.stem)
            scenario = m.group(1) if m else None
            label = f"{scenario}_{m.group(2)}" if m else None
            thumb = _thumbnail_path_for(str(rel)) if mime.startswith("video/") else None
            (p_title, p_slug, p_brand, p_url, p_desc, p_price) = (
                _brand_meta_for(str(rel)) if category == "brand_assets" else (None, None, None, None, None, None)
            )
            files.append(
                PortfolioFile(
                    id=str(rel),
                    filename=path.name,
                    path=str(rel),
                    category=category,
                    kind=_derive_kind(category, mime),
                    scenario=scenario,
                    label=label,
                    produced_at=datetime.fromtimestamp(
                        st.st_mtime, tz=UTC
                    ).isoformat(timespec="seconds"),
                    size_bytes=st.st_size,
                    mime_type=mime,
                    thumbnail_path=thumb,
                    product_title=p_title,
                    product_slug=p_slug,
                    product_brand=p_brand,
                    product_source_url=p_url,
                    product_description=p_desc,
                    product_price=p_price,
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
    kind: AssetKind | None = None,
    limit: int | None = None,
    offset: int = 0,
    sort: str = "recent",
) -> PortfolioResponse:
    """Return pipeline-generated media files.

    Query params:
    - `category`: filter to a single storage bucket (renders, seedance, ...).
    - `kind`: filter by lifecycle stage (`final_work` | `creation_intermediate` | `brand_kit`).
              Preferred over `category` for UI-oriented queries.
    - `limit`: cap number of files returned (after sort+filter+offset).
    - `offset`: skip N files after sort+filter (for pagination). Default 0.
    - `sort`: ordering mode. Options:
              - `recent` (default): by produced_at desc
              - `quality`: renders+fast_mode first, then produced_at desc
              - `size_desc`: largest files first
              - `size_asc`: smallest files first

    `total` is the total count AFTER filter but BEFORE limit/offset — use it to drive
    pagination controls.
    `by_category` aggregates the *unfiltered* full set so UI can show overall counts
    even when displaying a TOP-N slice.
    """
    all_files = _scan_portfolio_cached()

    by_cat: dict[str, dict[str, int]] = {}
    for f in all_files:
        entry = by_cat.setdefault(f.category, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += f.size_bytes

    if category:
        all_files = [f for f in all_files if f.category == category]

    if kind:
        all_files = [f for f in all_files if f.kind == kind]

    if sort == "quality":
        all_files = sorted(
            all_files,
            key=lambda f: (
                QUALITY_PRIORITY.get(f.category, 99),
                _negate_iso(f.produced_at),
            ),
        )
    elif sort == "size_desc":
        all_files = sorted(all_files, key=lambda f: f.size_bytes, reverse=True)
    elif sort == "size_asc":
        all_files = sorted(all_files, key=lambda f: f.size_bytes)
    else:
        all_files = sorted(all_files, key=lambda f: f.produced_at, reverse=True)

    total_after_filter = len(all_files)

    if offset > 0:
        all_files = all_files[offset:]

    if limit is not None and limit > 0:
        all_files = all_files[:limit]

    return PortfolioResponse(
        total=total_after_filter,
        by_category=by_cat,
        files=all_files,
    )


def _negate_iso(iso: str) -> str:
    """Return a sort key that yields desc order when paired with ascending sort.

    Python sorts strings lexically; for ISO-8601 dates we want most-recent first,
    so we map each char to its inverse ordinal. Stable across all valid ISO inputs.
    """
    return "".join(chr(0xFFFF - ord(c)) for c in iso)


class BrandPresetsResponse(BaseModel):
    brand: str
    presets: list[dict]
    scraped_at: str | None = None


_PRESET_CACHE: dict[str, tuple[BrandPresetsResponse, float]] = {}
_PRESET_TTL = 60


@router.get("/brand-presets", response_model=BrandPresetsResponse)
async def get_brand_presets(brand: str = "momcozy") -> BrandPresetsResponse:
    """Return scraped quick-template presets for a brand.

    Source of truth is the scraper output at
    output/brand_assets/<brand>/<brand>_presets.json, written by
    scripts/scrape_momcozy.py. Front-end QuickTemplate consumes this in
    preference to the bundled demo-data fallback so a re-scrape is visible
    without redeploying the web bundle.

    404 if the brand directory or presets file is absent.
    """
    safe_brand = re.sub(r"[^A-Za-z0-9_-]", "", brand) or "momcozy"
    now = time.time()
    cached = _PRESET_CACHE.get(safe_brand)
    if cached is not None and now - cached[1] < _PRESET_TTL:
        return cached[0]

    presets_path = OUTPUT_DIR / "brand_assets" / safe_brand / f"{safe_brand}_presets.json"
    if not presets_path.is_file():
        raise HTTPException(status_code=404, detail=f"No presets for brand={safe_brand}")
    try:
        presets_data = json.loads(presets_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read presets: {exc}") from exc

    manifest_path = OUTPUT_DIR / "brand_assets" / safe_brand / "_manifest.json"
    scraped_at: str | None = None
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            scraped_at = manifest.get("scraped_at")
        except (json.JSONDecodeError, OSError):
            scraped_at = None

    resp = BrandPresetsResponse(
        brand=safe_brand,
        presets=presets_data if isinstance(presets_data, list) else [],
        scraped_at=scraped_at,
    )
    _PRESET_CACHE[safe_brand] = (resp, now)
    return resp
