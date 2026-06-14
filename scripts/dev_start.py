#!/usr/bin/env python3
"""
One-shot dev server start for AI_Vedio.
Kills stale processes, starts uvicorn (backend) + next.js (frontend).
Cross-platform (macOS + Linux).
Usage: python3 scripts/dev_start.py [port_frontend]
"""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

# Resolve project root from this script's location (works anywhere).
SCRIPT_DIR = Path(__file__).resolve().parent
BASE = str(SCRIPT_DIR.parent)
FRONTEND_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 3001

# Prefer .venv python if present (we need 3.11+ for StrEnum)
_venv_python = Path(BASE) / ".venv" / "bin" / "python3"
PYTHON = str(_venv_python) if _venv_python.exists() else "python3"


def log(msg):
    print(f"[dev_start] {msg}")


def kill_processes(match):
    """Kill all processes whose cmdline contains `match`. Uses pgrep (cross-platform)."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", match],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in out.stdout.split() if p.isdigit()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        if pids:
            log(f"killed {len(pids)} process(es) matching '{match}'")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        log(f"pgrep unavailable, skipping cleanup for '{match}'")


def port_free(port):
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        return False


# Step 1: Clean up
log("cleaning up old processes...")
kill_processes("uvicorn src.api")
kill_processes("next dev")
time.sleep(2)

# Step 2: Pick frontend port (3001 or 3002)
PORT = FRONTEND_PORT
if not port_free(PORT):
    log(f"port {PORT} busy, trying 3002")
    PORT = 3002
    if not port_free(PORT):
        log("both 3001 and 3002 busy — wait 60s or kill manually")
        sys.exit(1)

# Step 3: Start backend
log(f"starting uvicorn on :8001 (python={PYTHON})...")
subprocess.Popen(
    [PYTHON, "-m", "uvicorn", "src.api:app", "--port", "8001", "--host", "0.0.0.0", "--reload", "--reload-dir", "src"],
    cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(4)

# Verify backend
try:
    import urllib.request
    r = urllib.request.urlopen("http://localhost:8001/docs", timeout=5)
    log(f"backend OK (HTTP {r.status})")
except Exception as e:
    log(f"backend may not be ready: {e}")

# Step 4: Start frontend
log(f"starting next.js on :{PORT}...")
subprocess.Popen(
    ["npx", "next", "dev", "--port", str(PORT)],
    cwd=f"{BASE}/web", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)

log("=== READY ===")
log("Backend:  http://localhost:8001/docs")
log(f"Frontend: http://localhost:{PORT}")
log("(wait ~20s for next.js compilation, then open in browser)")
