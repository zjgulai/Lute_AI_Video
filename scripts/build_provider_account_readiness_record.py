#!/usr/bin/env python3
"""Build a private provider account readiness record without provider calls."""

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
        SAMPLE_PLAN_REF,
        build_provider_account_readiness_payload,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checked-by", required=True, help="Concrete operator or owner name")
    parser.add_argument("--checked-at", help="ISO8601 dashboard check timestamp; defaults to current UTC")
    parser.add_argument("--provider", default="poyo")
    parser.add_argument("--available-credit-usd", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Private output JSON path")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing private readiness record")
    return parser.parse_args()


def _validate_private_output(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("account readiness output must be under tmp/ or outside the repository")
    return resolved


def main() -> int:
    args = _parse_args()
    try:
        output_path = _validate_private_output(args.output)
        if output_path.exists() and not args.force:
            raise ValueError("output already exists; pass --force to overwrite")
        payload = build_provider_account_readiness_payload(
            checked_by=args.checked_by,
            checked_at=args.checked_at,
            provider=args.provider,
            available_credit_usd=args.available_credit_usd,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print(f"Sample plan: {SAMPLE_PLAN_REF}", file=sys.stderr)
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"Wrote private account readiness record: {output_path}")
    print("Set AI_VIDEO_PROVIDER_ACCOUNT_READINESS_RECORD to this path before execute preflight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
