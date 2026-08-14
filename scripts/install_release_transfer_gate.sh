#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-install}"
SOURCE_ROOT="${SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_ROOT="${INSTALL_ROOT:-/usr/local/libexec/ai-video-release-transfer}"
VERSIONS_ROOT="$INSTALL_ROOT/versions"
WRAPPER_PATH="${WRAPPER_PATH:-/usr/local/sbin/ai-video-release-transfer-gate}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"
STAGING_ROOT="/var/lib/ai-video-release-transfer"
RELEASE_ROOT="/opt/ai-video"

fail() {
  printf 'ERROR: release_transfer_gate_install_failed\n' >&2
  exit 1
}

verify_regular_root_file() {
  local path=$1
  local mode=$2
  [ -f "$path" ] && [ ! -L "$path" ] || return 1
  [ "$(stat -c '%U:%G:%a' "$path")" = "root:root:$mode" ] || return 1
  [ "$(stat -c '%h' "$path")" = "1" ] || return 1
}

verify_root_directory() {
  local path=$1
  local mode=$2
  [ -d "$path" ] && [ ! -L "$path" ] || return 1
  [ "$(stat -c '%U:%G:%a' "$path")" = "root:root:$mode" ] || return 1
}

ensure_root_directory_exact() {
  local path=$1
  local mode=$2
  if [ -e "$path" ] || [ -L "$path" ]; then
    verify_root_directory "$path" "$mode" || return 1
  else
    install -d -o root -g root -m "0$mode" "$path" || return 1
  fi
  verify_root_directory "$path" "$mode"
}

acquire_install_lock() {
  local installer_path
  installer_path=$(readlink -f "$0") || fail
  exec "$PYTHON_BIN" -I - 0 0 "$INSTALL_ROOT/.install.lock" \
    "$installer_path" "$SOURCE_ROOT" "$INSTALL_ROOT" "$WRAPPER_PATH" \
    "$PYTHON_BIN" <<'PY_LOCK'
import fcntl
import os
import stat
import sys


def fail() -> None:
    print("ERROR: release_transfer_gate_install_failed", file=sys.stderr)
    raise SystemExit(1)


expected_uid = int(sys.argv[1])
expected_gid = int(sys.argv[2])
lock_path = sys.argv[3]
installer = sys.argv[4]
source_root = sys.argv[5]
install_root = sys.argv[6]
wrapper_path = sys.argv[7]
python_bin = sys.argv[8]
if not hasattr(os, "O_NOFOLLOW"):
    fail()
flags = os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
descriptor = -1
created = False
try:
    try:
        descriptor = os.open(
            lock_path,
            flags | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        created = True
    except FileExistsError:
        descriptor = os.open(lock_path, flags)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        fail()
    if created:
        os.fchown(descriptor, expected_uid, expected_gid)
        os.fchmod(descriptor, 0o600)
        info = os.fstat(descriptor)
    if (
        info.st_uid != expected_uid
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        fail()
    path_info = os.lstat(lock_path)
    if (
        not stat.S_ISREG(path_info.st_mode)
        or path_info.st_dev != info.st_dev
        or path_info.st_ino != info.st_ino
        or path_info.st_nlink != 1
    ):
        fail()
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_inheritable(descriptor, True)
    environment = {
        "AI_VIDEO_INSTALL_LOCK_FD": str(descriptor),
        "HOME": "/root",
        "INSTALL_ROOT": install_root,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHON_BIN": python_bin,
        "SOURCE_ROOT": source_root,
        "WRAPPER_PATH": wrapper_path,
    }
    os.execve(installer, [installer, "install-locked"], environment)
except (OSError, ValueError):
    fail()
finally:
    if descriptor >= 0:
        os.close(descriptor)
PY_LOCK
}

verify_inherited_install_lock() {
  local descriptor=${AI_VIDEO_INSTALL_LOCK_FD:-}
  [[ "$descriptor" =~ ^[0-9]+$ ]] || return 1
  "$PYTHON_BIN" -I - "$descriptor" "$INSTALL_ROOT/.install.lock" <<'PY'
import fcntl
import os
import stat
import sys

descriptor = int(sys.argv[1])
path = sys.argv[2]
info = os.fstat(descriptor)
path_info = os.lstat(path)
if (
    not stat.S_ISREG(info.st_mode)
    or info.st_uid != 0
    or info.st_gid != 0
    or stat.S_IMODE(info.st_mode) != 0o600
    or info.st_nlink != 1
    or path_info.st_dev != info.st_dev
    or path_info.st_ino != info.st_ino
):
    raise SystemExit(1)
fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
PY
  flock -n "$descriptor" || return 1
}

render_wrapper() {
  printf '%s\n' '#!/bin/sh' 'set -eu'
  printf '%s\n' "PYTHON_BIN='$PYTHON_BIN'"
  printf '%s\n' 'SELF=$(readlink -f "$0") || exit 126'
  printf '%s\n' 'RUNTIME_DIR=$(dirname "$SELF")'
  printf '%s\n' 'GATE="$RUNTIME_DIR/release_transfer_gate.py"'
  printf '%s\n' 'case "${1:-}" in'
  printf '%s\n' '  --staging-forward)'
  printf '%s\n' '    [ "$#" -eq 1 ] || exit 126'
  printf '%s\n' '    [ -n "${SSH_ORIGINAL_COMMAND:-}" ] || exit 126'
  printf '%s\n' '    exec sudo -n "$0" --staging-command "$SSH_ORIGINAL_COMMAND"'
  printf '%s\n' '    ;;'
  printf '%s\n' '  --staging-command)'
  printf '%s\n' '    [ "$(id -u)" -eq 0 ] || exit 126'
  printf '%s\n' '    shift'
  printf '%s\n' '    [ "$#" -eq 1 ] || exit 126'
  printf '%s\n' '    exec "$PYTHON_BIN" -I "$GATE" --role staging --command "$1"'
  printf '%s\n' '    ;;'
  printf '%s\n' '  --production)'
  printf '%s\n' '    [ "$(id -u)" -eq 0 ] || exit 126'
  printf '%s\n' '    shift'
  printf '%s\n' '    [ "$#" -eq 5 ] || exit 126'
  printf '%s\n' '    exec "$PYTHON_BIN" -I "$GATE" --role production --command "$*"'
  printf '%s\n' '    ;;'
  printf '%s\n' '  *) exit 126 ;;'
  printf '%s\n' 'esac'
}

verify_bundle() {
  local runtime=$1
  verify_root_directory "$runtime" 755 || return 1
  verify_regular_root_file "$runtime/release_transfer.py" 755 || return 1
  verify_regular_root_file "$runtime/release_transfer_gate.py" 755 || return 1
  verify_regular_root_file "$runtime/release-transfer-gate" 755 || return 1
  cmp -s "$SOURCE_ROOT/scripts/release_transfer.py" \
    "$runtime/release_transfer.py" || return 1
  cmp -s "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py" \
    "$runtime/release_transfer_gate.py" || return 1
  cmp -s "$runtime/release-transfer-gate" <(render_wrapper) || return 1
  "$PYTHON_BIN" -I - \
    "$runtime/release_transfer.py" \
    "$runtime/release_transfer_gate.py" <<'PY' >/dev/null
import ast
import pathlib
import sys

for raw_path in sys.argv[1:]:
    path = pathlib.Path(raw_path)
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
PY
  "$PYTHON_BIN" -I - \
    "$runtime/release_transfer_gate.py" \
    "$STAGING_ROOT" "$RELEASE_ROOT" <<'PY' >/dev/null
import importlib.util
import pathlib
import sys

gate_path = pathlib.Path(sys.argv[1]).resolve(strict=True)
spec = importlib.util.spec_from_file_location(
    "_ai_video_release_transfer_gate_selftest",
    gate_path,
)
if spec is None or spec.loader is None:
    raise SystemExit(1)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

module.verify_atomic_rename_compatibility(
    pathlib.Path(sys.argv[2]),
    pathlib.Path(sys.argv[3]),
)
PY
}

verify_runtime_roots() {
  local runtime=$1
  verify_root_directory "$INSTALL_ROOT" 755 || return 1
  verify_root_directory "$VERSIONS_ROOT" 755 || return 1
  verify_root_directory "$runtime" 755 || return 1
  verify_regular_root_file "$INSTALL_ROOT/.install.lock" 600 || return 1
}

verify_source_bundle_inputs() {
  verify_root_directory "$SOURCE_ROOT" 755 || return 1
  verify_root_directory "$SOURCE_ROOT/scripts" 755 || return 1
  verify_root_directory "$SOURCE_ROOT/deploy" 755 || return 1
  verify_root_directory "$SOURCE_ROOT/deploy/lighthouse" 755 || return 1
  verify_regular_root_file "$SOURCE_ROOT/scripts/release_transfer.py" 755 \
    || return 1
  verify_regular_root_file \
    "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py" 755 \
    || return 1
}

bundle_sha256() {
  {
    sha256sum "$SOURCE_ROOT/scripts/release_transfer.py" | awk '{print $1}'
    sha256sum "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py" | awk '{print $1}'
    render_wrapper | sha256sum | awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

runtime_bundle_sha256() {
  local runtime=$1
  {
    sha256sum "$runtime/release_transfer.py" | awk '{print $1}'
    sha256sum "$runtime/release_transfer_gate.py" | awk '{print $1}'
    sha256sum "$runtime/release-transfer-gate" | awk '{print $1}'
  } | sha256sum | awk '{print $1}'
}

verify_installation() {
  local expected_version=${1:-}
  [ -n "$expected_version" ] || return 1
  [ -L "$WRAPPER_PATH" ] || return 1
  local expected_runtime="$VERSIONS_ROOT/$expected_version"
  local expected_wrapper="$expected_runtime/release-transfer-gate"
  verify_runtime_roots "$expected_runtime" || return 1
  [ "$(readlink -f "$WRAPPER_PATH")" = "$expected_wrapper" ] || return 1
  verify_bundle "$expected_runtime" || return 1
  [ "$(runtime_bundle_sha256 "$expected_runtime")" = "$expected_version" ] \
    || return 1
  [ -d "$STAGING_ROOT" ] && [ ! -L "$STAGING_ROOT" ] || return 1
  [ "$(stat -c '%U:%G:%a' "$STAGING_ROOT")" = "root:root:700" ] || return 1
  [ -d "$RELEASE_ROOT" ] && [ ! -L "$RELEASE_ROOT" ] || return 1
}

atomic_replace() {
  local source=$1
  local destination=$2
  "$PYTHON_BIN" -I - "$source" "$destination" <<'PY'
import os
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
if destination.exists() and destination.is_dir() and not destination.is_symlink():
    raise SystemExit(1)
os.replace(source, destination)
PY
}

cleanup_candidate() {
  local candidate=${1:-}
  [ -n "$candidate" ] || return 0
  [ -d "$candidate" ] && [ ! -L "$candidate" ] || return 0
  find "$candidate" -mindepth 1 -maxdepth 1 -type f -links 1 -delete \
    || return 1
  rmdir "$candidate" 2>/dev/null || return 1
}

remove_install_temp_file() {
  /bin/rm -f -- "$1"
}

cleanup_install_artifacts() {
  local candidate=$1
  local pointer=$2
  local previous=$3
  local preserve_previous=${4:-0}
  local cleanup_failed=0
  cleanup_candidate "$candidate" || cleanup_failed=1
  remove_install_temp_file "$pointer" || cleanup_failed=1
  if [ "$preserve_previous" -eq 0 ]; then
    remove_install_temp_file "$previous" || cleanup_failed=1
  fi
  [ "$cleanup_failed" -eq 0 ]
}

rollback_pointer() {
  local expected_wrapper=$1
  local previous=$2
  local had_previous=$3
  if [ -L "$WRAPPER_PATH" ] \
    && [ "$(readlink -f "$WRAPPER_PATH")" = "$expected_wrapper" ]; then
    if [ "$had_previous" -eq 1 ]; then
      atomic_replace "$previous" "$WRAPPER_PATH" || return 1
    else
      "$PYTHON_BIN" -I - "$WRAPPER_PATH" "$expected_wrapper" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
expected = pathlib.Path(sys.argv[2])
if not path.is_symlink() or path.resolve(strict=True) != expected:
    raise SystemExit(1)
path.unlink()
PY
    fi
  elif [ "$had_previous" -eq 1 ]; then
    cmp -s "$previous" "$WRAPPER_PATH" || return 1
  elif [ -e "$WRAPPER_PATH" ] || [ -L "$WRAPPER_PATH" ]; then
    return 1
  fi
}

case "$ACTION" in
  install)
    [ "$(id -u)" -eq 0 ] || fail
    verify_source_bundle_inputs || fail
    command -v flock >/dev/null 2>&1 || fail
    ensure_root_directory_exact "$INSTALL_ROOT" 755 || fail
    ensure_root_directory_exact "$VERSIONS_ROOT" 755 || fail
    acquire_install_lock
    ;;
  install-locked)
    [ "$(id -u)" -eq 0 ] || fail
    command -v flock >/dev/null 2>&1 || fail
    verify_root_directory "$INSTALL_ROOT" 755 || fail
    verify_root_directory "$VERSIONS_ROOT" 755 || fail
    verify_inherited_install_lock || fail
    verify_source_bundle_inputs || fail
    RESULT_ACTION=install
    ensure_root_directory_exact "$STAGING_ROOT" 700 || fail
    version=$(bundle_sha256)
    runtime="$VERSIONS_ROOT/$version"
    candidate="$VERSIONS_ROOT/.candidate.$$.$RANDOM.$RANDOM"
    pointer="$INSTALL_ROOT/.pointer.$$.$RANDOM.$RANDOM"
    previous="$INSTALL_ROOT/.previous.$$.$RANDOM.$RANDOM"
    had_previous=0
    switch_started=0

    cleanup_install() {
      local rc=$?
      local cleanup_failed=0
      local preserve_previous=0
      trap - EXIT
      if [ "$rc" -ne 0 ] && [ "$switch_started" -eq 1 ]; then
        rollback_pointer "$runtime/release-transfer-gate" "$previous" \
          "$had_previous" || {
            cleanup_failed=1
            preserve_previous=1
          }
      fi
      cleanup_install_artifacts "$candidate" "$pointer" "$previous" \
        "$preserve_previous" \
        || cleanup_failed=1
      if [ "$cleanup_failed" -ne 0 ]; then
        printf '%s\n' 'ERROR: release_transfer_gate_install_cleanup_failed' >&2
        [ "$rc" -ne 0 ] || rc=1
      fi
      exit "$rc"
    }
    trap cleanup_install EXIT
    mkdir -m 0700 "$candidate" || fail
    install -o root -g root -m 0755 \
      "$SOURCE_ROOT/scripts/release_transfer.py" \
      "$candidate/release_transfer.py"
    install -o root -g root -m 0755 \
      "$SOURCE_ROOT/deploy/lighthouse/release_transfer_gate.py" \
      "$candidate/release_transfer_gate.py"
    render_wrapper > "$candidate/release-transfer-gate"
    chown root:root "$candidate/release-transfer-gate"
    chmod 0755 "$candidate/release-transfer-gate"
    chown root:root "$candidate"
    chmod 0755 "$candidate"
    verify_bundle "$candidate" || fail
    candidate_version=$(runtime_bundle_sha256 "$candidate")
    [ "$candidate_version" = "$version" ] || fail
    if [ -e "$runtime" ] || [ -L "$runtime" ]; then
      verify_bundle "$runtime" || fail
      cleanup_candidate "$candidate"
    else
      mv "$candidate" "$runtime"
    fi
    verify_runtime_roots "$runtime" || fail
    verify_bundle "$runtime" || fail
    [ "$(runtime_bundle_sha256 "$runtime")" = "$version" ] || fail
    if [ -e "$WRAPPER_PATH" ] || [ -L "$WRAPPER_PATH" ]; then
      [ ! -d "$WRAPPER_PATH" ] || fail
      cp -P "$WRAPPER_PATH" "$previous"
      had_previous=1
    fi
    ln -s "$runtime/release-transfer-gate" "$pointer"
    verify_runtime_roots "$runtime" || fail
    verify_bundle "$runtime" || fail
    [ "$(runtime_bundle_sha256 "$runtime")" = "$version" ] || fail
    switch_started=1
    atomic_replace "$pointer" "$WRAPPER_PATH" || fail
    verify_installation "$version" || fail
    remove_install_temp_file "$previous" || fail
    trap - EXIT
    ;;
  verify)
    [ "$(id -u)" -eq 0 ] || fail
    verify_source_bundle_inputs || fail
    version=$(bundle_sha256)
    verify_installation "$version" || fail
    ;;
  print-authorized-command)
    printf 'command="%s --staging-forward",restrict\n' "$WRAPPER_PATH"
    ;;
  *) fail ;;
esac

RESULT_ACTION=${RESULT_ACTION:-$ACTION}
if [ "$RESULT_ACTION" = install ] || [ "$RESULT_ACTION" = verify ]; then
  runtime="$VERSIONS_ROOT/$version"
  contract_sha=$(sha256sum "$runtime/release_transfer.py" | awk '{print $1}')
  gate_sha=$(sha256sum "$runtime/release_transfer_gate.py" | awk '{print $1}')
  wrapper_sha=$(sha256sum "$runtime/release-transfer-gate" | awk '{print $1}')
  printf '{"status":"passed","action":"%s","version":"%s","contract_sha256":"%s","gate_sha256":"%s","wrapper_sha256":"%s"}\n' \
    "$RESULT_ACTION" "$version" "$contract_sha" "$gate_sha" "$wrapper_sha"
else
  printf '{"status":"passed","action":"%s"}\n' "$RESULT_ACTION"
fi
