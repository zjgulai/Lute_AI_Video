#!/usr/bin/env python3
"""Retired non-W5 mutation runner; retained only for historical references."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "ERROR: run_s1_video.py is retired and cannot execute; "
        "use a fresh governed W5 exact-authorization plan.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
