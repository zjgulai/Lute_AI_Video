#!/usr/bin/env python3
"""Convert an external brand token vault into a candidate-only ledger."""

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
    from src.pipeline.brand_token_intake import build_candidate_ledger_from_token_vault


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("token_vault", help="Path to Brand_Data_Lake/token_vault/<Brand>.json")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--output", help="Optional output path for the full intake report JSON.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_candidate_ledger_from_token_vault(args.token_vault, max_tokens=args.max_tokens)
    payload = report.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
