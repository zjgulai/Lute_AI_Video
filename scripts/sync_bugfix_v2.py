#!/usr/bin/env python3
"""Sync Bugfix #1 (target_platforms mock override) + Bugfix #2 (API key floating button) to Mac."""
import base64, os, sys

FILES_B64 = {
    "src/agents/strategy.py":
    "Li4uIHRvb2wgY2FsbHMgYXJlIHNraXBwZWQgZHVlIHRvIGxlbmd0aC4uLgo=",
    "src/graph/nodes.py":
    "Li4uIHRvb2wgY2FsbHMgYXJlIHNraXBwZWQgZHVlIHRvIGxlbmd0aC4uLgo=",
    "web/src/components/SceneSelector.tsx":
    "Li4uIHRvb2wgY2FsbHMgYXJlIHNraXBwZWQgZHVlIHRvIGxlbmd0aC4uLgo=",
}

BASE = os.path.expanduser("~") + "/project/hermes_evo/AI_vedio"
BASE_SRV = "/workspace/projects/hermes_evo/AI_vedio"

def sync():
    with open(os.path.join(BASE_SRV, "src/agents/strategy.py"), "rb") as f:
        content = f.read()
    dest = os.path.join(BASE, "src/agents/strategy.py")
    with open(dest, "wb") as f:
        f.write(content)
    print(f"  -> {dest}")

    with open(os.path.join(BASE_SRV, "src/graph/nodes.py"), "rb") as f:
        content = f.read()
    dest = os.path.join(BASE, "src/graph/nodes.py")
    with open(dest, "wb") as f:
        f.write(content)
    print(f"  -> {dest}")

    with open(os.path.join(BASE_SRV, "web/src/components/SceneSelector.tsx"), "rb") as f:
        content = f.read()
    dest = os.path.join(BASE, "web/src/components/SceneSelector.tsx")
    with open(dest, "wb") as f:
        f.write(content)
    print(f"  -> {dest}")

    print("\nDone. On Mac:")
    print("  Kill port 3001: lsof -ti:3001 | xargs kill -9")
    print("  Restart: cd web && npx next dev --port 3001")
    print("  Restart backend: lsof -ti:8001 | xargs kill -9; uvicorn src.api:app --reload --port 8001")

if __name__ == "__main__":
    sync()
