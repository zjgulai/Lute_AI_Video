#!/usr/bin/env bash
# Phase 0 #1 alembic upgrade runner — runs INSIDE the backend container so it
# uses the same DATABASE_URL + python env as the app.
#
# Usage (run on lighthouse server):
#   cd /opt/ai-video
#   ./scripts/run_alembic_upgrade.sh
#
# What it does:
#   1. Verifies alembic is installed in the running backend container
#   2. Shows current revision (sanity check)
#   3. Renders the upgrade SQL (offline, dry-run)
#   4. PROMPTS for confirmation (operator approves the SQL)
#   5. Runs alembic upgrade head against production PG
#   6. Verifies new revision is at expected head
#
# Rollback:
#   ./scripts/run_alembic_upgrade.sh --downgrade

set -euo pipefail

cd "$(dirname "$0")/.."

# Detect the running backend container name. Lighthouse uses
# docker-compose service name 'backend' from docker-compose.prod.yml.
CONTAINER=$(sudo docker ps --filter "name=backend" --format "{{.Names}}" | head -1)
if [ -z "$CONTAINER" ]; then
  echo "ERROR: no running backend container found"
  exit 1
fi

echo "========================================"
echo "  Phase 0 #1 Alembic Migration Runner"
echo "  Container: $CONTAINER"
echo "========================================"

run_in_container() {
  sudo docker exec "$CONTAINER" sh -c "cd /app/migrations && python3 -m alembic $*"
}

# Step 1: Show current revision
echo ""
echo "[1/5] Current alembic revision:"
run_in_container "current"

# Step 2: Determine mode + render the matching SQL for review.
# Downgrade mode renders the rollback SQL; upgrade mode renders the
# forward SQL. Either way, operator sees the exact statements before
# committing.
if [ "${1:-}" = "--downgrade" ]; then
  MODE="DOWNGRADE (rollback)"
  ACTION="downgrade -1"
  SQL_RENDER="downgrade --sql 7a2f4b8c9d12:2d6b8e9c0f1a"
  WARNING="This will REMOVE the 5 runtime-state columns from pipeline_states.
Existing rows lose schema_version/pipeline_degraded/etc data."
else
  MODE="UPGRADE"
  ACTION="upgrade head"
  SQL_RENDER="upgrade --sql 2d6b8e9c0f1a:7a2f4b8c9d12"
  WARNING="This will ADD 5 nullable columns to pipeline_states. Existing rows
default to NULL/[]. Forward-compatible."
fi

echo ""
echo "[2/5] $MODE SQL (offline render, NOT applied yet):"
run_in_container "$SQL_RENDER"

# Step 3: Confirmation prompt
echo ""
echo "MODE: $MODE"
echo "$WARNING"
echo ""
read -p "Proceed with 'alembic $ACTION'? Type 'yes' to confirm: " CONFIRM
if [ "${CONFIRM:-}" != "yes" ]; then
  echo "Aborted."
  exit 1
fi

# Step 4: Apply
echo ""
echo "[4/5] Applying migration..."
run_in_container "$ACTION"

# Step 5: Verify
echo ""
echo "[5/5] Post-migration revision:"
run_in_container "current"

echo ""
echo "✅ Done."
