#!/usr/bin/env python3
"""
Sync the multi-scenario execution plan from server to Mac.

Usage:
    # On server: generate the base64 payload
    python3 scripts/sync_plan_to_mac.py --encode > /tmp/plan_payload.txt

    # On Mac: paste the payload into the decode command
    python3 scripts/sync_plan_to_mac.py --decode <PAYLOAD>
"""

import base64
import gzip
import json
import sys
from pathlib import Path


PLAN_PATH = Path("/workspace/projects/hermes_evo/AI_vedio/.hermes/plans/multi-scenario-execution-plan-20260426.md")
MAC_PATH = Path("/Users/pray/project/hermes_evo/AI_vedio/.hermes/plans/multi-scenario-execution-plan-20260426.md")


def encode():
    """Read file, compress, base64 encode, print."""
    data = PLAN_PATH.read_bytes()
    compressed = gzip.compress(data, compresslevel=9)
    b64 = base64.b64encode(compressed).decode()
    print(b64)


def decode():
    """Read base64 from stdin, decompress, write to Mac path."""
    b64 = sys.stdin.read().strip()
    if not b64:
        print("ERROR: no input. Pipe a base64 payload.")
        sys.exit(1)

    compressed = base64.b64decode(b64)
    data = gzip.decompress(compressed)
    MAC_PATH.parent.mkdir(parents=True, exist_ok=True)
    MAC_PATH.write_bytes(data)
    print(f"OK: wrote {len(data)} bytes to {MAC_PATH}")


if __name__ == "__main__":
    if "--encode" in sys.argv:
        encode()
    elif "--decode" in sys.argv:
        decode()
    else:
        print("Usage: --encode | --decode")
        sys.exit(1)
