#!/usr/bin/env bash
set -euo pipefail

: "${EXPECTED_SHA:?EXPECTED_SHA is required}"
: "${EXPECTED_BACKEND_IMAGE_ID:?EXPECTED_BACKEND_IMAGE_ID is required}"
: "${REMOTE_STAGE:?REMOTE_STAGE is required}"
: "${REMOTE_PRIVATE:?REMOTE_PRIVATE is required}"

FIXTURE_MODE="${AI_VIDEO_W5_WINDOW_FIXTURE:-0}"

[[ "${EXPECTED_SHA}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "invalid exact release SHA" >&2
  exit 2
}
[[ "${EXPECTED_BACKEND_IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  echo "invalid exact backend image ID" >&2
  exit 2
}
[[ "${REMOTE_STAGE}" = /* && "${REMOTE_PRIVATE}" = /* ]] || {
  echo "private paths must be absolute" >&2
  exit 2
}
case "${REMOTE_PRIVATE}" in
  /|/app|/app/|/app/output|/app/output/|*//*|*/../*|*/./*)
    echo "unsafe private container path" >&2
    exit 2
    ;;
esac
if [[ "${FIXTURE_MODE}" != "1" && "${REMOTE_PRIVATE}" != "/run/ai-video-w5" ]]; then
  echo "private container path must use the fixed W5 leaf" >&2
  exit 2
fi

SHARED_ROOT="${AI_VIDEO_SHARED_ROOT:-/opt/ai-video}"
ENV_FILE="${AI_VIDEO_ENV_FILE:-${SHARED_ROOT}/deploy/lighthouse/.env.prod}"
CURRENT_RELEASE="${SHARED_ROOT}/releases-${EXPECTED_SHA}"
COMPOSE_FILE="${CURRENT_RELEASE}/deploy/lighthouse/docker-compose.release.yml"
BACKUP_DIR=""
BACKUP_FILE=""
EVIDENCE_ID=""
EVIDENCE_DIR=""
RESTORE_ARMED=0
RESTORE_RUNNING=0

_restart_backend() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    return 0
  fi
  sudo env \
    RELEASE_IMAGE_TAG="${EXPECTED_SHA}" \
    RELEASE_SOURCE_SHA="${EXPECTED_SHA}" \
    AI_VIDEO_ENV_FILE="${ENV_FILE}" \
    docker compose \
      -p lighthouse \
      -f "${COMPOSE_FILE}" \
      up -d --no-deps --force-recreate backend >/dev/null
}

_wait_backend_ready() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    return 0
  fi
  local attempt
  for attempt in $(seq 1 24); do
    if sudo docker exec ai_video_backend python3 -c \
      'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8001/health/ready", timeout=10)' \
      >/dev/null 2>&1; then
      return 0
    fi
    sleep 5
  done
  return 1
}

_verify_reviewed_image() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    [[
      "${AI_VIDEO_W5_FIXTURE_IMAGE_REVISION:-}" == "${EXPECTED_SHA}"
      && "${AI_VIDEO_W5_FIXTURE_IMAGE_ID:-}" == "${EXPECTED_BACKEND_IMAGE_ID}"
    ]]
    return $?
  fi
  local image_ref="lighthouse-backend:${EXPECTED_SHA}"
  local revision image_id
  revision="$(sudo docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "${image_ref}")"
  image_id="$(sudo docker image inspect -f '{{.Id}}' "${image_ref}")"
  [[ "${revision}" == "${EXPECTED_SHA}" && "${image_id}" == "${EXPECTED_BACKEND_IMAGE_ID}" ]]
}

_verify_running_backend_identity() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    _verify_reviewed_image
    return
  fi
  local revision image_id configured_ref
  revision="$(sudo docker inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' ai_video_backend)"
  image_id="$(sudo docker inspect -f '{{.Image}}' ai_video_backend)"
  configured_ref="$(sudo docker inspect -f '{{.Config.Image}}' ai_video_backend)"
  [[ "${revision}" == "${EXPECTED_SHA}" ]] || return 1
  [[ "${image_id}" == "${EXPECTED_BACKEND_IMAGE_ID}" ]] || return 1
  [[ "${configured_ref}" == "lighthouse-backend:${EXPECTED_SHA}" ]] || return 1
}

_derive_evidence_path() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    EVIDENCE_ID="w5fastact:fixture"
    EVIDENCE_DIR="${REMOTE_STAGE}/persistent-evidence/${EVIDENCE_ID}"
    return
  fi
  EVIDENCE_ID="$(sudo python3 - "${REMOTE_STAGE}/activation.json" <<'PY'
import json
import os
import re
import stat
import sys

path = sys.argv[1]
descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
try:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 65536:
        raise SystemExit(1)
    raw = os.read(descriptor, 65537)
finally:
    os.close(descriptor)
if len(raw) > 65536:
    raise SystemExit(1)
value = json.loads(raw)
activation_id = value.get("activation_id") if type(value) is dict else None
if not isinstance(activation_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,191}", activation_id):
    raise SystemExit(1)
print(activation_id)
PY
)"
  EVIDENCE_DIR="/app/output/.w5-one-shot/${EVIDENCE_ID}"
}

_assert_persistent_evidence_unused() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    [[ ! -e "${EVIDENCE_DIR}/submit-invoked.json" ]]
    return
  fi
  sudo docker exec ai_video_backend sh -c \
    'test ! -e "$1/submit-invoked.json"' -- "${EVIDENCE_DIR}"
}

_provider_off_env_is_safe() {
  local command=(python3 - "${1}")
  if [[ "${FIXTURE_MODE}" != "1" ]]; then
    command=(sudo python3 - "${1}")
  fi
  "${command[@]}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
values = {}
for line in path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip().removeprefix("export ")
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        continue
    key, value = stripped.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
for key in (
    "W5_FAST_PLAN_PATH",
    "W5_FAST_ACTIVATION_PATH",
    "W5_FAST_RUNTIME_BINDING_PATH",
    "W5_FAST_EVIDENCE_PATH",
):
    if values.get(key):
        raise SystemExit(1)
for key in ("TIKTOK_PUBLISH_ENABLED", "SHOPIFY_PUBLISH_ENABLED"):
    if values.get(key, "false").lower() in {"1", "true", "yes", "on"}:
        raise SystemExit(1)
PY
}

verify_provider_off_restore() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    cmp -s "${BACKUP_FILE}" "${ENV_FILE}" || return 1
    _provider_off_env_is_safe "${ENV_FILE}" || return 1
    [[ "${AI_VIDEO_W5_FIXTURE_RESTORE_FAIL:-0}" != "1" ]] || return 1
    printf '%s\n' "provider_off_restore=pass" > "${REMOTE_STAGE}/restore-receipt.txt"
    return 0
  fi
  sudo cmp -s "${BACKUP_FILE}" "${ENV_FILE}" || return 1
  _provider_off_env_is_safe "${ENV_FILE}" || return 1
  [[ "$(readlink -f "${SHARED_ROOT}/current")" == "${CURRENT_RELEASE}" ]] || return 1
  _verify_running_backend_identity || return 1
  sudo docker exec -i ai_video_backend python3 - <<'PY'
import os

for key in (
    "W5_FAST_PLAN_PATH",
    "W5_FAST_ACTIVATION_PATH",
    "W5_FAST_RUNTIME_BINDING_PATH",
    "W5_FAST_EVIDENCE_PATH",
):
    if os.environ.get(key):
        raise SystemExit(1)
for key in ("TIKTOK_PUBLISH_ENABLED", "SHOPIFY_PUBLISH_ENABLED"):
    if os.environ.get(key, "false").lower() in {"1", "true", "yes", "on"}:
        raise SystemExit(1)
PY
}

restore_provider_off() {
  local original_rc=$?
  if [[ "${RESTORE_RUNNING}" == "1" ]]; then
    exit 90
  fi
  RESTORE_RUNNING=1
  set +e
  if [[ "${RESTORE_ARMED}" != "1" ]]; then
    exit "${original_rc}"
  fi
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    cp -p "${BACKUP_FILE}" "${ENV_FILE}"
  else
    sudo cp -p "${BACKUP_FILE}" "${ENV_FILE}"
  fi
  local restore_rc=$?
  if [[ "${restore_rc}" == "0" ]]; then
    _restart_backend
    restore_rc=$?
  fi
  if [[ "${restore_rc}" == "0" ]]; then
    _wait_backend_ready
    restore_rc=$?
  fi
  if [[ "${restore_rc}" == "0" ]]; then
    verify_provider_off_restore
    restore_rc=$?
  fi
  if [[ "${restore_rc}" != "0" ]]; then
    echo "provider-off restoration failed" >&2
    exit 90
  fi
  echo "provider-off restoration verified" >&2
  exit "${original_rc}"
}

trap restore_provider_off EXIT

configure_w5_window() {
  local command=(python3 - "${ENV_FILE}" "${REMOTE_PRIVATE}" "${EVIDENCE_DIR}")
  if [[ "${FIXTURE_MODE}" != "1" ]]; then
    command=(sudo python3 - "${ENV_FILE}" "${REMOTE_PRIVATE}" "${EVIDENCE_DIR}")
  fi
  "${command[@]}" <<'PY'
import os
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
private = sys.argv[2]
evidence = sys.argv[3]
managed = {
    "POYO_VIDEO_MODEL",
    "W5_FAST_PLAN_PATH",
    "W5_FAST_ACTIVATION_PATH",
    "W5_FAST_RUNTIME_BINDING_PATH",
    "W5_FAST_EVIDENCE_PATH",
    "TIKTOK_PUBLISH_ENABLED",
    "SHOPIFY_PUBLISH_ENABLED",
}
kept = []
for line in env_path.read_text(encoding="utf-8").splitlines():
    stripped = line.strip().removeprefix("export ")
    key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
    if key not in managed:
        kept.append(line)
kept.extend(
    [
        "POYO_VIDEO_MODEL=seedance-2",
        f"W5_FAST_PLAN_PATH={private}/plan.json",
        f"W5_FAST_ACTIVATION_PATH={private}/activation.json",
        f"W5_FAST_RUNTIME_BINDING_PATH={private}/binding.json",
        f"W5_FAST_EVIDENCE_PATH={evidence}",
        "TIKTOK_PUBLISH_ENABLED=false",
        "SHOPIFY_PUBLISH_ENABLED=false",
    ]
)
temporary = env_path.with_name(env_path.name + ".w5-window-tmp")
mode = env_path.stat().st_mode & 0o777
descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8", closefd=False) as target:
        target.write("\n".join(kept) + "\n")
        target.flush()
        os.fsync(target.fileno())
finally:
    os.close(descriptor)
os.replace(temporary, env_path)
PY

  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    return 0
  fi
  _restart_backend
  _wait_backend_ready
  _verify_running_backend_identity
  sudo docker exec ai_video_backend test ! -e "${REMOTE_PRIVATE}"
  sudo docker exec -u 0 ai_video_backend mkdir -m 700 "${REMOTE_PRIVATE}"
  local name
  for name in plan.json activation.json binding.json request.json; do
    sudo test -f "${REMOTE_STAGE}/${name}"
    sudo docker cp \
      "${REMOTE_STAGE}/${name}" \
      "ai_video_backend:${REMOTE_PRIVATE}/${name}" >/dev/null
  done
  local container_uid container_gid
  container_uid="$(sudo docker exec ai_video_backend id -u)"
  container_gid="$(sudo docker exec ai_video_backend id -g)"
  sudo docker exec -u 0 ai_video_backend chown \
    "${container_uid}:${container_gid}" "${REMOTE_PRIVATE}"
  sudo docker exec -u 0 ai_video_backend \
    sh -c 'chown "$2:$3" "$1"/*.json' -- \
    "${REMOTE_PRIVATE}" "${container_uid}" "${container_gid}"
  sudo docker exec -u 0 ai_video_backend chmod 700 "${REMOTE_PRIVATE}"
  sudo docker exec -u 0 ai_video_backend \
    sh -c 'chmod 600 "$1"/*.json' -- "${REMOTE_PRIVATE}"
  sudo docker exec -u 0 ai_video_backend sh -c \
    'set -eu; umask 077; parent=/app/output/.w5-one-shot; test ! -L /app/output; if test ! -e "$parent"; then mkdir -m 700 "$parent"; fi; test -d "$parent"; test ! -L "$parent"; chown "$2:$3" "$parent"; chmod 700 "$parent"; if test ! -e "$1"; then mkdir -m 700 "$1"; fi; test -d "$1"; test ! -L "$1"; test -z "$(find "$1" -mindepth 1 -maxdepth 1 -print -quit)"; chown "$2:$3" "$1"; chmod 700 "$1"' -- \
    "${EVIDENCE_DIR}" "${container_uid}" "${container_gid}"
  sudo docker exec -i ai_video_backend python3 - <<'PY'
import os
from pathlib import Path

private_keys = (
    "W5_FAST_PLAN_PATH",
    "W5_FAST_ACTIVATION_PATH",
    "W5_FAST_RUNTIME_BINDING_PATH",
)
if not all(os.environ.get(key) and Path(os.environ[key]).is_file() for key in private_keys):
    raise SystemExit(1)
evidence = os.environ.get("W5_FAST_EVIDENCE_PATH")
if not evidence or not Path(evidence).is_dir():
    raise SystemExit(1)
if os.environ.get("POYO_VIDEO_MODEL") != "seedance-2":
    raise SystemExit(1)
for key in ("TIKTOK_PUBLISH_ENABLED", "SHOPIFY_PUBLISH_ENABLED"):
    if os.environ.get(key, "false").lower() in {"1", "true", "yes", "on"}:
        raise SystemExit(1)
PY
}

run_operator() {
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    mkdir -p -m 700 "${EVIDENCE_DIR}"
    (
      set -o noclobber
      umask 077
      printf '%s\n' '{"state":"consumed_before_submit"}' > \
        "${EVIDENCE_DIR}/submit-invoked.json"
    ) || return 2
    printf '%s\n' '1' > "${EVIDENCE_DIR}/post-count.txt"
    return "${AI_VIDEO_W5_FIXTURE_RESULT:-0}"
  fi
  local submit_rc poll_rc ledger_rc
  set +e
  sudo docker exec -i \
    -e AI_VIDEO_W5_FAST_EXECUTE=1 \
    ai_video_backend \
    python3 /app/scripts/w5_fast_one_shot_operator.py submit
  submit_rc=$?
  set -e
  poll_rc=0
  if [[ "${submit_rc}" == "0" ]]; then
    set +e
    sudo docker exec ai_video_backend \
      python3 /app/scripts/w5_fast_one_shot_operator.py poll
    poll_rc=$?
    set -e
  fi
  set +e
  sudo docker exec ai_video_backend \
    python3 /app/scripts/w5_fast_one_shot_operator.py ledger
  ledger_rc=$?
  set -e
  if [[ "${submit_rc}" != "0" ]]; then
    return "${submit_rc}"
  fi
  if [[ "${poll_rc}" != "0" ]]; then
    return "${poll_rc}"
  fi
  return "${ledger_rc}"
}

prepare_provider_off_backup() {
  [[ -f "${ENV_FILE}" ]] || {
    echo "provider-off env file unavailable" >&2
    return 2
  }
  if [[ "${FIXTURE_MODE}" == "1" ]]; then
    BACKUP_DIR="$(mktemp -d "${REMOTE_STAGE}/provider-off-backup.XXXXXX")"
    BACKUP_FILE="${BACKUP_DIR}/env.before"
    cp -p "${ENV_FILE}" "${BACKUP_FILE}"
  else
    [[ "$(readlink -f "${SHARED_ROOT}/current")" == "${CURRENT_RELEASE}" ]] || {
      echo "current release mismatch" >&2
      return 2
    }
    [[ -f "${COMPOSE_FILE}" ]] || {
      echo "exact release compose unavailable" >&2
      return 2
    }
    BACKUP_DIR="$(sudo mktemp -d "${SHARED_ROOT}/deploy/lighthouse/w5-window.XXXXXX")"
    BACKUP_FILE="${BACKUP_DIR}/env.before"
    sudo cp -p "${ENV_FILE}" "${BACKUP_FILE}"
  fi
  _provider_off_env_is_safe "${BACKUP_FILE}"
  RESTORE_ARMED=1
}

main() {
  _derive_evidence_path
  _verify_reviewed_image
  _verify_running_backend_identity
  _assert_persistent_evidence_unused
  prepare_provider_off_backup
  configure_w5_window
  run_operator
}

main "$@"
