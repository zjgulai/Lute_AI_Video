#!/usr/bin/env bash
set -euo pipefail

# Exact systems.html sidecar transaction. This wrapper defaults to a read-only
# dry run and delegates remote validation/atomic activation to the audited
# Python state machine sent over SSH stdin.

SERVER_IP="${SERVER_IP:-101.34.52.232}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-video}"
ACTION="${ACTION:-sync}"
SYNC_SCOPE="${SYNC_SCOPE:-systems-only}"
DRY_RUN="${DRY_RUN:-1}"
CONFIRM_SYSTEMS_LIVE="${CONFIRM_SYSTEMS_LIVE:-0}"
BASELINE_SYSTEMS_SHA256="${BASELINE_SYSTEMS_SHA256:-}"
CANDIDATE_SYSTEMS_SHA256="${CANDIDATE_SYSTEMS_SHA256:-}"
SSH_KNOWN_HOSTS_FILE="${SSH_KNOWN_HOSTS_FILE:-}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-10}"
SSH_SERVER_ALIVE_INTERVAL="${SSH_SERVER_ALIVE_INTERVAL:-15}"
SSH_SERVER_ALIVE_COUNT_MAX="${SSH_SERVER_ALIVE_COUNT_MAX:-2}"
SSH_BIN="${SSH_BIN:-ssh}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMS_FILE="$SCRIPT_DIR/landing/systems.html"
REMOTE_HELPER="$SCRIPT_DIR/systems-sidecar-remote.py"
REMOTE_INSPECTOR="$SCRIPT_DIR/systems-sidecar-inspect.py"
REMOTE_LANDING_DIR="$REMOTE_DIR/deploy/lighthouse/landing"
REMOTE_TRANSACTION_DIR="$REMOTE_DIR/deploy/lighthouse/.landing-sidecar-sync/systems.html/${BASELINE_SYSTEMS_SHA256}--${CANDIDATE_SYSTEMS_SHA256}"
REMOTE_STAGE_PATH="$REMOTE_TRANSACTION_DIR/candidate.partial"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

require_lowercase_sha256() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[0-9a-f]{64}$ ]]; then
    fail "$name must be 64 lowercase hex"
  fi
}

require_positive_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "$value" =~ ^[1-9][0-9]*$ ]]; then
    fail "$name must be a positive integer"
  fi
}

if [ "$SYNC_SCOPE" != "systems-only" ]; then
  fail "SYNC_SCOPE must be systems-only"
fi
if [ "$ACTION" != "sync" ] && [ "$ACTION" != "rollback" ] && [ "$ACTION" != "inspect" ]; then
  fail "ACTION must be sync, rollback, or inspect"
fi
if [ "$DRY_RUN" != "1" ] && [ "$DRY_RUN" != "0" ]; then
  fail "DRY_RUN must be 1 or 0"
fi
if [ "$CONFIRM_SYSTEMS_LIVE" != "0" ] && [ "$CONFIRM_SYSTEMS_LIVE" != "1" ]; then
  fail "CONFIRM_SYSTEMS_LIVE must be 0 or 1"
fi
require_lowercase_sha256 "BASELINE_SYSTEMS_SHA256" "$BASELINE_SYSTEMS_SHA256"
require_lowercase_sha256 "CANDIDATE_SYSTEMS_SHA256" "$CANDIDATE_SYSTEMS_SHA256"
if [ "$BASELINE_SYSTEMS_SHA256" = "$CANDIDATE_SYSTEMS_SHA256" ]; then
  fail "baseline and candidate SHA must differ"
fi
if [ "$ACTION" = "inspect" ] && [ "$DRY_RUN" != "1" ]; then
  fail "ACTION=inspect is read-only and requires DRY_RUN=1"
fi
if [ "$DRY_RUN" = "0" ] && [ "$CONFIRM_SYSTEMS_LIVE" != "1" ]; then
  fail "live action requires CONFIRM_SYSTEMS_LIVE must be 1"
fi

if [[ ! "$REMOTE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] \
  || [[ "$REMOTE_DIR" = *"//"* ]] \
  || [[ "$REMOTE_DIR" = *"/../"* ]] \
  || [[ "$REMOTE_DIR" = *"/./"* ]] \
  || [[ "$REMOTE_DIR" = */.. ]] \
  || [[ "$REMOTE_DIR" = */. ]]; then
  fail "REMOTE_DIR must be a normalized absolute path without shell metacharacters"
fi
if [[ ! "$SERVER_IP" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  fail "SERVER_IP contains unsupported characters"
fi
if [[ ! "$SSH_USER" =~ ^[A-Za-z_][A-Za-z0-9_-]*$ ]]; then
  fail "SSH_USER contains unsupported characters"
fi
require_positive_integer "SSH_CONNECT_TIMEOUT" "$SSH_CONNECT_TIMEOUT"
require_positive_integer "SSH_SERVER_ALIVE_INTERVAL" "$SSH_SERVER_ALIVE_INTERVAL"
require_positive_integer "SSH_SERVER_ALIVE_COUNT_MAX" "$SSH_SERVER_ALIVE_COUNT_MAX"

if [ -z "${SSH_KEY:-}" ] || [ ! -f "$SSH_KEY" ] || [ -L "$SSH_KEY" ]; then
  fail "SSH_KEY must name a real regular private-key file"
fi
if [ -z "$SSH_KNOWN_HOSTS_FILE" ] \
  || [ ! -f "$SSH_KNOWN_HOSTS_FILE" ] \
  || [ -L "$SSH_KNOWN_HOSTS_FILE" ]; then
  fail "SSH_KNOWN_HOSTS_FILE must name a pinned regular known_hosts file"
fi
if ! command -v ssh-keygen >/dev/null 2>&1; then
  fail "ssh-keygen is required to validate the pinned host entry"
fi
if ! ssh-keygen -F "$SERVER_IP" -f "$SSH_KNOWN_HOSTS_FILE" >/dev/null 2>&1; then
  fail "SSH_KNOWN_HOSTS_FILE does not contain a pinned entry for SERVER_IP"
fi
if ! command -v "$SSH_BIN" >/dev/null 2>&1; then
  fail "SSH_BIN is not executable"
fi
if [ ! -f "$REMOTE_HELPER" ] || [ -L "$REMOTE_HELPER" ] \
  || [ ! -f "$REMOTE_INSPECTOR" ] || [ -L "$REMOTE_INSPECTOR" ]; then
  fail "remote systems helper or inspector is missing or unsafe"
fi

if [ "$ACTION" = "sync" ]; then
  if [ ! -f "$SYSTEMS_FILE" ] || [ -L "$SYSTEMS_FILE" ]; then
    fail "local systems.html candidate is missing or unsafe"
  fi
  local_candidate_sha256="$(python3 -I -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' "$SYSTEMS_FILE")"
  if [ "$local_candidate_sha256" != "$CANDIDATE_SYSTEMS_SHA256" ]; then
    fail "local systems.html SHA does not match CANDIDATE_SYSTEMS_SHA256"
  fi
fi

SSH_OPTS=(
  -i "$SSH_KEY"
  -o StrictHostKeyChecking=yes
  -o "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o "ConnectTimeout=$SSH_CONNECT_TIMEOUT"
  -o "ServerAliveInterval=$SSH_SERVER_ALIVE_INTERVAL"
  -o "ServerAliveCountMax=$SSH_SERVER_ALIVE_COUNT_MAX"
)

run_remote() {
  local mode="$1"
  "$SSH_BIN" "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" \
    python3 -I - \
    --mode "$mode" \
    --remote-dir "$REMOTE_DIR" \
    --baseline-sha256 "$BASELINE_SYSTEMS_SHA256" \
    --candidate-sha256 "$CANDIDATE_SYSTEMS_SHA256" \
    < "$REMOTE_HELPER"
}

run_inspect() {
  "$SSH_BIN" "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" \
    python3 -I - \
    --remote-dir "$REMOTE_DIR" \
    --baseline-sha256 "$BASELINE_SYSTEMS_SHA256" \
    --candidate-sha256 "$CANDIDATE_SYSTEMS_SHA256" \
    < "$REMOTE_INSPECTOR"
}

printf '%s\n' \
  "========================================" \
  "  Lighthouse systems.html Sidecar Gate" \
  "========================================" \
  "server:         $SSH_USER@$SERVER_IP" \
  "remote target:  $REMOTE_LANDING_DIR/systems.html" \
  "action:         $ACTION" \
  "scope:          $SYNC_SCOPE" \
  "baseline SHA:   $BASELINE_SYSTEMS_SHA256" \
  "candidate SHA:  $CANDIDATE_SYSTEMS_SHA256" \
  "dry run:        $DRY_RUN" \
  "delete remote:  no" \
  ""

if [ "$ACTION" = "inspect" ]; then
  run_inspect
  printf '\nInspection complete; no remote files were changed.\n'
  exit 0
elif [ "$ACTION" = "rollback" ]; then
  run_remote rollback-check
  if [ "$DRY_RUN" = "1" ]; then
    printf '\nRollback dry run complete; no remote files were changed.\n'
    exit 0
  fi
  run_remote rollback
  run_remote rollback-readback
  printf '\nSidecar rollback complete: systems.html restored to %s\n' "$BASELINE_SYSTEMS_SHA256"
  exit 0
fi

if [ -z "${RSYNC_BIN:-}" ]; then
  for candidate in /opt/homebrew/bin/rsync /usr/local/bin/rsync "$(command -v rsync 2>/dev/null || true)"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
      version_line="$("$candidate" --version 2>/dev/null | sed -n '1p' || true)"
      if printf '%s\n' "$version_line" | grep -Eq '^rsync[[:space:]]+version[[:space:]]+3'; then
        RSYNC_BIN="$candidate"
        break
      fi
    fi
  done
fi
RSYNC_VERSION_LINE=""
if [ -n "${RSYNC_BIN:-}" ] && [ -x "$RSYNC_BIN" ]; then
  RSYNC_VERSION_LINE="$("$RSYNC_BIN" --version 2>/dev/null | sed -n '1p' || true)"
fi
if [ -z "${RSYNC_BIN:-}" ] \
  || [ ! -x "$RSYNC_BIN" ] \
  || ! printf '%s\n' "$RSYNC_VERSION_LINE" | grep -Eq '^rsync[[:space:]]+version[[:space:]]+3'; then
  fail "GNU rsync 3.x is required for the systems.html transaction"
fi

RSYNC_SSH_COMMAND=""
printf -v RSYNC_SSH_COMMAND '%q ' "$SSH_BIN" "${SSH_OPTS[@]}"
RSYNC_SSH_COMMAND="${RSYNC_SSH_COMMAND% }"
RSYNC_ARGS=(
  -az
  --checksum
  --chmod=F644
  --protect-args
  --itemize-changes
  --no-owner
  --no-group
  --timeout=30
  -e "$RSYNC_SSH_COMMAND"
)

run_remote check
if [ "$DRY_RUN" = "1" ]; then
  "$RSYNC_BIN" "${RSYNC_ARGS[@]}" --dry-run \
    "$SYSTEMS_FILE" \
    "$SSH_USER@$SERVER_IP:$REMOTE_LANDING_DIR/systems.html"
  printf '\nDry run complete; no remote files were changed.\n'
  exit 0
fi

run_remote prepare
"$RSYNC_BIN" "${RSYNC_ARGS[@]}" \
  "$SYSTEMS_FILE" \
  "$SSH_USER@$SERVER_IP:$REMOTE_STAGE_PATH"
run_remote activate
run_remote readback

printf '\nSidecar sync complete: systems.html activated at https://lute-tlz-dddd.top/systems.html\n'
