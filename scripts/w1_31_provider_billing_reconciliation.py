#!/usr/bin/env python3
"""Preflight or execute the exact W1-31 single-task charge reconciliation."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.provider_billing_reconciliation import (  # noqa: E402
    build_preflight_report,
)

EXECUTE_ENV = "AI_VIDEO_W1_31_EXECUTE"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approval-record", type=Path, required=True)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


async def _main() -> int:
    args = _args()
    indent = 2 if args.pretty else None
    if args.execute:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason": "w1_31_execution_retired",
                    "provider_call_allowed": False,
                },
                ensure_ascii=False,
                indent=indent,
            )
        )
        return 2
    preflight = build_preflight_report(approval_record_path=args.approval_record)
    print(json.dumps(preflight.model_dump(mode="json"), ensure_ascii=False, indent=indent))
    return 2 if preflight.blocked else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
