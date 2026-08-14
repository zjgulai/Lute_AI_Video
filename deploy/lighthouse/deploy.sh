#!/usr/bin/env bash
# Provider-off immutable release deployment for Tencent Lighthouse.

set -Eeuo pipefail

cd "$(dirname "$0")"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.release.yml}"
RELEASE_SOURCE_SHA="${RELEASE_SOURCE_SHA:-}"
AI_VIDEO_SHARED_ROOT="${AI_VIDEO_SHARED_ROOT:-/opt/ai-video}"
RELEASE_ROOT="$(cd ../.. && pwd)"
APP_VERSION="$(python3 "$RELEASE_ROOT/scripts/project_version.py" --check)" || {
  echo "ERROR: release semantic version projections are invalid" >&2
  exit 1
}
ROLLBACK_COMPOSE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/docker-compose.prod.yml"
AI_VIDEO_ENV_FILE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.env.prod"
PORTAL_AUTH_ENV_FILE="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.portal-auth.env"
SHARED_AI_VIDEO_LOCATIONS="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/ai_video_locations.conf"
RELEASE_AI_VIDEO_LOCATIONS="$RELEASE_ROOT/deploy/lighthouse/ai_video_locations.conf"
NGINX_CONFIG_BACKUP="$AI_VIDEO_SHARED_ROOT/deploy/lighthouse/.ai_video_locations.rollback-$RELEASE_SOURCE_SHA"
CURRENT_LINK="$AI_VIDEO_SHARED_ROOT/current"
BACKUP_ROOT="${BACKUP_ROOT:-/opt/ai-video-backups}"
BACKUP_LOCK_FILE="$BACKUP_ROOT/.backup.lock"
BACKUP_FLOCK_BIN="${BACKUP_FLOCK_BIN:-$(command -v flock || true)}"
BACKUP_RUNTIME_DIR="${BACKUP_RUNTIME_DIR:-/usr/local/libexec/ai-video-backup}"
BACKUP_SCHEDULE_ROLLBACK_DIR="${BACKUP_SCHEDULE_ROLLBACK_DIR:-$AI_VIDEO_SHARED_ROOT/.backup-schedule.rollback-$RELEASE_SOURCE_SHA}"
BACKUP_CRONTAB_BIN="${BACKUP_CRONTAB_BIN:-$(command -v crontab || true)}"
ALLOW_MAINTENANCE_WINDOW="${ALLOW_MAINTENANCE_WINDOW:-0}"
CLEANUP_AFTER_DEPLOY="${CLEANUP_AFTER_DEPLOY:-0}"
CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-180}"
RUN_TOKEN_SMOKE="${RUN_TOKEN_SMOKE:-0}"
RUN_DEPLOY_SMOKE="${RUN_DEPLOY_SMOKE:-0}"
RELEASE_IMAGE_ARCHIVE="${RELEASE_IMAGE_ARCHIVE:-}"
RELEASE_IMAGE_ARCHIVE_SHA256="${RELEASE_IMAGE_ARCHIVE_SHA256:-${RELEASE_IMAGE_ARCHIVE}.sha256}"

ACTIVE_COMMAND=()
ACTIVE_RELEASE_KIND=""
ACTIVE_APP_VERSION=""
ACTIVE_SOURCE_REVISION=""
ACTIVE_IDENTITY_REQUIRED="0"
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
BACKUP_SCHEDULE_SNAPSHOT_READY="0"
BACKUP_SCHEDULE_CHANGED="0"
CURRENT_POINTER_UPDATED="0"

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

require_safe_absolute_path() {
  local name="$1" value="$2"
  [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "$name must be an absolute path without shell metacharacters"
}

if ! [[ "$RELEASE_SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  fail "RELEASE_SOURCE_SHA must be the reviewed 40-character Git SHA"
fi
require_zero_or_one ALLOW_MAINTENANCE_WINDOW "$ALLOW_MAINTENANCE_WINDOW"
require_zero_or_one CLEANUP_AFTER_DEPLOY "$CLEANUP_AFTER_DEPLOY"
require_safe_absolute_path BACKUP_ROOT "$BACKUP_ROOT"
require_safe_absolute_path BACKUP_LOCK_FILE "$BACKUP_LOCK_FILE"
require_safe_absolute_path BACKUP_RUNTIME_DIR "$BACKUP_RUNTIME_DIR"
require_safe_absolute_path BACKUP_SCHEDULE_ROLLBACK_DIR "$BACKUP_SCHEDULE_ROLLBACK_DIR"
[ "$BACKUP_RUNTIME_DIR" != "/" ] || fail "BACKUP_RUNTIME_DIR cannot be root"
[ "$BACKUP_ROOT" != "/" ] || fail "BACKUP_ROOT cannot be root"
[ "$BACKUP_SCHEDULE_ROLLBACK_DIR" != "/" ] \
  || fail "BACKUP_SCHEDULE_ROLLBACK_DIR cannot be root"
[ -n "$BACKUP_CRONTAB_BIN" ] || fail "crontab command is required"
require_safe_absolute_path BACKUP_CRONTAB_BIN "$BACKUP_CRONTAB_BIN"
[ -n "$BACKUP_FLOCK_BIN" ] || fail "flock command is required"
require_safe_absolute_path BACKUP_FLOCK_BIN "$BACKUP_FLOCK_BIN"
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

export RELEASE_SOURCE_SHA APP_VERSION
export RELEASE_IMAGE_TAG="$RELEASE_SOURCE_SHA"
export AI_VIDEO_SHARED_ROOT AI_VIDEO_ENV_FILE PORTAL_AUTH_ENV_FILE

# Production sudo uses env_reset, so compose interpolation inputs must cross the
# privilege boundary explicitly. Do not rely on shell exports surviving sudo.
COMPOSE=(
  sudo env
  "RELEASE_SOURCE_SHA=$RELEASE_SOURCE_SHA"
  "RELEASE_IMAGE_TAG=$RELEASE_IMAGE_TAG"
  "APP_VERSION=$APP_VERSION"
  "AI_VIDEO_ENV_FILE=$AI_VIDEO_ENV_FILE"
  docker compose -f "$COMPOSE_FILE"
)

configure_active_release() {
  local previous_compose previous_app_version image
  if [ -L "$CURRENT_LINK" ]; then
    PREVIOUS_RELEASE_ROOT="$(readlink -f "$CURRENT_LINK")"
    PREVIOUS_RELEASE_SHA="${PREVIOUS_RELEASE_ROOT##*/releases-}"
    if ! [[ "$PREVIOUS_RELEASE_SHA" =~ ^[0-9a-f]{40}$ ]] \
      || [ "$PREVIOUS_RELEASE_ROOT" != "$AI_VIDEO_SHARED_ROOT/releases-$PREVIOUS_RELEASE_SHA" ]; then
      fail "current release pointer is not a valid immutable release directory"
    fi
    previous_compose="$PREVIOUS_RELEASE_ROOT/deploy/lighthouse/docker-compose.release.yml"
    [ -f "$previous_compose" ] || fail "previous release compose is unavailable"
    previous_app_version="$APP_VERSION"
    if [ -f "$PREVIOUS_RELEASE_ROOT/scripts/project_version.py" ]; then
      previous_app_version="$(python3 "$PREVIOUS_RELEASE_ROOT/scripts/project_version.py" --check)" \
        || fail "previous release semantic version projections are invalid"
      ACTIVE_APP_VERSION="$previous_app_version"
      ACTIVE_SOURCE_REVISION="$PREVIOUS_RELEASE_SHA"
      ACTIVE_IDENTITY_REQUIRED="1"
    fi
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
      "APP_VERSION=$previous_app_version"
      "AI_VIDEO_SHARED_ROOT=$AI_VIDEO_SHARED_ROOT"
      "AI_VIDEO_ENV_FILE=$AI_VIDEO_ENV_FILE"
      "PORTAL_AUTH_ENV_FILE=$PORTAL_AUTH_ENV_FILE"
      docker compose -f "$previous_compose"
    )
    ACTIVE_RELEASE_KIND="immutable"
  elif [ -e "$CURRENT_LINK" ]; then
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
  local expected_version="$1" expected_revision="$2" identity_required="$3"
  sudo docker exec ai_video_backend python3 -c '
import json
import sys
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
if sys.argv[3] == "1":
    if payload.get("version") != sys.argv[1]:
        raise SystemExit("backend semantic version does not match release")
    if payload.get("source_revision") != sys.argv[2]:
        raise SystemExit("backend source revision does not match release")
' "$expected_version" "$expected_revision" "$identity_required" >/dev/null
}

verify_legacy_renderer_health() {
  sudo docker exec ai_video_rendering node -e '
const http = require("node:http");
const request = http.get(
  "http://127.0.0.1:3001/health",
  { timeout: 10_000 },
  (response) => {
    let body = "";
    response.setEncoding("utf8");
    response.on("data", (chunk) => {
      body += chunk;
      if (body.length > 65_536) request.destroy(new Error("health payload too large"));
    });
    response.on("end", () => {
      try {
        const payload = JSON.parse(body);
        const healthy = response.statusCode === 200
          && payload.status === "ok"
          && typeof payload.remotion === "string"
          && payload.remotion.length > 0
          && payload.ffmpeg === true
          && payload.chromium === true;
        process.exit(healthy ? 0 : 1);
      } catch {
        process.exit(1);
      }
    });
  },
);
request.on("timeout", () => request.destroy(new Error("health timeout")));
request.on("error", () => process.exit(1));
' >/dev/null 2>&1
}

verify_renderer_health() {
  local probe_policy="$1"
  case "$probe_policy" in
    strict)
      sudo docker exec ai_video_rendering node /app/healthcheck.mjs \
        >/dev/null 2>&1
      ;;
    active-compatible)
      if sudo docker exec ai_video_rendering test -f /app/healthcheck.mjs \
        >/dev/null 2>&1; then
        sudo docker exec ai_video_rendering node /app/healthcheck.mjs \
          >/dev/null 2>&1
      else
        verify_legacy_renderer_health
      fi
      ;;
    *)
      fail "unknown renderer health probe policy: $probe_policy"
      ;;
  esac
}

verify_release_health() {
  local expected_version="$1" expected_revision="$2" identity_required="$3"
  local renderer_probe_policy="$4" attempt
  for attempt in $(seq 1 24); do
    if verify_backend_health "$expected_version" "$expected_revision" "$identity_required" \
      && sudo docker exec ai_video_frontend wget -qO- http://127.0.0.1:3000/ >/dev/null 2>&1 \
      && verify_renderer_health "$renderer_probe_policy"; then
      echo "  Application containers healthy with verified PostgreSQL schema (attempt $attempt/24)"
      return 0
    fi
    [ "$attempt" = "24" ] || sleep 5
  done
  return 1
}

verify_public_health() {
  local expected_version="$1" expected_revision="$2" identity_required="$3" attempt payload
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
if sys.argv[3] == "1":
    assert payload.get("version") == sys.argv[1]
    assert payload.get("source_revision") == sys.argv[2]
' "$expected_version" "$expected_revision" "$identity_required" >/dev/null 2>&1; then
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
    || ! verify_release_health "$ACTIVE_APP_VERSION" "$ACTIVE_SOURCE_REVISION" "$ACTIVE_IDENTITY_REQUIRED" active-compatible \
    || ! verify_public_health "$ACTIVE_APP_VERSION" "$ACTIVE_SOURCE_REVISION" "$ACTIVE_IDENTITY_REQUIRED"; then
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
  if ! verify_release_health "$ACTIVE_APP_VERSION" "$ACTIVE_SOURCE_REVISION" "$ACTIVE_IDENTITY_REQUIRED" active-compatible \
    || ! verify_public_health "$ACTIVE_APP_VERSION" "$ACTIVE_SOURCE_REVISION" "$ACTIVE_IDENTITY_REQUIRED"; then
    ROLLBACK_FAILED="1"
    echo "  ROLLBACK_FAILED: unchanged production services did not recover." >&2
  else
    echo "  Pre-switch failure recovered without recreating application containers." >&2
  fi
  set -e
}

cleanup_backup_schedule_snapshot() {
  local cleanup_rc=0
  if [ -n "$BACKUP_SCHEDULE_ROLLBACK_DIR" ]; then
    sudo rm -rf -- "$BACKUP_SCHEDULE_ROLLBACK_DIR" >/dev/null 2>&1 \
      || cleanup_rc=1
    sudo test ! -e "$BACKUP_SCHEDULE_ROLLBACK_DIR" || cleanup_rc=1
  fi
  if [ "$cleanup_rc" -eq 0 ]; then
    BACKUP_SCHEDULE_SNAPSHOT_READY="0"
  fi
  return "$cleanup_rc"
}

snapshot_backup_schedule() {
  sudo test ! -e "$BACKUP_SCHEDULE_ROLLBACK_DIR" \
    || fail "backup schedule rollback snapshot already exists"
  if ! sudo mkdir "$BACKUP_SCHEDULE_ROLLBACK_DIR"; then
    fail "unable to create the backup schedule rollback snapshot"
  fi
  if ! sudo chmod 0700 "$BACKUP_SCHEDULE_ROLLBACK_DIR"; then
    cleanup_backup_schedule_snapshot || true
    fail "unable to secure the backup schedule rollback snapshot"
  fi
  if ! sudo sh -eu -c '
    crontab_bin="$1"
    snapshot_dir="$2"
    if "$crontab_bin" -l >"$snapshot_dir/root.crontab" 2>"$snapshot_dir/crontab.error"; then
      touch "$snapshot_dir/crontab.present"
    elif grep -qi "no crontab for" "$snapshot_dir/crontab.error"; then
      : >"$snapshot_dir/root.crontab"
      touch "$snapshot_dir/crontab.absent"
    else
      exit 1
    fi
    rm -f "$snapshot_dir/crontab.error"
  ' sh "$BACKUP_CRONTAB_BIN" "$BACKUP_SCHEDULE_ROLLBACK_DIR"; then
    cleanup_backup_schedule_snapshot || true
    fail "unable to snapshot the root backup crontab"
  fi

  if sudo test -L "$BACKUP_RUNTIME_DIR"; then
    cleanup_backup_schedule_snapshot || true
    fail "backup runtime directory must not be a symlink"
  elif sudo test -d "$BACKUP_RUNTIME_DIR"; then
    if ! sudo cp -a "$BACKUP_RUNTIME_DIR" "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" \
      || ! sudo touch "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime.present"; then
      cleanup_backup_schedule_snapshot || true
      fail "unable to snapshot the backup runtime"
    fi
  elif sudo test -e "$BACKUP_RUNTIME_DIR"; then
    cleanup_backup_schedule_snapshot || true
    fail "backup runtime path exists but is not a directory"
  else
    if ! sudo touch "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime.absent"; then
      cleanup_backup_schedule_snapshot || true
      fail "unable to record the absent backup runtime"
    fi
  fi
  BACKUP_SCHEDULE_SNAPSHOT_READY="1"
}

restore_backup_schedule() {
  local candidate_runtime_backup compensation_rc restore_rc=0 runtime_stage
  candidate_runtime_backup="${BACKUP_RUNTIME_DIR}.candidate-${RELEASE_SOURCE_SHA}"
  runtime_stage="${BACKUP_RUNTIME_DIR}.restore-${RELEASE_SOURCE_SHA}"
  [ "$BACKUP_SCHEDULE_SNAPSHOT_READY" = "1" ] || return 0

  if ! sudo sh -eu -c '
    snapshot_dir="$1"
    present_count=0
    absent_count=0
    [ -f "$snapshot_dir/crontab.present" ] && present_count=1
    [ -f "$snapshot_dir/crontab.absent" ] && absent_count=1
    [ "$((present_count + absent_count))" -eq 1 ]
    present_count=0
    absent_count=0
    [ -f "$snapshot_dir/runtime.present" ] && present_count=1
    [ -f "$snapshot_dir/runtime.absent" ] && absent_count=1
    [ "$((present_count + absent_count))" -eq 1 ]
  ' sh "$BACKUP_SCHEDULE_ROLLBACK_DIR"; then
    echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: snapshot markers are incomplete or ambiguous; live schedule preserved." >&2
    return 1
  fi

  if sudo test -f "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime.present"; then
    if sudo test -L "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" \
      || ! sudo test -d "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" \
      || ! sudo test -r "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" \
      || ! sudo test -x "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime"; then
      echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: runtime snapshot is unavailable; live schedule preserved." >&2
      return 1
    fi
    if ! sudo test ! -e "$runtime_stage" \
      || ! sudo test ! -e "$candidate_runtime_backup" \
      || ! sudo cp -a "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" "$runtime_stage" \
      || ! sudo diff -qr "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" "$runtime_stage" \
        >/dev/null 2>&1; then
      sudo rm -rf -- "$runtime_stage" >/dev/null 2>&1 || true
      echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: unable to stage the original runtime; live schedule preserved." >&2
      return 1
    fi
  fi

  if sudo test -L "$BACKUP_RUNTIME_DIR" \
    || ! sudo test -d "$BACKUP_RUNTIME_DIR" \
    || ! sudo test ! -e "$candidate_runtime_backup"; then
    sudo rm -rf -- "$runtime_stage" >/dev/null 2>&1 || true
    echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: candidate runtime cannot be preserved; live schedule preserved." >&2
    return 1
  fi

  if ! sudo mv -- "$BACKUP_RUNTIME_DIR" "$candidate_runtime_backup"; then
    sudo rm -rf -- "$runtime_stage" >/dev/null 2>&1 || true
    echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: candidate runtime could not be preserved; live schedule preserved." >&2
    return 1
  fi

  if sudo test -f "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime.present"; then
    if ! sudo mv -- "$runtime_stage" "$BACKUP_RUNTIME_DIR" \
      || ! sudo diff -qr "$BACKUP_SCHEDULE_ROLLBACK_DIR/runtime" "$BACKUP_RUNTIME_DIR" \
        >/dev/null 2>&1; then
      compensation_rc=0
      sudo rm -rf -- "$BACKUP_RUNTIME_DIR" "$runtime_stage" \
        >/dev/null 2>&1 || compensation_rc=1
      if [ "$compensation_rc" -eq 0 ]; then
        sudo mv -- "$candidate_runtime_backup" "$BACKUP_RUNTIME_DIR" \
          >/dev/null 2>&1 || compensation_rc=1
      fi
      if [ "$compensation_rc" -eq 0 ]; then
        echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: runtime restore failed; disabled candidate runtime was retained." >&2
      else
        ROLLBACK_FAILED="1"
        echo "  BACKUP_SCHEDULE_STATE_UNKNOWN: runtime restore compensation failed; snapshot retained and manual recovery is required." >&2
      fi
      return 1
    fi
  elif ! sudo test ! -e "$BACKUP_RUNTIME_DIR"; then
    compensation_rc=0
    sudo rm -rf -- "$BACKUP_RUNTIME_DIR" "$runtime_stage" \
      >/dev/null 2>&1 || compensation_rc=1
    if [ "$compensation_rc" -eq 0 ]; then
      sudo mv -- "$candidate_runtime_backup" "$BACKUP_RUNTIME_DIR" \
        >/dev/null 2>&1 || compensation_rc=1
    fi
    if [ "$compensation_rc" -eq 0 ]; then
      echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: absent runtime restore failed; disabled candidate runtime was retained." >&2
    else
      ROLLBACK_FAILED="1"
      echo "  BACKUP_SCHEDULE_STATE_UNKNOWN: absent-runtime compensation failed; snapshot retained and manual recovery is required." >&2
    fi
    return 1
  fi

  if sudo test -f "$BACKUP_SCHEDULE_ROLLBACK_DIR/crontab.present"; then
    sudo "$BACKUP_CRONTAB_BIN" "$BACKUP_SCHEDULE_ROLLBACK_DIR/root.crontab" \
      || restore_rc=1
    if [ "$restore_rc" -eq 0 ]; then
      sudo sh -eu -c '
        "$1" -l | cmp -s - "$2"
      ' sh "$BACKUP_CRONTAB_BIN" "$BACKUP_SCHEDULE_ROLLBACK_DIR/root.crontab" \
        || restore_rc=1
    fi
  else
    sudo "$BACKUP_CRONTAB_BIN" -r >/dev/null 2>&1 || true
    sudo sh -eu -c '
      if output=$("$1" -l 2>&1); then
        exit 1
      fi
      printf "%s" "$output" | grep -qi "no crontab for"
    ' sh "$BACKUP_CRONTAB_BIN" || restore_rc=1
  fi

  if [ "$restore_rc" -ne 0 ]; then
    compensation_rc=0
    sudo rm -rf -- "$BACKUP_RUNTIME_DIR" >/dev/null 2>&1 \
      || compensation_rc=1
    if [ "$compensation_rc" -eq 0 ]; then
      sudo mv -- "$candidate_runtime_backup" "$BACKUP_RUNTIME_DIR" \
        >/dev/null 2>&1 || compensation_rc=1
    fi
    disable_backup_schedule_for_rollback >/dev/null 2>&1 \
      || compensation_rc=1
    if [ "$compensation_rc" -eq 0 ]; then
      echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: original cron was not verified; disabled candidate schedule was retained." >&2
    else
      ROLLBACK_FAILED="1"
      echo "  BACKUP_SCHEDULE_STATE_UNKNOWN: runtime or cron compensation failed; snapshot retained and manual recovery is required." >&2
    fi
    return 1
  fi

  sudo rm -rf -- "$candidate_runtime_backup" "$runtime_stage" \
    >/dev/null 2>&1 || restore_rc=1
  cleanup_backup_schedule_snapshot || restore_rc=1
  if [ "$restore_rc" -eq 0 ]; then
    BACKUP_SCHEDULE_CHANGED="0"
    echo "  Original backup runtime and root cron were restored." >&2
    return 0
  fi
  echo "  BACKUP_SCHEDULE_ROLLBACK_FAILED: original backup schedule was not restored." >&2
  return 1
}

commit_backup_schedule() {
  cleanup_backup_schedule_snapshot \
    || fail "unable to remove committed backup schedule rollback snapshot"
  BACKUP_SCHEDULE_CHANGED="0"
}

restore_release_pointer() {
  local rollback_link
  [ "$CURRENT_POINTER_UPDATED" = "1" ] || return 0
  if [ -n "$PREVIOUS_RELEASE_ROOT" ]; then
    rollback_link="$AI_VIDEO_SHARED_ROOT/.current-rollback-$RELEASE_SOURCE_SHA"
    sudo ln -sfn "$PREVIOUS_RELEASE_ROOT" "$rollback_link"
    if ! sudo python3 - "$rollback_link" "$CURRENT_LINK" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
    then
      return 1
    fi
  else
    if ! sudo python3 - "$CURRENT_LINK" "$RELEASE_ROOT" <<'PY'
import os
import sys
from pathlib import Path

current = Path(sys.argv[1])
expected = Path(sys.argv[2]).resolve()
if not current.is_symlink() or Path(os.path.realpath(current)) != expected:
    raise SystemExit("refusing to remove an unexpected current release pointer")
current.unlink()
PY
    then
      return 1
    fi
  fi
  CURRENT_POINTER_UPDATED="0"
  echo "  Previous release pointer was restored before original backup schedule restoration." >&2
}

install_and_verify_backup_schedule() {
  snapshot_backup_schedule
  BACKUP_SCHEDULE_CHANGED="1"
  sudo env \
    MODE=install \
    CRON_ENABLED=0 \
    MIGRATE_LEGACY=1 \
    RETENTION_DAYS=3 \
    CURRENT_RELEASE_ROOT="$RELEASE_ROOT" \
    SOURCE_MANIFEST_PATH="$RELEASE_ROOT/source-manifest.v1.json" \
    RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    BACKUP_RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    /bin/bash "$RELEASE_ROOT/scripts/install_backup_cron.sh"
  sudo env \
    MODE=verify \
    CRON_ENABLED=0 \
    RETENTION_DAYS=3 \
    CURRENT_RELEASE_ROOT="$RELEASE_ROOT" \
    SOURCE_MANIFEST_PATH="$RELEASE_ROOT/source-manifest.v1.json" \
    RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    BACKUP_RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    /bin/bash "$RELEASE_ROOT/scripts/install_backup_cron.sh"
}

verify_no_backup_in_progress() {
  sudo test -d "$BACKUP_ROOT" || fail "production backup root is missing"
  sudo "$BACKUP_FLOCK_BIN" -n "$BACKUP_LOCK_FILE" true \
    || fail "another production backup is already running"
}

activate_backup_schedule() {
  sudo env \
    MODE=install \
    CRON_ENABLED=1 \
    MIGRATE_LEGACY=1 \
    RETENTION_DAYS=3 \
    CURRENT_RELEASE_ROOT="$CURRENT_LINK" \
    SOURCE_MANIFEST_PATH="$CURRENT_LINK/source-manifest.v1.json" \
    RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    BACKUP_RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    /bin/bash "$RELEASE_ROOT/scripts/install_backup_cron.sh"
  sudo env \
    MODE=verify \
    CRON_ENABLED=1 \
    RETENTION_DAYS=3 \
    CURRENT_RELEASE_ROOT="$CURRENT_LINK" \
    SOURCE_MANIFEST_PATH="$CURRENT_LINK/source-manifest.v1.json" \
    RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    BACKUP_RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    /bin/bash "$RELEASE_ROOT/scripts/install_backup_cron.sh"
}

disable_backup_schedule_for_rollback() {
  sudo env \
    MODE=install \
    CRON_ENABLED=0 \
    MIGRATE_LEGACY=1 \
    RETENTION_DAYS=3 \
    CURRENT_RELEASE_ROOT="$RELEASE_ROOT" \
    SOURCE_MANIFEST_PATH="$RELEASE_ROOT/source-manifest.v1.json" \
    RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    BACKUP_RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    /bin/bash "$RELEASE_ROOT/scripts/install_backup_cron.sh" \
    || return 1
  sudo env \
    MODE=verify \
    CRON_ENABLED=0 \
    RETENTION_DAYS=3 \
    CURRENT_RELEASE_ROOT="$RELEASE_ROOT" \
    SOURCE_MANIFEST_PATH="$RELEASE_ROOT/source-manifest.v1.json" \
    RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    BACKUP_RUNTIME_DIR="$BACKUP_RUNTIME_DIR" \
    /bin/bash "$RELEASE_ROOT/scripts/install_backup_cron.sh" \
    || return 1
}

release_exit_handler() {
  local exit_status="$?"
  local rollback_consistent="1"
  trap - EXIT
  cleanup_restore_container
  cleanup_backup_helper
  if [ "$exit_status" -ne 0 ] && [ "$DEPLOY_COMPLETE" != "1" ]; then
    if [ "$BACKUP_SCHEDULE_CHANGED" = "1" ] \
      && [ "$CURRENT_POINTER_UPDATED" = "1" ] \
      && ! disable_backup_schedule_for_rollback; then
      rollback_consistent="0"
      ROLLBACK_FAILED="1"
      echo "  BACKUP_SCHEDULE_QUIESCE_FAILED: current pointer and original schedule were not changed." >&2
    fi
    if [ "$CURRENT_POINTER_UPDATED" = "1" ] \
      && [ "$rollback_consistent" = "1" ] \
      && ! restore_release_pointer; then
      rollback_consistent="0"
      ROLLBACK_FAILED="1"
      echo "  RELEASE_POINTER_ROLLBACK_FAILED: current pointer was not restored; backup schedule remains disabled." >&2
    fi
    if [ "$rollback_consistent" = "1" ]; then
      if [ "$APP_SWITCH_STARTED" = "1" ]; then
        rollback_release
      elif [ "$MAINTENANCE_BEGUN" = "1" ]; then
        restore_preswitch_services
      fi
      if [ "$ROLLBACK_FAILED" = "1" ]; then
        rollback_consistent="0"
        echo "  BACKUP_SCHEDULE_RESTORE_SKIPPED: application rollback is unhealthy; backup schedule remains disabled." >&2
      fi
    else
      echo "  APPLICATION_ROLLBACK_SKIPPED: preserving the candidate application/current consistency for manual recovery." >&2
    fi
    if [ "$BACKUP_SCHEDULE_CHANGED" = "1" ] \
      && [ "$rollback_consistent" = "1" ] \
      && ! restore_backup_schedule; then
      ROLLBACK_FAILED="1"
    fi
  fi
  if [ "$ROLLBACK_FAILED" = "1" ]; then
    echo "ERROR: release failed and rollback verification also failed." >&2
  fi
  exit "$exit_status"
}

trap release_exit_handler EXIT
trap 'exit 130' HUP INT TERM

echo "[0/9] Validating release inputs and compose..."
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

echo "[1/9] Loading the exact CI-reviewed backend/frontend/rendering images..."
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
  image_version="$(sudo docker image inspect --format='{{index .Config.Labels "org.opencontainers.image.version"}}' "$image")"
  [ "$image_version" = "$APP_VERSION" ] || fail "image semantic version mismatch for $image"
done
sudo docker run --rm --network none --entrypoint python3 \
  "lighthouse-backend:$RELEASE_IMAGE_TAG" -c \
  'from pathlib import Path; from src.services.provider_price_catalog import ProviderPriceCatalog; assert Path("/app/configs/provider-cost-catalog.v1.json").is_file(); ProviderPriceCatalog.load_default()'

echo "[2/9] Quiescing and verifying the production backup schedule..."
install_and_verify_backup_schedule
verify_no_backup_in_progress

echo "[3/9] Entering AI Video maintenance while preserving shared ingress..."
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
  sudo RETENTION_DAYS=3 BACKUP_ROOT="$BACKUP_ROOT" \
    PROJECT_ROOT="$RELEASE_ROOT" \
    SOURCE_MANIFEST_PATH="$RELEASE_ROOT/source-manifest.v1.json" \
    DUMP_SCRIPT="$BACKUP_RUNTIME_DIR/pg_dump_logical.py" \
    BACKUP_MANIFEST_SCRIPT="$BACKUP_RUNTIME_DIR/backup_manifest.py" \
    CONTAINER_NAME="$BACKUP_HELPER_ID" \
    /bin/bash "$BACKUP_RUNTIME_DIR/backup_production.sh"
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
    BACKUP_MANIFEST_SCRIPT="$RELEASE_ROOT/scripts/backup_manifest.py" \
    /bin/bash "$RELEASE_ROOT/scripts/restore_backup_database.sh" "$latest" >/dev/null
  sudo test -s "$latest/restore_verified.json" || fail "fresh backup lacks restore verification evidence"
  sudo python3 - "$latest/pg_dump_stats.json" "$latest/restore_verified.json" <<'PY'
import json
import sys
from pathlib import Path

stats = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
restore = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
expected = stats.get("expected_tables")
tables = stats.get("tables")
actual_counts = restore.get("actual_counts")
if (
    not isinstance(expected, list)
    or not expected
    or any(not isinstance(name, str) or not name for name in expected)
    or len(expected) != len(set(expected))
    or not isinstance(tables, dict)
    or set(tables) != set(expected)
    or restore.get("status") != "passed"
    or restore.get("table_count") != len(expected)
    or not isinstance(actual_counts, dict)
    or set(actual_counts) != set(expected)
):
    raise SystemExit(
        "scheduled backup table coverage differs from isolated restore"
    )
print(f"scheduled_backup_business_table_count={len(expected)}")
PY
  cleanup_restore_container
  cleanup_backup_helper
  echo "  Fresh complete backup passed isolated restore verification."
}

echo "[4/9] Creating and isolated-restoring a fresh production backup..."
run_verified_backup

echo "[5/9] Applying explicit schema-first migration gate..."
"${COMPOSE[@]}" run --rm --no-deps \
  -e DEPLOY_MIGRATION_AUTH=APPLY_REVIEWED_RELEASE \
  backend /bin/bash /app/scripts/deploy_alembic_gate.sh --apply

echo "[6/9] Switching AI Video application containers behind preserved ingress..."
APP_SWITCH_STARTED="1"
"${COMPOSE[@]}" up -d --no-deps --force-recreate rendering backend frontend
verify_release_health "$APP_VERSION" "$RELEASE_SOURCE_SHA" 1 strict \
  || fail "release application health or identity did not pass"
"${COMPOSE[@]}" run --rm --no-deps backend /bin/bash /app/scripts/deploy_alembic_gate.sh --check

echo "[7/9] Reloading only the reviewed AI Video config in preserved shared nginx..."
sudo test ! -e "$NGINX_CONFIG_BACKUP" \
  || fail "nginx rollback config already exists for this release"
sudo cp -p "$SHARED_AI_VIDEO_LOCATIONS" "$NGINX_CONFIG_BACKUP"
NGINX_CONFIG_CHANGED="1"
sudo cp "$RELEASE_AI_VIDEO_LOCATIONS" "$SHARED_AI_VIDEO_LOCATIONS"
sudo docker exec ai_video_nginx nginx -t >/dev/null
sudo docker exec ai_video_nginx nginx -s reload >/dev/null
verify_public_health "$APP_VERSION" "$RELEASE_SOURCE_SHA" 1 \
  || fail "release public health or identity did not pass"

echo "[8/9] Recording the successful release pointer and backup schedule..."
NEXT_LINK="$AI_VIDEO_SHARED_ROOT/.current-$RELEASE_SOURCE_SHA"
sudo ln -sfn "$RELEASE_ROOT" "$NEXT_LINK"
sudo python3 - "$NEXT_LINK" "$CURRENT_LINK" <<'PY'
import os
import sys

os.replace(sys.argv[1], sys.argv[2])
PY
CURRENT_POINTER_UPDATED="1"
activate_backup_schedule
commit_backup_schedule
DEPLOY_COMPLETE="1"

echo "[9/9] Preserving current and previous release images for offline rollback..."
echo "  Cleanup skipped."

echo "Deploy complete: provider-off release $RELEASE_SOURCE_SHA"
