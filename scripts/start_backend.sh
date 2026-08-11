#!/bin/bash
# Start backend with all required env vars loaded from .env

cd "$(dirname "$0")/.."
source .venv/bin/activate

# Kill any existing uvicorn on port 8001
lsof -ti:8001 | xargs kill -9 2>/dev/null
sleep 1

# Load .env explicitly
set -a
source .env
set +a

credential_state() {
  local name="$1"
  if [ -n "${!name:-}" ]; then
    echo "${name}: configured"
  else
    echo "${name}: not_configured"
  fi
}

credential_state API_KEY
credential_state ELEVENLABS_API_KEY
credential_state POYO_API_KEY
echo "Starting uvicorn on port 8001..."

uvicorn src.api:app --reload --port 8001 --reload-dir src
