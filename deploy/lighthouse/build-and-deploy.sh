#!/usr/bin/env bash
set -euo pipefail

# AI Video — safe Lighthouse sync + deploy wrapper.
# Run from the local repository root. The remote host performs the frontend
# build and container restart via deploy/lighthouse/deploy.sh.

SERVER_IP="${SERVER_IP:-101.34.52.232}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-video}"
DRY_RUN="${DRY_RUN:-0}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-15}"
SSH_SERVER_ALIVE_INTERVAL="${SSH_SERVER_ALIVE_INTERVAL:-30}"
SSH_SERVER_ALIVE_COUNT_MAX="${SSH_SERVER_ALIVE_COUNT_MAX:-4}"
CLEANUP_AFTER_DEPLOY="${CLEANUP_AFTER_DEPLOY:-0}"
CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-180}"
RUN_DEPLOY_SMOKE="${RUN_DEPLOY_SMOKE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXCLUDE_FILE="${EXCLUDE_FILE:-$SCRIPT_DIR/rsync-excludes.txt}"

if [ -z "${SSH_KEY:-}" ]; then
  for candidate in \
    "$REPO_ROOT/ai_video.pem" \
    "$HOME/Downloads/ai_video.pem" \
    "$HOME/ai_video.pem"
  do
    if [ -f "$candidate" ]; then
      SSH_KEY="$candidate"
      break
    fi
  done
fi

if [ -z "${SSH_KEY:-}" ] || [ ! -f "$SSH_KEY" ]; then
  echo "ERROR: SSH_KEY not set and ai_video.pem not found in repo root, ~/Downloads, or ~/" >&2
  echo "Usage: SSH_KEY=/path/to/ai_video.pem $0" >&2
  exit 1
fi

if [ ! -f "$EXCLUDE_FILE" ]; then
  echo "ERROR: rsync exclude file not found: $EXCLUDE_FILE" >&2
  exit 1
fi

for setting in SSH_CONNECT_TIMEOUT SSH_SERVER_ALIVE_INTERVAL SSH_SERVER_ALIVE_COUNT_MAX CLEANUP_TIMEOUT_SECONDS; do
  value="${!setting}"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: $setting must be a positive integer." >&2
    exit 1
  fi
done

for setting in CLEANUP_AFTER_DEPLOY RUN_DEPLOY_SMOKE; do
  value="${!setting}"
  if [ "$value" != "0" ] && [ "$value" != "1" ]; then
    echo "ERROR: $setting must be 0 or 1." >&2
    exit 1
  fi
done

SSH_OPTIONS=(
  -i "$SSH_KEY"
  -o StrictHostKeyChecking=accept-new
  -o BatchMode=yes
  -o ConnectTimeout="$SSH_CONNECT_TIMEOUT"
  -o ServerAliveInterval="$SSH_SERVER_ALIVE_INTERVAL"
  -o ServerAliveCountMax="$SSH_SERVER_ALIVE_COUNT_MAX"
)
printf -v RSYNC_SSH_COMMAND '%q ' ssh "${SSH_OPTIONS[@]}"
RSYNC_SSH_COMMAND="${RSYNC_SSH_COMMAND% }"

if [ -z "${RSYNC_BIN:-}" ]; then
  for candidate in \
    "/opt/homebrew/bin/rsync" \
    "/usr/local/bin/rsync" \
    "$(command -v rsync 2>/dev/null || true)"
  do
    if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
      continue
    fi
    version_line="$("$candidate" --version 2>/dev/null | sed -n '1p' || true)"
    if printf '%s\n' "$version_line" | grep -Eq '^rsync[[:space:]]+version[[:space:]]+3'; then
      RSYNC_BIN="$candidate"
      break
    fi
  done
fi

RSYNC_VERSION_LINE=""
if [ -n "${RSYNC_BIN:-}" ] && [ -x "$RSYNC_BIN" ]; then
  RSYNC_VERSION_LINE="$("$RSYNC_BIN" --version 2>/dev/null | sed -n '1p' || true)"
fi
if [ -z "${RSYNC_BIN:-}" ] || [ ! -x "$RSYNC_BIN" ] \
  || ! printf '%s\n' "$RSYNC_VERSION_LINE" | grep -Eq '^rsync[[:space:]]+version[[:space:]]+3'; then
  echo "ERROR: GNU rsync 3.x is required for --chmod=F644,D755." >&2
  echo "Install with 'brew install rsync' on macOS, or set RSYNC_BIN=/path/to/rsync." >&2
  exit 1
fi

RSYNC_ARGS=(
  -avz
  --delete
  --chmod=F644,D755
  -e "$RSYNC_SSH_COMMAND"
  --exclude-from="$EXCLUDE_FILE"
)

if [ "$DRY_RUN" = "1" ]; then
  RSYNC_ARGS+=(--dry-run)
fi

echo "========================================"
echo "  AI Video Lighthouse Sync + Deploy"
echo "========================================"
echo "server:     $SSH_USER@$SERVER_IP"
echo "remote dir: $REMOTE_DIR"
echo "ssh key:    $SSH_KEY"
echo "excludes:   $EXCLUDE_FILE"
echo "rsync:      $RSYNC_BIN"
echo "dry run:    $DRY_RUN"
echo "rebuild backend:   ${REBUILD_BACKEND:-0}"
echo "rebuild rendering: ${REBUILD_RENDERING:-0}"
echo "token smoke:${RUN_TOKEN_SMOKE:-0}"
echo "cleanup after deploy: $CLEANUP_AFTER_DEPLOY"
echo "authenticated deploy smoke: $RUN_DEPLOY_SMOKE"
echo ""

cd "$REPO_ROOT"

echo "[1/2] Syncing repository to Lighthouse..."
"$RSYNC_BIN" "${RSYNC_ARGS[@]}" ./ "$SSH_USER@$SERVER_IP:$REMOTE_DIR/"

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "Dry run complete; remote deploy skipped."
  exit 0
fi

echo ""
echo "[2/2] Running remote deploy.sh..."
ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$SERVER_IP" \
  "cd '$REMOTE_DIR/deploy/lighthouse' && REBUILD_BACKEND=${REBUILD_BACKEND:-0} REBUILD_RENDERING=${REBUILD_RENDERING:-0} RUN_TOKEN_SMOKE=${RUN_TOKEN_SMOKE:-0} CLEANUP_AFTER_DEPLOY=$CLEANUP_AFTER_DEPLOY CLEANUP_TIMEOUT_SECONDS=$CLEANUP_TIMEOUT_SECONDS RUN_DEPLOY_SMOKE=$RUN_DEPLOY_SMOKE bash deploy.sh"

echo ""
echo "Deploy complete: https://video.lute-tlz-dddd.top"
