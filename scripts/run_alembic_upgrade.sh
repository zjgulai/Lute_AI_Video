#!/usr/bin/env bash
# Manual Alembic migration runner.  It runs INSIDE the backend container so it
# uses the same DATABASE_URL and Python environment as the application.
#
# Usage (run on the Lighthouse server only after the separately authorized
# backup/migration gate):
#   ./scripts/run_alembic_upgrade.sh
#   ./scripts/run_alembic_upgrade.sh --downgrade

set -euo pipefail

usage() {
  echo "Usage: $0 [--downgrade]" >&2
}

if [ "$#" -gt 1 ]; then
  usage
  exit 2
fi

case "${1:-}" in
  "")
    REQUESTED_MODE="upgrade"
    ;;
  --downgrade)
    REQUESTED_MODE="downgrade"
    ;;
  *)
    usage
    exit 2
    ;;
esac

cd "$(dirname "$0")/.."

# Lighthouse uses a backend container whose name contains "backend".
CONTAINER=$(sudo docker ps --filter "name=backend" --format "{{.Names}}" | head -1)
if [ -z "$CONTAINER" ]; then
  echo "ERROR: no running backend container found" >&2
  exit 1
fi

echo "========================================"
echo "  Alembic Migration Runner"
echo "  Container: $CONTAINER"
echo "========================================"

run_in_container() {
  # Pass Alembic arguments positionally instead of interpolating them into the
  # shell command.  The only shell work is changing to the migration directory.
  sudo docker exec "$CONTAINER" sh -c \
    'cd /app/migrations && exec python3 -m alembic "$@"' alembic "$@"
}

extract_current_revisions() {
  awk '
    /^[[:space:]]*$/ { next }
    /^[[:space:]]*(INFO|DEBUG|WARN|WARNING|ERROR)[[:space:]]/ { next }
    $1 ~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$/ && (NF == 1 || $0 ~ /\(head\)/) {
      print $1
    }
  '
}

extract_head_revisions() {
  awk '
    $1 ~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$/ && $0 ~ /\(head\)/ {
      print $1
    }
  '
}

count_revisions() {
  awk 'NF { count += 1 } END { print count + 0 }'
}

# Discover state from the migration graph at runtime.  No historical revision
# is embedded in this executor.
CURRENT_OUTPUT=$(run_in_container current)
CURRENT_REVISIONS=$(printf '%s\n' "$CURRENT_OUTPUT" | extract_current_revisions)
CURRENT_COUNT=$(printf '%s\n' "$CURRENT_REVISIONS" | count_revisions)
if [ "$CURRENT_COUNT" -gt 1 ]; then
  echo "ERROR: database reports multiple current Alembic revisions" >&2
  printf '%s\n' "$CURRENT_OUTPUT" >&2
  exit 1
fi
if [ "$CURRENT_COUNT" -eq 0 ]; then
  CURRENT_REVISION="base"
else
  CURRENT_REVISION=$(printf '%s\n' "$CURRENT_REVISIONS" | head -1)
fi

HEAD_OUTPUT=$(run_in_container heads)
HEAD_REVISIONS=$(printf '%s\n' "$HEAD_OUTPUT" | extract_head_revisions)
HEAD_COUNT=$(printf '%s\n' "$HEAD_REVISIONS" | count_revisions)
if [ "$HEAD_COUNT" -ne 1 ]; then
  echo "ERROR: expected exactly one Alembic head, found $HEAD_COUNT" >&2
  printf '%s\n' "$HEAD_OUTPUT" >&2
  exit 1
fi
HEAD_REVISION=$(printf '%s\n' "$HEAD_REVISIONS" | head -1)

echo ""
echo "[1/5] Discovered migration state:"
printf '%s\n' "$CURRENT_OUTPUT"
printf '%s\n' "$HEAD_OUTPUT"
echo "Current revision: $CURRENT_REVISION"
echo "Target head: $HEAD_REVISION"

if [ "$REQUESTED_MODE" = "upgrade" ] && [ "$CURRENT_REVISION" = "$HEAD_REVISION" ]; then
  echo ""
  echo "Already at Alembic head; no migration was applied."
  exit 0
fi

if [ "$REQUESTED_MODE" = "downgrade" ] && [ "$CURRENT_REVISION" = "base" ]; then
  echo "ERROR: cannot downgrade -1 from Alembic base" >&2
  exit 1
fi

if [ "$REQUESTED_MODE" = "downgrade" ]; then
  MODE="DOWNGRADE (one revision)"
  ACTION="downgrade -1"
  echo ""
  echo "[2/5] $MODE SQL (offline render, NOT applied yet):"
  run_in_container downgrade --sql "${CURRENT_REVISION}:-1"
  WARNING="SUBMISSION LEDGER DATA RISK:
If the rendered -1 step is the submission-ledger revision, it drops
idempotency_records and can permanently delete original-job mappings. This is
not an application rollback.
Proceed only after reviewing the rendered SQL, taking a verified backup, and
obtaining the explicit data-retention approval required for table removal."
else
  MODE="UPGRADE"
  ACTION="upgrade head"
  echo ""
  echo "[2/5] $MODE SQL (offline render, NOT applied yet):"
  if [ "$CURRENT_REVISION" = "base" ]; then
    run_in_container upgrade --sql head
  else
    run_in_container upgrade --sql "${CURRENT_REVISION}:head"
  fi
  WARNING="This applies every pending migration from $CURRENT_REVISION to the
single discovered head $HEAD_REVISION. Review the rendered SQL and verified
backup evidence before continuing."
fi

echo ""
echo "MODE: $MODE"
echo "$WARNING"
echo ""
read -r -p "Proceed with 'alembic $ACTION'? Type 'yes' to confirm: " CONFIRM
if [ "${CONFIRM:-}" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

echo ""
echo "[4/5] Applying migration..."
if [ "$REQUESTED_MODE" = "downgrade" ]; then
  run_in_container downgrade -1
else
  run_in_container upgrade head
fi

POST_OUTPUT=$(run_in_container current)
POST_REVISIONS=$(printf '%s\n' "$POST_OUTPUT" | extract_current_revisions)
POST_COUNT=$(printf '%s\n' "$POST_REVISIONS" | count_revisions)
if [ "$POST_COUNT" -gt 1 ]; then
  echo "ERROR: post-migration database reports multiple current revisions" >&2
  printf '%s\n' "$POST_OUTPUT" >&2
  exit 1
fi
if [ "$POST_COUNT" -eq 0 ]; then
  POST_REVISION="base"
else
  POST_REVISION=$(printf '%s\n' "$POST_REVISIONS" | head -1)
fi

echo ""
echo "[5/5] Post-migration state:"
printf '%s\n' "$POST_OUTPUT"
echo "Post-migration revision: $POST_REVISION"

if [ "$REQUESTED_MODE" = "upgrade" ] && [ "$POST_REVISION" != "$HEAD_REVISION" ]; then
  echo "ERROR: upgrade verification failed; current revision is not head" >&2
  exit 1
fi
if [ "$REQUESTED_MODE" = "downgrade" ] && [ "$POST_REVISION" = "$CURRENT_REVISION" ]; then
  echo "ERROR: downgrade verification failed; revision did not change" >&2
  exit 1
fi

echo ""
echo "Done."
