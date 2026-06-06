#!/usr/bin/env python3
"""Dry-run first checklist for P2 real production smoke after recharge."""

from __future__ import annotations

import argparse
import contextlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://video.lute-tlz-dddd.top"
DEMO_API_KEY = "ai_video_demo_2026"
CONFIRM_ENV = "CONFIRM_P2_TOKEN_SMOKE"
TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"
APPROVAL_RECORD_ENV = "AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD"
ACCOUNT_READINESS_RECORD_ENV = "AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD"
SMOKE_PACKET_SCRIPT = "scripts/build_authorized_live_smoke_packet.py"


@dataclass(frozen=True)
class EnvRequirement:
    name: str
    description: str
    reject_demo_key: bool = False


@dataclass(frozen=True)
class SmokeCommand:
    name: str
    cwd: Path
    argv: tuple[str, ...]
    env: dict[str, str]


REQUIRED_ENV = (
    EnvRequirement("API_KEY", "Production backend API key for Lighthouse smoke", True),
    EnvRequirement("PLAYWRIGHT_API_KEY", "Non-demo production API key for Playwright", True),
    EnvRequirement(APPROVAL_RECORD_ENV, "Private C21 approval record JSON with budget stop-loss"),
    EnvRequirement(ACCOUNT_READINESS_RECORD_ENV, "Private provider account readiness JSON with manual balance check"),
    EnvRequirement("POYO_API_KEY", "Funded poyo.ai key configured for production"),
    EnvRequirement("DEEPSEEK_API_KEY", "DeepSeek key configured for production"),
    EnvRequirement("SILICONFLOW_API_KEY", "SiliconFlow CosyVoice key configured for production"),
)


def _mask(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _env_status() -> list[str]:
    lines = []
    for item in REQUIRED_ENV:
        value = os.environ.get(item.name, "")
        status = "MISSING" if not value else f"set ({_mask(value)})"
        if item.reject_demo_key and value == DEMO_API_KEY:
            status = "REJECTED demo key"
        lines.append(f"- {item.name}: {status} — {item.description}")
    return lines


def _build_commands(base_url: str, *, execute: bool = False) -> list[SmokeCommand]:
    common_env = {
        TOKEN_SMOKE_ENV: "1",
        "P2_RECHARGE_SMOKE_MODE": "execute" if execute else "dry-run",
        "BASE": base_url,
        "PLAYWRIGHT_PROD_URL": base_url,
        "API_KEY": os.environ.get("API_KEY", ""),
        "PLAYWRIGHT_API_KEY": os.environ.get("PLAYWRIGHT_API_KEY", ""),
    }
    return [
        SmokeCommand(
            name="Momcozy sterilizer authorized-live asset smoke harness",
            cwd=REPO_ROOT,
            argv=("python", "scripts/authorized_live_token_smoke_harness.py", "--execute", "--pretty"),
            env=common_env,
        ),
    ]


def _format_command(command: SmokeCommand) -> str:
    env_prefix = " ".join(
        f"{key}={value}" for key, value in command.env.items() if key in {TOKEN_SMOKE_ENV, "BASE", "PLAYWRIGHT_PROD_URL"}
    )
    return f"(cd {command.cwd.relative_to(REPO_ROOT) or '.'} && {env_prefix} {' '.join(command.argv)})"


def _print_dry_run(base_url: str) -> None:
    print("P2 recharge smoke checklist — DRY RUN")
    print("No commands were executed.")
    print(f"Target base URL: {base_url}")
    print("")
    print("Required before execution:")
    for line in _env_status():
        print(line)
    print("")
    print("Before execute, build a no-token launch packet:")
    print(f"python {SMOKE_PACKET_SCRIPT} --include-preflight")
    print("")
    print("After recharge, execute with:")
    print(
        "CONFIRM_P2_TOKEN_SMOKE=1 RUN_TOKEN_SMOKE=1 "
        "API_KEY=<production-api-key> PLAYWRIGHT_API_KEY=<production-api-key> "
        "POYO_API_KEY=<funded-poyo-key> DEEPSEEK_API_KEY=<deepseek-key> "
        "SILICONFLOW_API_KEY=<siliconflow-key> "
        f"{APPROVAL_RECORD_ENV}=<private-approval-json> "
        f"{ACCOUNT_READINESS_RECORD_ENV}=<private-account-readiness-json> "
        "python scripts/p2_recharge_smoke_checklist.py --execute"
    )
    print("")
    print("Would run:")
    for command in _build_commands(base_url, execute=False):
        print(f"- {command.name}: {_format_command(command)}")


def _validate_execute_env() -> list[str]:
    errors = []
    if os.environ.get(CONFIRM_ENV) != "1":
        errors.append(f"{CONFIRM_ENV}=1 is required for --execute")
    if os.environ.get(TOKEN_SMOKE_ENV) != "1":
        errors.append(f"{TOKEN_SMOKE_ENV}=1 is required for --execute")

    for item in REQUIRED_ENV:
        value = os.environ.get(item.name, "")
        if not value:
            errors.append(f"{item.name} is required for --execute")
        elif item.reject_demo_key and value == DEMO_API_KEY:
            errors.append(f"{item.name} must be a non-demo key; demo key is rejected")
    return errors


def _build_execute_preflight_report():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    with contextlib.redirect_stdout(sys.stderr):
        from src.pipeline.token_smoke_preflight import build_token_smoke_preflight_report

    return build_token_smoke_preflight_report()


def _validate_execute_preflight() -> int:
    report = _build_execute_preflight_report()
    if not report.blocked:
        print(f"Token smoke preflight passed: {report.report_id}")
        return 0

    print(f"ERROR: token smoke preflight blocked execute ({report.report_id})", file=sys.stderr)
    for check in report.checks:
        if check.status == "block":
            print(f"ERROR: [{check.name}] {check.detail}", file=sys.stderr)
    return 2


def _run_commands(commands: list[SmokeCommand]) -> int:
    for command in commands:
        print(f"Running: {command.name}")
        env = os.environ.copy()
        env.update(command.env)
        result = subprocess.run(command.argv, cwd=command.cwd, env=env, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run real token-consuming smoke. Requires double confirmation env vars.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if not args.execute:
        _print_dry_run(args.base_url)
        return 0

    errors = _validate_execute_env()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 2

    preflight_exit = _validate_execute_preflight()
    if preflight_exit != 0:
        return preflight_exit

    return _run_commands(_build_commands(args.base_url, execute=True))


if __name__ == "__main__":
    raise SystemExit(main())
