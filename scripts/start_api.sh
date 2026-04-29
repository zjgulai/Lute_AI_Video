#!/bin/bash
# Resolve repo root from this script's location (works on host & container)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# Activate venv if present — we need Python 3.11+ for `from enum import StrEnum`
if [ -f .venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

exec python3 -m uvicorn src.api:app --port 8001 --host 0.0.0.0 --reload --reload-dir src
