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

# Step 2: Render upgrade SQL for review
echo ""
echo "[2/5] Upgrade SQL (offline render, NOT applied yet):"
run_in_container "upgrade --sql 2d6b8e9c0f1a:7a2f4b8c9d12"

# Step 3: Confirmation prompt
echo ""
if [ "${1:-}" = "--downgrade" ]; then
  echo "MODE: DOWNGRADE (rollback)"
  echo "This will REMOVE the 5 runtime-state columns from pipeline_states."
  echo "Existing rows lose schema_version/pipeline_degraded/etc data."
  ACTION="downgrade -1"
else
  echo "MODE: UPGRADE"
  echo "This will ADD 5 nullable columns to pipeline_states. Existing rows"
  echo "default to NULL/[]. Forward-compatible."
  ACTION="upgrade head"
fi

read -p "Proceed with '$ACTION'? Type 'yes' to confirm: " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
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
