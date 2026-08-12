"""Hermetic execution tests for the production deployment state machine."""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"
RELEASE_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.release.yml"
CURRENT_SHA = "a" * 40
PREVIOUS_SHA = "b" * 40
RELEASE_COMPOSE_ENV_KEYS = frozenset(
    re.findall(r"\$\{([A-Z0-9_]+)", RELEASE_COMPOSE.read_text(encoding="utf-8"))
)


FAKE_SUDO = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys

args = sys.argv[1:]
log = pathlib.Path(os.environ["FAKE_DEPLOY_LOG"])
with log.open("a", encoding="utf-8") as stream:
    stream.write("sudo " + " ".join(args) + "\n")

# Match production sudo env_reset for the interpolation inputs derived from the
# release compose contract. The deploy script must pass each through `sudo env`.
compose_env_keys = tuple(
    key for key in os.environ["FAKE_REQUIRED_COMPOSE_ENV_KEYS"].split(",") if key
)
for key in compose_env_keys:
    os.environ.pop(key, None)

while args and args[0] == "env":
    args.pop(0)
    while args and "=" in args[0] and not args[0].startswith("/"):
        key, value = args.pop(0).split("=", 1)
        os.environ[key] = value

joined = " ".join(args)
snapshot_dir = os.environ.get("BACKUP_SCHEDULE_ROLLBACK_DIR", "")
if (
    os.environ.get("FAIL_STAGE") == "schedule_snapshot_chmod"
    and args[:2] == ["chmod", "0700"]
    and args[-1] == snapshot_dir
):
    raise SystemExit(50)
if (
    os.environ.get("FAIL_STAGE") == "schedule_snapshot_copy"
    and args[:2] == ["cp", "-a"]
    and args[-1] == f"{snapshot_dir}/runtime"
):
    raise SystemExit(51)
if (
    os.environ.get("FAIL_STAGE") == "schedule_snapshot_marker"
    and args[:1] == ["touch"]
    and args[-1] == f"{snapshot_dir}/runtime.present"
):
    raise SystemExit(52)
if (
    args[:3] == ["rm", "-rf", "--"]
    and args[-1] == os.environ.get("BACKUP_SCHEDULE_ROLLBACK_DIR")
    and os.environ.get("FAIL_STAGE") in {
        "schedule_commit",
        "schedule_commit_pointer_restore",
    }
):
    marker = pathlib.Path(os.environ["FAKE_COMMIT_FAILURE_MARKER"])
    if not marker.exists():
        marker.write_text("failed once\n", encoding="utf-8")
        raise SystemExit(48)
if "install_backup_cron.sh" in joined:
    mode = os.environ.get("MODE", "install")
    enabled = os.environ.get("CRON_ENABLED", "1")
    runtime = pathlib.Path(os.environ["BACKUP_RUNTIME_DIR"])
    crontab = pathlib.Path(os.environ["FAKE_CRONTAB_FILE"])
    expected_crontab = (
        "candidate active backup cron\n"
        if enabled == "1"
        else "candidate disabled backup cron\n"
    )
    if mode == "install":
        runtime.mkdir(parents=True, exist_ok=True)
        for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
            (runtime / name).write_text(f"candidate {name}\n", encoding="utf-8")
        crontab.write_text(expected_crontab, encoding="utf-8")
        if os.environ.get("FAIL_STAGE") == "cron_install":
            raise SystemExit(44)
        if (
            os.environ.get("FAIL_STAGE") == "schedule_activate"
            and enabled == "1"
        ):
            raise SystemExit(49)
        print("backup_runtime_verification=passed")
        raise SystemExit(0)
    if mode == "verify":
        if os.environ.get("FAIL_STAGE") == "cron_verify":
            raise SystemExit(45)
        if crontab.read_text(encoding="utf-8") != expected_crontab:
            raise SystemExit(46)
        if any(
            not (runtime / name).read_text(encoding="utf-8").startswith("candidate ")
            for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py")
        ):
            raise SystemExit(47)
        print("backup_runtime_verification=passed")
        raise SystemExit(0)
if "backup_production.sh" in joined:
    if os.environ.get("FAIL_STAGE") == "backup":
        raise SystemExit(41)
    root = pathlib.Path(os.environ["BACKUP_ROOT"])
    backup = root / "2026-07-20_120000"
    backup.mkdir(parents=True)
    (backup / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n"
        "pg_client_image: postgres@sha256:" + "c" * 64 + "\n",
        encoding="utf-8",
    )
    tables = [f"business_{index:02d}" for index in range(18)]
    (backup / "pg_dump_stats.json").write_text(
        json.dumps(
            {
                "expected_tables": tables,
                "tables": {name: {"rows": 1} for name in tables},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    raise SystemExit(0)
if "restore_backup_database.sh" in joined:
    if os.environ.get("FAIL_STAGE") == "restore":
        raise SystemExit(42)
    backup = pathlib.Path(args[-1])
    tables = [f"business_{index:02d}" for index in range(18)]
    restored_tables = (
        tables[:-1]
        if os.environ.get("FAIL_STAGE") == "backup_table_coverage"
        else tables
    )
    (backup / "restore_verified.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "table_count": len(tables),
                "actual_counts": {name: 1 for name in restored_tables},
            }
        )
        + "\n"
    )
    raise SystemExit(0)

if not args:
    raise SystemExit(0)
if args[0] in {"find", "awk", "test"}:
    raise SystemExit(subprocess.run(args, check=False).returncode)
if args[0] != "docker":
    raise SystemExit(subprocess.run(args, check=False).returncode)

docker = args[1:]
loaded = pathlib.Path(os.environ["FAKE_LOADED"])
stack = pathlib.Path(os.environ["FAKE_STACK"])
current_sha = os.environ.get("RELEASE_SOURCE_SHA", os.environ["FAKE_CURRENT_SHA"])
previous_sha = os.environ.get("FAKE_PREVIOUS_SHA", "")

if docker[:2] == ["image", "inspect"]:
    target = docker[-1]
    is_previous = bool(previous_sha and previous_sha in target)
    if not is_previous and not loaded.exists() and os.environ.get("FAKE_EXISTING_TAG") != "1":
        raise SystemExit(1)
    if "--format={{index .Config.Labels \"org.opencontainers.image.revision\"}}" in docker:
        print(previous_sha if is_previous else current_sha)
    if "--format={{index .Config.Labels \"org.opencontainers.image.version\"}}" in docker:
        if os.environ.get("FAIL_STAGE") == "image_version" and not is_previous:
            print("9.9.9")
        else:
            print(os.environ.get("APP_VERSION", "2.0.0"))
    raise SystemExit(0)
if docker[:1] == ["load"]:
    loaded.write_text("loaded\n")
    raise SystemExit(0)
if docker[:1] == ["run"]:
    if "-d" in docker:
        if any("ai_video_backup_" in item for item in docker):
            print("helper-container-id")
        else:
            print("restore-container-id")
    raise SystemExit(0)
if docker[:1] == ["rm"]:
    raise SystemExit(0)
if docker[:1] == ["exec"]:
    if "pg_isready" in docker:
        raise SystemExit(0)
    active = stack.read_text().strip() if stack.exists() else "active"
    if "ai_video_rendering" in docker:
        is_legacy_active = active != "release" and os.environ.get(
            "FAKE_ACTIVE_RENDERER_LEGACY"
        ) == "1"
        if "test" in docker and "/app/healthcheck.mjs" in docker:
            raise SystemExit(1 if is_legacy_active else 0)
        if "/app/healthcheck.mjs" in docker:
            if is_legacy_active or (
                active == "release"
                and os.environ.get("FAIL_STAGE") == "candidate_renderer_health"
            ):
                raise SystemExit(1)
            raise SystemExit(0)
        if "http://127.0.0.1:3001/health" in joined:
            if os.environ.get("FAKE_ACTIVE_RENDERER_HEALTH_FAIL") == "1":
                raise SystemExit(1)
            raise SystemExit(0)
    if os.environ.get("FAIL_STAGE") == "app_health" and active == "release" and "ai_video_backend" in docker:
        raise SystemExit(1)
    raise SystemExit(0)
if docker[:1] == ["compose"]:
    compose_path = docker[docker.index("-f") + 1]
    if compose_path == os.environ["COMPOSE_FILE"] and any(
        not os.environ.get(key) for key in compose_env_keys
    ):
        raise SystemExit(15)
    command = next((item for item in ("config", "stop", "start", "up", "run") if item in docker), "")
    if command == "run" and "--apply" in docker and os.environ.get("FAIL_STAGE") == "migration":
        raise SystemExit(43)
    if command == "up" and "backend" in docker:
        stack.write_text("release" if compose_path == os.environ["COMPOSE_FILE"] else "active")
    raise SystemExit(0)
raise SystemExit(0)
'''


FAKE_CURL = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys
stack_path = pathlib.Path(os.environ["FAKE_STACK"])
stack = stack_path.read_text().strip() if stack_path.exists() else "active"
if os.environ.get("FAIL_STAGE") == "public_health" and stack == "release":
    raise SystemExit(22)
revision = os.environ.get("RELEASE_SOURCE_SHA", os.environ["FAKE_CURRENT_SHA"])
if stack != "release" and os.environ.get("FAKE_PREVIOUS_SHA"):
    revision = os.environ["FAKE_PREVIOUS_SHA"]
if os.environ.get("FAIL_STAGE") == "public_identity" and stack == "release":
    revision = "f" * 40
print(json.dumps({
    "status":"ok",
    "version":os.environ.get("APP_VERSION", "2.0.0"),
    "source_revision":revision,
    "persistence":{"backend":"postgresql","status":"healthy","tables_verified":True},
}))
'''


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _run_deploy(
    tmp_path: Path,
    *,
    fail_stage: str = "",
    previous_release: bool = False,
    existing_tag: bool = False,
    cleanup: str = "0",
    media_sign_secret: str | None = "m" * 32,
    active_renderer_healthy: bool = True,
    existing_crontab: bool = True,
    hold_backup_lock: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str]:
    shared = tmp_path / "shared"
    (tmp_path / "backups").mkdir()
    lighthouse = shared / "deploy" / "lighthouse"
    lighthouse.mkdir(parents=True)
    (lighthouse / "docker-compose.prod.yml").write_text("services: {}\n")
    (lighthouse / "ai_video_locations.conf").write_text("# previous config\n")
    backend_env = "ENVIRONMENT=production\n"
    if media_sign_secret is not None:
        backend_env += f"MEDIA_SIGN_SECRET={media_sign_secret}\n"
    (lighthouse / ".env.prod").write_text(backend_env)
    (lighthouse / ".portal-auth.env").write_text("PORTAL_SESSION_SECRET=fixture\n")

    if previous_release:
        previous = shared / f"releases-{PREVIOUS_SHA}"
        previous_compose = previous / "deploy" / "lighthouse"
        previous_compose.mkdir(parents=True)
        (previous_compose / "docker-compose.release.yml").write_text("services: {}\n")
        (shared / "current").symlink_to(previous)

    archive = tmp_path / f"release-images-{CURRENT_SHA}.tar.gz"
    archive.write_bytes(b"reviewed-image-archive")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        f"{digest}  {archive.name}\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_executable(fake_bin / "sudo", FAKE_SUDO)
    _write_executable(fake_bin / "curl", FAKE_CURL)
    _write_executable(fake_bin / "sleep", "#!/bin/sh\nexit 0\n")
    _write_executable(
        fake_bin / "flock",
        '''#!/usr/bin/env python3
import fcntl
import subprocess
import sys

args = sys.argv[1:]
if len(args) < 3 or args[0] != "-n":
    raise SystemExit(64)
with open(args[1], "a+", encoding="utf-8") as lock:
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(1)
    raise SystemExit(subprocess.run(args[2:], check=False).returncode)
''',
    )
    _write_executable(
        fake_bin / "python3",
        f'''#!/usr/bin/env bash
set -euo pipefail
if [ "${{FAIL_STAGE:-}}" = "schedule_commit_pointer_restore" ] \
  && [ "${{1:-}}" = "-" ] \
  && [ "${{2:-}}" = "${{AI_VIDEO_SHARED_ROOT}}/current" ]; then
  exit 53
fi
exec {shlex.quote(sys.executable)} "$@"
''',
    )
    crontab_store = tmp_path / "root.crontab"
    if existing_crontab:
        crontab_store.write_text("legacy backup cron\n", encoding="utf-8")
    _write_executable(
        fake_bin / "crontab",
        """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "-l" ]; then
  if [ -f "${FAKE_CRONTAB_FILE:?}" ]; then
    cat "$FAKE_CRONTAB_FILE"
  else
    printf 'no crontab for root\n' >&2
    exit 1
  fi
elif [ "${1:-}" = "-r" ]; then
  rm -f "${FAKE_CRONTAB_FILE:?}"
else
  cp "$1" "${FAKE_CRONTAB_FILE:?}"
fi
""",
    )

    backup_runtime = tmp_path / "backup-runtime"
    backup_runtime.mkdir()
    for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
        (backup_runtime / name).write_text(f"legacy {name}\n", encoding="utf-8")

    log = tmp_path / "deploy.log"
    loaded = tmp_path / "loaded"
    stack = tmp_path / "stack"
    stack.write_text("active\n")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "AI_VIDEO_SHARED_ROOT": str(shared),
        "BACKUP_ROOT": str(tmp_path / "backups"),
        "BACKUP_FLOCK_BIN": str(fake_bin / "flock"),
        "COMPOSE_FILE": str(RELEASE_COMPOSE),
        "RELEASE_SOURCE_SHA": CURRENT_SHA,
        "RELEASE_IMAGE_ARCHIVE": str(archive),
        "ALLOW_MAINTENANCE_WINDOW": "1",
        "RUN_TOKEN_SMOKE": "0",
        "RUN_DEPLOY_SMOKE": "0",
        "CLEANUP_AFTER_DEPLOY": cleanup,
        "FAKE_DEPLOY_LOG": str(log),
        "FAKE_CURRENT_SHA": CURRENT_SHA,
        "FAKE_REQUIRED_COMPOSE_ENV_KEYS": ",".join(
            sorted(RELEASE_COMPOSE_ENV_KEYS)
        ),
        "FAKE_LOADED": str(loaded),
        "FAKE_STACK": str(stack),
        "FAKE_PREVIOUS_SHA": PREVIOUS_SHA if previous_release else "",
        "FAKE_EXISTING_TAG": "1" if existing_tag else "0",
        "FAKE_ACTIVE_RENDERER_LEGACY": "1",
        "FAKE_ACTIVE_RENDERER_HEALTH_FAIL": (
            "0" if active_renderer_healthy else "1"
        ),
        "FAKE_CRONTAB_FILE": str(crontab_store),
        "BACKUP_RUNTIME_DIR": str(backup_runtime),
        "BACKUP_SCHEDULE_ROLLBACK_DIR": str(tmp_path / "backup-schedule-rollback"),
        "FAKE_COMMIT_FAILURE_MARKER": str(tmp_path / "commit-failed-once"),
        "FAIL_STAGE": fail_stage,
    }
    lock_holder: subprocess.Popen[str] | None = None
    ready = tmp_path / "backup-lock-ready"
    if hold_backup_lock:
        lock_holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                """import fcntl, pathlib, sys, time
lock = open(sys.argv[1], 'a+', encoding='utf-8')
fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
pathlib.Path(sys.argv[2]).write_text('ready\\n', encoding='utf-8')
time.sleep(30)
""",
                str(tmp_path / "backups" / ".backup.lock"),
                str(ready),
            ],
            text=True,
        )
        for _ in range(100):
            if ready.exists():
                break
            time.sleep(0.01)
        assert ready.exists()
    try:
        result = subprocess.run(
            ["bash", str(DEPLOY_SCRIPT)],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    finally:
        if lock_holder is not None:
            lock_holder.terminate()
            lock_holder.wait(timeout=5)
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.parametrize(
    "fail_stage",
    [
        "cron_install",
        "cron_verify",
        "backup",
        "restore",
        "backup_table_coverage",
        "migration",
    ],
)
def test_preswitch_failure_restores_stopped_services_without_recreate(
    tmp_path: Path,
    fail_stage: str,
) -> None:
    result, log = _run_deploy(tmp_path, fail_stage=fail_stage)

    assert result.returncode != 0
    assert "compose -f" in log
    if fail_stage in {"cron_install", "cron_verify"}:
        assert "stop rendering backend" not in log
        assert "start rendering backend" not in log
    else:
        assert log.index("CRON_ENABLED=0") < log.index("stop rendering backend")
        assert "start rendering backend" in log
    assert "start nginx" not in log
    assert "force-recreate rendering backend frontend" not in log
    assert "portal_auth" not in log
    assert "ROLLBACK_FAILED" not in result.stderr
    assert (tmp_path / "root.crontab").read_text() == "legacy backup cron\n"
    for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
        assert (tmp_path / "backup-runtime" / name).read_text() == f"legacy {name}\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()
    if fail_stage == "backup_table_coverage":
        assert "scheduled backup table coverage differs from isolated restore" in result.stderr


@pytest.mark.parametrize("fail_stage", ["app_health", "public_health"])
@pytest.mark.parametrize("previous_release", [False, True])
def test_postswitch_failure_rolls_back_legacy_or_previous_release_without_sidecars(
    tmp_path: Path,
    fail_stage: str,
    previous_release: bool,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        fail_stage=fail_stage,
        previous_release=previous_release,
    )

    assert result.returncode != 0
    assert "up -d --no-deps --force-recreate rendering backend frontend" in log
    assert "up -d --no-deps --force-recreate nginx" not in log
    assert "portal_auth" not in log
    if fail_stage == "public_health":
        assert "docker exec ai_video_nginx nginx -s reload" in log
    if previous_release:
        assert f"releases-{PREVIOUS_SHA}/deploy/lighthouse/docker-compose.release.yml" in log
    else:
        assert "docker-compose.prod.yml" in log
    assert "ROLLBACK_FAILED" not in result.stderr
    assert "http://127.0.0.1:3001/health" in log
    assert (tmp_path / "root.crontab").read_text() == "legacy backup cron\n"
    for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
        assert (tmp_path / "backup-runtime" / name).read_text() == f"legacy {name}\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()


def test_candidate_renderer_never_uses_legacy_health_fallback(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, fail_stage="candidate_renderer_health")

    assert result.returncode != 0
    rollback_switch = log.rindex("up -d --no-deps --force-recreate rendering backend frontend")
    strict_probe = log.index("node /app/healthcheck.mjs")
    legacy_probe = log.index("http://127.0.0.1:3001/health")
    assert strict_probe < rollback_switch < legacy_probe
    assert "ROLLBACK_FAILED" not in result.stderr


def test_failed_schedule_migration_preserves_absent_root_crontab(
    tmp_path: Path,
) -> None:
    result, _ = _run_deploy(
        tmp_path,
        fail_stage="cron_install",
        existing_crontab=False,
    )

    assert result.returncode != 0
    assert not (tmp_path / "root.crontab").exists()
    assert not (tmp_path / "backup-schedule-rollback").exists()


def test_legacy_active_renderer_failure_marks_rollback_failed(tmp_path: Path) -> None:
    failed_result, failed_log = _run_deploy(
        tmp_path,
        fail_stage="app_health",
        active_renderer_healthy=False,
    )

    assert failed_result.returncode != 0
    assert "http://127.0.0.1:3001/health" in failed_log
    assert "ROLLBACK_FAILED" in failed_result.stderr
    assert "BACKUP_SCHEDULE_RESTORE_SKIPPED" in failed_result.stderr
    assert (tmp_path / "root.crontab").read_text() == "candidate disabled backup cron\n"
    assert (tmp_path / "backup-schedule-rollback").exists()


@pytest.mark.parametrize("previous_release", [False, True])
def test_schedule_commit_failure_restores_apps_schedule_and_current_pointer(
    tmp_path: Path,
    previous_release: bool,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        fail_stage="schedule_commit",
        previous_release=previous_release,
    )

    assert result.returncode != 0
    assert "unable to remove committed backup schedule rollback snapshot" in result.stderr
    assert log.count("up -d --no-deps --force-recreate rendering backend frontend") >= 2
    assert (tmp_path / "root.crontab").read_text() == "legacy backup cron\n"
    for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
        assert (tmp_path / "backup-runtime" / name).read_text() == f"legacy {name}\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()
    assert result.stderr.index(
        "Previous release pointer was restored before original backup schedule restoration."
    ) < result.stderr.index("Original backup runtime and root cron were restored.")
    current = tmp_path / "shared" / "current"
    if previous_release:
        assert current.resolve() == tmp_path / "shared" / f"releases-{PREVIOUS_SHA}"
    else:
        assert not current.exists()


@pytest.mark.parametrize("previous_release", [False, True])
def test_schedule_activation_failure_restores_apps_schedule_and_current_pointer(
    tmp_path: Path,
    previous_release: bool,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        fail_stage="schedule_activate",
        previous_release=previous_release,
    )

    assert result.returncode != 0
    assert "CRON_ENABLED=0" in log
    assert "CRON_ENABLED=1" in log
    assert log.count("up -d --no-deps --force-recreate rendering backend frontend") >= 2
    assert (tmp_path / "root.crontab").read_text() == "legacy backup cron\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()
    assert result.stderr.index(
        "Previous release pointer was restored before original backup schedule restoration."
    ) < result.stderr.index("Original backup runtime and root cron were restored.")
    current = tmp_path / "shared" / "current"
    if previous_release:
        assert current.resolve() == tmp_path / "shared" / f"releases-{PREVIOUS_SHA}"
    else:
        assert not current.exists()


def test_pointer_restore_failure_keeps_backup_schedule_disabled(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        fail_stage="schedule_commit_pointer_restore",
    )

    assert result.returncode != 0
    assert "RELEASE_POINTER_ROLLBACK_FAILED" in result.stderr
    assert "backup schedule remains disabled" in result.stderr
    assert "Original backup runtime and root cron were restored." not in result.stderr
    assert "APPLICATION_ROLLBACK_SKIPPED" in result.stderr
    assert "CRON_ENABLED=0" in log
    assert log.count("up -d --no-deps --force-recreate rendering backend frontend") == 1
    assert (tmp_path / "root.crontab").read_text() == "candidate disabled backup cron\n"
    assert (tmp_path / "backup-schedule-rollback").exists()
    assert (tmp_path / "shared" / "current").resolve() == REPO_ROOT


@pytest.mark.parametrize(
    "fail_stage",
    [
        "schedule_snapshot_chmod",
        "schedule_snapshot_copy",
        "schedule_snapshot_marker",
    ],
)
def test_partial_schedule_snapshot_failure_is_cleaned_without_mutating_schedule(
    tmp_path: Path,
    fail_stage: str,
) -> None:
    result, _ = _run_deploy(tmp_path, fail_stage=fail_stage)

    assert result.returncode != 0
    assert (tmp_path / "root.crontab").read_text() == "legacy backup cron\n"
    runtime = tmp_path / "backup-runtime"
    for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
        assert (runtime / name).read_text() == f"legacy {name}\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()


def test_existing_image_tag_fails_before_maintenance(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, existing_tag=True)

    assert result.returncode != 0
    assert "immutable release image tag already exists" in result.stderr
    assert " stop nginx" not in log


def test_running_scheduled_backup_fails_before_maintenance(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, hold_backup_lock=True)

    assert result.returncode != 0
    assert "another production backup is already running" in result.stderr
    assert "CRON_ENABLED=0" in log
    assert "stop rendering backend" not in log
    assert (tmp_path / "root.crontab").read_text() == "legacy backup cron\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()


def test_image_version_mismatch_fails_before_maintenance(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, fail_stage="image_version")

    assert result.returncode != 0
    assert "image semantic version mismatch" in result.stderr
    assert "stop rendering backend" not in log


def test_public_release_identity_mismatch_rolls_back(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, fail_stage="public_identity")

    assert result.returncode != 0
    assert "release public health or identity did not pass" in result.stderr
    assert "up -d --no-deps --force-recreate rendering backend frontend" in log


def test_cleanup_is_rejected_before_any_docker_command(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, cleanup="1")

    assert result.returncode != 0
    assert "preserves rollback images" in result.stderr
    assert log == ""


@pytest.mark.parametrize("media_sign_secret", [None, "too-short"])
def test_media_sign_secret_fails_before_image_load_or_maintenance(
    tmp_path: Path,
    media_sign_secret: str | None,
) -> None:
    result, log = _run_deploy(tmp_path, media_sign_secret=media_sign_secret)

    assert result.returncode != 0
    assert "MEDIA_SIGN_SECRET" in result.stderr
    assert "docker load" not in log
    assert "stop nginx" not in log


def test_success_uses_reviewed_backup_helper_migrates_then_restores_ingress(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(tmp_path)

    assert result.returncode == 0, result.stderr
    release_compose_command = next(
        line
        for line in log.splitlines()
        if f"docker compose -f {RELEASE_COMPOSE} config" in line
    )
    tokens = shlex.split(release_compose_command)
    env_start = tokens.index("env") + 1
    docker_start = tokens.index("docker")
    passed_env_keys = {
        token.split("=", 1)[0] for token in tokens[env_start:docker_start]
    }
    assert passed_env_keys == RELEASE_COMPOSE_ENV_KEYS
    assert f"PROJECT_ROOT={REPO_ROOT}" in log
    assert f"DUMP_SCRIPT={tmp_path}/backup-runtime/pg_dump_logical.py" in log
    assert f"BACKUP_MANIFEST_SCRIPT={tmp_path}/backup-runtime/backup_manifest.py" in log
    assert "install_backup_cron.sh" in log
    assert "MODE=install" in log
    assert "MODE=verify" in log
    assert "MIGRATE_LEGACY=1" in log
    assert "stop nginx" not in log
    assert "stop rendering backend" in log
    assert "deploy_alembic_gate.sh --apply" in log
    assert "up -d --no-deps --force-recreate rendering backend frontend" in log
    assert "up -d --no-deps --force-recreate nginx" not in log
    assert "docker exec ai_video_nginx nginx -s reload" in log
    assert log.index("stop rendering backend") < log.index("backup_production.sh")
    assert log.index("restore_backup_database.sh") < log.index(
        "deploy_alembic_gate.sh --apply"
    )
    assert log.index("deploy_alembic_gate.sh --apply") < log.index(
        "up -d --no-deps --force-recreate rendering backend frontend"
    )
    assert "portal_auth" not in log
    assert "/api/fast/generate" not in log
    assert "CRON_ENABLED=0" in log
    assert "CRON_ENABLED=1" in log
    assert f"flock -n {tmp_path}/backups/.backup.lock true" in log
    assert log.index("CRON_ENABLED=0") < log.index("stop rendering backend")
    assert (tmp_path / "root.crontab").read_text() == "candidate active backup cron\n"
    assert not (tmp_path / "backup-schedule-rollback").exists()
    assert "scheduled_backup_business_table_count=18" in result.stdout
