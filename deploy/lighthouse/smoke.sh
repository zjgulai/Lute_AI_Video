#!/usr/bin/env bash
# Provider-off public smoke. This script has no credential or provider path.

set -Eeuo pipefail

BASE="${BASE:-https://video.lute-tlz-dddd.top}"
EXPECTED_APP_VERSION="${EXPECTED_APP_VERSION:-}"
EXPECTED_SOURCE_REVISION="${EXPECTED_SOURCE_REVISION:-}"

if [ -n "${API_KEY:-}" ] || [ -n "${PLAYWRIGHT_API_KEY:-}" ]; then
  echo "ERROR: provider-off public smoke forbids API key input" >&2
  exit 2
fi
if [ "${RUN_TOKEN_SMOKE:-0}" != "0" ]; then
  echo "ERROR: provider/token smoke is available only through an exact authorized executor" >&2
  exit 2
fi
if [[ "$BASE" != https://* ]]; then
  echo "ERROR: public smoke requires an HTTPS base URL" >&2
  exit 2
fi
if [ -z "$EXPECTED_APP_VERSION" ]; then
  echo "ERROR: EXPECTED_APP_VERSION is required" >&2
  exit 2
fi
if ! [[ "$EXPECTED_SOURCE_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: EXPECTED_SOURCE_REVISION must be the reviewed 40-character Git SHA" >&2
  exit 2
fi

CURL=(curl --silent --show-error --proto '=https' --tlsv1.2 --max-time 15)
FAILED=0

check_status() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then
    echo "[OK] $name -> $actual"
  else
    echo "[FAIL] $name -> expected $expected, got $actual" >&2
    FAILED=$((FAILED + 1))
  fi
}

health_payload="$("${CURL[@]}" --fail "$BASE/api/health")" || {
  echo "[FAIL] GET /api/health" >&2
  exit 1
}
printf '%s' "$health_payload" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
persistence = payload.get("persistence") or {}
assert payload.get("status") == "ok"
assert payload.get("version") == sys.argv[1]
assert payload.get("source_revision") == sys.argv[2]
assert persistence.get("backend") == "postgresql"
assert persistence.get("status") == "healthy"
assert persistence.get("tables_verified") is True
' "$EXPECTED_APP_VERSION" "$EXPECTED_SOURCE_REVISION" || {
  echo "[FAIL] public health or release identity mismatch" >&2
  exit 1
}
echo "[OK] public health, PostgreSQL and dual release identity"

frontend_status="$("${CURL[@]}" --output /dev/null --write-out '%{http_code}' "$BASE/")"
check_status "GET /" "200" "$frontend_status"

unauthorized_status="$("${CURL[@]}" --output /dev/null --write-out '%{http_code}' \
  "$BASE/api/toolbox/tools")"
check_status "GET /api/toolbox/tools without key" "401" "$unauthorized_status"

if [ "$FAILED" -ne 0 ]; then
  echo "provider-off public smoke failed: $FAILED check(s)" >&2
  exit 1
fi

echo "provider-off public smoke passed; provider_call=false"
