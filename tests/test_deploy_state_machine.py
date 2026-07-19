"""Hermetic execution tests for the production deployment state machine."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_SCRIPT = REPO_ROOT / "deploy" / "lighthouse" / "deploy.sh"
RELEASE_COMPOSE = REPO_ROOT / "deploy" / "lighthouse" / "docker-compose.release.yml"
CURRENT_SHA = "a" * 40
PREVIOUS_SHA = "b" * 40


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

while args and args[0] == "env":
    args.pop(0)
    while args and "=" in args[0] and not args[0].startswith("/"):
        key, value = args.pop(0).split("=", 1)
        os.environ[key] = value

joined = " ".join(args)
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
    raise SystemExit(0)
if "restore_backup_database.sh" in joined:
    if os.environ.get("FAIL_STAGE") == "restore":
        raise SystemExit(42)
    backup = pathlib.Path(args[-1])
    (backup / "restore_verified.json").write_text('{"status":"passed"}\n')
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
current_sha = os.environ["RELEASE_SOURCE_SHA"]
previous_sha = os.environ.get("FAKE_PREVIOUS_SHA", "")

if docker[:2] == ["image", "inspect"]:
    target = docker[-1]
    is_previous = bool(previous_sha and previous_sha in target)
    if not is_previous and not loaded.exists() and os.environ.get("FAKE_EXISTING_TAG") != "1":
        raise SystemExit(1)
    if "--format={{index .Config.Labels \"org.opencontainers.image.revision\"}}" in docker:
        print(previous_sha if is_previous else current_sha)
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
    if os.environ.get("FAIL_STAGE") == "app_health" and active == "release" and "ai_video_backend" in docker:
        raise SystemExit(1)
    raise SystemExit(0)
if docker[:1] == ["compose"]:
    compose_path = docker[docker.index("-f") + 1]
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
print(json.dumps({"status":"ok","persistence":{"backend":"postgresql","status":"healthy","tables_verified":True}}))
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

    log = tmp_path / "deploy.log"
    loaded = tmp_path / "loaded"
    stack = tmp_path / "stack"
    stack.write_text("active\n")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "AI_VIDEO_SHARED_ROOT": str(shared),
        "BACKUP_ROOT": str(tmp_path / "backups"),
        "COMPOSE_FILE": str(RELEASE_COMPOSE),
        "RELEASE_SOURCE_SHA": CURRENT_SHA,
        "RELEASE_IMAGE_ARCHIVE": str(archive),
        "ALLOW_MAINTENANCE_WINDOW": "1",
        "RUN_TOKEN_SMOKE": "0",
        "RUN_DEPLOY_SMOKE": "0",
        "CLEANUP_AFTER_DEPLOY": cleanup,
        "FAKE_DEPLOY_LOG": str(log),
        "FAKE_LOADED": str(loaded),
        "FAKE_STACK": str(stack),
        "FAKE_PREVIOUS_SHA": PREVIOUS_SHA if previous_release else "",
        "FAKE_EXISTING_TAG": "1" if existing_tag else "0",
        "FAIL_STAGE": fail_stage,
    }
    result = subprocess.run(
        ["bash", str(DEPLOY_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result, log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.mark.parametrize("fail_stage", ["backup", "restore", "migration"])
def test_preswitch_failure_restores_stopped_services_without_recreate(
    tmp_path: Path,
    fail_stage: str,
) -> None:
    result, log = _run_deploy(tmp_path, fail_stage=fail_stage)

    assert result.returncode != 0
    assert "compose -f" in log
    assert "start rendering backend" in log
    assert "start nginx" not in log
    assert "force-recreate rendering backend frontend" not in log
    assert "portal_auth" not in log


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


def test_existing_image_tag_fails_before_maintenance(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, existing_tag=True)

    assert result.returncode != 0
    assert "immutable release image tag already exists" in result.stderr
    assert " stop nginx" not in log


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
    assert f"PROJECT_ROOT={REPO_ROOT}" in log
    assert f"DUMP_SCRIPT={REPO_ROOT}/scripts/pg_dump_logical.py" in log
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
