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

echo "API_KEY: $API_KEY"
echo "ELEVENLABS_API_KEY: ${ELEVENLABS_API_KEY:0:20}..."
echo "POYO_API_KEY: ${POYO_API_KEY:0:20}..."
echo "Starting uvicorn on port 8001..."

uvicorn src.api:app --reload --port 8001 --reload-dir src
