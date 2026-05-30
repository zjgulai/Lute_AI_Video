#!/usr/bin/env bash
set -euo pipefail

# AI Video — safe Lighthouse sync + deploy wrapper.
# Run from the local repository root. The remote host performs the frontend
# build and container restart via deploy/lighthouse/deploy.sh.

SERVER_IP="${SERVER_IP:-101.34.52.232}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-video}"
DRY_RUN="${DRY_RUN:-0}"

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

RSYNC_ARGS=(
  -avz
  --delete
  --chmod=F644,D755
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=accept-new"
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
echo "dry run:    $DRY_RUN"
echo ""

cd "$REPO_ROOT"

echo "[1/2] Syncing repository to Lighthouse..."
rsync "${RSYNC_ARGS[@]}" ./ "$SSH_USER@$SERVER_IP:$REMOTE_DIR/"

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "Dry run complete; remote deploy skipped."
  exit 0
fi

echo ""
echo "[2/2] Running remote deploy.sh..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new "$SSH_USER@$SERVER_IP" \
  "cd '$REMOTE_DIR/deploy/lighthouse' && bash deploy.sh"

echo ""
echo "Deploy complete: https://video.lute-tlz-dddd.top"
