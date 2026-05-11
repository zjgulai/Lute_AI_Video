#!/usr/bin/env bash
# Periodic re-scrape of brand product images.
# Runs scrape_momcozy.py inside the backend container, then bumps the LRU cache
# by sending SIGHUP to uvicorn (which the FastAPI app handles as a no-op but
# triggers process restart through systemd / docker compose health checks if
# wired). For the Lighthouse compose stack we instead just `docker exec ... 
# python /tmp/scrape_momcozy.py --force` and rely on the next cache TTL expiry
# (60s for /brand-presets, 30s for portfolio scan).
#
# Schedule: weekly Sunday 03:30 UTC+8 via cron on the Lighthouse host.
# Output: /var/log/brand-assets-refresh.log (rotated by logrotate).
set -euo pipefail

LOG=/var/log/brand-assets-refresh.log
COMPOSE_FILE=/opt/ai-video/deploy/lighthouse/docker-compose.prod.yml
SCRAPER_HOST=/opt/ai-video/scripts/scrape_momcozy.py
SCRAPER_CONTAINER=/tmp/scrape_momcozy.py
TS="$(date -Iseconds)"

mkdir -p "$(dirname "$LOG")"

{
  echo "===== brand-assets-refresh @ $TS ====="
  if ! docker compose -f "$COMPOSE_FILE" ps --status running --format '{{.Name}}' | grep -q ai_video_backend; then
    echo "[ERR] ai_video_backend not running, aborting"
    exit 1
  fi
  docker cp "$SCRAPER_HOST" ai_video_backend:"$SCRAPER_CONTAINER"
  docker exec ai_video_backend python3 "$SCRAPER_CONTAINER" --force
  echo "[OK] scrape complete @ $(date -Iseconds)"
  echo
} >>"$LOG" 2>&1
