#!/usr/bin/env python3
"""Run the L4D-2 single-video poyo Seedance smoke behind explicit gates."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from src.pipeline.l4d_video_only_smoke import (
        build_l4d_video_only_poyo_submitter_from_env,
        run_l4d_video_only_smoke,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Check gates and build the one-video job plan only.")
    mode.add_argument("--execute", action="store_true", help="Submit one poyo seedance-2 video job after all gates pass.")
    parser.add_argument(
        "--enable-poyo-http-submitter",
        action="store_true",
        help="Opt in to the poyo HTTP submitter in execute mode.",
    )
    parser.add_argument("--output", type=Path, help="Optional report JSON path under tmp/ or outside the repo.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output report.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser.parse_args()


def _validate_output_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("L4D video-only report output must be under tmp/ or outside the repository")
    return resolved


def main() -> int:
    args = _parse_args()
    mode = "execute" if args.execute else "dry_run" if args.dry_run else "disabled"
    submitter_factory = (
        (lambda: build_l4d_video_only_poyo_submitter_from_env(env=os.environ))
        if args.enable_poyo_http_submitter and mode == "execute"
        else None
    )
    report = run_l4d_video_only_smoke(mode=mode, env=os.environ, submitter_factory=submitter_factory)
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2 if args.pretty else None)

    if args.output is None:
        print(text)
    else:
        try:
            output_path = _validate_output_path(args.output)
            if output_path.exists() and not args.force:
                raise ValueError("output already exists; pass --force to overwrite")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text + "\n")
            print(f"Wrote L4D video-only smoke report: {output_path}")
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    return 2 if report.status == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
