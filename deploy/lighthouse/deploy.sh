#!/usr/bin/env bash
# Provider-off immutable release deployment for Tencent Lighthouse.

set -Eeuo pipefail

cd "$(dirname "$0")"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.release.yml}"
RELEASE_SOURCE_SHA="${RELEASE_SOURCE_SHA:-}"
AI_VIDEO_SHARED_ROOT="${AI_VIDEO_SHARED_ROOT:-/opt/ai-video}"
RELEASE_ROOT="$(cd ../.. && pwd)"
ROLLBACK_COMPOSE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/docker-compose.prod.yml"
AI_VIDEO_ENV_FILE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.env.prod"
PORTAL_AUTH_ENV_FILE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.portal-auth.env"
SHARED_AI_VIDEO_LOCATIONS="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/ai_video_locations.conf"
RELEASE_AI_VIDEO_LOCATIONS="$RELEASE_ROOT/deploy/lighthouse/ai_video_locations.conf"
NGINX_CONFIG_BACKUP="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.ai_video_locations.rollback-$RELEASE_SOURCE_SHA"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/ai-video-backups}"
ALLOW_MAINTENANCE_WINDOW="${ALLOW_MAINTENANCE_WINDOW:-0}"
CLEANUP_AFTER_DEPLOY="${CLEANUP_AFTER_DEPLOY:-0}"
CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-180}"
RUN_TOKEN_SMOKE="${RUN_TOKEN_SMOKE:-0}"
RUN_DEPLOY_SMOKE="${RUN_DEPLOY_SMOKE:-0}"
RENDERING_ALPINE_MIRROR="${RENDERING_ALPINE_MIRROR:-https://mirrors.cloud.tencent.com/alpine}"
RELEASE_IMAGE_ARCHIVE="${RELEASE_IMAGE_ARCHIVE:-}"
RELEASE_IMAGE_ARCHIVE_SHA256="${RELEASE_IMAGE_ARCHIVE_SHA256:-${RELEASE_IMAGE_ARCHIVE}.sha256}"

COMPOSE=(sudo docker compose -f "$COMPOSE_FILE")
ACTIVE_COMMAND=()
ACTIVE_RELEASE_KIND=""
PREVIOUS_RELEASE_ROOT=""
PREVIOUS_RELEASE_SHA=""
DEPLOY_COMPLETE="0"
MAINTENANCE_BEGUN="0"
OLD_BACKEND_STOPPED="0"
APP_SWITCH_STARTED="0"
ROLLBACK_FAILED="0"
RESTORE_CONTAINER_ID=""
BACKUP_HELPER_ID=""
NGINX_CONFIG_CHANGED="0"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_zero_or_one() {
  local name="$1" value="$2"
  if [ "$value" != "0" ] && [ "$value" != "1" ]; then
    fail "$name must be 0 or 1"
  fi
}

if ! [[ "$RELEASE_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  fail "RELEASE_SOURCE_SHA must be the reviewed 40-character Git SHA"
fi
require_zero_or_one ALLOW_MAINTENANCE_WINDOW "$ALLOW_MAINTENANCE_WINDOW"
require_zero_or_one CLEANUP_AFTER_DEPLOY "$CLEANUP_AFTER_DEPLOY"
if [ "$ALLOW_MAINTENANCE_WINDOW" != "1" ]; then
  fail "provider-off rollout requires explicit ALLOW_MAINTENANCE_WINDOW=1"
fi
if [ "$RUN_TOKEN_SMOKE" != "0" ] || [ "$RUN_DEPLOY_SMOKE" != "0" ]; then
  fail "canonical deployment forbids token and authenticated smoke execution"
fi
if [ "$CLEANUP_AFTER_DEPLOY" != "0" ]; then
  fail "canonical deployment preserves rollback images; CLEANUP_AFTER_DEPLOY must be 0"
fi
if ! [[ "$CLEANUP_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  fail "CLEANUP_TIMEOUT_SECONDS must be a positive integer"
fi

export RELEASE_SOURCE_SHA
export RELEASE_IMAGE_TAG="$RELEASE_SOURCE_SHA"
export AI_VIDEO_SHARED_ROOT AI_VIDEO_ENV_FILE PORTAL_AUTH_ENV_FILE
export RENDERING_ALPINE_MIRROR

configure_active_release() {
  local current_link="$AI_VIDEO_SHARED_ROOT/current" previous_compose image
  if [ -L "$current_link" ]; then
    PREVIOUS_RELEASE_ROOT="$(readlink -f "$current_link")"
    PREVIOUS_RELEASE_SHA="${PREVIOUS_RELEASE_ROOT##*/releases-}"
    if ! [[ "$PREVIOUS_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] \
      || [ "$PREVIOUS_RELEASE_ROOT" != "$AI_VIDEO_SHARED_ROOT/releases-$PREVIOUS_RELEASE_SHA" ]; then
      fail "current release pointer is not a valid immutable release directory"
    fi
    previous_compose="$PREVIOUS_RELEASE_ROOT/deploy/lighthouse/docker-compose.release.yml"
    [ -f "$previous_compose" ] || fail "previous release compose is unavailable"
    for image in \
      "lighthouse-backend:$PREVIOUS_RELEASE_SHA" \
      "lighthouse-frontend:$PREVIOUS_RELEASE_SHA" \
      "lighthouse-rendering:$PREVIOUS_RELEASE_SHA"
    do
      sudo docker image inspect "$image" >/dev/null 2>&1 \
        || fail "previous rollback image is unavailable: $image"
    done
    ACTIVE_COMMAND=(
      sudo env
      "RELEASE_SOURCE_SHA=$PREVIOUS_RELEASE_SHA"
      "RELEASE_IMAGE_TAG=$PREVIOUS_RELEASE_SHA"
      "AI_VIDEO_SHARED_ROOT=$AI_VIDEO_SHARED_ROOT"
      "AI_VIDEO_ENV_FILE=$AI_VIDEO_ENV_FILE"
      "PORTAL_AUTH_ENV_FILE=$PORTAL_AUTH_ENV_FILE"
      "RENDERING_ALPINE_MIRROR=$RENDERING_ALPINE_MIRROR"
      docker compose -f "$previous_compose"
    )
    ACTIVE_RELEASE_KIND="immutable"
  elif [ -e "$current_link" ]; then
    fail "current release pointer exists but is not a symlink"
  else
    ACTIVE_COMMAND=(sudo docker compose -f "$ROLLBACK_COMPOSE")
    ACTIVE_RELEASE_KIND="legacy-first-release"
  fi
}

configure_active_release

cleanup_restore_container() {
  if [ -n "$RESTORE_CONTAINER_ID" ]; then
    sudo docker rm -f "$RESTORE_CONTAINER_ID" >/dev/null 2>&1 || true
    RESTORE_CONTAINER_ID=""
  fi
}

cleanup_backup_helper() {
  if [ -n "$BACKUP_HELPER_ID" ]; then
    sudo docker rm -f "$BACKUP_HELPER_ID" >/dev/null 2>&1 || true
    BACKUP_HELPER_ID=""
  fi
}

verify_backend_health() {
  sudo docker exec ai_video_backend python3 -c '
import json
import urllib.request
payload = json.load(urllib.request.urlopen("http://127.0.0.1:8001/health", timeout=10))
persistence = payload.get("persistence") or {}
if payload.get("status") != "ok":
    raise SystemExit("backend status is not ok")
if persistence.get("backend") != "postgresql":
    raise SystemExit("persistence backend is not postgresql")
if persistence.get("status") != "healthy":
    raise SystemExit("persistence status is not healthy")
if persistence.get("tables_verified") is not True:
    raise SystemExit("required PostgreSQL tables are not verified")
' >/dev/null
}

verify_release_health() {
  local attempt
  for attempt in $(seq 1 24); do
    if verify_backend_health \
      && sudo docker exec ai_video_frontend wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1 \
      && sudo docker exec ai_video_rendering wget -qO- http://127.0.0.1:3001/health >/dev/null 2>&1; then
      echo "  Application containers healthy with verified PostgreSQL schema (attempt $attempt/24)"
      return 0
    fi
    [ "$attempt" = "24" ] || sleep 5
  done
  return 1
}

verify_public_health() {
  local attempt payload
  for attempt in $(seq 1 24); do
    if sudo docker exec ai_video_nginx nginx -t >/dev/null 2>&1; then
      payload="$(curl -fsS --max-time 10 \
        --resolve video.lute-tlz-dddd.top:443:127.0.0.1 \
        https://video.lute-tlz-dddd.top/api/health 2>/dev/null || true)"
      if printf '%s' "$payload" | python3 -c '
import json, sys
payload = json.load(sys.stdin)
persistence = payload.get("persistence") or {}
assert payload.get("status") == "ok"
assert persistence.get("backend") == "postgresql"
assert persistence.get("status") == "healthy"
assert persistence.get("tables_verified") is True
' >/dev/null 2>&1; then
        echo "  Public HTTPS health passed with verified PostgreSQL schema (attempt $attempt/24)"
        return 0
      fi
    fi
    [ "$attempt" = "24" ] || sleep 5
  done
  return 1
}

restore_shared_nginx_config() {
  if [ "$NGINX_CONFIG_CHANGED" = "1" ] && [ -f "$NGINX_CONFIG_BACKUP" ]; then
    sudo cp "$NGINX_CONFIG_BACKUP" "$SHARED_AI_VIDEO_LOCATIONS"
    sudo docker exec ai_video_nginx nginx -t >/dev/null 2>&1 \
      && sudo docker exec ai_video_nginx nginx -s reload >/dev/null 2>&1
  fi
}

rollback_release() {
  set +e
  cleanup_restore_container
  cleanup_backup_helper
  echo "  Release failed after maintenance began; restoring preserved production compose..." >&2
  "${ACTIVE_COMMAND[@]}" up -d --no-deps --force-recreate rendering backend frontend >/dev/null 2>&1
  app_rc="$?"
  restore_shared_nginx_config
  nginx_rc="$?"
  if [ "$app_rc" -ne 0 ] || [ "$nginx_rc" -ne 0 ] \
    || ! verify_release_health || ! verify_public_health; then
    ROLLBACK_FAILED="1"
    echo "  ROLLBACK_FAILED: preserved production compose did not pass health verification." >&2
  else
    echo "  Rollback completed and passed application/public health verification." >&2
  fi
  set -e
}

restore_preswitch_services() {
  set +e
  cleanup_restore_container
  cleanup_backup_helper
  if [ "$OLD_BACKEND_STOPPED" = "1" ]; then
    "${ACTIVE_COMMAND[@]}" start rendering backend >/dev/null 2>&1
  fi
  if ! verify_release_health || ! verify_public_health; then
    ROLLBACK_FAILED="1"
    echo "  ROLLBACK_FAILED: unchanged production services did not recover." >&2
  else
    echo "  Pre-switch failure recovered without recreating application containers." >&2
  fi
  set -e
}

release_exit_handler() {
  local exit_status="$?"
  trap - EXIT
  cleanup_restore_container
  cleanup_backup_helper
  if [ "$exit_status" -ne 0 ] && [ "$DEPLOY_COMPLETE" != "1" ]; then
    if [ "$APP_SWITCH_STARTED" = "1" ]; then
      rollback_release
    elif [ "$MAINTENANCE_BEGUN" = "1" ]; then
      restore_preswitch_services
    fi
  fi
  if [ "$ROLLBACK_FAILED" = "1" ]; then
    echo "ERROR: release failed and rollback verification also failed." >&2
  fi
  exit "$exit_status"
}

trap release_exit_handler EXIT
trap 'exit 130' HUP INT TERM

echo "[0/8] Validating release inputs and compose..."
[ -f "$COMPOSE_FILE" ] || fail "release compose not found: $COMPOSE_FILE"
[ -f "$ROLLBACK_COMPOSE" ] || fail "preserved rollback compose not found"
[ -f "$AI_VIDEO_ENV_FILE" ] || fail "production backend env file not found"
[ -f "$SHARED_AI_VIDEO_LOCATIONS" ] || fail "shared AI Video nginx config not found"
[ -f "$RELEASE_AI_VIDEO_LOCATIONS" ] || fail "release AI Video nginx config not found"
python3 - "$AI_VIDEO_ENV_FILE" <<'PY'
import re
import sys
from pathlib import Path

matches = []
for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    match = re.fullmatch(
        r"\s*(?:export\s+)?MEDIA_SIGN_SECRET\s*=\s*(.*?)\s*",
        line,
    )
    if match:
        value = match.group(1)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        matches.append(value)
if len(matches) != 1:
    raise SystemExit("MEDIA_SIGN_SECRET must appear exactly once in production env")
if len(matches[0].encode("utf-8")) < 32:
    raise SystemExit("MEDIA_SIGN_SECRET must be at least 32 UTF-8 bytes")
PY
[ -f "$RELEASE_IMAGE_ARCHIVE" ] || fail "reviewed release image archive not found"
[ -f "$RELEASE_IMAGE_ARCHIVE_SHA256" ] || fail "release image archive checksum not found"
"${COMPOSE[@]}" config --quiet
echo "  Rollback source: $ACTIVE_RELEASE_KIND${PREVIOUS_RELEASE_SHA:+ ($PREVIOUS_RELEASE_SHA)}"

echo "[1/8] Loading the exact CI-reviewed backend/frontend/rendering images..."
for image in \
  "lighthouse-backend:$RELEASE_IMAGE_TAG" \
  "lighthouse-frontend:$RELEASE_IMAGE_TAG" \
  "lighthouse-rendering:$RELEASE_IMAGE_TAG"
do
  if sudo docker image inspect "$image" >/dev/null 2>&1; then
    fail "immutable release image tag already exists: $image"
  fi
done
(cd "$(dirname "$RELEASE_IMAGE_ARCHIVE")" && sha256sum -c "$(basename "$RELEASE_IMAGE_ARCHIVE_SHA256")")
sudo docker load -i "$RELEASE_IMAGE_ARCHIVE" >/dev/null
for image in \
  "lighthouse-backend:$RELEASE_IMAGE_TAG" \
  "lighthouse-frontend:$RELEASE_IMAGE_TAG" \
  "lighthouse-rendering:$RELEASE_IMAGE_TAG"
do
  image_revision="$(sudo docker image inspect --format='{{index .Config.Labels "org.opencontainers.image.revision"}}' "$image")"
  [ "$image_revision" = "$RELEASE_SOURCE_SHA" ] || fail "image revision mismatch for $image"
done
sudo docker run --rm --network none --entrypoint python3 \
  "lighthouse-backend:$RELEASE_IMAGE_TAG" -c \
  'from pathlib import Path; from src.services.provider_price_catalog import ProviderPriceCatalog; assert Path("/app/configs/provider-cost-catalog.v1.json").is_file(); ProviderPriceCatalog.load_default()'

echo "[2/8] Entering AI Video maintenance while preserving shared ingress..."
MAINTENANCE_BEGUN="1"
"${ACTIVE_COMMAND[@]}" stop rendering backend
OLD_BACKEND_STOPPED="1"

run_verified_backup() {
  local before latest manifest_status helper_name restore_name restore_password restore_url pg_image
  helper_name="ai_video_backup_${RELEASE_SOURCE_SHA:0:12}"
  BACKUP_HELPER_ID="$(sudo docker run -d --name "$helper_name" \
    --env-file "$AI_VIDEO_ENV_FILE" \
    --network lighthouse_ai_video_net \
    -v lighthouse_backend_output:/app/output \
    --entrypoint sh "lighthouse-backend:$RELEASE_IMAGE_TAG" \
    -eu -c 'exec sleep 3600')"
  [ -n "$BACKUP_HELPER_ID" ] || fail "failed to start reviewed backup helper"
  before="$(sudo find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??_??????' -print 2>/dev/null | sort | tail -1)"
  sudo RETENTION_DAYS=15 BACKUP_ROOT="$BACKUP_ROOT" \
    PROJECT_ROOT="$RELEASE_ROOT" \
    DUMP_SCRIPT="$RELEASE_ROOT/scripts/pg_dump_logical.py" \
    CONTAINER_NAME="$BACKUP_HELPER_ID" \
    /bin/bash "$RELEASE_ROOT/scripts/backup_production.sh"
  latest="$(sudo find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '20??-??-??_??????' -print | sort | tail -1)"
  [ -n "$latest" ] && [ "$latest" != "$before" ] || fail "fresh production backup was not created"
  manifest_status="$(sudo awk -F': ' '$1 == "status" {print $2}' "$latest/manifest.txt")"
  [ "$manifest_status" = "complete" ] || fail "fresh production backup is incomplete"

  restore_name="l4_restore_${RELEASE_SOURCE_SHA:0:12}"
  restore_password="$(openssl rand -hex 32)"
  pg_image="$(sudo awk -F': ' '$1 == "pg_client_image" {print $2}' "$latest/manifest.txt")"
  [[ "$pg_image" =~ ^postgres@sha256:[0-9a-f]{64}$ ]] || fail "backup PostgreSQL image is not digest pinned"
  RESTORE_CONTAINER_ID="$(sudo docker run -d --name "$restore_name" --network lighthouse_ai_video_net \
    -e POSTGRES_USER=restore -e POSTGRES_PASSWORD="$restore_password" \
    -e POSTGRES_DB=ai_video_restore "$pg_image")"
  [ -n "$RESTORE_CONTAINER_ID" ] || fail "failed to start isolated restore database"
  for attempt in $(seq 1 30); do
    if sudo docker exec "$restore_name" pg_isready -U restore -d ai_video_restore >/dev/null 2>&1; then
      break
    fi
    [ "$attempt" = "30" ] && fail "isolated restore PostgreSQL did not become ready"
    sleep 2
  done
  restore_url="postgresql://restore:${restore_password}@${restore_name}:5432/ai_video_restore"
  printf '%s\n' "$restore_url" | sudo env \
    EXPECTED_RESTORE_HOST="$restore_name" \
    RESTORE_SCOPE=isolated \
    RESTORE_CONFIRMATION=RESTORE_EMPTY_DATABASE \
    NETWORK_NAME=lighthouse_ai_video_net \
    BACKEND_CONTAINER="$BACKUP_HELPER_ID" \
    RESTORE_SCRIPT="$RELEASE_ROOT/scripts/pg_restore_logical.py" \
    VERIFY_SCRIPT="$RELEASE_ROOT/scripts/verify_restored_database.py" \
    /bin/bash "$RELEASE_ROOT/scripts/restore_backup_database.sh" "$latest" >/dev/null
  sudo test -s "$latest/restore_verified.json" || fail "fresh backup lacks restore verification evidence"
  cleanup_restore_container
  cleanup_backup_helper
  echo "  Fresh complete backup passed isolated restore verification."
}

echo "[3/8] Creating and isolated-restoring a fresh production backup..."
run_verified_backup

echo "[4/8] Applying explicit schema-first migration gate..."
"${COMPOSE[@]}" run --rm --no-deps \
  -e DEPLOY_MIGRATION_AUTH=APPLY_REVIEWED_RELEASE \
  backend /bin/bash /app/scripts/deploy_alembic_gate.sh --apply

echo "[5/8] Switching AI Video application containers behind preserved ingress..."
APP_SWITCH_STARTED="1"
"${COMPOSE[@]}" up -d --no-deps --force-recreate rendering backend frontend
verify_release_health || fail "release application health did not pass"
"${COMPOSE[@]}" run --rm --no-deps backend /bin/bash /app/scripts/deploy_alembic_gate.sh --check

echo "[6/8] Reloading only the reviewed AI Video config in preserved shared nginx..."
sudo test ! -e "$NGINX_CONFIG_BACKUP" \
  || fail "nginx rollback config already exists for this release"
sudo cp -p "$SHARED_AI_VIDEO_LOCATIONS" "$NGINX_CONFIG_BACKUP"
NGINX_CONFIG_CHANGED="1"
sudo cp "$RELEASE_AI_VIDEO_LOCATIONS" "$SHARED_AI_VIDEO_LOCATIONS"
sudo docker exec ai_video_nginx nginx -t >/dev/null
sudo docker exec ai_video_nginx nginx -s reload >/dev/null
verify_public_health || fail "release public health did not pass"

echo "[7/8] Recording the successful release pointer..."
CURRENT_LINK="$AI_VIDEO_SHARED_ROOT/current"
NEXT_LINK="$AI_VIDEO_SHARED_ROOT/.current-$RELEASE_SOURCE_SHA"
ln -sfn "$RELEASE_ROOT" "$NEXT_LINK"
python3 - "$NEXT_LINK" "$CURRENT_LINK" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
DEPLOY_COMPLETE="1"

echo "[8/8] Preserving current and previous release images for offline rollback..."
echo "  Cleanup skipped."

echo "Deploy complete: provider-off release $RELEASE_SOURCE_SHA"
