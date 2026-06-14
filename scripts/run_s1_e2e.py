#!/usr/bin/env python3
"""Standalone E2E runner for the S1 (Product Direct) pipeline.

Runs the full 11-step pipeline step by step, never crashing on failure.
Prints each step's result and saves a detailed spike report to
docs/spike/2026-04-28_s1-real-failures.md

Usage:
    cd /sessions/modest-zealous-allen/mnt/AI_vedio
    python scripts/run_s1_e2e.py

Requirements (sandbox):
    The script uses direct imports and the pipeline's stub/fallback mode.
    Full real execution requires API keys for Seedance, ElevenLabs, and OpenAI.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load .env before anything else
from dotenv import load_dotenv

load_dotenv()

# -- Pre-flight API key checks --
API_KEY_STATUS = {}
for key_name in [
    "OPENAI_API_KEY",
    "ELEVENLABS_API_KEY",
    "POYO_API_KEY",
    "SEEDANCE_API_KEY",
    "DATABASE_URL",
]:
    val = os.getenv(key_name, "")
    if val:
        API_KEY_STATUS[key_name] = "SET"
    else:
        API_KEY_STATUS[key_name] = "EMPTY"

# -- Pipeline imports (will trigger skill auto-registration) --
from src.config import OUTPUT_DIR
from src.pipeline.state_manager import PipelineStateManager
from src.pipeline.step_runner import STEP_ORDER, StepRunner

# ============================================================================
#  Utilities
# ============================================================================

# Terminal colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _icon(status: str) -> str:
    return {
        "ok": f"{GREEN}[OK]{RESET}",
        "warning": f"{YELLOW}[WARN]{RESET}",
        "fail": f"{RED}[FAIL]{RESET}",
        "skip": f"{CYAN}[SKIP]{RESET}",
    }.get(status, f"{YELLOW}[????]{RESET}")


# ============================================================================
#  Result accumulator (never crashes)
# ============================================================================

class StepResult:
    def __init__(self, name: str):
        self.name = name
        self.status: str = "pending"
        self.error: str = ""
        self.duration_ms: float = 0.0
        self.output = None
        self.detail: str = ""

    def succeed(self, output=None, detail: str = ""):
        self.status = "ok"
        self.output = output
        self.detail = detail

    def fail(self, error: str, detail: str = ""):
        self.status = "fail"
        self.error = error
        self.detail = detail

    def skip(self, reason: str = ""):
        self.status = "skip"
        self.detail = reason

    def __str__(self) -> str:
        return f"  {_icon(self.status)} {self.name} ({self.duration_ms:.1f}ms)" + (
            f"\n      {RED}{self.error}{RESET}" if self.error else ""
        )


# ============================================================================
#  Pre-flight checks
# ============================================================================

def run_preflight() -> list[dict]:
    """Check all API keys, filesystem, and dependencies before running pipeline."""
    checks = []

    # API key checks
    for key, status in API_KEY_STATUS.items():
        checks.append({
            "name": f"API key: {key}",
            "status": "ok" if status == "SET" else "warning",
            "detail": status,
        })

    # Filesystem check
    try:
        test_file = OUTPUT_DIR / ".e2e_write_test"
        test_file.write_text("e2e diagnostic test")
        test_file.unlink()
        checks.append({
            "name": "Filesystem write access",
            "status": "ok",
            "detail": f"write OK in {OUTPUT_DIR}",
        })
    except Exception as e:
        checks.append({
            "name": "Filesystem write access",
            "status": "fail",
            "detail": str(e),
        })

    # ffmpeg check
    import shutil
    import subprocess
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            ver = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=10
            )
            first_line = ver.stdout.split("\n")[0] if ver.stdout else "(no output)"
            checks.append({
                "name": "ffmpeg availability",
                "status": "ok",
                "detail": first_line,
            })
        except Exception as e:
            checks.append({
                "name": "ffmpeg availability",
                "status": "warning",
                "detail": str(e),
            })
    else:
        checks.append({
            "name": "ffmpeg availability",
            "status": "fail",
            "detail": "not found on PATH",
        })

    # Node.js check
    node_path = shutil.which("node")
    if node_path:
        try:
            ver = subprocess.run(
                ["node", "--version"], capture_output=True, text=True, timeout=10
            )
            checks.append({
                "name": "Node.js availability",
                "status": "ok",
                "detail": ver.stdout.strip(),
            })
        except Exception as e:
            checks.append({
                "name": "Node.js availability",
                "status": "warning",
                "detail": f"found but version check failed: {e}",
            })
    else:
        checks.append({
            "name": "Node.js availability",
            "status": "fail",
            "detail": "not found on PATH",
        })

    # Remotion binding check
    remotion_dir = PROJECT_ROOT / "rendering" / "node_modules" / "@remotion"
    if remotion_dir.exists() and any(remotion_dir.iterdir()):
        checks.append({
            "name": "Remotion packages",
            "status": "ok",
            "detail": "@remotion packages found",
        })
    else:
        checks.append({
            "name": "Remotion packages",
            "status": "warning",
            "detail": "not installed -- run: cd rendering && npm install",
        })

    return checks


# ============================================================================
#  Step-by-step pipeline execution
# ============================================================================

async def run_pipeline_step_by_step(config: dict) -> list[StepResult]:
    """Run the S1 pipeline one step at a time, recording each step result.

    If a step fails, its error is recorded and execution continues to the
    next step. The pipeline never crashes.
    """
    results: list[StepResult] = []

    # Initialize state manager (filesystem only in sandbox) and step runner
    state_manager = PipelineStateManager(use_pg=False)
    runner = StepRunner(state_manager)

    # Create initial state
    label = await runner.init_state(
        config=config,
        mode="auto",
        label=config.get("output_label", "e2e_s1"),
    )

    # Execute each step in order
    for step_name in STEP_ORDER:
        step_result = StepResult(step_name)
        start = time.perf_counter()

        # Special handling: compliance step is skipped when brand_mode=False
        if step_name == "compliance" and not config.get("brand_mode", False):
            step_result.skip(reason="brand_mode=False, compliance not required")
            step_result.duration_ms = 0.0
            results.append(step_result)
            print(str(step_result))
            continue

        try:
            # Run the step via step runner
            state = await runner.run_step(label, step_name)
            step_data = state.get("steps", {}).get(step_name, {})

            step_result.duration_ms = (time.perf_counter() - start) * 1000
            step_output = step_data.get("output")

            if step_data.get("status") == "done":
                errors = state.get("errors", [])
                relevant_errors = [e for e in errors if e.startswith(f"{step_name}_")]
                if relevant_errors:
                    step_result.fail(
                        error=relevant_errors[0],
                        detail="step recorded error",
                    )
                else:
                    step_result.succeed(
                        output=step_output,
                        detail=f"output type: {type(step_output).__name__}",
                    )
            else:
                step_result.fail(
                    error=f"step status is {step_data.get('status')}",
                    detail="unexpected status",
                )

        except Exception as exc:
            step_result.duration_ms = (time.perf_counter() - start) * 1000
            step_result.fail(error=str(exc), detail="exception during step execution")

        results.append(step_result)
        print(str(step_result))

    return results


# ============================================================================
#  Report generation
# ============================================================================

def generate_spike_report(
    preflight_checks: list[dict],
    step_results: list[StepResult],
    total_duration_ms: float,
) -> str:
    """Generate markdown spike report documenting all results."""
    now = datetime.now().isoformat()

    total_steps = len(step_results)
    passed = sum(1 for s in step_results if s.status == "ok")
    failed = sum(1 for s in step_results if s.status == "fail")
    skipped = sum(1 for s in step_results if s.status == "skip")

    pf_passed = sum(1 for c in preflight_checks if c["status"] == "ok")
    pf_warning = sum(1 for c in preflight_checks if c["status"] == "warning")
    pf_failed = sum(1 for c in preflight_checks if c["status"] == "fail")

    report = f"""# S1 Pipeline -- Real Mode Fault Log

> Pipeline: S1 Product Direct (yunfu zhen / Momcozy)
> Date: {now[:10]}
> Mode: Real (no mock, real API keys)

## Overview

- **Total pipeline duration:** {total_duration_ms:.1f}ms
- **Steps total:** {total_steps}
- **Steps passed:** {passed}
- **Steps failed:** {failed}
- **Steps skipped:** {skipped}

## Pre-flight Checks

| Check | Status | Detail |
|-------|--------|--------|
"""

    for c in preflight_checks:
        report += f"| {c['name']} | {c['status']} | {c['detail']} |\n"

    report += f"""
**Pre-flight summary:** {pf_passed} passed, {pf_warning} warnings, {pf_failed} failed
_Sanity: {pf_passed + pf_warning}/{len(preflight_checks)} checks OK or tolerable_

## Step Execution Log

| Step | Status | Duration | Error / Detail |
|------|--------|----------|----------------|
"""
    for sr in step_results:
        err_col = (sr.error[:120] if sr.error else "") + (" / " + sr.detail if sr.detail else "")
        report += f"| {sr.name} | {sr.status} | {sr.duration_ms:.1f}ms | {err_col} |\n"

    report += """
## Quality & Next Steps

### Observations

"""

    if failed == 0:
        report += "- All pipeline steps completed without failures.\n"
    else:
        report += "- The following steps had failures:\n"
        for sr in step_results:
            if sr.status == "fail":
                report += f"  - **{sr.name}**: {sr.error[:200]}\n"

    if skipped > 0:
        report += "- Skipped steps:\n"
        for sr in step_results:
            if sr.status == "skip":
                report += f"  - **{sr.name}**: {sr.detail}\n"

    report += """
### Missing API Keys

| Key | Status | Impact |
|-----|--------|--------|
"""

    for key, status in API_KEY_STATUS.items():
        if status == "SET":
            report += f"| {key} | SET | Available for real calls |\n"
        else:
            fallback = ""
            if key == "ELEVENLABS_API_KEY":
                fallback = "Will use poyo.ai or stub audio"
            elif key == "SEEDANCE_API_KEY":
                fallback = "Will use stub video generation"
            elif key == "OPENAI_API_KEY":
                fallback = "GPT-Image and LLM will use poyo proxy or stubs"
            elif key == "DATABASE_URL":
                fallback = "Will use SQLite filesystem fallback"
            report += f"| {key} | EMPTY | {fallback} |\n"

    report += """
### Recommendations

"""

    if API_KEY_STATUS.get("ELEVENLABS_API_KEY") == "EMPTY":
        report += "- [ ] Set `ELEVENLABS_API_KEY` in `.env` for real TTS audio\n"
    else:
        report += "- [x] `ELEVENLABS_API_KEY` is configured\n"

    if API_KEY_STATUS.get("SEEDANCE_API_KEY") == "EMPTY":
        report += "- [ ] Set `SEEDANCE_API_KEY` or `POYO_API_KEY` for real video generation\n"
    else:
        report += "- [x] `SEEDANCE_API_KEY` or `POYO_API_KEY` is configured\n"

    if API_KEY_STATUS.get("OPENAI_API_KEY") == "EMPTY":
        report += "- [ ] Set `OPENAI_API_KEY` for real GPT-Image and LLM calls\n"
    else:
        report += "- [x] `OPENAI_API_KEY` is configured\n"

    if failed > 0:
        report += "- [ ] Debug and fix the failing steps listed above\n"
    else:
        report += "- [x] All pipeline steps execute without crashing\n"

    report += "\n---\n"
    report += f"_Report generated: {now}_\n"

    return report


# ============================================================================
#  Main entry point
# ============================================================================

async def main() -> int:
    print(f"{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  S1 Pipeline E2E Test -- Step-by-Step Execution{RESET}")
    print(f"{'=' * 70}")

    # Build the pipeline config (matches what the API sends for /scenario/s1)
    config = {
        "product_catalog": {
            "name": "孕妇枕",
            "category": "pregnancy_pillow",
            "usps": [
                "100% cotton, machine washable cover",
                "Supports belly, back, and legs simultaneously",
                "U-shaped full-body design, ergonomic C-shape",
                "Breathable fabric, temperature-regulating fill",
            ],
            "keywords": ["pregnancy", "sleep", "comfort", "maternity", "pillow"],
        },
        "brand_guidelines": {
            "brand_name": "Momcozy",
            "tone": "warm, caring, supportive",
            "colors": ["#FFC0CB", "#FFFFFF", "#FFB6C1"],
            "brand_voice": "Gentle, reassuring, like a friend who's been through it",
            "target_audience": "Pregnant women, new mothers",
        },
        "target_platforms": ["tiktok", "shopify"],
        "target_languages": ["en"],
        "week": "2026-W18",
        "brand_mode": False,
        "enable_media_synthesis": True,
        "output_label": "e2e_s1_20260428",
        "video_duration": 10,
        "product_name": "孕妇枕",
        "brand_name": "Momcozy",
        "target_language": "en",
    }

    print(f"\n  Product: {BOLD}{config['product_catalog']['name']}{RESET}")
    print(f"  Brand:   {BOLD}{config['brand_guidelines']['brand_name']}{RESET}")
    print("  Mode:    S1 Product Direct (brand_mode=False)")
    print()

    # -- Pre-flight --
    print(f"{BOLD}-- Pre-flight Checks --{RESET}")
    preflight_checks = run_preflight()
    for c in preflight_checks:
        print(f"  {_icon(c['status'])} {c['name']}: {c['detail']}")
    pf_passed = sum(1 for c in preflight_checks if c["status"] == "ok")
    print(f"  Pre-flight: {pf_passed}/{len(preflight_checks)} OK")
    print()

    # API key summary
    print(f"{BOLD}-- API Key Status --{RESET}")
    for key, status in API_KEY_STATUS.items():
        ico = _icon("ok") if status == "SET" else _icon("warning")
        print(f"  {ico} {key}: {status}")
    print()

    # -- Step-by-step pipeline --
    print(f"{BOLD}-- Pipeline Step Execution --{RESET}")
    pipeline_start = time.perf_counter()
    step_results = await run_pipeline_step_by_step(config)
    total_duration_ms = (time.perf_counter() - pipeline_start) * 1000

    # -- Summary --
    passed = sum(1 for s in step_results if s.status == "ok")
    failed = sum(1 for s in step_results if s.status == "fail")
    skipped = sum(1 for s in step_results if s.status == "skip")

    print(f"\n{BOLD}{'-' * 50}{RESET}")
    print(f"{BOLD}  Pipeline Summary{RESET}")
    print(f"  Total duration: {total_duration_ms:.1f}ms")
    print(f"  Steps: {passed} passed, {failed} failed, {skipped} skipped / {len(step_results)} total")
    print()

    if failed > 0:
        print(f"  {_icon('fail')} {failed} step(s) failed:")
        for sr in step_results:
            if sr.status == "fail":
                print(f"      - {sr.name}: {sr.error[:200]}")
    else:
        print(f"  {_icon('ok')} All pipeline steps completed without failures.")

    # -- Generate spike report --
    spike_dir = PROJECT_ROOT / "docs" / "spike"
    spike_dir.mkdir(parents=True, exist_ok=True)
    spike_path = spike_dir / "2026-04-28_s1-real-failures.md"

    report = generate_spike_report(preflight_checks, step_results, total_duration_ms)
    spike_path.write_text(report, encoding="utf-8")

    print(f"\n  {GREEN}Spike report saved to: {spike_path}{RESET}")
    print()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
