#!/usr/bin/env bash
# Install a root-owned backup runtime and its managed root-crontab entry.

set -euo pipefail

RETENTION_DAYS="${RETENTION_DAYS:-15}"
BACKUP_SCRIPT="${BACKUP_SCRIPT:-/opt/ai-video/scripts/backup_production.sh}"
DUMP_SCRIPT_SOURCE="${DUMP_SCRIPT_SOURCE:-$(dirname "$BACKUP_SCRIPT")/pg_dump_logical.py}"
MANIFEST_SCRIPT_SOURCE="${MANIFEST_SCRIPT_SOURCE:-$(dirname "$BACKUP_SCRIPT")/backup_manifest.py}"
CURRENT_RELEASE_ROOT="${CURRENT_RELEASE_ROOT:-/opt/ai-video/current}"
SOURCE_MANIFEST_PATH="${SOURCE_MANIFEST_PATH:-${CURRENT_RELEASE_ROOT}/source-manifest.v1.json}"
RUNTIME_DIR="${RUNTIME_DIR:-/usr/local/libexec/ai-video-backup}"
BACKUP_LOG_FILE="${BACKUP_LOG_FILE:-/var/log/hermes-backup.log}"
CRON_LOCK_FILE="${CRON_LOCK_FILE:-/var/lock/ai-video-backup-cron.lock}"
MIGRATE_LEGACY="${MIGRATE_LEGACY:-0}"
CRONTAB_BIN="${CRONTAB_BIN:-crontab}"
INSTALL_BIN="${INSTALL_BIN:-install}"
CHOWN_BIN="${CHOWN_BIN:-chown}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
FLOCK_BIN="${FLOCK_BIN:-flock}"
MARKER="ai-video-production-backup"
RUNTIME_DIR="${RUNTIME_DIR%/}"
RUNTIME_BACKUP_SCRIPT="${RUNTIME_DIR}/backup_production.sh"
RUNTIME_DUMP_SCRIPT="${RUNTIME_DIR}/pg_dump_logical.py"
RUNTIME_MANIFEST_SCRIPT="${RUNTIME_DIR}/backup_manifest.py"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_safe_absolute_path() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || fail "${name} must be an absolute path without shell metacharacters"
}

[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]*$ ]] \
  || fail "RETENTION_DAYS must be a positive integer"
[[ "$MIGRATE_LEGACY" =~ ^[01]$ ]] \
  || fail "MIGRATE_LEGACY must be 0 or 1"
require_safe_absolute_path "BACKUP_SCRIPT" "$BACKUP_SCRIPT"
require_safe_absolute_path "DUMP_SCRIPT_SOURCE" "$DUMP_SCRIPT_SOURCE"
require_safe_absolute_path "MANIFEST_SCRIPT_SOURCE" "$MANIFEST_SCRIPT_SOURCE"
require_safe_absolute_path "CURRENT_RELEASE_ROOT" "$CURRENT_RELEASE_ROOT"
require_safe_absolute_path "SOURCE_MANIFEST_PATH" "$SOURCE_MANIFEST_PATH"
require_safe_absolute_path "RUNTIME_DIR" "$RUNTIME_DIR"
require_safe_absolute_path "BACKUP_LOG_FILE" "$BACKUP_LOG_FILE"
require_safe_absolute_path "CRON_LOCK_FILE" "$CRON_LOCK_FILE"
[ "$RUNTIME_DIR" != "/" ] || fail "RUNTIME_DIR cannot be root"
[ "$(id -u)" -eq 0 ] || fail "run with sudo /bin/bash so the root crontab is updated"

for command_name in \
  "$CRONTAB_BIN" "$INSTALL_BIN" "$CHOWN_BIN" "$DOCKER_BIN" "$FLOCK_BIN"
do
  command -v "$command_name" >/dev/null 2>&1 \
    || fail "required command not found: ${command_name}"
done
[ -f "$BACKUP_SCRIPT" ] || fail "backup script not found: ${BACKUP_SCRIPT}"
[ -f "$DUMP_SCRIPT_SOURCE" ] || fail "dump script not found: ${DUMP_SCRIPT_SOURCE}"
[ -f "$MANIFEST_SCRIPT_SOURCE" ] \
  || fail "manifest script not found: ${MANIFEST_SCRIPT_SOURCE}"
[ -f "$SOURCE_MANIFEST_PATH" ] \
  || fail "source manifest not found: ${SOURCE_MANIFEST_PATH}"

DOCKER_PATH=$(command -v "$DOCKER_BIN")
FLOCK_PATH=$(command -v "$FLOCK_BIN")
require_safe_absolute_path "DOCKER_PATH" "$DOCKER_PATH"
require_safe_absolute_path "FLOCK_PATH" "$FLOCK_PATH"

mkdir -p "$(dirname "$CRON_LOCK_FILE")"
exec 8>"$CRON_LOCK_FILE"
"$FLOCK_BIN" -n 8 || fail "another backup cron installation is running"

CURRENT=$(mktemp)
UPDATED=$(mktemp)
ERROR_LOG=$(mktemp)
cleanup() {
  rm -f "$CURRENT" "$UPDATED" "$ERROR_LOG"
}
trap cleanup EXIT

if ! "$CRONTAB_BIN" -l >"$CURRENT" 2>"$ERROR_LOG"; then
  if ! grep -qi "no crontab for" "$ERROR_LOG"; then
    cat "$ERROR_LOG" >&2
    fail "unable to read the current root crontab"
  fi
  : >"$CURRENT"
fi

LEGACY_COUNT=$(awk -v marker="$MARKER" -v script="$BACKUP_SCRIPT" '
  index($0, marker) == 0 && index($0, script) > 0 { count += 1 }
  END { print count + 0 }
' "$CURRENT")
if [ "$LEGACY_COUNT" -gt 0 ] && [ "$MIGRATE_LEGACY" != "1" ]; then
  fail "legacy backup cron found; review it and rerun with MIGRATE_LEGACY=1"
fi

awk -v marker="$MARKER" -v script="$BACKUP_SCRIPT" -v migrate="$MIGRATE_LEGACY" '
  index($0, marker) > 0 { next }
  migrate == "1" && index($0, script) > 0 { next }
  { print }
' "$CURRENT" >"$UPDATED"

"$INSTALL_BIN" -d -o root -g root -m 0755 "$RUNTIME_DIR"
"$INSTALL_BIN" -o root -g root -m 0755 "$BACKUP_SCRIPT" "$RUNTIME_BACKUP_SCRIPT"
"$INSTALL_BIN" -o root -g root -m 0644 "$DUMP_SCRIPT_SOURCE" "$RUNTIME_DUMP_SCRIPT"
"$INSTALL_BIN" -o root -g root -m 0644 \
  "$MANIFEST_SCRIPT_SOURCE" "$RUNTIME_MANIFEST_SCRIPT"

mkdir -p "$(dirname "$BACKUP_LOG_FILE")"
touch "$BACKUP_LOG_FILE"
"$CHOWN_BIN" root:root "$BACKUP_LOG_FILE"
chmod 0600 "$BACKUP_LOG_FILE"

CRON_LINE="0 3 * * * umask 077; DOCKER_BIN=${DOCKER_PATH} FLOCK_BIN=${FLOCK_PATH} PROJECT_ROOT=${CURRENT_RELEASE_ROOT} SOURCE_MANIFEST_PATH=${SOURCE_MANIFEST_PATH} DUMP_SCRIPT=${RUNTIME_DUMP_SCRIPT} BACKUP_MANIFEST_SCRIPT=${RUNTIME_MANIFEST_SCRIPT} RETENTION_DAYS=${RETENTION_DAYS} /bin/bash ${RUNTIME_BACKUP_SCRIPT} >> ${BACKUP_LOG_FILE} 2>&1 # ${MARKER}"
printf '%s\n' "$CRON_LINE" >>"$UPDATED"

"$CRONTAB_BIN" "$UPDATED"

INSTALLED_COUNT=$("$CRONTAB_BIN" -l | grep -Fc "$MARKER" || true)
[ "$INSTALLED_COUNT" -eq 1 ] || fail "backup cron verification failed"
INSTALLED_LINE=$("$CRONTAB_BIN" -l | grep -F "$MARKER")
[ "$INSTALLED_LINE" = "$CRON_LINE" ] || fail "installed backup cron differs from expected"
printf 'Installed root cron entry:\n%s\n' "$INSTALLED_LINE"
