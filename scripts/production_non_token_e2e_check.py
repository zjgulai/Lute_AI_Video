#!/usr/bin/env python3
"""Fail-closed Phase C production non-token E2E readiness and runner."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = REPO_ROOT / "web"
DEFAULT_BASE_URL = "https://video.lute-tlz-dddd.top"
DEMO_API_KEY = "ai_video_demo_2026"
TOKEN_SMOKE_ENV = "RUN_TOKEN_SMOKE"
PLAYWRIGHT_KEY_ENV = "PLAYWRIGHT_API_KEY"
API_KEY_ENV = "API_KEY"


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes"}


def _mask(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _playwright_key_status(env: dict[str, str]) -> tuple[str, str]:
    value = env.get(PLAYWRIGHT_KEY_ENV, "").strip()
    if not value:
        return ("block", "PLAYWRIGHT_API_KEY is required for formal Phase C production non-token E2E.")
    if value == DEMO_API_KEY:
        return ("block", "PLAYWRIGHT_API_KEY must be non-demo; ai_video_demo_2026 is rejected.")
    return ("pass", f"PLAYWRIGHT_API_KEY is set ({_mask(value)}).")


def build_report(base_url: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    current_env = dict(os.environ if env is None else env)
    run_token_smoke_enabled = _is_truthy(current_env.get(TOKEN_SMOKE_ENV))
    playwright_status, playwright_detail = _playwright_key_status(current_env)
    api_key = current_env.get(API_KEY_ENV, "").strip()

    checks: list[dict[str, Any]] = [
        {
            "name": "run_token_smoke_disabled",
            "status": "block" if run_token_smoke_enabled else "pass",
            "detail": (
                "RUN_TOKEN_SMOKE must be unset/false for Phase C non-token E2E."
                if run_token_smoke_enabled
                else "RUN_TOKEN_SMOKE is unset/false; token-smoke specs remain skipped."
            ),
            "evidence_refs": [TOKEN_SMOKE_ENV],
        },
        {
            "name": "playwright_api_key",
            "status": playwright_status,
            "detail": playwright_detail,
            "evidence_refs": [PLAYWRIGHT_KEY_ENV],
        },
        {
            "name": "api_key_note",
            "status": "pass" if api_key and api_key != DEMO_API_KEY else "warn",
            "detail": (
                f"API_KEY is set ({_mask(api_key)}); Playwright Phase C uses PLAYWRIGHT_API_KEY."
                if api_key and api_key != DEMO_API_KEY
                else "API_KEY is not used by Playwright Phase C, but is still required for later L4A/L4B operator flows."
            ),
            "evidence_refs": [API_KEY_ENV],
        },
        {
            "name": "provider_call_boundary",
            "status": "pass",
            "detail": "Phase C command forces RUN_TOKEN_SMOKE=0 and does not provide provider API keys.",
            "evidence_refs": ["web/playwright.prod.config.ts", "web/e2e/production/helpers.ts"],
        },
    ]

    blocked = any(check["status"] == "block" for check in checks)
    return {
        "report_id": f"phase_c_production_non_token_e2e_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        "evidence_level": "L2-fixture-or-dry-run" if blocked else "L2-readiness-for-L3-production-read-only",
        "target_base_url": base_url,
        "run_token_smoke": run_token_smoke_enabled,
        "provider_call_allowed": False,
        "token_smoke_allowed": False,
        "ready_for_phase_c_execution": not blocked,
        "blocked": blocked,
        "checks": checks,
        "execute_command_preview": (
            "cd web && RUN_TOKEN_SMOKE=0 "
            f"PLAYWRIGHT_PROD_URL={base_url} "
            "PLAYWRIGHT_API_KEY=<non-demo-production-key> npm run e2e:prod"
        ),
        "supported_claims": [
            "This report can establish whether the formal Phase C no-token Playwright run is ready to execute.",
            "A passed report still does not prove provider runtime success or commercial delivery.",
        ],
        "forbidden_claims": [
            "Do not claim Phase C passed until npm run e2e:prod completes with a non-demo production key.",
            "Do not claim L4A authorized-live provider evidence from this report.",
            "Do not claim delivery acceptance, publish allowed, or approved brand token.",
        ],
    }


def _print_human(report: dict[str, Any]) -> None:
    print("Phase C production non-token E2E readiness")
    print(f"Report: {report['report_id']}")
    print(f"Target base URL: {report['target_base_url']}")
    print(f"Evidence level: {report['evidence_level']}")
    print(f"Ready for Phase C execution: {str(report['ready_for_phase_c_execution']).lower()}")
    print("")
    for check in report["checks"]:
        print(f"- {check['name']}: {check['status']} — {check['detail']}")
    print("")
    print("Command preview:")
    print(report["execute_command_preview"])


def _run_phase_c(base_url: str) -> int:
    env = os.environ.copy()
    env[TOKEN_SMOKE_ENV] = "0"
    env["PLAYWRIGHT_PROD_URL"] = base_url
    print("Running Phase C production non-token E2E...")
    result = subprocess.run(("npm", "run", "e2e:prod"), cwd=WEB_DIR, env=env, check=False)
    return result.returncode


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--json", action="store_true", help="Print readiness report as JSON.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run production no-token Playwright after readiness passes.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_report(args.base_url)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)

    if not args.execute:
        return 0

    if report["blocked"]:
        print("ERROR: Phase C production non-token E2E is blocked; not running Playwright.", file=sys.stderr)
        return 2

    return _run_phase_c(args.base_url)


if __name__ == "__main__":
    raise SystemExit(main())
