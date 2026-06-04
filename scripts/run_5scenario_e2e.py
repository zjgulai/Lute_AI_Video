#!/usr/bin/env python3
"""Production 5-scenario non-demo E2E runner.

Uses submit+poll pattern to avoid HTTP timeout on long pipelines.
Serial execution to avoid LLM rate limit conflicts.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Production uses self-signed cert — skip verification
VERIFY_SSL = False

API_BASE = "https://101.34.52.232/api"
API_KEY = "ai_video_demo_2026"

POLL_INTERVAL = 30.0
MAX_POLL_MINUTES = 45

# ── Payload fixtures (minimal valid, derived from tests + D2 report) ──

S1_PAYLOAD = {
    "product_catalog": {
        "product_name": "Hands-Free Breast Pump",
        "usps": [
            "Silent motor under 40dB",
            "180ml large capacity",
            "Wireless & hands-free",
        ],
        "pain_points": [
            "Loud pumps wake the baby",
            "Tangled wires restrict movement",
        ],
        "usage_scenario": "Bedroom, during baby nap time",
        "target_audience": "New moms aged 25-35, active on TikTok",
        "category": "Baby Feeding",
        "competitor_context": "Most pumps are bulky and noisy",
    },
    "brand_guidelines": {
        "brand_name": "MomEase",
        "tone_of_voice": {
            "archetype": "Supportive Friend",
            "keywords": ["gentle", "empowering", "real"],
        },
    },
    "target_platforms": ["tiktok"],
    "video_duration": 30,
    "enable_media_synthesis": True,
}

S2_PAYLOAD = {
    "brand_package": {
        "brand_name": "MomEase",
        "brand_story": "Empowering new mothers with gentle, innovative solutions",
        "visual_identity": {
            "primary_color": "#D75C70",
            "secondary_color": "#FDF8F6",
            "font_family": "Inter",
        },
        "tone_of_voice": {
            "archetype": "Supportive Friend",
            "keywords": ["gentle", "empowering", "real"],
        },
        "product_lines": ["wearable breast pump", "bottle warmer"],
    },
    "target_platforms": ["tiktok"],
    "video_duration": 30,
}

S3_PAYLOAD = {
    "video_url": "https://www.tiktok.com/@mama.tips/video/7234567890123456789",
    "product": {
        "name": "LactFit X1 Wearable Pump",
        "usps": ["Ultra-quiet 38dB motor", "Hands-free design", "180ml capacity"],
        "brand_name": "LactFit",
        "category": "breast pump",
    },
    "influencer_name": "MamaTips",
    "brief_id": "RMX-2026-001",
    "video_duration": 30,
}

S4_PAYLOAD = {
    "footage_assets": [
        {"filename": "scene1.mp4", "duration": 15, "description": "Close-up of product"},
        {"filename": "scene2.mp4", "duration": 20, "description": "Lifestyle usage shot"},
    ],
    "product_info": {
        "name": "LactFit Wearable Breast Pump X1",
        "brand_name": "LactFit",
        "category": "Baby Feeding",
        "usps": ["Silent", "Hands-free", "Large capacity"],
    },
    "topic": "Working mom daily routine with wearable pump",
    "target_platforms": ["tiktok"],
}

S5_PAYLOAD = {
    "brand_id": "momcozy",
    "product_sku": {
        "name": "LactFit Wearable Breast Pump X1",
        "shortName": "X1 Pump",
        "views": [
            {"label": "主视图", "title": "Front View", "usage_note": "Hero shot"},
            {"label": "45度视图", "title": "Angle View", "usage_note": "Detail shot"},
            {"label": "侧视图", "title": "Side View", "usage_note": "Profile"},
            {"label": "底视图", "title": "Bottom View", "usage_note": "Base detail"},
            {"label": "佩戴图", "title": "Worn View", "usage_note": "In-use shot"},
            {"label": "包装图", "title": "Package View", "usage_note": "Box shot"},
        ],
    },
    "scene_id": "living-room",
    "selected_models": [
        {"name": "Sarah", "role": "new mom", "description": "28yo, first-time mother"},
    ],
    "story_description": "A busy working mom preparing for her day, showing how the wearable pump fits seamlessly into her morning routine",
    "video_duration": 30,
}

FAST_PAYLOAD = {
    "user_prompt": "Create a 5-second product highlight video for a hands-free breast pump. Show the product being used while mom works at her desk.",
    "duration": 5,
    "enable_tts": True,
}


# ── Runner ──

def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    sys.stdout.flush()


def submit_scenario(scenario: str, payload: dict) -> str:
    url = f"{API_BASE}/scenario/{scenario}/submit"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    log(f"Submitting {scenario}...")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30, verify=VERIFY_SSL)
        resp.raise_for_status()
        data = resp.json()
        label = data.get("label", "")
        log(f"  label={label}")
        return label
    except requests.exceptions.HTTPError as e:
        log(f"  Submit failed: {e}")
        if e.response is not None:
            try:
                detail = e.response.json()
                log(f"  Response: {json.dumps(detail, ensure_ascii=False)[:500]}")
            except Exception:
                log(f"  Response: {e.response.text[:500]}")
        raise


def poll_status(scenario: str, label: str) -> dict:
    url = f"{API_BASE}/scenario/{scenario}/status/{label}"
    headers = {"X-API-Key": API_KEY}
    resp = requests.get(url, headers=headers, timeout=30, verify=VERIFY_SSL)
    resp.raise_for_status()
    return resp.json()


def wait_for_completion(scenario: str, label: str) -> dict:
    max_polls = int(MAX_POLL_MINUTES * 60 / POLL_INTERVAL)
    status_data: dict = {}
    for i in range(max_polls):
        time.sleep(POLL_INTERVAL)
        status_data = poll_status(scenario, label)
        status = status_data.get("status", "unknown")
        progress = status_data.get("progress", 0)
        current = status_data.get("current_step", "")
        log(f"  [{i+1}] status={status} progress={progress:.0%} current={current}")

        if status in ("completed", "error"):
            return status_data

        errors = status_data.get("errors", [])
        if errors:
            log(f"  errors={errors}")

    log(f"  TIMEOUT after {MAX_POLL_MINUTES} min")
    return status_data


def verify_video_exists(label: str) -> tuple[bool, str]:
    """Check if final video exists in container output dir."""
    import subprocess
    cmd = [
        "ssh", "-i", "/Users/pray/project/hermes_evo/AI_vedio/ai_video.pem",
        "-o", "StrictHostKeyChecking=no",
        "ubuntu@101.34.52.232",
        f"sudo docker exec lighthouse-backend-1 find /app/output/renders -name '*{label}*.mp4' -ls 2>/dev/null || true",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    output = result.stdout.strip()
    if output:
        # Extract file size from ls output
        parts = output.split()
        size = parts[6] if len(parts) > 6 else "?"
        return True, size
    return False, "0"


def run_fast_mode(payload: dict) -> dict:
    """Fast Mode uses blocking /fast/generate endpoint."""
    log(f"\n{'='*50}")
    log("SCENARIO Fast Mode")
    log(f"{'='*50}")
    start = time.time()
    url = f"{API_BASE}/fast/generate"
    headers = {"Content-Type": "application/json", "X-API-Key": API_KEY}
    log("Submitting fast/generate...")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=1800, verify=VERIFY_SSL)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        log(f"  HTTP error: {e}")
        data = {"success": False, "error": str(e)}
        if e.response is not None:
            try:
                data = e.response.json()
            except Exception:
                data["raw_response"] = e.response.text[:500]
    except Exception as e:
        log(f"  Request error: {e}")
        data = {"success": False, "error": str(e)}

    elapsed = time.time() - start

    status = "completed" if data.get("success") else "error"
    final_path = data.get("video_path", "")
    label = Path(final_path).stem if final_path else ""
    exists, size = verify_video_exists(label) if label else (False, "0")

    summary = {
        "scenario": "fast",
        "name": "Fast Mode",
        "label": label,
        "status": status,
        "elapsed_seconds": round(elapsed, 1),
        "progress": 1.0 if status == "completed" else 0,
        "errors": [data.get("error", ""), data.get("detail", "")] if status == "error" else [],
        "final_video_path": final_path,
        "video_exists": exists,
        "video_size": size,
    }
    log(f"  RESULT: status={status} elapsed={elapsed:.0f}s video_exists={exists} size={size}")
    return summary


def run_scenario(name: str, scenario: str, payload: dict) -> dict:
    log(f"\n{'='*50}")
    log(f"SCENARIO {name} ({scenario})")
    log(f"{'='*50}")
    start = time.time()
    label = submit_scenario(scenario, payload)
    result = wait_for_completion(scenario, label)
    elapsed = time.time() - start

    status = result.get("status", "unknown")
    errors = result.get("errors", [])
    progress = result.get("progress", 0)

    # Try to extract final video path from result or steps
    result_dict = result.get("result") or {}
    final_path = ""
    if isinstance(result_dict, dict):
        final_path = result_dict.get("final_video_path", "")
    if not final_path and isinstance(result_dict, dict) and "assemble_final" in (result_dict.get("steps") or {}):
        assemble = result_dict.get("steps", {}).get("assemble_final", {}).get("output")
        if isinstance(assemble, dict):
            final_path = assemble.get("video_path", "")
        elif isinstance(assemble, (list, tuple)) and len(assemble) > 0:
            final_path = str(assemble[0])

    exists, size = verify_video_exists(label) if label else (False, "0")

    summary = {
        "scenario": scenario,
        "name": name,
        "label": label,
        "status": status,
        "elapsed_seconds": round(elapsed, 1),
        "progress": progress,
        "errors": errors,
        "final_video_path": final_path,
        "video_exists": exists,
        "video_size": size,
    }
    log(f"  RESULT: status={status} elapsed={elapsed:.0f}s video_exists={exists} size={size}")
    if errors:
        log(f"  ERRORS: {json.dumps(errors, ensure_ascii=False)[:500]}")
    return summary


def main() -> None:
    out_dir = Path("/Users/pray/project/hermes_evo/AI_vedio/tmp/outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"5scenario-e2e-{timestamp}.json"

    results = []

    scenarios = [
        ("Product Direct", "s1", S1_PAYLOAD),
        ("Brand Campaign", "s2", S2_PAYLOAD),
        ("Influencer Remix", "s3", S3_PAYLOAD),
        ("Live Shoot", "s4", S4_PAYLOAD),
        ("Brand VLOG", "s5", S5_PAYLOAD),
    ]

    total_start = time.time()

    # Run Fast Mode first (blocking, ~50s)
    summary = run_fast_mode(FAST_PAYLOAD)
    results.append(summary)

    # Run S1-S5 serially (submit+poll)
    for name, scenario, payload in scenarios:
        try:
            summary = run_scenario(name, scenario, payload)
            results.append(summary)
        except Exception as e:
            log(f"  EXCEPTION: {e}")
            results.append({
                "scenario": scenario,
                "name": name,
                "label": "",
                "status": "error",
                "elapsed_seconds": 0,
                "progress": 0,
                "errors": [str(e)],
                "final_video_path": "",
                "video_exists": False,
                "video_size": "0",
            })
        # Save incremental results after each scenario
        with open(out_file, "w") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "total_elapsed_seconds": round(time.time() - total_start, 1),
                    "scenarios": results,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        # Early exit on error (configurable)
        if summary["status"] == "error":
            log("  ⚠️  Scenario failed — continuing with next (review logs)")

    total_elapsed = time.time() - total_start
    passed = sum(1 for r in results if r["status"] == "completed")
    log(f"\n{'='*50}")
    log(f"ALL DONE: {passed}/{len(results)} passed, total={total_elapsed:.0f}s")
    log(f"Report: {out_file}")
    log(f"{'='*50}")


if __name__ == "__main__":
    main()
