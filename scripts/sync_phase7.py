#!/usr/bin/env python3
"""Sync Phase 7 — brand naming, SVG icon upgrade, and layout fixes to Mac."""
import os

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
    for relpath in FILES:
        src_path = os.path.join(SRC, relpath)
        dst_path = os.path.join(DST, relpath)
        with open(src_path, "rb") as f:
            content = f.read()
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        with open(dst_path, "wb") as f:
            f.write(content)
        print(f"  OK  {dst_path}")

    print("\n同步完成。在 Mac 上:")
    print("  1. 关旧进程: lsof -ti:3001 | xargs kill -9; lsof -ti:8001 | xargs kill -9")
    print("  2. 重启前端: cd web && npx next dev --port 3001")
    print("  3. 重启后端: uvicorn src.api:app --reload --port 8001")

if __name__ == "__main__":
    sync()
