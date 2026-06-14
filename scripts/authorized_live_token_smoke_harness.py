#!/usr/bin/env python3
"""Gated C21 authorized-live sample harness.

Default mode is disabled. The script never configures a provider submitter by
itself, so it cannot call an external provider unless future code explicitly
wires that dependency after user approval.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(sys.stderr):
    from src.pipeline.authorized_live_harness import run_authorized_live_harness
    from src.pipeline.authorized_live_poyo_runtime import build_authorized_live_poyo_runtime_submitter


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Run local preflight and prepare a sample job spec only.")
    mode.add_argument("--execute", action="store_true", help="Attempt execute mode. Requires explicit env gates.")
    parser.add_argument(
        "--approval-record",
        help="Path to explicit C21 authorized-live approval JSON. Defaults to AI_VIDEO_AUTHORIZED_LIVE_APPROVAL_RECORD.",
    )
    parser.add_argument(
        "--enable-poyo-http-submitter",
        action="store_true",
        help="Opt in to authorized-live poyo HTTP submitter wiring after all execute gates pass.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON report.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    mode = "execute" if args.execute else "dry_run" if args.dry_run else "disabled"
    submitter_factory = build_authorized_live_poyo_runtime_submitter if args.enable_poyo_http_submitter and mode == "execute" else None
    report = run_authorized_live_harness(
        mode=mode,
        approval_record_path=args.approval_record,
        submitter_factory=(lambda: submitter_factory(env=os.environ)) if submitter_factory is not None else None,
    )
    print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2 if args.pretty else None))
    return 2 if report.status == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
