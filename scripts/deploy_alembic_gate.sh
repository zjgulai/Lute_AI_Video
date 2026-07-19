#!/usr/bin/env bash
# Non-interactive schema gate executed inside the reviewed backend image.

set -euo pipefail

MODE="${1:---check}"
case "$MODE" in
  --check|--apply) ;;
  *)
    echo "ERROR: usage: $0 [--check|--apply]" >&2
    exit 2
    ;;
esac

case "${ENVIRONMENT:-}" in
  prod|production) ;;
  *)
    echo "ERROR: deploy schema gate requires ENVIRONMENT=production." >&2
    exit 1
    ;;
esac

case "${DATABASE_URL:-}" in
  postgresql://*|postgres://*) ;;
  *)
    echo "ERROR: deploy schema gate requires a PostgreSQL DATABASE_URL." >&2
    exit 1
    ;;
esac

cd /app/migrations

extract_current() {
  awk '
    /^[[:space:]]*$/ { next }
    /^[[:space:]]*(INFO|DEBUG|WARN|WARNING|ERROR)[[:space:]]/ { next }
    $1 ~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$/ && (NF == 1 || $0 ~ /\(head\)/) { print $1 }
  '
}

extract_heads() {
  awk '$1 ~ /^[A-Za-z0-9][A-Za-z0-9_.-]*$/ && $0 ~ /\(head\)/ { print $1 }'
}

HEAD_OUTPUT="$(python3 -m alembic heads)"
HEAD_REVISIONS="$(printf '%s\n' "$HEAD_OUTPUT" | extract_heads)"
HEAD_COUNT="$(printf '%s\n' "$HEAD_REVISIONS" | awk 'NF { count += 1 } END { print count + 0 }')"
if [ "$HEAD_COUNT" != "1" ]; then
  echo "ERROR: expected exactly one Alembic head, found $HEAD_COUNT." >&2
  exit 1
fi
HEAD_REVISION="$(printf '%s\n' "$HEAD_REVISIONS" | head -1)"

read_current_revision() {
  local output revisions count
  output="$(python3 -m alembic current)"
  revisions="$(printf '%s\n' "$output" | extract_current)"
  count="$(printf '%s\n' "$revisions" | awk 'NF { count += 1 } END { print count + 0 }')"
  if [ "$count" -gt 1 ]; then
    echo "ERROR: database reports multiple current Alembic revisions." >&2
    exit 1
  fi
  if [ "$count" = "0" ]; then
    printf 'base\n'
  else
    printf '%s\n' "$revisions" | head -1
  fi
}

CURRENT_REVISION="$(read_current_revision)"
echo "Alembic current revision: $CURRENT_REVISION"
echo "Alembic target head: $HEAD_REVISION"

if [ "$MODE" = "--apply" ] && [ "$CURRENT_REVISION" != "$HEAD_REVISION" ]; then
  if [ "${DEPLOY_MIGRATION_AUTH:-}" != "APPLY_REVIEWED_RELEASE" ]; then
    echo "ERROR: DEPLOY_MIGRATION_AUTH is required for schema mutation." >&2
    exit 1
  fi
  python3 -m alembic upgrade head
fi

POST_REVISION="$(read_current_revision)"
if [ "$POST_REVISION" != "$HEAD_REVISION" ]; then
  echo "ERROR: database revision does not match the single Alembic head." >&2
  exit 1
fi

echo "Alembic schema gate: passed at $POST_REVISION"
