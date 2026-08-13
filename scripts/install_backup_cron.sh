#!/usr/bin/env bash
# Install a root-owned backup runtime and its managed root-crontab entry.

set -euo pipefail

RETENTION_DAYS="${RETENTION_DAYS:-3}"
MAX_RETENTION_DAYS=3650
MODE="${MODE:-install}"
CRON_ENABLED="${CRON_ENABLED:-1}"
CURRENT_RELEASE_ROOT="${CURRENT_RELEASE_ROOT:-/opt/ai-video/current}"
BACKUP_SCRIPT="${BACKUP_SCRIPT:-${CURRENT_RELEASE_ROOT}/scripts/backup_production.sh}"
DUMP_SCRIPT_SOURCE="${DUMP_SCRIPT_SOURCE:-${CURRENT_RELEASE_ROOT}/scripts/pg_dump_logical.py}"
MANIFEST_SCRIPT_SOURCE="${MANIFEST_SCRIPT_SOURCE:-${CURRENT_RELEASE_ROOT}/scripts/backup_manifest.py}"
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
CMP_BIN="${CMP_BIN:-cmp}"
STAT_BIN="${STAT_BIN:-stat}"
MARKER="ai-video-production-backup"
LEGACY_SHARED_BACKUP_SCRIPT="/opt/ai-video/scripts/backup_production.sh"
LEGACY_CURRENT_BACKUP_SCRIPT="/opt/ai-video/current/scripts/backup_production.sh"
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

[[ "$RETENTION_DAYS" =~ ^[1-9][0-9]{0,3}$ ]] \
  || fail "RETENTION_DAYS must be a canonical decimal integer between 1 and ${MAX_RETENTION_DAYS}"
[ "$((10#$RETENTION_DAYS))" -le "$MAX_RETENTION_DAYS" ] \
  || fail "RETENTION_DAYS must be a canonical decimal integer between 1 and ${MAX_RETENTION_DAYS}"
[[ "$MODE" =~ ^(install|verify)$ ]] \
  || fail "MODE must be install or verify"
[[ "$CRON_ENABLED" =~ ^[01]$ ]] \
  || fail "CRON_ENABLED must be 0 or 1"
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

for command_name in "$CRONTAB_BIN" "$DOCKER_BIN" "$FLOCK_BIN" "$CMP_BIN" "$STAT_BIN"
do
  command -v "$command_name" >/dev/null 2>&1 \
    || fail "required command not found: ${command_name}"
done
if [ "$MODE" = "install" ]; then
  for command_name in "$INSTALL_BIN" "$CHOWN_BIN"; do
    command -v "$command_name" >/dev/null 2>&1 \
      || fail "required command not found: ${command_name}"
  done
fi
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

CRON_COMMAND="umask 077; DOCKER_BIN=${DOCKER_PATH} FLOCK_BIN=${FLOCK_PATH} PROJECT_ROOT=${CURRENT_RELEASE_ROOT} SOURCE_MANIFEST_PATH=${SOURCE_MANIFEST_PATH} DUMP_SCRIPT=${RUNTIME_DUMP_SCRIPT} BACKUP_MANIFEST_SCRIPT=${RUNTIME_MANIFEST_SCRIPT} RETENTION_DAYS=${RETENTION_DAYS} /bin/bash ${RUNTIME_BACKUP_SCRIPT} >> ${BACKUP_LOG_FILE} 2>&1"
if [ "$CRON_ENABLED" = "1" ]; then
  CRON_LINE="0 3 * * * ${CRON_COMMAND} # ${MARKER}"
else
  CRON_LINE="# ai-video-production-backup-disabled ${CRON_COMMAND} # ${MARKER}"
fi

count_unmanaged_backup_jobs() {
  awk \
    -v marker="$MARKER" \
    -v current="$BACKUP_SCRIPT" \
    -v shared="$LEGACY_SHARED_BACKUP_SCRIPT" \
    -v legacy_current="$LEGACY_CURRENT_BACKUP_SCRIPT" \
    -v runtime="$RUNTIME_BACKUP_SCRIPT" '
    function has_backup_script() {
      for (field = 1; field <= NF; field += 1) {
        if ($field == current || $field == shared || $field == legacy_current || $field == runtime) {
          return 1
        }
      }
      return 0
    }
    index($0, marker) == 0 && has_backup_script() { count += 1 }
    END { print count + 0 }
  '
}

verify_runtime() {
  local installed_count installed_legacy_count installed_line
  local path expected_kind expected_mode actual_uid actual_gid actual_mode
  local runtime_contract

  for runtime_contract in \
    "${RUNTIME_DIR}:directory:755" \
    "${RUNTIME_BACKUP_SCRIPT}:file:755" \
    "${RUNTIME_DUMP_SCRIPT}:file:644" \
    "${RUNTIME_MANIFEST_SCRIPT}:file:644"
  do
    IFS=: read -r path expected_kind expected_mode <<<"$runtime_contract"
    [ ! -L "$path" ] \
      || fail "installed backup runtime metadata differs from expected"
    if [ "$expected_kind" = "directory" ]; then
      [ -d "$path" ] \
        || fail "installed backup runtime metadata differs from expected"
    else
      [ -f "$path" ] \
        || fail "installed backup runtime metadata differs from expected"
    fi
    if actual_uid=$("$STAT_BIN" -c '%u' "$path" 2>/dev/null); then
      actual_gid=$("$STAT_BIN" -c '%g' "$path")
      actual_mode=$("$STAT_BIN" -c '%a' "$path")
    else
      actual_uid=$("$STAT_BIN" -f '%u' "$path")
      actual_gid=$("$STAT_BIN" -f '%g' "$path")
      actual_mode=$("$STAT_BIN" -f '%Lp' "$path")
    fi
    [ "$actual_uid" = "0" ] \
      && [ "$actual_gid" = "0" ] \
      && [ "$actual_mode" = "$expected_mode" ] \
      || fail "installed backup runtime metadata differs from expected"
  done

  [ -f "$RUNTIME_BACKUP_SCRIPT" ] \
    || fail "installed backup runtime is missing: ${RUNTIME_BACKUP_SCRIPT}"
  [ -f "$RUNTIME_DUMP_SCRIPT" ] \
    || fail "installed dump runtime is missing: ${RUNTIME_DUMP_SCRIPT}"
  [ -f "$RUNTIME_MANIFEST_SCRIPT" ] \
    || fail "installed manifest runtime is missing: ${RUNTIME_MANIFEST_SCRIPT}"
  "$CMP_BIN" -s "$BACKUP_SCRIPT" "$RUNTIME_BACKUP_SCRIPT" \
    || fail "installed backup runtime differs from reviewed source"
  "$CMP_BIN" -s "$DUMP_SCRIPT_SOURCE" "$RUNTIME_DUMP_SCRIPT" \
    || fail "installed dump runtime differs from reviewed source"
  "$CMP_BIN" -s "$MANIFEST_SCRIPT_SOURCE" "$RUNTIME_MANIFEST_SCRIPT" \
    || fail "installed manifest runtime differs from reviewed source"

  installed_legacy_count=$("$CRONTAB_BIN" -l | count_unmanaged_backup_jobs)
  [ "$installed_legacy_count" -eq 0 ] \
    || fail "unmanaged backup cron verification failed"
  installed_count=$("$CRONTAB_BIN" -l | grep -Fc "$MARKER" || true)
  [ "$installed_count" -eq 1 ] || fail "backup cron verification failed"
  installed_line=$("$CRONTAB_BIN" -l | grep -F "$MARKER")
  [ "$installed_line" = "$CRON_LINE" ] \
    || fail "installed backup cron differs from expected"
  printf 'backup_runtime_verification=passed\n'
}

if [ "$MODE" = "verify" ]; then
  verify_runtime
  exit 0
fi

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

LEGACY_COUNT=$(count_unmanaged_backup_jobs <"$CURRENT")
if [ "$LEGACY_COUNT" -gt 0 ] && [ "$MIGRATE_LEGACY" != "1" ]; then
  fail "legacy backup cron found; review it and rerun with MIGRATE_LEGACY=1"
fi

awk \
  -v marker="$MARKER" \
  -v current="$BACKUP_SCRIPT" \
  -v shared="$LEGACY_SHARED_BACKUP_SCRIPT" \
  -v legacy_current="$LEGACY_CURRENT_BACKUP_SCRIPT" \
  -v runtime="$RUNTIME_BACKUP_SCRIPT" \
  -v migrate="$MIGRATE_LEGACY" '
  function has_backup_script() {
    for (field = 1; field <= NF; field += 1) {
      if ($field == current || $field == shared || $field == legacy_current || $field == runtime) {
        return 1
      }
    }
    return 0
  }
  index($0, marker) > 0 { next }
  migrate == "1" && has_backup_script() { next }
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

printf '%s\n' "$CRON_LINE" >>"$UPDATED"

"$CRONTAB_BIN" "$UPDATED"

verify_runtime
printf 'Installed root cron entry:\n%s\n' "$CRON_LINE"
