#!/usr/bin/env bash
# Hermes-Evo production backup: PostgreSQL logical dump + media snapshot.

set -euo pipefail

umask 077

BACKUP_ROOT="${BACKUP_ROOT:-/opt/ai-video-backups}"
PROJECT_ROOT="${PROJECT_ROOT:-/opt/ai-video}"
CONTAINER_NAME="${CONTAINER_NAME:-ai_video_backend}"
RETENTION_DAYS="${RETENTION_DAYS:-15}"
MIN_PG_ROWS="${MIN_PG_ROWS:-1}"
TIMESTAMP="${BACKUP_TIMESTAMP:-$(date +%Y-%m-%d_%H%M%S)}"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
PARTIAL_DIR="${BACKUP_ROOT}/.${TIMESTAMP}.partial"
LOCK_FILE="${BACKUP_ROOT}/.backup.lock"
DUMP_SCRIPT="${DUMP_SCRIPT:-${PROJECT_ROOT}/scripts/pg_dump_logical.py}"
REMOTE_DUMP_SCRIPT="/tmp/pg_dump_logical_${TIMESTAMP}.py"
REMOTE_DUMP_FILE="/tmp/pg_dump_${TIMESTAMP}.jsonl"
DOCKER_BIN="${DOCKER_BIN:-docker}"
FLOCK_BIN="${FLOCK_BIN:-flock}"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S%z')" "$*"
}

fail() {
  log "ERROR: $*" >&2
  exit 1
}

require_non_negative_integer() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || fail "${name} must be a non-negative integer"
}

require_positive_integer() {
  local name="$1"
  local value="$2"
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || fail "${name} must be a positive integer"
}

sha256_file() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
  else
    fail "sha256sum or shasum is required"
  fi
}

cleanup() {
  local exit_code=$?

  "$DOCKER_BIN" exec "$CONTAINER_NAME" rm -f \
    "$REMOTE_DUMP_SCRIPT" "$REMOTE_DUMP_FILE" >/dev/null 2>&1 || true

  if [ "$exit_code" -ne 0 ] && [ -d "$PARTIAL_DIR" ]; then
    rm -rf -- "$PARTIAL_DIR"
    log "Removed incomplete backup: ${PARTIAL_DIR}" >&2
  fi
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

require_positive_integer "RETENTION_DAYS" "$RETENTION_DAYS"
require_non_negative_integer "MIN_PG_ROWS" "$MIN_PG_ROWS"
[[ "$TIMESTAMP" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}$ ]] \
  || fail "BACKUP_TIMESTAMP must use YYYY-MM-DD_HHMMSS"
[[ "$CONTAINER_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] \
  || fail "CONTAINER_NAME contains invalid characters"

command -v "$DOCKER_BIN" >/dev/null 2>&1 || fail "docker command not found: ${DOCKER_BIN}"
command -v "$FLOCK_BIN" >/dev/null 2>&1 || fail "flock command not found: ${FLOCK_BIN}"
[ -f "$DUMP_SCRIPT" ] || fail "logical dump script not found: ${DUMP_SCRIPT}"

mkdir -p "$BACKUP_ROOT"
exec 9>"$LOCK_FILE"
"$FLOCK_BIN" -n 9 || fail "another production backup is already running"

[ ! -e "$BACKUP_DIR" ] || fail "completed backup already exists: ${BACKUP_DIR}"
[ ! -e "$PARTIAL_DIR" ] || fail "partial backup already exists: ${PARTIAL_DIR}"
mkdir "$PARTIAL_DIR"

log "=== Hermes-Evo Backup Start ==="
log "1/5 Dumping PostgreSQL through backend container"
"$DOCKER_BIN" cp "$DUMP_SCRIPT" "${CONTAINER_NAME}:${REMOTE_DUMP_SCRIPT}"
"$DOCKER_BIN" exec "$CONTAINER_NAME" \
  python3 "$REMOTE_DUMP_SCRIPT" "$REMOTE_DUMP_FILE" \
  >"${PARTIAL_DIR}/pg_dump_stats.json"
"$DOCKER_BIN" cp \
  "${CONTAINER_NAME}:${REMOTE_DUMP_FILE}" \
  "${PARTIAL_DIR}/pg_dump.jsonl"

log "2/5 Validating PostgreSQL dump"
python3 - \
  "${PARTIAL_DIR}/pg_dump_stats.json" \
  "${PARTIAL_DIR}/pg_dump.jsonl" \
  "$MIN_PG_ROWS" <<'PY'
import json
import sys
from pathlib import Path

stats_path = Path(sys.argv[1])
dump_path = Path(sys.argv[2])
minimum_rows = int(sys.argv[3])

with stats_path.open(encoding="utf-8") as stream:
    stats = json.load(stream)

tables = stats.get("tables")
if not isinstance(tables, dict) or not tables:
    raise SystemExit("backup stats do not contain table results")

expected_tables = stats.get("expected_tables")
if not isinstance(expected_tables, list) or not expected_tables:
    raise SystemExit("backup stats do not declare expected tables")
if set(expected_tables) != set(tables):
    raise SystemExit("logical dump table set does not match expected tables")

missing = sorted(name for name, result in tables.items() if "rows" not in result)
if missing:
    raise SystemExit(f"logical dump skipped required tables: {', '.join(missing)}")

total_rows = stats.get("total_rows")
if not isinstance(total_rows, int) or total_rows < minimum_rows:
    raise SystemExit(
        f"logical dump row count {total_rows!r} is below minimum {minimum_rows}"
    )

actual_rows = sum(1 for line in dump_path.open(encoding="utf-8") if line.strip())
if actual_rows != total_rows:
    raise SystemExit(
        f"logical dump row mismatch: stats={total_rows}, jsonl={actual_rows}"
    )

if stats.get("file_size") != dump_path.stat().st_size:
    raise SystemExit("logical dump size does not match pg_dump_stats.json")
PY

PG_SIZE_BYTES=$(wc -c <"${PARTIAL_DIR}/pg_dump.jsonl" | tr -d '[:space:]')
PG_ROW_COUNT=$(wc -l <"${PARTIAL_DIR}/pg_dump.jsonl" | tr -d '[:space:]')
log "PostgreSQL dump: ${PG_SIZE_BYTES} bytes, ${PG_ROW_COUNT} rows"

log "3/5 Copying media snapshot"
mkdir "${PARTIAL_DIR}/output"
"$DOCKER_BIN" cp \
  "${CONTAINER_NAME}:/app/output/." \
  "${PARTIAL_DIR}/output/"
python3 - "${PARTIAL_DIR}/output" "${PARTIAL_DIR}/media_manifest.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
files = []
total_size = 0

for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
    if path.is_symlink():
        raise SystemExit(f"media snapshot contains unsupported symlink: {path.relative_to(root)}")
    if not path.is_file():
        continue

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    size = path.stat().st_size
    total_size += size
    files.append({
        "path": path.relative_to(root).as_posix(),
        "size_bytes": size,
        "sha256": digest.hexdigest(),
    })

manifest_path.write_text(
    json.dumps(
        {
            "file_count": len(files),
            "total_size_bytes": total_size,
            "files": files,
        },
        indent=2,
        ensure_ascii=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
read -r MEDIA_COUNT MEDIA_SIZE_BYTES < <(
  python3 - "${PARTIAL_DIR}/media_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(manifest["file_count"], manifest["total_size_bytes"])
PY
)
log "Media snapshot: ${MEDIA_COUNT} files, ${MEDIA_SIZE_BYTES} bytes"

log "4/5 Writing manifest and publishing completed backup"
PG_SHA256=$(sha256_file "${PARTIAL_DIR}/pg_dump.jsonl")
STATS_SHA256=$(sha256_file "${PARTIAL_DIR}/pg_dump_stats.json")
MEDIA_MANIFEST_SHA256=$(sha256_file "${PARTIAL_DIR}/media_manifest.json")
BACKEND_IMAGE=$("$DOCKER_BIN" inspect "$CONTAINER_NAME" --format='{{.Config.Image}}')
cat >"${PARTIAL_DIR}/manifest.txt" <<EOF
project: ai-video
backup_timestamp: ${TIMESTAMP}
completed_at: $(date -u +%Y-%m-%dT%H:%M:%SZ)
hostname: $(hostname)
container_name: ${CONTAINER_NAME}
backend_image: ${BACKEND_IMAGE}
pg_dump_size_bytes: ${PG_SIZE_BYTES}
pg_dump_rows: ${PG_ROW_COUNT}
pg_dump_sha256: ${PG_SHA256}
pg_dump_stats_sha256: ${STATS_SHA256}
media_count: ${MEDIA_COUNT}
media_size_bytes: ${MEDIA_SIZE_BYTES}
media_manifest_sha256: ${MEDIA_MANIFEST_SHA256}
retention_days: ${RETENTION_DAYS}
status: complete
EOF

mv "$PARTIAL_DIR" "$BACKUP_DIR"
log "Published completed backup: ${BACKUP_DIR}"

log "5/5 Removing completed AI Video backups older than ${RETENTION_DAYS} days"
while IFS= read -r -d '' expired_dir; do
  manifest="${expired_dir}/manifest.txt"
  if [ -f "$manifest" ] \
    && grep -Fxq 'project: ai-video' "$manifest" \
    && grep -Fxq 'status: complete' "$manifest"; then
    log "Removing expired backup: ${expired_dir}"
    rm -rf -- "$expired_dir"
  else
    log "Skipping unrecognized timestamp directory: ${expired_dir}"
  fi
done < <(
  find "$BACKUP_ROOT" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -name '20??-??-??_??????' \
    -mtime "+${RETENTION_DAYS}" \
    -print0
)

REMAINING=0
while IFS= read -r -d '' retained_dir; do
  manifest="${retained_dir}/manifest.txt"
  if [ -f "$manifest" ] \
    && grep -Fxq 'project: ai-video' "$manifest" \
    && grep -Fxq 'status: complete' "$manifest"; then
    REMAINING=$((REMAINING + 1))
  fi
done < <(
  find "$BACKUP_ROOT" \
    -mindepth 1 \
    -maxdepth 1 \
    -type d \
    -name '20??-??-??_??????' \
    -print0
)
log "Total completed backups retained: ${REMAINING}"
log "=== Backup Complete: ${BACKUP_DIR} ==="
