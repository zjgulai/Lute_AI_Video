#!/usr/bin/env python3
"""Trigger S1 Product Direct pipeline to generate a complete video.

Usage:
    cd /Users/pray/project/hermes_evo/AI_vedio
    source .venv/bin/activate
    python3 scripts/run_s1_video.py

Output: prints JSON response and saves to /tmp/s1_video_response.json
"""

import json
import sys
import time

import requests

API_BASE = "http://127.0.0.1:8001"
API_KEY = "ai_video_demo_2026"

PRODUCT = {
    "name": "Wearable Breast Pump",
    "product_name": "Hands-Free Breast Pump",
    "usps": [
        "Silent motor under 40dB",
        "180ml large capacity",
        "Wireless & hands-free",
    ],
    "pain_points": [
        "Loud pumps wake the baby",
        "Tangled wires restrict movement",
        "Small capacity needs frequent emptying",
    ],
    "usage_scenario": "Bedroom, during baby nap time",
    "target_audience": "New moms aged 25-35, active on TikTok",
    "category": "Baby Feeding",
    "competitor_context": "Most pumps are bulky and noisy",
}

BRAND = {
    "brand_name": "MomEase",
    "tone_of_voice": {
        "archetype": "Supportive Friend",
        "keywords": ["gentle", "empowering", "real"],
    },
}

PAYLOAD = {
    "product_catalog": PRODUCT,
    "brand_guidelines": BRAND,
    "target_platforms": ["tiktok", "shopify"],
    "video_duration": 30,
    "enable_media_synthesis": True,
}


def main():
    url = f"{API_BASE}/scenario/s1"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": API_KEY,
    }

    print(f"[{time.strftime('%H:%M:%S')}] POST {url}")
    print(f"[{time.strftime('%H:%M:%S')}] Video duration: {PAYLOAD['video_duration']}s")
    print(f"[{time.strftime('%H:%M:%S')}] Product: {PRODUCT['product_name']}")
    print("-" * 50)

    try:
        r = requests.post(url, headers=headers, json=PAYLOAD, timeout=600)
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to backend. Is uvicorn running on port 8001?")
        print("Run: cd /Users/pray/project/hermes_evo/AI_vedio && uvicorn src.api:app --reload --port 8001")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print("ERROR: Request timed out after 600s. Pipeline may still be running in background.")
        sys.exit(1)

    try:
        data = r.json()
    except json.JSONDecodeError:
        print(f"ERROR: Invalid JSON response (status {r.status_code}):")
        print(r.text[:500])
        sys.exit(1)

    # Save response
    out_path = "/tmp/s1_video_response.json"
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("-" * 50)
    print(f"[{time.strftime('%H:%M:%S')}] Response saved to: {out_path}")

    if data.get("success"):
        label = data.get("label", "unknown")
        print(f"[{time.strftime('%H:%M:%S')}] Pipeline completed! Label: {label}")
        print(f"[{time.strftime('%H:%M:%S')}] Check output video:")
        print(f"  ls -lh /Users/pray/project/hermes_evo/AI_vedio/output/renders/{label}*.mp4")
    else:
        print(f"[{time.strftime('%H:%M:%S')}] Pipeline failed or returned errors.")
        if "error" in data:
            print(f"  Error: {data['error']}")


if __name__ == "__main__":
    main()
