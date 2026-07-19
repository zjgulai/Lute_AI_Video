#!/usr/bin/env python3
"""Build an exact private W1-31 dual-confirmation record without provider calls."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.provider_billing_reconciliation import (  # noqa: E402
    AUTHORIZATION_STATEMENT,
    build_private_approval_payload,
    parse_private_approval_record,
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--approved-by", required=True)
    parser.add_argument("--confirmed-by", required=True)
    parser.add_argument("--price-checked-at", required=True)
    parser.add_argument("--account-readiness-checked-at", required=True)
    parser.add_argument("--available-credit-micro-units", type=int, required=True)
    parser.add_argument("--authorization-statement", required=True)
    parser.add_argument("--approved-at")
    parser.add_argument("--expires-minutes", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _args()
    now = datetime.now(UTC).replace(microsecond=0)
    approved_at = args.approved_at or now.isoformat().replace("+00:00", "Z")
    expires_at = (now + timedelta(minutes=args.expires_minutes)).isoformat().replace("+00:00", "Z")
    try:
        if args.authorization_statement != AUTHORIZATION_STATEMENT:
            raise ValueError("authorization statement is not exact")
        if not 1 <= args.expires_minutes <= 120:
            raise ValueError("expires-minutes must be between 1 and 120")
        payload = build_private_approval_payload(
            approval_id=args.approval_id,
            approved_by=args.approved_by,
            confirmed_by=args.confirmed_by,
            approved_at=approved_at,
            expires_at=expires_at,
            price_checked_at=args.price_checked_at,
            account_readiness_checked_at=args.account_readiness_checked_at,
            available_credit_micro_units=args.available_credit_micro_units,
            authorization_statement=args.authorization_statement,
        )
        output = args.output.expanduser().resolve()
        repo_tmp = (REPO_ROOT / "tmp").resolve()
        if output.is_relative_to(REPO_ROOT) and not output.is_relative_to(repo_tmp):
            raise ValueError("output must be under tmp/ or outside the repository")
        if output.exists():
            raise ValueError("output already exists")
        output.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        os.chmod(output, 0o600)
        parse_private_approval_record(output, now=now)
    except (OSError, ValueError):
        print("ERROR: w1_31_approval_record_build_failed", file=sys.stderr)
        return 2
    print("Wrote exact private W1-31 approval record with mode 0600.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
