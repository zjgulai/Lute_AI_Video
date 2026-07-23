#!/usr/bin/env python3
"""Check private W5 Fast activation readiness without provider execution."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.w5_fast_activation import (  # noqa: E402
    build_w5_fast_readiness_report,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--activation", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = build_w5_fast_readiness_report(
        plan_path=args.plan,
        activation_path=args.activation,
        now=datetime.now(UTC),
    )
    print(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2 if args.pretty else None,
            sort_keys=True,
        )
    )
    return 0 if report.ready_for_private_binding else 2


if __name__ == "__main__":
    raise SystemExit(main())
