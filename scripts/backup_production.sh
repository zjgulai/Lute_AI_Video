#!/bin/bash
# Hermes-Evo Production Backup — daily cron
# - PG dump via psycopg (Tencent Cloud RDS, no local pg_dump)
# - media rsync from backend container's /app/output
# - 7-day rotation
# Location: /opt/ai-video-backups/{YYYY-MM-DD_HHMMSS}/

set -euo pipefail

BACKUP_ROOT="/opt/ai-video-backups"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
CONTAINER_NAME="ai_video_backend"
RETENTION_DAYS=7

echo "[$(date)] === Hermes-Evo Backup Start ==="
sudo mkdir -p "${BACKUP_DIR}"
cd "${BACKUP_DIR}"

echo "[$(date)] 1/4 Dumping PG via psycopg..."
sudo docker cp /opt/ai-video/scripts/pg_dump_logical.py "${CONTAINER_NAME}:/tmp/pg_dump_logical.py"
sudo docker exec "${CONTAINER_NAME}" python3 /tmp/pg_dump_logical.py /tmp/pg_dump.jsonl > pg_dump_stats.json
sudo docker cp "${CONTAINER_NAME}:/tmp/pg_dump.jsonl" pg_dump.jsonl
PG_SIZE=$(sudo du -h pg_dump.jsonl | cut -f1)
ROW_COUNT=$(sudo wc -l < pg_dump.jsonl || echo 0)
echo "[$(date)] PG dump: ${PG_SIZE}, ${ROW_COUNT} rows"

echo "[$(date)] 2/4 Syncing media files..."
sudo mkdir -p output
sudo docker cp "${CONTAINER_NAME}:/app/output/." output/ 2>&1 | tail -3
MEDIA_COUNT=$(sudo find output -type f 2>/dev/null | wc -l)
MEDIA_SIZE=$(sudo du -sh output 2>/dev/null | cut -f1)
echo "[$(date)] Media: ${MEDIA_COUNT} files, ${MEDIA_SIZE}"

echo "[$(date)] 3/4 Writing manifest..."
sudo tee manifest.txt > /dev/null <<EOF
backup_timestamp: ${TIMESTAMP}
hostname: $(hostname)
pg_dump_size: ${PG_SIZE}
pg_dump_rows: ${ROW_COUNT}
media_count: ${MEDIA_COUNT}
media_size: ${MEDIA_SIZE}
backend_image: $(sudo docker inspect ${CONTAINER_NAME} --format='{{.Config.Image}}')
EOF
sudo cat manifest.txt

echo "[$(date)] 4/4 Cleaning up old backups (>${RETENTION_DAYS} days)..."
sudo find "${BACKUP_ROOT}" -maxdepth 1 -type d -name "20*" -mtime +${RETENTION_DAYS} -exec rm -rf {} \; 2>/dev/null || true

REMAINING=$(sudo ls -1d "${BACKUP_ROOT}"/20* 2>/dev/null | wc -l)
echo "[$(date)] Total backups retained: ${REMAINING}"
echo "[$(date)] === Backup Complete: ${BACKUP_DIR} ==="
