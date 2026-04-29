#!/usr/bin/env python3
"""Pre-cache 2 demo videos + 1 thumbnail using ffmpeg (no API keys needed).

Generates short, playable .mp4 files with text overlay so the frontend
Media Tab has real content to display during the leadership demo.

Usage:
    cd ~/project/hermes_evo/AI_vedio
    source .venv/bin/activate
    python scripts/prepare_demo_cache.py

Output:
    output/demo/product_direct_demo.mp4
    output/demo/brand_campaign_demo.mp4
    output/demo/thumbnail_demo.png
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Ensure output/demo exists
DEMO_DIR = Path("output/demo")
DEMO_DIR.mkdir(parents=True, exist_ok=True)

PRODUCT_VIDEO = DEMO_DIR / "product_direct_demo.mp4"
BRAND_VIDEO = DEMO_DIR / "brand_campaign_demo.mp4"
THUMBNAIL_IMG = DEMO_DIR / "thumbnail_demo.png"


def run_ffmpeg(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)


def generate_product_video() -> None:
    """5-sec product demo with text overlay."""
    print("Generating product_direct_demo.mp4 ...")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=#f5f5f7:s=720x1280:d=5",
        "-vf",
        (
            "drawtext=text='Wearable Breast Pump X1':"
            "fontcolor=#1d1d1f:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2-60,"
            "drawtext=text='Hands-free • Quiet • Hospital-grade':"
            "fontcolor=#86868b:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2+20"
        ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", "5",
        str(PRODUCT_VIDEO),
    ])
    print(f"  → {PRODUCT_VIDEO} ({PRODUCT_VIDEO.stat().st_size} bytes)")


def generate_brand_video() -> None:
    """5-sec brand campaign with text overlay."""
    print("Generating brand_campaign_demo.mp4 ...")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=#FFC0CB:s=720x1280:d=5",
        "-vf",
        (
            "drawtext=text='DemoBrand':"
            "fontcolor=#FFFFFF:fontsize=64:x=(w-text_w)/2:y=(h-text_h)/2-60,"
            "drawtext=text='Warm • Professional • Trusted':"
            "fontcolor=#FFFFFF:fontsize=36:x=(w-text_w)/2:y=(h-text_h)/2+30"
        ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", "5",
        str(BRAND_VIDEO),
    ])
    print(f"  → {BRAND_VIDEO} ({BRAND_VIDEO.stat().st_size} bytes)")


def generate_thumbnail() -> None:
    """1-sec static frame exported as PNG."""
    print("Generating thumbnail_demo.png ...")
    run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=#f5f5f7:s=1024x1792:d=1",
        "-vf",
        (
            "drawtext=text='Wearable Breast Pump X1':"
            "fontcolor=#1d1d1f:fontsize=56:x=(w-text_w)/2:y=(h-text_h)/2,"
            "drawtext=text='Tap to learn more →':"
            "fontcolor=#7CB342:fontsize=40:x=(w-text_w)/2:y=(h-text_h)/2+80"
        ),
        "-vframes", "1",
        str(THUMBNAIL_IMG),
    ])
    print(f"  → {THUMBNAIL_IMG} ({THUMBNAIL_IMG.stat().st_size} bytes)")


def main() -> int:
    print("Preparing demo cache (ffmpeg-based, no API keys required)...\n")

    generate_product_video()
    generate_brand_video()
    generate_thumbnail()

    print("\n✅ Demo cache ready.")
    print(f"   Serve via: http://localhost:8001/api/media/{PRODUCT_VIDEO.name}")
    print(f"   Serve via: http://localhost:8001/api/media/{BRAND_VIDEO.name}")
    print(f"   Serve via: http://localhost:8001/api/media/{THUMBNAIL_IMG.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
