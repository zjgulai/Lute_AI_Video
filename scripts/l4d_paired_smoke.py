#!/usr/bin/env python3
"""Retired non-W5 provider entrypoint; retained only for historical references."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "ERROR: l4d_paired_smoke.py is retired and cannot execute; "
        "use a fresh governed W5 exact-authorization plan.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
