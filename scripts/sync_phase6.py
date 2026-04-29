#!/usr/bin/env python3
"""Sync Phase 6 frontend redesign v3 — split layout + fix bugs.
Usage: cd /Users/pray/project/hermes_evo/AI_vedio && python3 scripts/sync_phase6.py
"""

import os

BASE = "/Users/pray/project/hermes_evo/AI_vedio/web/src"

FILES = {}
server_base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for relpath in [
    "src/app/page.tsx",
    "src/app/layout.tsx",
    "src/app/globals.css",
    "src/components/types.ts",
    "src/components/api.ts",
    "src/components/SceneSelector.tsx",
    "src/components/PipelineMonitor.tsx",
    "src/components/ReviewPanel.tsx",
    "src/components/AuditScoreCard.tsx",
    "src/components/DistributionView.tsx",
]:
    src = os.path.join(server_base, "web", relpath)
    with open(src, "rb") as f:
        FILES[relpath] = f.read()

print("=== Syncing Phase 6 frontend v3 — split layout ===")
print(f"  Base: {BASE}")
print()

for relpath, data in FILES.items():
    target_relative = relpath.replace("src/", "", 1)
    target = os.path.join(BASE, target_relative)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as f:
        f.write(data)
    print(f"  Wrote: {target}")

print()
print("=== Done ===")
print("Layout changes:")
print("  - Left sidebar (320px): PipelineMonitor always visible")
print("  - Right panel: SceneSelector / ReviewPanel / DistributionView")
print("  - Removed embedded monitor from ReviewPanel")
print("  - Fixed duplicate script key warnings")
print("  - Fixed viewport metadata warning")
