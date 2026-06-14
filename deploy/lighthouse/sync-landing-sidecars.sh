#!/usr/bin/env bash
set -euo pipefail

# Sync only the apex landing static files that are intentionally excluded from
# the normal AI Video repository deploy. Default is dry-run to avoid accidental
# production mutation.

SERVER_IP="${SERVER_IP:-101.34.52.232}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-video}"
DRY_RUN="${DRY_RUN:-1}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LANDING_DIR="$SCRIPT_DIR/landing"
REMOTE_LANDING_DIR="$REMOTE_DIR/deploy/lighthouse/landing"

LANDING_FILES=(
  index.html
  login.html
  register.html
  systems.html
  lute-auth.css
  lute-auth.js
)

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
  echo "Usage: SSH_KEY=/path/to/ai_video.pem DRY_RUN=1 $0" >&2
  exit 1
fi

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

for file in "${LANDING_FILES[@]}"; do
  if [ ! -f "$LANDING_DIR/$file" ]; then
    echo "ERROR: landing file missing: $LANDING_DIR/$file" >&2
    exit 1
  fi
done

SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new)
RSYNC_ARGS=(
  -avz
  --chmod=F644,D755
  -e "ssh ${SSH_OPTS[*]}"
)

if [ "$DRY_RUN" = "1" ]; then
  RSYNC_ARGS+=(--dry-run)
elif [ "$DRY_RUN" != "0" ]; then
  echo "ERROR: DRY_RUN must be 1 or 0" >&2
  exit 1
fi

echo "========================================"
echo "  Lighthouse Apex Landing Sidecar Sync"
echo "========================================"
echo "server:        $SSH_USER@$SERVER_IP"
echo "remote dir:    $REMOTE_LANDING_DIR"
echo "ssh key:       $SSH_KEY"
echo "rsync:         $RSYNC_BIN"
echo "dry run:       $DRY_RUN"
echo "delete remote: no"
echo ""

echo "[1/3] Remote boundary check..."
ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" \
  "test -d '$REMOTE_LANDING_DIR' && docker exec ai_video_nginx nginx -t >/dev/null"
echo "  remote landing dir exists and nginx config is valid"
echo ""

echo "[2/3] Syncing landing files..."
(
  cd "$LANDING_DIR"
  "$RSYNC_BIN" "${RSYNC_ARGS[@]}" "${LANDING_FILES[@]}" \
    "$SSH_USER@$SERVER_IP:$REMOTE_LANDING_DIR/"
)

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "Dry run complete; no remote files were changed."
  exit 0
fi

echo ""
echo "[3/3] Verifying remote files..."
remote_verify_cmd="set -e"
for file in "${LANDING_FILES[@]}"; do
  remote_verify_cmd="$remote_verify_cmd; test -f '$REMOTE_LANDING_DIR/$file'"
done
remote_verify_cmd="$remote_verify_cmd; docker exec ai_video_nginx nginx -t >/dev/null"

ssh "${SSH_OPTS[@]}" "$SSH_USER@$SERVER_IP" "$remote_verify_cmd"
echo "  remote landing files exist and nginx config is valid"
echo ""
echo "Sidecar sync complete: https://lute-tlz-dddd.top"
