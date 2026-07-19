#!/usr/bin/env python3
"""Read a local W1-31 ledger without provider, credential, or production access."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.pipeline.provider_billing_reconciliation import read_local_w131_ledger  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-directory", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        report = read_local_w131_ledger(args.run_directory)
    except (OSError, ValueError, sqlite3.Error):
        print(json.dumps({"status": "blocked", "reason": "w1_31_ledger_readback_failed"}))
        return 2
    print(
        json.dumps(
            report.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
