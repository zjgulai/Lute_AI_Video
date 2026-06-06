#!/usr/bin/env python3
"""Build a no-token human review packet for pending-review media assets."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    from src.pipeline.pending_review_asset_packet import build_pending_review_asset_packet


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary_json", type=Path, help="Authorized-live smoke summary JSON.")
    parser.add_argument(
        "--pending-review-dir",
        type=Path,
        help="Optional local pending-review media directory. Defaults to summary.local_pending_review_dir.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path; must be under tmp/ or outside repo.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing output file.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser.parse_args()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def _validate_output_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    repo_tmp = (REPO_ROOT / "tmp").resolve()
    if resolved.is_relative_to(REPO_ROOT.resolve()) and not resolved.is_relative_to(repo_tmp):
        raise ValueError("pending review packet output must be under tmp/ or outside the repository")
    return resolved


def _relative(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    args = _parse_args()
    try:
        summary_path = args.summary_json.expanduser().resolve()
        packet = build_pending_review_asset_packet(
            _read_json(summary_path),
            pending_review_dir=args.pending_review_dir,
            source_summary_ref=_relative(summary_path),
            repo_root=REPO_ROOT,
        )
        text = json.dumps(packet.model_dump(mode="json"), ensure_ascii=False, indent=2 if args.pretty else None)

        if args.output is None:
            print(text)
            return 0

        output_path = _validate_output_path(args.output)
        if output_path.exists() and not args.force:
            raise ValueError("output already exists; pass --force to overwrite")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n")
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote pending-review asset packet: {_relative(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
