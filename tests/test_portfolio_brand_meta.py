"""Tests for src/routers/portfolio.py brand-asset metadata enrichment.

Covers:
- _load_brand_info reads info.json correctly + caches.
- _brand_meta_for returns empty tuple for non-brand paths.
- _brand_meta_for fills metadata from info.json when present.
- _brand_meta_for returns slug+brand only when info.json missing.
- get_brand_presets endpoint reads brand presets file.
- get_brand_presets returns 404 when presets file missing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

import pytest


@pytest.fixture
def brand_assets_root(tmp_path, monkeypatch) -> Iterator[Path]:
    """Create a fake OUTPUT_DIR with a fully populated brand_assets/momcozy tree."""
    output_dir = tmp_path / "output"
    momcozy = output_dir / "brand_assets" / "momcozy"
    pump = momcozy / "m5-smart"
    (pump / "images").mkdir(parents=True)
    (pump / "info.json").write_text(json.dumps({
        "slug": "m5-smart",
        "title": "Momcozy M5 Smart Wearable Breast Pump",
        "vendor": "momcozy",
        "type": "Breast Pump",
        "description": "App-controlled upgrade to our best-selling M5.",
        "usps": ["Hands-free", "App control"],
        "price": "$119.99",
        "source_url": "https://momcozy.com/products/m5-smart",
        "scene": "product_direct",
        "images": ["brand_assets/momcozy/m5-smart/images/01.jpg"],
        "scraped_at": "2026-05-09T18:17:25Z",
    }), encoding="utf-8")

    no_info = momcozy / "no-info-product"
    (no_info / "images").mkdir(parents=True)

    (momcozy / "momcozy_presets.json").write_text(json.dumps([
        {"id": "momcozy-m5-smart", "name": "M5 Smart", "scene": "product_direct"},
    ]), encoding="utf-8")
    (momcozy / "_manifest.json").write_text(json.dumps({
        "scraped_at": "2026-05-09T18:20:00Z",
        "products": [{"slug": "m5-smart"}],
        "failed": [],
    }), encoding="utf-8")

    from src import config as _config

    monkeypatch.setattr(_config, "OUTPUT_DIR", output_dir)

    import src.routers.portfolio as portfolio_mod

    monkeypatch.setattr(portfolio_mod, "OUTPUT_DIR", output_dir)
    portfolio_mod._load_brand_info.cache_clear()
    portfolio_mod._PRESET_CACHE.clear()

    yield output_dir

    portfolio_mod._load_brand_info.cache_clear()
    portfolio_mod._PRESET_CACHE.clear()


def test_load_brand_info_reads_json(brand_assets_root):
    from src.routers.portfolio import _load_brand_info

    info = _load_brand_info("momcozy", "m5-smart")
    assert info is not None
    assert info["title"] == "Momcozy M5 Smart Wearable Breast Pump"
    assert info["price"] == "$119.99"


def test_load_brand_info_missing_returns_none(brand_assets_root):
    from src.routers.portfolio import _load_brand_info

    assert _load_brand_info("momcozy", "no-info-product") is None
    assert _load_brand_info("momcozy", "nonexistent-slug") is None
    assert _load_brand_info("unknown-brand", "anything") is None


def test_brand_meta_non_brand_path_returns_empty(brand_assets_root):
    from src.routers.portfolio import _brand_meta_for

    meta = _brand_meta_for("seedance/s1_001.mp4")
    assert meta == (None, None, None, None, None, None)


def test_brand_meta_fills_from_info_json(brand_assets_root):
    from src.routers.portfolio import _brand_meta_for

    title, slug, brand, url, desc, price = _brand_meta_for(
        "brand_assets/momcozy/m5-smart/images/01.jpg"
    )
    assert title == "Momcozy M5 Smart Wearable Breast Pump"
    assert slug == "m5-smart"
    assert brand == "momcozy"
    assert url == "https://momcozy.com/products/m5-smart"
    assert desc and desc.startswith("App-controlled")
    assert price == "$119.99"


def test_brand_meta_missing_info_returns_partial(brand_assets_root):
    from src.routers.portfolio import _brand_meta_for

    title, slug, brand, url, desc, price = _brand_meta_for(
        "brand_assets/momcozy/no-info-product/images/01.jpg"
    )
    assert title is None
    assert slug == "no-info-product"
    assert brand == "momcozy"
    assert url is None
    assert desc is None
    assert price is None


@pytest.mark.asyncio
async def test_get_brand_presets_returns_data(brand_assets_root):
    from src.routers.portfolio import get_brand_presets

    resp = await get_brand_presets(brand="momcozy")
    assert resp.brand == "momcozy"
    assert len(resp.presets) == 1
    assert resp.presets[0]["id"] == "momcozy-m5-smart"
    assert resp.scraped_at == "2026-05-09T18:20:00Z"


@pytest.mark.asyncio
async def test_get_brand_presets_404_when_missing(brand_assets_root):
    from fastapi import HTTPException

    from src.routers.portfolio import get_brand_presets

    with pytest.raises(HTTPException) as exc_info:
        await get_brand_presets(brand="nonexistent")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_brand_presets_sanitizes_brand_arg(brand_assets_root):
    from fastapi import HTTPException

    from src.routers.portfolio import get_brand_presets

    with pytest.raises(HTTPException) as exc_info:
        await get_brand_presets(brand="../etc/passwd")
    assert exc_info.value.status_code == 404
