#!/usr/bin/env python3
"""Build a private authorized-live token smoke approval record without provider calls."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from src.pipeline.token_smoke_preflight import (  # noqa: E402
        APPROVAL_STATEMENT_TEMPLATE,
        DEFAULT_AUTH_BUDGET_LIMIT,
        DEFAULT_AUTH_BUDGET_LIMIT_USD,
        DEFAULT_AUTH_MODEL,
        DEFAULT_AUTH_PROVIDER,
        DEFAULT_AUTH_PROVIDER_MODEL_SCOPE,
        DEFAULT_AUTH_TEST_SCOPE,
        build_authorized_live_approval_payload,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-by", required=True, help="Concrete operator or owner name")
    parser.add_argument("--approval-statement", required=True, help="Exact C21 authorization statement")
    parser.add_argument("--approved-at", help="ISO8601 approval timestamp; defaults to current UTC")
    parser.add_argument("--expires-at", help="ISO8601 expiry timestamp; defaults to four hours after approval")
    parser.add_argument("--provider", default=DEFAULT_AUTH_PROVIDER)
    parser.add_argument("--model", default=DEFAULT_AUTH_MODEL)
    parser.add_argument("--provider-model-scope", default=DEFAULT_AUTH_PROVIDER_MODEL_SCOPE)
    parser.add_argument("--test-scope", default=DEFAULT_AUTH_TEST_SCOPE)
    parser.add_argument("--budget-limit", default=DEFAULT_AUTH_BUDGET_LIMIT)
    parser.add_argument("--budget-limit-usd", type=float, default=DEFAULT_AUTH_BUDGET_LIMIT_USD)
    parser.add_argument("--output", type=Path, help="Private output JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing private approval record")
    parser.add_argument(
        "--print-required-statement",
        action="store_true",
        help="Print the exact statement for the selected provider/model/budget and exit",
    )
    return parser.parse_args()


def _validate_private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("approval record output must be under tmp/ or outside the repository")
    return resolved


def main() -> int:
    args = _parse_args()
    required_statement = APPROVAL_STATEMENT_TEMPLATE.format(
        provider_model_scope=args.provider_model_scope,
        test_scope=args.test_scope,
        budget_limit=args.budget_limit,
    )
    if args.print_required_statement:
        print(required_statement)
        return 0

    try:
        if args.output is None:
            raise ValueError("--output is required unless --print-required-statement is used")
        output_path = _validate_private_output(args.output)
        if output_path.exists() and not args.force:
            raise ValueError("output already exists; pass --force to overwrite")
        payload = build_authorized_live_approval_payload(
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            expires_at=args.expires_at,
            approval_statement=args.approval_statement,
            provider=args.provider,
            model=args.model,
            provider_model_scope=args.provider_model_scope,
            test_scope=args.test_scope,
            budget_limit=args.budget_limit,
            budget_limit_usd=args.budget_limit_usd,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Required statement: {required_statement}", file=sys.stderr)
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote private approval record: {output_path}")
    print("Set AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD to this path before execute preflight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
