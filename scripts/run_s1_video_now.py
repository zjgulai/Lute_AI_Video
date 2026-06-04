#!/usr/bin/env python3
"""Generate video with user-specified product — unbuffered output for demo."""
import json
import sys
import time

import requests

API_BASE = "http://127.0.0.1:8001"
API_KEY = "ai_video_demo_2026"

PAYLOAD = {
    "product_catalog": {
        "name": "Trunk Baby Organizer",
        "product_name": "Trunk Baby Organizer",
        "usps": ["quick grab access", "5 clear compartments", "stays stable in car", "collapsible"],
        "category": "Baby",
        "usage_scenario": "Car trunk, family outings",
        "pain_points": ["Trunk chaos after one trip", "Cannot find items when needed"],
        "target_audience": "New parents 25-35, dual-income families",
        "competitor_context": ["Generic plastic bins", "Soft-sided organizers"]
    },
    "brand_guidelines": {
        "brand_name": "Momcozy",
        "tone_of_voice": {
            "archetype": "Caregiver",
            "keywords": ["warm", "empowering"],
            "do_examples": ["Family outings should feel easier"],
            "dont_examples": ["Revolutionary organizing technology"]
        }
    },
    "target_platforms": ["tiktok", "shopify"],
    "target_languages": ["en"],
    "video_duration": 30,
    "enable_media_synthesis": True,
}

print(f"[{time.strftime('%H:%M:%S')}] Starting video generation...")
print(f"[{time.strftime('%H:%M:%S')}] Product: Trunk Baby Organizer")
print(f"[{time.strftime('%H:%M:%S')}] Duration: 30s")
print("-" * 50, flush=True)

try:
    r = requests.post(
        f"{API_BASE}/scenario/s1",
        headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        json=PAYLOAD,
        timeout=600,
    )
except requests.exceptions.ConnectionError:
    print("ERROR: Backend not running on port 8001", flush=True)
    sys.exit(1)

print(f"[{time.strftime('%H:%M:%S')}] Response status: {r.status_code}", flush=True)

try:
    data = r.json()
except Exception:
    print(f"ERROR: Invalid response: {r.text[:200]}", flush=True)
    sys.exit(1)

out = "/tmp/s1_video_momcozy.json"
with open(out, "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(json.dumps(data, indent=2, ensure_ascii=False))
print("-" * 50, flush=True)
print(f"[{time.strftime('%H:%M:%S')}] Saved to: {out}", flush=True)

if data.get("success"):
    label = data.get("label", "unknown")
    print(f"[{time.strftime('%H:%M:%S')}] DONE! Label: {label}", flush=True)
    print(f"Video file: /Users/pray/project/hermes_evo/AI_vedio/output/renders/{label}.mp4", flush=True)
else:
    print(f"[{time.strftime('%H:%M:%S')}] FAILED: {data.get('error', 'unknown error')}", flush=True)
