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
STRICT_READ_ONLY_GREP_INVERT = r"(@token-smoke|P4-4 — Error paths)"
STRICT_READ_ONLY_ENV = "PLAYWRIGHT_PHASE_C_STRICT_READ_ONLY"


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


def build_report(
    base_url: str,
    env: dict[str, str] | None = None,
    *,
    strict_read_only: bool = False,
) -> dict[str, Any]:
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
        "strict_read_only": strict_read_only,
        "provider_call_allowed": False,
        "token_smoke_allowed": False,
        "non_get_requests_allowed": not strict_read_only,
        "ready_for_phase_c_execution": not blocked,
        "blocked": blocked,
        "checks": checks,
        "execute_command_preview": (
            "cd web && RUN_TOKEN_SMOKE=0 "
            f"PLAYWRIGHT_PROD_URL={base_url} "
            "PLAYWRIGHT_API_KEY=<non-demo-production-key> "
            f"npx playwright test --config=playwright.prod.config.ts --grep-invert '{STRICT_READ_ONLY_GREP_INVERT}'"
            if strict_read_only
            else (
                "cd web && RUN_TOKEN_SMOKE=0 "
                f"PLAYWRIGHT_PROD_URL={base_url} "
                "PLAYWRIGHT_API_KEY=<non-demo-production-key> npm run e2e:prod"
            )
        ),
        "supported_claims": [
            "This report can establish whether the formal Phase C no-token Playwright run is ready to execute.",
            (
                "Strict read-only mode excludes P4-4 error-path POST tests."
                if strict_read_only
                else "Default mode still includes 4xx error-path POST tests that do not create provider jobs."
            ),
            "A passed report still does not prove provider runtime success or commercial delivery.",
        ],
        "forbidden_claims": [
            "Do not claim Phase C passed until the selected Playwright command completes with a non-demo production key.",
            "Do not claim L4A authorized-live provider evidence from this report.",
            "Do not claim delivery acceptance, publish allowed, or approved brand token.",
            "Do not claim strict read-only execution unless --strict-read-only was used.",
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


def _run_phase_c(base_url: str, *, strict_read_only: bool = False) -> int:
    env = os.environ.copy()
    env[TOKEN_SMOKE_ENV] = "0"
    env["PLAYWRIGHT_PROD_URL"] = base_url
    command: tuple[str, ...] = ("npm", "run", "e2e:prod")
    if strict_read_only:
        env[STRICT_READ_ONLY_ENV] = "1"
        command = (
            "npx",
            "playwright",
            "test",
            "--config=playwright.prod.config.ts",
            "--grep-invert",
            STRICT_READ_ONLY_GREP_INVERT,
        )
    suffix = " (strict read-only)" if strict_read_only else ""
    print(f"Running Phase C production non-token E2E{suffix}...")
    result = subprocess.run(command, cwd=WEB_DIR, env=env, check=False)
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
    parser.add_argument(
        "--strict-read-only",
        action="store_true",
        help="Exclude P4-4 POST error-path tests while keeping token-smoke specs skipped.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_report(args.base_url, strict_read_only=args.strict_read_only)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)

    if not args.execute:
        return 0

    if report["blocked"]:
        print("ERROR: Phase C production non-token E2E is blocked; not running Playwright.", file=sys.stderr)
        return 2

    return _run_phase_c(args.base_url, strict_read_only=args.strict_read_only)


if __name__ == "__main__":
    raise SystemExit(main())
