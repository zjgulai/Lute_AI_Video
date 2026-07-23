#!/usr/bin/env bash
set -euo pipefail

# AI Video — safe Lighthouse sync + deploy wrapper.
# Run from the local repository root. The remote host builds reviewed,
# SHA-tagged images and switches containers via deploy/lighthouse/deploy.sh.

SERVER_IP="${SERVER_IP:-101.34.52.232}"
SSH_USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-/opt/ai-video}"
DRY_RUN="${DRY_RUN:-1}"
RELEASE_SOURCE_SHA="${RELEASE_SOURCE_SHA:-}"
SSH_CONNECT_TIMEOUT="${SSH_CONNECT_TIMEOUT:-15}"
SSH_SERVER_ALIVE_INTERVAL="${SSH_SERVER_ALIVE_INTERVAL:-30}"
SSH_SERVER_ALIVE_COUNT_MAX="${SSH_SERVER_ALIVE_COUNT_MAX:-4}"
CLEANUP_AFTER_DEPLOY="${CLEANUP_AFTER_DEPLOY:-0}"
CLEANUP_TIMEOUT_SECONDS="${CLEANUP_TIMEOUT_SECONDS:-180}"
RUN_DEPLOY_SMOKE="${RUN_DEPLOY_SMOKE:-0}"
RUN_TOKEN_SMOKE="${RUN_TOKEN_SMOKE:-0}"
ALLOW_MAINTENANCE_WINDOW="${ALLOW_MAINTENANCE_WINDOW:-0}"
SSH_KNOWN_HOSTS_FILE="${SSH_KNOWN_HOSTS_FILE:-}"
RELEASE_IMAGE_ARCHIVE="${RELEASE_IMAGE_ARCHIVE:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
EXCLUDE_FILE="${EXCLUDE_FILE:-$SCRIPT_DIR/rsync-excludes.txt}"

if [ "$DRY_RUN" != "0" ] && [ "$DRY_RUN" != "1" ]; then
  echo "ERROR: DRY_RUN must be 0 or 1." >&2
  exit 1
fi
if [ "$RUN_TOKEN_SMOKE" != "0" ]; then
  echo "ERROR: canonical deployment is provider-off; RUN_TOKEN_SMOKE must be 0." >&2
  exit 1
fi
if [ "$RUN_DEPLOY_SMOKE" != "0" ]; then
  echo "ERROR: canonical deployment does not invoke authenticated smoke.sh." >&2
  exit 1
fi
if [ "$CLEANUP_AFTER_DEPLOY" != "0" ]; then
  echo "ERROR: canonical deployment preserves rollback images; CLEANUP_AFTER_DEPLOY must be 0." >&2
  exit 1
fi
if [ "$ALLOW_MAINTENANCE_WINDOW" != "0" ] && [ "$ALLOW_MAINTENANCE_WINDOW" != "1" ]; then
  echo "ERROR: ALLOW_MAINTENANCE_WINDOW must be 0 or 1." >&2
  exit 1
fi
if [ "$DRY_RUN" = "0" ] && [ "$ALLOW_MAINTENANCE_WINDOW" != "1" ]; then
  echo "ERROR: live rollout requires explicit ALLOW_MAINTENANCE_WINDOW=1." >&2
  exit 1
fi
if ! [[ "$REMOTE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "ERROR: REMOTE_DIR must be a safe absolute path." >&2
  exit 1
fi

if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: release source must be a Git worktree." >&2
  exit 1
fi

SOURCE_BRANCH="$(git -C "$REPO_ROOT" symbolic-ref --quiet --short HEAD || true)"
if [ "$SOURCE_BRANCH" != "main" ]; then
  echo "ERROR: release source branch must be main." >&2
  exit 1
fi

if [ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]; then
  echo "ERROR: release source worktree must be clean." >&2
  exit 1
fi

SOURCE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if ! [[ "$SOURCE_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: release source SHA is invalid." >&2
  exit 1
fi
if ! REMOTE_MAIN_OUTPUT="$(git -C "$REPO_ROOT" ls-remote --exit-code origin refs/heads/main 2>/dev/null)"; then
  echo "ERROR: unable to verify the live origin/main SHA." >&2
  exit 1
fi
REMOTE_MAIN_SHA="$(printf '%s\n' "$REMOTE_MAIN_OUTPUT" | awk '$2 == "refs/heads/main" {print $1}')"
if ! [[ "$REMOTE_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]] \
  || [ "$(printf '%s\n' "$REMOTE_MAIN_OUTPUT" | awk '$2 == "refs/heads/main" {count += 1} END {print count + 0}')" != "1" ]; then
  echo "ERROR: origin/main did not resolve to exactly one Git SHA." >&2
  exit 1
fi
if [ "$REMOTE_MAIN_SHA" != "$SOURCE_SHA" ]; then
  echo "ERROR: release source must match origin/main." >&2
  exit 1
fi

if [ "$DRY_RUN" = "0" ]; then
  if [ -z "$RELEASE_SOURCE_SHA" ] || [ "$RELEASE_SOURCE_SHA" != "$SOURCE_SHA" ]; then
    echo "ERROR: live deploy requires RELEASE_SOURCE_SHA to match the reviewed source." >&2
    exit 1
  fi
  if [ -z "$RELEASE_IMAGE_ARCHIVE" ] || [ ! -f "$RELEASE_IMAGE_ARCHIVE" ] \
    || [ ! -f "${RELEASE_IMAGE_ARCHIVE}.sha256" ]; then
    echo "ERROR: live deploy requires the CI-reviewed image archive and checksum." >&2
    exit 1
  fi
  if ! [[ "$(basename "$RELEASE_IMAGE_ARCHIVE")" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "ERROR: release image archive basename is unsafe." >&2
    exit 1
  fi
  if command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "$RELEASE_IMAGE_ARCHIVE")" && sha256sum -c "$(basename "$RELEASE_IMAGE_ARCHIVE").sha256")
  else
    (cd "$(dirname "$RELEASE_IMAGE_ARCHIVE")" && shasum -a 256 -c "$(basename "$RELEASE_IMAGE_ARCHIVE").sha256")
  fi
fi

REMOTE_RELEASE_DIR="$REMOTE_DIR/releases-$SOURCE_SHA"

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

if [ -z "$SSH_KNOWN_HOSTS_FILE" ] || [ ! -f "$SSH_KNOWN_HOSTS_FILE" ]; then
  echo "ERROR: SSH_KNOWN_HOSTS_FILE must reference the pinned production host identity." >&2
  exit 1
fi
if ! ssh-keygen -F "$SERVER_IP" -f "$SSH_KNOWN_HOSTS_FILE" >/dev/null 2>&1; then
  echo "ERROR: pinned known_hosts file has no entry for the production host." >&2
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

for setting in CLEANUP_AFTER_DEPLOY; do
  value="${!setting}"
  if [ "$value" != "0" ] && [ "$value" != "1" ]; then
    echo "ERROR: $setting must be 0 or 1." >&2
    exit 1
  fi
done

SSH_OPTIONS=(
  -i "$SSH_KEY"
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$SSH_KNOWN_HOSTS_FILE"
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
echo "shared root: $REMOTE_DIR"
echo "release dir: $REMOTE_RELEASE_DIR"
echo "ssh key:    $SSH_KEY"
echo "excludes:   $EXCLUDE_FILE"
echo "rsync:      $RSYNC_BIN"
echo "dry run:    $DRY_RUN"
echo "source branch: $SOURCE_BRANCH"
echo "source SHA:    $SOURCE_SHA"
echo "token smoke:0 (provider-off invariant)"
echo "cleanup after deploy: $CLEANUP_AFTER_DEPLOY"
echo "maintenance window authorized: $ALLOW_MAINTENANCE_WINDOW"
echo ""

cd "$REPO_ROOT"

SOURCE_MANIFEST_PATH="$REPO_ROOT/source-manifest.v1.json"
if [ -e "$SOURCE_MANIFEST_PATH" ]; then
  echo "ERROR: source manifest output path already exists." >&2
  exit 1
fi
cleanup_source_manifest() {
  rm -f -- "$SOURCE_MANIFEST_PATH"
}
trap cleanup_source_manifest EXIT
python3 scripts/backup_manifest.py source-create \
  --root . \
  --git-sha "$SOURCE_SHA" \
  --output "$SOURCE_MANIFEST_PATH" >/dev/null

echo "[1/2] Syncing repository to Lighthouse..."
if ! ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$SERVER_IP" "test ! -e '$REMOTE_RELEASE_DIR'"; then
  echo "ERROR: immutable release directory already exists: $REMOTE_RELEASE_DIR" >&2
  exit 1
fi
if [ "$DRY_RUN" = "0" ]; then
  ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$SERVER_IP" "mkdir '$REMOTE_RELEASE_DIR'"
fi
"$RSYNC_BIN" "${RSYNC_ARGS[@]}" ./ "$SSH_USER@$SERVER_IP:$REMOTE_RELEASE_DIR/"

if [ "$DRY_RUN" = "0" ]; then
  "$RSYNC_BIN" -avz -e "$RSYNC_SSH_COMMAND" \
    "$RELEASE_IMAGE_ARCHIVE" "${RELEASE_IMAGE_ARCHIVE}.sha256" \
    "$SSH_USER@$SERVER_IP:$REMOTE_RELEASE_DIR/"
fi

if [ "$DRY_RUN" = "1" ]; then
  echo ""
  echo "Dry run complete; remote deploy skipped."
  exit 0
fi

echo ""
echo "[2/2] Running remote deploy.sh..."
ssh "${SSH_OPTIONS[@]}" "$SSH_USER@$SERVER_IP" \
  "cd '$REMOTE_RELEASE_DIR/deploy/lighthouse' && AI_VIDEO_SHARED_ROOT='$REMOTE_DIR' RELEASE_SOURCE_SHA='$SOURCE_SHA' RELEASE_IMAGE_ARCHIVE='$REMOTE_RELEASE_DIR/$(basename "$RELEASE_IMAGE_ARCHIVE")' RUN_TOKEN_SMOKE=0 RUN_DEPLOY_SMOKE=0 ALLOW_MAINTENANCE_WINDOW=1 CLEANUP_AFTER_DEPLOY=0 bash deploy.sh"

echo ""
echo "Deploy complete: https://video.lute-tlz-dddd.top"
