#!/usr/bin/env python3
"""Build a no-token launch packet for the authorized-live smoke gate."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "https://video.lute-tlz-dddd.top"
CONFIRM_ENV = "CONFIRM_P2_TOKEN_SMOKE"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from src.pipeline.token_smoke_preflight import (  # noqa: E402
        ACCOUNT_READINESS_RECORD_ENV,
        APPROVAL_RECORD_ENV,
        APPROVAL_STATEMENT_TEMPLATE,
        DEFAULT_AUTH_BUDGET_LIMIT,
        DEFAULT_AUTH_BUDGET_LIMIT_USD,
        DEFAULT_AUTH_MODEL,
        DEFAULT_AUTH_PROVIDER,
        DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
        DEFAULT_AUTH_TEST_SCOPE,
        PROVIDER_REVALIDATION_REF,
        REQUIRED_API_KEY_ENVS,
        RUN_TOKEN_SMOKE_ENV,
        SAMPLE_PLAN_REF,
        build_token_smoke_preflight_report,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--provider", default=DEFAULT_AUTH_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_AUTH_MODEL)
    parser.add_argument("--provider-model-scope", default=DEFAULT_AUTH_PROVIDER_MODEL_SCOPE)
    parser.add_argument("--test-scope", default=DEFAULT_AUTH_TEST_SCOPE)
    parser.add_argument("--budget-limit", default=DEFAULT_AUTH_BUDGET_LIMIT)
    parser.add_argument("--budget-limit-usd", type=float, default=DEFAULT_AUTH_BUDGET_LIMIT_USD)
    parser.add_argument(
        "--include-preflight",
        action="store_true",
        help="Include a no-token preflight projection in the packet.",
    )
    parser.add_argument(
        "--preflight-env",
        choices=("empty", "current"),
        default="empty",
        help="Use empty env for deterministic blocked proof, or current process env.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path; must be under tmp/ or outside repo.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    return parser.parse_args()


def _validate_private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("smoke packet output must be under tmp/ or outside the repository")
    return resolved


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _build_packet(args: argparse.Namespace) -> dict[str, Any]:
    required_statement = APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=args.provider_model_scope,
        test_scope=args.test_scope,
        budget_limit=args.budget_limit,
    )
    packet: dict[str, Any] = {
        "packet_id": f"authorized_live_smoke_packet_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "evidence_level": "L2-fixture-or-dry-run",
        "no_provider_call": True,
        "provider_call_allowed": False,
        "target_base_url": args.base_url,
        "provider": args.provider,
        "model": args.model,
        "provider_model_scope": args.provider_model_scope,
        "test_scope": args.test_scope,
        "budget_limit": args.budget_limit,
        "budget_limit_usd": args.budget_limit_usd,
        "required_authorization_statement": required_statement,
        "generic_confirmation_is_not_authorization": True,
        "rejected_confirmation_examples": ["继续下一步", "同意下一步", "确认执行"],
        "required_private_records": {
            "approval_record_env": APPROVAL_RECORD_ENV,
            "account_readiness_record_env": ACCOUNT_READINESS_RECORD_ENV,
            "output_location_rule": "private records must stay under tmp/ or outside the repository",
        },
        "required_runtime_env": {
            CONFIRM_ENV: "1",
            RUN_TOKEN_SMOKE_ENV: "1",
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT": "1",
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS": "private poyo payload JSON under tmp/ or outside repo",
            "API_KEY": "non-demo production backend key",
            "PLAYWRIGHT_API_KEY": "non-demo production Playwright key",
            **{env_name: "configured; value is never printed by this packet" for env_name in REQUIRED_API_KEY_ENVS},
        },
        "sample_plan_ref": SAMPLE_PLAN_REF,
        "provider_revalidation_ref": PROVIDER_REVALIDATION_REF,
        "record_build_commands": [
            (
                "python scripts/build_authorized_live_approval_record.py "
                "--approved-by <operator-name> "
                f"--approval-statement '{required_statement}' "
                f"--provider-model-scope '{args.provider_model_scope}' "
                f"--test-scope '{args.test_scope}' "
                f"--budget-limit '{args.budget_limit}' "
                f"--budget-limit-usd {args.budget_limit_usd:.2f} "
                "--output tmp/outputs/authorized-live-token-smoke-approval.json"
            ),
            (
                "python scripts/build_provider_account_readiness_record.py "
                "--checked-by <operator-name> "
                f"--available-credit-usd {args.budget_limit_usd:.2f} "
                "--output tmp/outputs/poyo-account-readiness.json"
            ),
        ],
        "dry_run_preflight_command": "python scripts/commercial_token_smoke_preflight.py --pretty",
        "execute_command_preview": (
            f"{CONFIRM_ENV}=1 {RUN_TOKEN_SMOKE_ENV}=1 "
            f"{APPROVAL_RECORD_ENV}=<private-approval-json> "
            f"{ACCOUNT_READINESS_RECORD_ENV}=<private-account-readiness-json> "
            "AI_VIDEO_AUTHORIZED_LIVE_EXECUTE=1 "
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_TRANSPORT=1 "
            "AI_VIDEO_AUTHORIZED_LIVE_POYO_PAYLOADS=<private-poyo-payloads-json> "
            "API_KEY=<production-api-key> PLAYWRIGHT_API_KEY=<production-api-key> "
            "POYO_API_KEY=<funded-poyo-key> DEEPSEEK_API_KEY=<deepseek-key> "
            "SILICONFLOW_API_KEY=<siliconflow-key> "
            "python scripts/p2_recharge_smoke_checklist.py --execute"
        ),
        "supported_claims": [
            "The launch packet documents the authorized-live gate inputs.",
            "The packet itself does not contact provider APIs or validate account balance.",
        ],
        "forbidden_claims": [
            "Do not claim L4 authorized-live evidence from this packet alone.",
            "Do not claim poyo key validity, balance, runtime success, or commercial delivery completion.",
        ],
    }
    if args.include_preflight:
        env = os.environ if args.preflight_env == "current" else {}
        report = build_token_smoke_preflight_report(env=env)
        packet["preflight_projection"] = report.model_dump(mode="json")
        packet["preflight_env_source"] = args.preflight_env
    return packet


def main() -> int:
    args = _parse_args()
    try:
        payload = _build_packet(args)
        if args.output is None:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        output_path = _validate_private_output(args.output)
        if output_path.exists() and not args.force:
            raise ValueError("output already exists; pass --force to overwrite")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote no-token authorized-live smoke packet: {_relative(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
