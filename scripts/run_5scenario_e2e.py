#!/usr/bin/env python3
"""Production 5-scenario smoke helper with explicit authorization and no-ops default.

Default mode is dry-run. Run requires explicit execution confirmation and non-demo
keys, so this script cannot accidentally trigger real token consumption.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_BASE_URL = "https://video.lute-tlz-dddd.top"
DEMO_API_KEY = "ai_video_demo_2026"
DEMO_KEY_WARNING = "demo key is rejected"
CONFIRM_ENV = "CONFIRM_P2_TOKEN_SMOKE"
RUN_TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"
REQUIRED_RUN_ENV = (
    ("API_KEY", "Production backend API key", True),
    ("PLAYWRIGHT_API_KEY", "Production Playwright backend API key", True),
    ("POYO_API_KEY", "Poyo account key", True),
    ("DEEPSEEK_API_KEY", "DeepSeek key", True),
    ("SILICONFLOW_API_KEY", "SiliconFlow key", True),
)

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "tmp" / "outputs"
POLL_INTERVAL_SECONDS = 30.0
MAX_POLL_MINUTES = 45
SUBMISSION_READBACK_DELAYS_SECONDS = (0.0, 1.0, 2.0, 5.0)

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

SCENARIO_MATRIX: dict[str, tuple[str, str, dict[str, Any]]] = {
    "fast": ("Fast Mode", "fast", FAST_PAYLOAD),
    "s1": ("Product Direct", "s1", S1_PAYLOAD),
    "s2": ("Brand Campaign", "s2", S2_PAYLOAD),
    "s3": ("Influencer Remix", "s3", S3_PAYLOAD),
    "s4": ("Live Shoot", "s4", S4_PAYLOAD),
    "s5": ("Brand VLOG", "s5", S5_PAYLOAD),
}


# ── Utilities ──

def resolve_api_base(base_url: str) -> str:
    return base_url.rstrip("/") + "/api"


def _mask(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _verify_ssl_for_url(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return not host.startswith("101.") and host not in {"localhost", "127.0.0.1"}


def _validate_execute_env(env: Mapping[str, str]) -> list[str]:
    errors: list[str] = []
    if env.get(CONFIRM_ENV) != "1":
        errors.append(f"{CONFIRM_ENV}=1 is required")
    if env.get(RUN_TOKEN_SMOKE_ENV) != "1":
        errors.append(f"{RUN_TOKEN_SMOKE_ENV}=1 is required")

    for key_name, _desc, reject_demo in REQUIRED_RUN_ENV:
        value = env.get(key_name, "")
        if not value:
            errors.append(f"{key_name} is required")
            continue
        if reject_demo and value == DEMO_API_KEY:
            errors.append(f"{key_name} must be non-demo key, rejected demo key")

    return errors


def _env_status_preview() -> list[str]:
    lines: list[str] = []
    required = {name: (desc, reject_demo) for name, desc, reject_demo in REQUIRED_RUN_ENV}
    current = os.environ
    for name, (description, reject_demo) in required.items():
        value = current.get(name, "")
        if not value:
            status = "MISSING"
        elif reject_demo and value == DEMO_API_KEY:
            status = "REJECTED demo key"
        else:
            status = f"set ({_mask(value)})"
        lines.append(f"- {name}: {status} — {description}")
    lines.append(
        f"- {CONFIRM_ENV}: {'set' if current.get(CONFIRM_ENV) == '1' else 'MISSING'} — Execution confirmation"
    )
    lines.append(
        f"- {RUN_TOKEN_SMOKE_ENV}: {'set' if current.get(RUN_TOKEN_SMOKE_ENV) == '1' else 'MISSING'} — Token smoke enable"
    )
    return lines


def build_run_command(*, base_url: str, scenarios: list[str], output: Path | None = None) -> str:
    selected = ",".join(scenarios)
    output_arg = f" --output {output}" if output else ""
    return (
        f"CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 API_KEY=<production-api-key> "
        f"PLAYWRIGHT_API_KEY=<production-api-key> POYO_API_KEY=<funded-poyo-key> "
        f"DEEPSEEK_API_KEY=<deepseek-key> SILICONFLOW_API_KEY=<siliconflow-key> "
        f"python scripts/run_5scenario_e2e.py --execute --base-url {base_url} "
        f"--scenario {selected}{output_arg}"
    )


def build_scenario_plan(scenarios: list[str] | None = None) -> list[tuple[str, str, dict[str, Any]]]:
    if not scenarios:
        return [
            (name, scenario_key, payload)
            for scenario_key, (name, scenario_key, payload) in SCENARIO_MATRIX.items()
        ]

    missing = [s for s in scenarios if s not in SCENARIO_MATRIX]
    if missing:
        raise ValueError(f"invalid scenario(s): {', '.join(missing)}")

    return [(SCENARIO_MATRIX[s][0], SCENARIO_MATRIX[s][1], SCENARIO_MATRIX[s][2]) for s in scenarios]


# ── Runner core ──

def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")
    sys.stdout.flush()


def submit_scenario(
    *,
    api_base: str,
    scenario: str,
    payload: dict[str, Any],
    api_key: str,
    idempotency_key: str,
    verify_ssl: bool,
    timeout_seconds: float = 30.0,
) -> str:
    url = f"{api_base}/scenario/{scenario}/submit"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": api_key,
        "Idempotency-Key": idempotency_key,
    }
    log(f"Submitting {scenario}...")
    ambiguous_error: Exception | None = None
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
            verify=verify_ssl,
        )
        if resp.status_code >= 500:
            ambiguous_error = requests.HTTPError(response=resp)
        else:
            resp.raise_for_status()
            try:
                data = resp.json()
            except ValueError as exc:
                ambiguous_error = exc
            else:
                label = data.get("label", "")
                if label:
                    log(f"  label={label}")
                    return str(label)
                ambiguous_error = ValueError(f"submit response missing label for {scenario}")
    except requests.HTTPError:
        raise
    except requests.RequestException as exc:
        ambiguous_error = exc

    if ambiguous_error is None:
        raise RuntimeError("submit response was neither accepted nor rejected")

    log("  submit response was ambiguous; checking durable submission state")
    label = readback_scenario_submission(
        api_base=api_base,
        scenario=scenario,
        api_key=api_key,
        idempotency_key=idempotency_key,
        verify_ssl=verify_ssl,
        timeout_seconds=timeout_seconds,
    )
    if label:
        log(f"  recovered label={label}")
        return label
    raise ambiguous_error


def readback_scenario_submission(
    *,
    api_base: str,
    scenario: str,
    api_key: str,
    idempotency_key: str,
    verify_ssl: bool,
    timeout_seconds: float = 30.0,
) -> str | None:
    """Recover an ambiguous submit with bounded GETs and no second POST."""

    url = f"{api_base}/submissions/idempotency"
    headers = {
        "X-API-Key": api_key,
        "Idempotency-Key": idempotency_key,
    }
    for delay in SUBMISSION_READBACK_DELAYS_SECONDS:
        if delay:
            time.sleep(delay)
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout_seconds,
                verify=verify_ssl,
            )
        except requests.RequestException:
            continue
        if response.status_code == 404 or response.status_code >= 500:
            continue
        response.raise_for_status()
        data = response.json()
        if data.get("resource_type") != "scenario" or data.get("scenario") != scenario:
            raise ValueError("submission readback returned an unexpected resource")
        submit_response = data.get("submit_response") or {}
        label = data.get("resource_id") or (
            submit_response.get("label") if isinstance(submit_response, dict) else None
        )
        if label:
            return str(label)
    return None


def poll_status(
    *,
    api_base: str,
    scenario: str,
    label: str,
    api_key: str,
    verify_ssl: bool,
    timeout_seconds: float = 30.0,
) -> dict:
    url = f"{api_base}/scenario/{scenario}/status/{label}"
    headers = {"X-API-Key": api_key}
    resp = requests.get(url, headers=headers, timeout=timeout_seconds, verify=verify_ssl)
    resp.raise_for_status()
    return resp.json()


def wait_for_completion(
    *,
    api_base: str,
    scenario: str,
    label: str,
    api_key: str,
    verify_ssl: bool,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    max_poll_minutes: int = MAX_POLL_MINUTES,
) -> dict:
    max_polls = int(max_poll_minutes * 60 / poll_interval)
    status_data: dict = {}
    for i in range(max_polls):
        time.sleep(poll_interval)
        status_data = poll_status(
            api_base=api_base,
            scenario=scenario,
            label=label,
            api_key=api_key,
            verify_ssl=verify_ssl,
        )
        status = status_data.get("status", "unknown")
        progress = status_data.get("progress", 0)
        current = status_data.get("current_step", "")
        log(f"  [{i+1}] status={status} progress={progress:.0%} current={current}")

        if status in ("completed", "error", "failed", "recovery_required"):
            return status_data

        errors = status_data.get("errors", [])
        if errors:
            log(f"  errors={errors}")

    log(f"  TIMEOUT after {max_poll_minutes} min")
    return status_data


def verify_video_exists(
    *,
    label: str,
    enabled: bool,
    remote_host: str = "ubuntu@101.34.52.232",
    remote_container: str = "lighthouse-backend-1",
    remote_key: str = Path(__file__).resolve().parents[1] / "ai_video.pem",
    remote_path: str = "/app/output/renders",
    ssh_timeout: int = 30,
) -> tuple[bool, str]:
    """Check final video existence in remote render directory.

    Disabled by default (enabled=False) to keep command smoke safe in local/dev runs.
    """
    if not enabled:
        return False, "0"

    cmd = [
        "ssh",
        "-i",
        str(remote_key),
        "-o",
        "StrictHostKeyChecking=no",
        remote_host,
        f"sudo docker exec {remote_container} find {remote_path} -name '*{label}*.mp4' -ls 2>/dev/null || true",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=ssh_timeout)
    output = result.stdout.strip()
    if output:
        parts = output.split()
        size = parts[6] if len(parts) > 6 else "?"
        return True, size
    return False, "0"


def run_fast_mode(*, api_base: str, payload: dict[str, Any], api_key: str, verify_ssl: bool) -> dict[str, Any]:
    """Fast Mode uses blocking /fast/generate endpoint."""
    log(f"\n{'='*50}")
    log("SCENARIO Fast Mode")
    log(f"{'='*50}")
    start = time.time()
    url = f"{api_base}/fast/generate"
    headers = {"Content-Type": "application/json", "X-API-Key": api_key}
    log("Submitting fast/generate...")
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=1800, verify=verify_ssl)
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
    exists, size = (False, "0")
    if label:
        exists, size = verify_video_exists(label=label, enabled=False)

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


def run_scenario(
    *,
    name: str,
    scenario: str,
    payload: dict[str, Any],
    api_base: str,
    api_key: str,
    verify_ssl: bool,
    poll_interval: float,
    max_poll_minutes: int,
    verify_remote_video: bool = False,
) -> dict[str, Any]:
    log(f"\n{'='*50}")
    log(f"SCENARIO {name} ({scenario})")
    log(f"{'='*50}")
    start = time.time()
    idempotency_key = f"scenario-smoke-{scenario}-{uuid.uuid4()}"
    label = submit_scenario(
        api_base=api_base,
        scenario=scenario,
        payload=payload,
        api_key=api_key,
        idempotency_key=idempotency_key,
        verify_ssl=verify_ssl,
    )
    result = wait_for_completion(
        api_base=api_base,
        scenario=scenario,
        label=label,
        api_key=api_key,
        verify_ssl=verify_ssl,
        poll_interval=poll_interval,
        max_poll_minutes=max_poll_minutes,
    )
    elapsed = time.time() - start

    status = result.get("status", "unknown")
    errors = result.get("errors", [])
    progress = result.get("progress", 0)

    # Try to extract final video path from result
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

    exists, size = verify_video_exists(label=label, enabled=verify_remote_video)

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Production API base url")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIO_MATRIX.keys()),
        help="Scenario key to run. Repeat for multiple. Default runs all.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Output directory for run summary JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print execution plan only. Default when --execute is not set.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute all selected scenarios against production endpoints.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=POLL_INTERVAL_SECONDS,
        help="Scenario polling interval in seconds.",
    )
    parser.add_argument(
        "--max-poll-minutes",
        type=int,
        default=MAX_POLL_MINUTES,
        help="Scenario poll timeout in minutes.",
    )
    parser.add_argument(
        "--verify-remote-video",
        action="store_true",
        help="Enable remote container video existence check.",
    )
    return parser.parse_args()


def _print_dry_run(args: argparse.Namespace) -> None:
    api_base = resolve_api_base(args.base_url)
    scenario_keys = args.scenario or []
    plan = build_scenario_plan(scenario_keys)
    out_dir = Path(args.output_dir)

    print("5-scenario production smoke checker — DRY RUN")
    print("No commands were executed.")
    print(f"Target API: {api_base}")
    print(f"Remote video verify (default): {'disabled' if not args.verify_remote_video else 'enabled'}")
    print("")
    print("Planned steps:")
    for idx, (_, scenario, _payload) in enumerate(plan, start=1):
        print(f"{idx}. {scenario.upper()}")

    print("Required before execution:")
    for line in _env_status_preview():
        print(line)

    print("")
    print("Run command:")
    print(build_run_command(base_url=args.base_url, scenarios=[scenario for _, scenario, _ in plan], output=out_dir / "5scenario-e2e-preview.json"))
    print("")


def _run(args: argparse.Namespace) -> int:
    api_key = os.getenv("API_KEY", "")
    if not api_key:
        raise RuntimeError("API_KEY is required for execute mode")

    env_errors = _validate_execute_env(os.environ)
    if env_errors:
        for reason in env_errors:
            print(f"ERROR: {reason}", file=sys.stderr)
        return 2

    api_base = resolve_api_base(args.base_url)
    verify_ssl = _verify_ssl_for_url(args.base_url)
    plan = build_scenario_plan(args.scenario)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"5scenario-e2e-{timestamp}.json"

    results: list[dict[str, Any]] = []
    total_start = time.time()

    for name, scenario, payload in plan:
        try:
            if scenario == "fast":
                summary = run_fast_mode(api_base=api_base, payload=payload, api_key=api_key, verify_ssl=verify_ssl)
            else:
                summary = run_scenario(
                    name=name,
                    scenario=scenario,
                    payload=payload,
                    api_base=api_base,
                    api_key=api_key,
                    verify_ssl=verify_ssl,
                    poll_interval=args.poll_interval,
                    max_poll_minutes=args.max_poll_minutes,
                    verify_remote_video=args.verify_remote_video,
                )
            results.append(summary)
        except Exception as exc:
            log(f"  EXCEPTION: {exc}")
            results.append(
                {
                    "scenario": scenario,
                    "name": name,
                    "label": "",
                    "status": "error",
                    "elapsed_seconds": 0,
                    "progress": 0,
                    "errors": [str(exc)],
                    "final_video_path": "",
                    "video_exists": False,
                    "video_size": "0",
                }
            )

        with open(out_file, "w") as f:
            json.dump(
                {
                    "timestamp": timestamp,
                    "base_url": args.base_url,
                    "api_base": api_base,
                    "total_elapsed_seconds": round(time.time() - total_start, 1),
                    "scenarios": results,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        if results[-1]["status"] == "error":
            log("  ⚠️  Scenario failed — continuing with next (review logs)\n")

    total_elapsed = time.time() - total_start
    passed = sum(1 for r in results if r["status"] == "completed")
    log(f"\n{'='*50}")
    log(f"ALL DONE: {passed}/{len(results)} passed, total={total_elapsed:.0f}s")
    log(f"Report: {out_file}")
    log(f"{'='*50}")
    return 0


def main() -> int:
    args = _parse_args()
    if not args.execute:
        _print_dry_run(args)
        return 0

    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())
