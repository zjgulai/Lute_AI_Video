#!/usr/bin/env python3
"""Scrape momcozy.com top products into brand_assets library.

Run inside the backend container (has httpx, network egress):
  docker cp scripts/scrape_momcozy.py ai_video_backend:/tmp/
  docker exec -it ai_video_backend python /tmp/scrape_momcozy.py

Output layout:
  output/brand_assets/momcozy/
    momcozy_presets.json               # TEMPLATE_PRESETS shape for frontend
    _manifest.json                     # audit trail: URLs, timestamps, failures
    {product_slug}/
      info.json                        # {title, usps, description, source_url, ...}
      images/01.webp, 02.webp, ...     # product hero images from Shopify .js API

Contract with src/routers/portfolio.py:
- CATEGORIES must map "brand_assets" → ("brand_assets", "external_scrape")
- kind must resolve to "brand_kit" so AssetPicker shows these under
  /api/portfolio/?kind=brand_kit

Data sources (momcozy.com is a Shopify store):
- <url>.js            — structured JSON: title, price, tags, images[], media[]
- <url> HTML          — only used to grab <meta property="og:description">
                         and <meta name="description"> for human-readable copy

Idempotent: skips cached products unless --force.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

OUTPUT_DIR = Path(os.environ.get("VIDEO_OUTPUT_DIR", "/app/output")).resolve()
BRAND_DIR = OUTPUT_DIR / "brand_assets" / "momcozy"

PRODUCT_URLS = [
    "https://momcozy.com/products/momcozy-kleanpal-pro-baby-bottle-washer",
    "https://momcozy.com/products/m5-smart-wearable-breast-pump-upgraded-with-app-control",
    "https://momcozy.com/products/momcozy-mobile-style-hands-free-breast-pump",
    "https://momcozy.com/products/momcozy-mobile-flow-hands-free-breast-pump",
    "https://momcozy.com/products/momcozy-wellness-1-warm-massage-wearable-breast-pump-w1",
    "https://momcozy.com/products/momcozy-5-inch-dual-mode-smart-baby-monitor-with-2-camera-bm04",
    "https://momcozy.com/products/momcozy-2-in-1-electric-baby-swing",
    "https://momcozy.com/products/2-in-1-spray-suction-electric-nasal-aspirator",
    "https://momcozy.com/products/momcozy-ergowrap-postpartum-belly-band",
    "https://momcozy.com/products/momcozy-bellyembrace-maternity-belly-band",
    "https://momcozy.com/products/portable-milk-warmer-22oz-cooler-on-the-go-bundle",
    "https://momcozy.com/products/momcozy-pro-collagen-belly-firming-moisturizer",
]

USER_AGENT = "MomcozyBrandAssetBot/1.0 (+https://momcozy.com; first-party-crawler)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json"}

RATE_LIMIT_SECONDS = 1.0

SCENE_BY_KEYWORD = {
    "pump": "product_direct",
    "bottle": "product_direct",
    "washer": "product_direct",
    "monitor": "product_direct",
    "swing": "brand_vlog",
    "belly": "product_direct",
    "warmer": "product_direct",
    "aspirator": "product_direct",
    "moisturizer": "product_direct",
    "pillow": "product_direct",
    "bra": "product_direct",
}


def slug_from_url(url: str) -> str:
    m = re.search(r"/products/([^/?#]+)", url)
    return m.group(1) if m else hashlib.md5(url.encode()).hexdigest()[:12]


def fetch_product_json(client: httpx.Client, product_url: str) -> dict[str, Any] | None:
    try:
        r = client.get(product_url + ".js", headers=HEADERS, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            print(f"  ! {product_url}.js -> HTTP {r.status_code}", file=sys.stderr)
            return None
        return r.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        print(f"  ! {product_url}.js -> {exc}", file=sys.stderr)
        return None


def fetch_og_description(client: httpx.Client, product_url: str) -> str:
    try:
        r = client.get(product_url, headers=HEADERS, timeout=30, follow_redirects=True)
        if r.status_code != 200:
            return ""
        src = r.text
        m = re.search(r'<meta[^>]*property="og:description"[^>]*content="([^"]+)"', src)
        if m:
            return html_lib.unescape(m.group(1))
        m = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]+)"', src)
        if m:
            return html_lib.unescape(m.group(1))
    except httpx.HTTPError:
        pass
    return ""


def _absolutize(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def _upsize_shopify_url(url: str, width: int = 1200) -> str:
    """Shopify CDN supports ?width=N query — bump to get full-quality version.

    Strips any existing ?v=... cache-buster and appends ?width=N. We prefer a
    width param over version so the CDN resizes server-side; cache-buster is
    optional since the filename itself is content-addressed.
    """
    base = url.split("?")[0]
    return f"{base}?width={width}"


def download(client: httpx.Client, url: str, dest: Path, force: bool = False) -> bool:
    if dest.exists() and dest.stat().st_size > 1024 and not force:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = client.get(url, headers=HEADERS, timeout=60, follow_redirects=True)
        if r.status_code != 200:
            return False
        content = r.content
        if len(content) < 1024:
            return False
        dest.write_bytes(content)
        return True
    except httpx.HTTPError as exc:
        print(f"  ! download {url} -> {exc}", file=sys.stderr)
        return False


def infer_scene(title: str, tags: list[str]) -> str:
    haystack = (title + " " + " ".join(tags)).lower()
    for kw, scene in SCENE_BY_KEYWORD.items():
        if kw in haystack:
            return scene
    return "product_direct"


def price_display(price_cents: int | None) -> str:
    if not price_cents:
        return ""
    return f"${price_cents / 100:.2f}"


def derive_usps(title: str, tags: list[str], description: str) -> list[str]:
    """Build 3-6 short USPs from tags + sentence-split description."""
    usps: list[str] = []
    for tag in tags:
        t = tag.strip()
        if not t or len(t) > 60:
            continue
        if not re.match(r"^[a-zA-Z0-9]", t):
            continue
        usps.append(t.title() if t.islower() else t)
    for sentence in re.split(r"(?<=[.!?])\s+", description):
        s = sentence.strip()
        if 15 < len(s) < 140 and not s.startswith(("Click", "Shop", "Add to")):
            usps.append(s)
            if len(usps) >= 6:
                break
    seen = set()
    uniq: list[str] = []
    for u in usps:
        key = u.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(u)
    return uniq[:6]


def build_preset(slug: str, info: dict[str, Any]) -> dict[str, Any]:
    title = info["title"]
    usps = info.get("usps") or []
    key_features = "\n".join(usps[:5]) if usps else info.get("description", "")[:300]
    short_id = re.sub(r"[^a-z0-9-]", "", slug.lower())[:40]
    price_str = info.get("price", "")
    return {
        "id": f"momcozy-{short_id}",
        "name": title,
        "nameEn": title,
        "description": f"momcozy.com 官方产品页 {price_str}".strip(),
        "descriptionEn": f"Official momcozy.com product page {price_str}".strip(),
        "scene": info.get("scene", "product_direct"),
        "videoType": "product_explain",
        "values": {
            "product_name": title,
            "brand_name": "Momcozy",
            "key_features": key_features,
            "brand_voice": "温暖、真实、像妈妈之间分享 / warm, real, mom-to-mom sharing",
        },
    }


def process_product(client: httpx.Client, url: str, force: bool = False) -> dict[str, Any] | None:
    slug = slug_from_url(url)
    dest_root = BRAND_DIR / slug
    info_path = dest_root / "info.json"

    if info_path.exists() and not force:
        print(f"  [skip] {slug} (cached)")
        return json.loads(info_path.read_text())

    print(f"  ↓ {slug}")
    data = fetch_product_json(client, url)
    if not data:
        return None
    time.sleep(RATE_LIMIT_SECONDS / 2)

    description = fetch_og_description(client, url)
    time.sleep(RATE_LIMIT_SECONDS / 2)

    title = data.get("title", "Unknown Product")
    tags = data.get("tags") or []
    price_cents = data.get("price")
    price = price_display(price_cents)

    dest_root.mkdir(parents=True, exist_ok=True)
    (dest_root / "images").mkdir(exist_ok=True)

    image_urls = [_absolutize(u) for u in (data.get("images") or [])[:12]]

    image_paths: list[str] = []
    for i, u in enumerate(image_urls):
        ext = Path(u.split("?")[0]).suffix.lower() or ".jpg"
        upsized = _upsize_shopify_url(u, 1200)
        dest = dest_root / "images" / f"{i+1:02d}{ext}"
        if download(client, upsized, dest, force=force):
            image_paths.append(str(dest.relative_to(OUTPUT_DIR)))
        time.sleep(RATE_LIMIT_SECONDS / 2)

    usps = derive_usps(title, tags, description)

    info = {
        "slug": slug,
        "title": title,
        "vendor": data.get("vendor", "momcozy"),
        "type": data.get("type", ""),
        "description": description,
        "usps": usps,
        "tags": tags,
        "price": price,
        "source_url": url,
        "scene": infer_scene(title, tags),
        "images": image_paths,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    info_path.write_text(json.dumps(info, ensure_ascii=False, indent=2))
    print(f"  ✓ {slug}: {len(image_paths)} images, {len(usps)} USPs")
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Redownload / reparse even when cached")
    parser.add_argument("--urls", nargs="+", help="Override product URLs (default: built-in TOP list)")
    args = parser.parse_args()

    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    urls = args.urls or PRODUCT_URLS
    print(f"Target: {len(urls)} products → {BRAND_DIR}")

    manifest: dict[str, Any] = {
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "user_agent": USER_AGENT,
        "products": [],
        "failed": [],
    }
    presets: list[dict[str, Any]] = []

    with httpx.Client() as client:
        for url in urls:
            info = process_product(client, url, force=args.force)
            if info is None:
                manifest["failed"].append(url)
                continue
            manifest["products"].append({
                "slug": info["slug"],
                "title": info["title"],
                "source_url": info["source_url"],
                "n_images": len(info["images"]),
                "n_usps": len(info["usps"]),
            })
            presets.append(build_preset(info["slug"], info))
            time.sleep(RATE_LIMIT_SECONDS)

    (BRAND_DIR / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (BRAND_DIR / "momcozy_presets.json").write_text(json.dumps(presets, ensure_ascii=False, indent=2))

    print(f"\nDone. {len(manifest['products'])} ok / {len(manifest['failed'])} failed")
    print(f"Presets: {BRAND_DIR / 'momcozy_presets.json'}")
    return 0 if not manifest["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
