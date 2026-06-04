#!/usr/bin/env python3
"""No-token preflight report before C9 authorized live token smoke."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(sys.stderr):
    from src.pipeline.token_smoke_preflight import build_token_smoke_preflight_report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--approval-record",
        help="Path to explicit C9 authorized-live approval JSON. Defaults to AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON report.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_token_smoke_preflight_report(approval_record_path=args.approval_record)
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2 if args.pretty else None))
    return 2 if report.blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
