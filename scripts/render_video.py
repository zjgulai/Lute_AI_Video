#!/usr/bin/env python3
"""Retired non-W5 provider-capable runner; retained for historical references."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "ERROR: render_video.py is retired and cannot execute; "
        "use repository-owned provider-off checks or a fresh governed W5 plan.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
