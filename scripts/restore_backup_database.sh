#!/usr/bin/env bash
# Restore one schema-backed backup into a verified empty PostgreSQL database.

set -Eeuo pipefail
umask 077

BACKUP_DIR="${1:-}"
DOCKER_BIN="${DOCKER_BIN:-docker}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-ai_video_backend}"
NETWORK_NAME="${NETWORK_NAME:-lighthouse_ai_video_net}"
RESTORE_SCRIPT="${RESTORE_SCRIPT:-/opt/ai-video/scripts/pg_restore_logical.py}"
VERIFY_SCRIPT="${VERIFY_SCRIPT:-/opt/ai-video/scripts/verify_restored_database.py}"
EXPECTED_RESTORE_HOST="${EXPECTED_RESTORE_HOST:-}"
RESTORE_SCOPE="${RESTORE_SCOPE:-isolated}"
RESTORE_CONFIRMATION="${RESTORE_CONFIRMATION:-}"
VERIFY_OUTPUT=""

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
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

emit_libpq_bundle() {
  printf '%s\n' "$TARGET_DATABASE_URL" \
    | python3 -c '
import base64
import sys
from urllib.parse import parse_qs, unquote, urlparse

parsed = urlparse(sys.stdin.readline().strip())
host = parsed.hostname or sys.exit("restore target host is missing")
port = parsed.port or 5432
database = unquote(parsed.path.lstrip("/"))
user = unquote(parsed.username or "")
password = unquote(parsed.password or "")
sslmode = parse_qs(parsed.query).get("sslmode", ["prefer"])[0]

def escape_pgpass(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:")

pgpass = (
    f"{escape_pgpass(host)}:{port}:{escape_pgpass(database)}:"
    f"{escape_pgpass(user)}:{escape_pgpass(password)}\n"
)
for value in (pgpass, host, str(port), database, user, sslmode):
    print(base64.b64encode(value.encode()).decode())
'
}

manifest_field() {
  local key="$1"
  local value
  value=$(awk -F': ' -v key="$key" '$1 == key {print $2}' "${BACKUP_DIR}/manifest.txt")
  [ -n "$value" ] || fail "manifest field is missing: ${key}"
  printf '%s\n' "$value"
}

cleanup() {
  if [ -n "$VERIFY_OUTPUT" ]; then
    rm -f "$VERIFY_OUTPUT"
  fi
}
trap cleanup EXIT
trap 'exit 130' HUP INT TERM

[ -n "$BACKUP_DIR" ] || fail "backup directory argument is required"
[ -d "$BACKUP_DIR" ] || fail "backup directory does not exist"
[ -n "$EXPECTED_RESTORE_HOST" ] || fail "EXPECTED_RESTORE_HOST is required"
[ "$RESTORE_CONFIRMATION" = "RESTORE_EMPTY_DATABASE" ] \
  || fail "RESTORE_CONFIRMATION must be RESTORE_EMPTY_DATABASE"
case "$RESTORE_SCOPE" in
  isolated)
    [[ "$EXPECTED_RESTORE_HOST" =~ ^l4[_-]restore[_-] ]] \
      || fail "isolated restore host must use the l4_restore_ prefix"
    ;;
  production)
    [ "${ALLOW_PRODUCTION_RESTORE:-0}" = "1" ] \
      || fail "ALLOW_PRODUCTION_RESTORE=1 is required"
    [ "${PRODUCTION_RESTORE_CONFIRMATION:-}" = "I_ACKNOWLEDGE_PRODUCTION_DATABASE_RESTORE" ] \
      || fail "exact production restore confirmation is required"
    ;;
  *) fail "RESTORE_SCOPE must be isolated or production" ;;
esac

IFS= read -r TARGET_DATABASE_URL || fail "target database URL is required on stdin"
[ -n "$TARGET_DATABASE_URL" ] || fail "target database URL is empty"
printf '%s\n' "$TARGET_DATABASE_URL" \
  | python3 -c '
import sys
from urllib.parse import urlparse

expected = sys.argv[1]
parsed = urlparse(sys.stdin.readline().strip())
if parsed.scheme not in {"postgres", "postgresql"}:
    raise SystemExit("restore target must use PostgreSQL")
if parsed.hostname != expected:
    raise SystemExit("restore target hostname mismatch")
' "$EXPECTED_RESTORE_HOST"

for required_file in \
  manifest.txt pg_dump.jsonl pg_dump_stats.json pg_schema.dump pg_schema.list \
  pg_schema_signature_after.json; do
  [ -f "${BACKUP_DIR}/${required_file}" ] \
    || fail "required backup artifact is missing: ${required_file}"
  [ ! -L "${BACKUP_DIR}/${required_file}" ] \
    || fail "backup artifacts must not be symlinks"
done
[ -f "$RESTORE_SCRIPT" ] || fail "logical restore script not found"
[ -f "$VERIFY_SCRIPT" ] || fail "restore verifier script not found"
command -v "$DOCKER_BIN" >/dev/null 2>&1 || fail "docker command not found"

[ "$(manifest_field project)" = "ai-video" ] || fail "backup project marker is invalid"
[ "$(manifest_field status)" = "complete" ] || fail "backup is not complete"
[ "$(manifest_field pg_dump_sha256)" = "$(sha256_file "${BACKUP_DIR}/pg_dump.jsonl")" ] \
  || fail "pg_dump.jsonl checksum mismatch"
[ "$(manifest_field pg_dump_stats_sha256)" = "$(sha256_file "${BACKUP_DIR}/pg_dump_stats.json")" ] \
  || fail "pg_dump_stats.json checksum mismatch"
[ "$(manifest_field pg_schema_sha256)" = "$(sha256_file "${BACKUP_DIR}/pg_schema.dump")" ] \
  || fail "pg_schema.dump checksum mismatch"
[ "$(manifest_field pg_schema_list_sha256)" = "$(sha256_file "${BACKUP_DIR}/pg_schema.list")" ] \
  || fail "pg_schema.list checksum mismatch"
[ "$(manifest_field pg_schema_signature_after_sha256)" = "$(sha256_file "${BACKUP_DIR}/pg_schema_signature_after.json")" ] \
  || fail "pg_schema_signature_after.json checksum mismatch"
PG_SCHEMA_SIGNATURE=$(manifest_field pg_schema_signature)
python3 - \
  "${BACKUP_DIR}/pg_dump_stats.json" \
  "${BACKUP_DIR}/pg_schema_signature_after.json" \
  "$PG_SCHEMA_SIGNATURE" <<'PY'
import json
import re
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get(
    "schema_signature"
)
after = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")).get(
    "schema_signature"
)
manifest_signature = sys.argv[3]
if not all(
    isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
    for value in (before, after, manifest_signature)
):
    raise SystemExit("schema signature evidence is invalid")
if len({before, after, manifest_signature}) != 1:
    raise SystemExit("schema signature evidence does not match")
PY

PG_SERVER_MAJOR=$(manifest_field pg_server_major)
PG_CLIENT_SOURCE_TAG=$(manifest_field pg_client_source_tag)
PG_CLIENT_IMAGE=$(manifest_field pg_client_image)
[[ "$PG_SERVER_MAJOR" =~ ^[0-9]+$ ]] || fail "invalid PostgreSQL server major"
[ "$PG_CLIENT_SOURCE_TAG" = "postgres:${PG_SERVER_MAJOR}" ] \
  || fail "PostgreSQL client source tag does not match server major"
[[ "$PG_CLIENT_IMAGE" =~ ^postgres@sha256:[0-9a-f]{64}$ ]] \
  || fail "PostgreSQL client image is not digest-pinned"
"$DOCKER_BIN" image inspect "$PG_CLIENT_IMAGE" >/dev/null 2>&1 \
  || fail "digest-pinned PostgreSQL client image is unavailable"
RESOLVED_DIGEST=$(
  "$DOCKER_BIN" image inspect "$PG_CLIENT_SOURCE_TAG" \
    --format='{{index .RepoDigests 0}}'
)
[ "$RESOLVED_DIGEST" = "$PG_CLIENT_IMAGE" ] \
  || fail "local PostgreSQL client tag no longer resolves to the backup digest"

"$DOCKER_BIN" run --rm -i --network none "$PG_CLIENT_IMAGE" pg_restore --list \
  <"${BACKUP_DIR}/pg_schema.dump" \
  | cmp - "${BACKUP_DIR}/pg_schema.list" \
  || fail "schema archive list does not match the backup"

PUBLIC_TABLE_COUNT=$(
  emit_libpq_bundle \
    | "$DOCKER_BIN" run --rm -i \
        --network "$NETWORK_NAME" \
        "$PG_CLIENT_IMAGE" \
        sh -eu -c '
          umask 077
          IFS= read -r pgpass_b64
          IFS= read -r host_b64
          IFS= read -r port_b64
          IFS= read -r database_b64
          IFS= read -r user_b64
          IFS= read -r sslmode_b64
          decode() { printf "%s" "$1" | base64 -d; }
          printf "%s" "$pgpass_b64" | base64 -d > /tmp/pgpass
          chmod 600 /tmp/pgpass
          export PGPASSFILE=/tmp/pgpass
          export PGHOST="$(decode "$host_b64")"
          export PGPORT="$(decode "$port_b64")"
          export PGDATABASE="$(decode "$database_b64")"
          export PGUSER="$(decode "$user_b64")"
          export PGSSLMODE="$(decode "$sslmode_b64")"
          unset pgpass_b64 host_b64 port_b64 database_b64 user_b64 sslmode_b64
          exec psql --no-psqlrc -Atqc "SELECT count(*) FROM pg_tables WHERE schemaname = '\''public'\''"
        '
)
[ "$PUBLIC_TABLE_COUNT" = "0" ] || fail "restore target database is not empty"

emit_libpq_bundle \
  | "$DOCKER_BIN" run --rm -i \
      --network "$NETWORK_NAME" \
      -v "${BACKUP_DIR}:/backup:ro" \
      "$PG_CLIENT_IMAGE" \
      sh -eu -c '
        umask 077
        IFS= read -r pgpass_b64
        IFS= read -r host_b64
        IFS= read -r port_b64
        IFS= read -r database_b64
        IFS= read -r user_b64
        IFS= read -r sslmode_b64
        decode() { printf "%s" "$1" | base64 -d; }
        printf "%s" "$pgpass_b64" | base64 -d > /tmp/pgpass
        chmod 600 /tmp/pgpass
        export PGPASSFILE=/tmp/pgpass
        export PGHOST="$(decode "$host_b64")"
        export PGPORT="$(decode "$port_b64")"
        export PGDATABASE="$(decode "$database_b64")"
        export PGUSER="$(decode "$user_b64")"
        export PGSSLMODE="$(decode "$sslmode_b64")"
        unset pgpass_b64 host_b64 port_b64 database_b64 user_b64 sslmode_b64
        exec pg_restore --dbname="$PGDATABASE" --schema-only --single-transaction --exit-on-error --no-owner --no-privileges /backup/pg_schema.dump
      '

BACKEND_IMAGE_ID=$(
  "$DOCKER_BIN" inspect "$BACKEND_CONTAINER" --format='{{.Image}}'
)
[[ "$BACKEND_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] \
  || fail "backend container image id is invalid"

printf '%s\n' "$TARGET_DATABASE_URL" \
  | "$DOCKER_BIN" run --rm -i \
      --network "$NETWORK_NAME" \
      --read-only \
      --tmpfs /tmp \
      --user 0:0 \
      -e PYTHONDONTWRITEBYTECODE=1 \
      -v "${BACKUP_DIR}:/backup:ro" \
      -v "${RESTORE_SCRIPT}:/run/restore.py:ro" \
      --entrypoint sh \
      "$BACKEND_IMAGE_ID" \
      -eu -c 'IFS= read -r database_url; export DATABASE_URL="$database_url"; unset database_url; cd /app; exec python3 /run/restore.py /backup/pg_dump.jsonl'

VERIFY_OUTPUT=$(mktemp)
printf '%s\n' "$TARGET_DATABASE_URL" \
  | "$DOCKER_BIN" run --rm -i \
      --network "$NETWORK_NAME" \
      --read-only \
      --tmpfs /tmp \
      --user 0:0 \
      -e PYTHONDONTWRITEBYTECODE=1 \
      -v "${BACKUP_DIR}:/backup:ro" \
      -v "${VERIFY_SCRIPT}:/run/verify.py:ro" \
      --entrypoint sh \
      "$BACKEND_IMAGE_ID" \
      -eu -c 'IFS= read -r database_url; export DATABASE_URL="$database_url"; unset database_url; cd /app; exec python3 /run/verify.py /backup/pg_dump_stats.json' \
      >"$VERIFY_OUTPUT"

MANIFEST_SHA256=$(sha256_file "${BACKUP_DIR}/manifest.txt")
python3 - \
  "$VERIFY_OUTPUT" \
  "${BACKUP_DIR}/restore_verified.json" \
  "$MANIFEST_SHA256" \
  "$RESTORE_SCOPE" \
  "$EXPECTED_RESTORE_HOST" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

summary = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if summary.get("status") != "passed":
    raise SystemExit("restore verifier did not pass")
marker = {
    "status": "passed",
    "verified_at": datetime.now(timezone.utc).isoformat(),
    "manifest_sha256": sys.argv[3],
    "restore_scope": sys.argv[4],
    "target_host": sys.argv[5],
    "table_count": summary.get("table_count"),
    "total_rows": summary.get("total_rows"),
    "actual_counts": summary.get("actual_counts"),
}
marker_path = Path(sys.argv[2])
marker_path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
os.chmod(marker_path, 0o600)
print(json.dumps(marker, sort_keys=True))
PY

unset TARGET_DATABASE_URL
printf 'restore_database=passed\n'
