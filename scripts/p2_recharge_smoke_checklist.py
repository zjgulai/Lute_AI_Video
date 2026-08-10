#!/usr/bin/env python3
"""Retired P2/C21 compatibility stub; live execution moved to governed W5."""

from __future__ import annotations

import argparse
import sys


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", help="Ignored historical compatibility option.")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def main() -> int:
    _parse_args()
    print(
        "ERROR: P2/C21 recharge smoke is retired and cannot execute; "
        "use a fresh governed W5 exact-authorization plan.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
