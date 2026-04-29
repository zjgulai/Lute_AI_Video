#!/usr/bin/env python3
"""Sync bug fixes to Mac.
Usage: python3 scripts/sync_bugfix.py
Works in any Python 3 (venv or system), no dependencies required.
"""

import base64, os, sys, shutil, subprocess

BASE = "/Users/pray/project/hermes_evo/AI_vedio"

# ── files to sync (relative path -> destination content) ──
FILES = {}
for relpath in ["src/api.py", "src/agents/thumbnail.py"]:
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", relpath)
    with open(src, "rb") as f:
        FILES[relpath] = f.read()

print("=== Syncing bug fixes to Mac ===")
print(f"  Base: {BASE}")
print()

for relpath, data in FILES.items():
    target = os.path.join(BASE, relpath)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(data)
    print(f"  Wrote: {target}")

# Clear __pycache__
pycache_root = os.path.join(BASE)
for root, dirs, files in os.walk(pycache_root):
    if "__pycache__" in root:
        try:
            shutil.rmtree(root)
            print(f"  Cleaned: {root}")
        except OSError as e:
            print(f"  WARN: could not clean {root}: {e}")

print()
print("=== Done ===")
print("Changes:")
print("  1. src/api.py:283 — pipeline_complete key check: 'thumbnail_review' -> 'thumbnail'")
print("  2. src/agents/thumbnail.py:151-165 — _build_prompt removed 'No text in the image',")
print("     added per-variant text overlay descriptions.")
print()
print("If uvicorn is running with --reload, it picks up changes automatically.")
print("Otherwise: pkill -f uvicorn && . .venv/bin/activate && uvicorn src.api:app --reload --port 8001")
