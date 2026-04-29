#!/usr/bin/env python3
"""Sync brand color changes — reads server files and writes local copies.
Run from Mac: python3 scripts/sync_brand_color.py
"""
import os

# Server filesystem mount point (adjust if your docker mount is different)
SRC = "/workspace/projects/hermes_evo/AI_vedio"
DST = os.path.expanduser("~") + "/project/hermes_evo/AI_vedio"

FILES = [
    "web/src/app/page.tsx",
    "web/src/app/globals.css",
    "web/src/components/types.ts",
    "web/src/components/SceneSelector.tsx",
    "web/src/components/PipelineMonitor.tsx",
    "web/src/components/ReviewPanel.tsx",
    "web/src/components/DistributionView.tsx",
    "web/src/components/AuditScoreCard.tsx",
]

def sync():
    # Check if we're on the server (SRC exists) or on Mac
    if os.path.isdir(SRC):
        source = SRC
    else:
        # Assume we're on Mac — files are already local, just copy in-place
        source = DST

    for relpath in FILES:
        src_path = os.path.join(source, relpath)
        dst_path = os.path.join(DST, relpath)
        if not os.path.exists(src_path):
            print(f"  SKIP  {relpath} (source not found)")
            continue
        with open(src_path, "rb") as f:
            content = f.read()
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "wb") as f:
            f.write(content)
        print(f"  OK  {dst_path}")

    print("\n完成。重启前后端即可。")

if __name__ == "__main__":
    sync()
