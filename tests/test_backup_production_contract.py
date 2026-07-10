"""Hermetic contracts for production backup and cron installation."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup_production.sh"
CRON_INSTALLER = REPO_ROOT / "scripts" / "install_backup_cron.sh"
PG_DUMP_SCRIPT = REPO_ROOT / "scripts" / "pg_dump_logical.py"
PG_RESTORE_SCRIPT = REPO_ROOT / "scripts" / "pg_restore_logical.py"
DR_RUNBOOK = REPO_ROOT / "docs" / "disaster_recovery_runbook.md"
BRAND_ASSETS_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "brand-assets-refresh.md"


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def _fake_backup_tools(tmp_path: Path) -> tuple[Path, Path]:
    dump_content = (
        '{"_table":"tenants","_data":{"id":"tenant-1"}}\n'
        '{"_table":"api_keys","_data":{"id":"key-1"}}\n'
    )
    dump_size = len(dump_content.encode())
    docker = _write_executable(
        tmp_path / "docker",
        f"""#!/usr/bin/env bash
set -euo pipefail
command_name="$1"
shift
case "$command_name" in
  cp)
    source_path="$1"
    destination_path="$2"
    if [[ "$source_path" == *":/tmp/pg_dump_"* ]]; then
      cat >"$destination_path" <<'EOF'
{dump_content}EOF
    elif [[ "$source_path" == *":/app/output/." ]]; then
      if [ "${{FAKE_DOCKER_FAIL_MEDIA:-0}}" = "1" ]; then
        exit 42
      fi
      mkdir -p "$destination_path/brand_assets"
      printf 'media-fixture' >"$destination_path/brand_assets/fixture.bin"
    fi
    ;;
  exec)
    if [[ "$*" == *" python3 "* ]]; then
      printf '%s\n' '{{"timestamp":"2026-07-10T00:00:00Z","expected_tables":["tenants","api_keys"],"tables":{{"tenants":{{"rows":1}},"api_keys":{{"rows":1}}}},"total_rows":2,"file_size":{dump_size}}}'
    fi
    ;;
  inspect)
    printf '%s\n' 'ai-video-backend:test'
    ;;
  *)
    printf 'unexpected fake docker command: %s\n' "$command_name" >&2
    exit 64
    ;;
esac
""",
    )
    flock = _write_executable(
        tmp_path / "flock",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    return docker, flock


def _backup_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    docker, flock = _fake_backup_tools(tmp_path)
    backup_root = tmp_path / "backups"
    project_root = tmp_path / "project"
    dump_script = project_root / "scripts" / "pg_dump_logical.py"
    dump_script.parent.mkdir(parents=True)
    dump_script.write_text("# fixture\n")

    env = os.environ.copy()
    fake_docker = _write_executable(tmp_path / "docker-command", "#!/usr/bin/env bash\nexit 0\n")
    env.update(
        {
            "BACKUP_ROOT": str(backup_root),
            "PROJECT_ROOT": str(project_root),
            "DOCKER_BIN": str(docker),
            "FLOCK_BIN": str(flock),
            "BACKUP_TIMESTAMP": "2026-07-10_120000",
            "RETENTION_DAYS": "15",
        }
    )
    return env, backup_root


def _age(path: Path, days: int) -> None:
    timestamp = time.time() - (days * 24 * 60 * 60)
    os.utime(path, (timestamp, timestamp))


def test_backup_publishes_only_validated_snapshot_then_applies_15_day_retention(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    backup_root.mkdir()
    expired = backup_root / "2026-06-01_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text("project: ai-video\nstatus: complete\n")
    _age(expired, 20)
    foreign_timestamp = backup_root / "2026-06-02_030000"
    foreign_timestamp.mkdir()
    _age(foreign_timestamp, 20)
    unrelated = backup_root / "reddit-voc-site-20260601-030000"
    unrelated.mkdir()
    _age(unrelated, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    completed = backup_root / "2026-07-10_120000"
    assert completed.is_dir()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()
    assert not expired.exists()
    assert foreign_timestamp.is_dir(), "retention must require an AI Video manifest marker"
    assert unrelated.is_dir(), "retention must ignore non-AI-video backup namespaces"
    assert json.loads((completed / "pg_dump_stats.json").read_text())["total_rows"] == 2
    assert (completed / "pg_dump.jsonl").read_text().count("\n") == 2
    assert (completed / "output" / "brand_assets" / "fixture.bin").is_file()
    media_manifest = json.loads((completed / "media_manifest.json").read_text())
    assert media_manifest["file_count"] == 1
    assert media_manifest["files"][0]["path"] == "brand_assets/fixture.bin"
    assert re.fullmatch(r"[0-9a-f]{64}", media_manifest["files"][0]["sha256"])
    manifest = (completed / "manifest.txt").read_text()
    assert "status: complete" in manifest
    assert "retention_days: 15" in manifest
    assert re.search(r"pg_dump_sha256: [0-9a-f]{64}\n", manifest)


def test_backup_failure_removes_partial_and_preserves_existing_backups(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["FAKE_DOCKER_FAIL_MEDIA"] = "1"
    backup_root.mkdir()
    expired = backup_root / "2026-06-01_030000"
    expired.mkdir()
    _age(expired, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 42
    assert expired.is_dir(), "retention must not run after an incomplete backup"
    assert not (backup_root / "2026-07-10_120000").exists()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()


def test_backup_rejects_zero_day_retention_before_creating_snapshot(tmp_path: Path) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["RETENTION_DAYS"] = "0"

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "RETENTION_DAYS must be a positive integer" in result.stderr
    assert not (backup_root / "2026-07-10_120000").exists()


def _fake_crontab(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    store = tmp_path / "root.crontab"
    fake_id = _write_executable(
        bin_dir / "id",
        "#!/usr/bin/env bash\n[ \"${1:-}\" = \"-u\" ] && printf '0\\n'\n",
    )
    fake_crontab = _write_executable(
        bin_dir / "crontab",
        """#!/usr/bin/env bash
set -euo pipefail
if [ "${1:-}" = "-l" ]; then
  if [ -f "${FAKE_CRONTAB_FILE:?}" ]; then
    cat "$FAKE_CRONTAB_FILE"
    exit 0
  fi
  printf 'no crontab for root\n' >&2
  exit 1
fi
cp "$1" "${FAKE_CRONTAB_FILE:?}"
""",
    )
    fake_install = _write_executable(
        bin_dir / "install",
        """#!/usr/bin/env bash
set -euo pipefail
directory_mode=0
paths=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -d) directory_mode=1; shift ;;
    -o|-g|-m) shift 2 ;;
    *) paths+=("$1"); shift ;;
  esac
done
destination="${paths[${#paths[@]}-1]}"
if [ "$directory_mode" = "1" ]; then
  mkdir -p "$destination"
else
  source_path="${paths[${#paths[@]}-2]}"
  mkdir -p "$(dirname "$destination")"
  cp "$source_path" "$destination"
fi
""",
    )
    fake_chown = _write_executable(
        bin_dir / "chown",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    return fake_id, fake_crontab, fake_install, fake_chown, store


def test_cron_installer_is_idempotent_and_preserves_unrelated_jobs(tmp_path: Path) -> None:
    _, fake_crontab, fake_install, fake_chown, store = _fake_crontab(tmp_path)
    backup_script = tmp_path / "backup_production.sh"
    backup_script.write_text("#!/usr/bin/env bash\n")
    dump_script = tmp_path / "pg_dump_logical.py"
    dump_script.write_text("# fixture\n")
    runtime_dir = tmp_path / "runtime"
    log_file = tmp_path / "hermes-backup.log"
    store.write_text(
        "15 4 * * * /usr/local/bin/unrelated-job\n"
        f"0 3 * * * {backup_script} >> /tmp/old-backup.log 2>&1\n"
    )
    fake_flock = _write_executable(tmp_path / "flock", "#!/usr/bin/env bash\nexit 0\n")
    fake_docker = _write_executable(
        tmp_path / "docker-command",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_crontab.parent}:{env['PATH']}",
            "CRONTAB_BIN": str(fake_crontab),
            "INSTALL_BIN": str(fake_install),
            "CHOWN_BIN": str(fake_chown),
            "DOCKER_BIN": str(fake_docker),
            "FLOCK_BIN": str(fake_flock),
            "FAKE_CRONTAB_FILE": str(store),
            "BACKUP_SCRIPT": str(backup_script),
            "DUMP_SCRIPT_SOURCE": str(dump_script),
            "RUNTIME_DIR": str(runtime_dir),
            "CRON_LOCK_FILE": str(tmp_path / "cron.lock"),
            "BACKUP_LOG_FILE": str(log_file),
            "RETENTION_DAYS": "15",
            "MIGRATE_LEGACY": "1",
        }
    )
    for _ in range(2):
        result = subprocess.run(
            ["bash", str(CRON_INSTALLER)],
            cwd=REPO_ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    installed = store.read_text()
    assert "15 4 * * * /usr/local/bin/unrelated-job" in installed
    assert installed.count("ai-video-production-backup") == 1
    assert installed.count(str(backup_script)) == 0
    assert f"/bin/bash {runtime_dir}/backup_production.sh" in installed
    assert f"DUMP_SCRIPT={runtime_dir}/pg_dump_logical.py" in installed
    assert (runtime_dir / "backup_production.sh").is_file()
    assert (runtime_dir / "pg_dump_logical.py").is_file()
    assert log_file.is_file()
    assert log_file.stat().st_mode & 0o777 == 0o600


def test_cron_installer_requires_explicit_legacy_migration(tmp_path: Path) -> None:
    _, fake_crontab, fake_install, fake_chown, store = _fake_crontab(tmp_path)
    backup_script = tmp_path / "backup_production.sh"
    backup_script.write_text("#!/usr/bin/env bash\n")
    dump_script = tmp_path / "pg_dump_logical.py"
    dump_script.write_text("# fixture\n")
    original = f"0 3 * * * {backup_script} >> /tmp/legacy.log 2>&1\n"
    store.write_text(original)
    fake_flock = _write_executable(tmp_path / "flock", "#!/usr/bin/env bash\nexit 0\n")
    fake_docker = _write_executable(tmp_path / "docker-command", "#!/usr/bin/env bash\nexit 0\n")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_crontab.parent}:{env['PATH']}",
            "CRONTAB_BIN": str(fake_crontab),
            "INSTALL_BIN": str(fake_install),
            "CHOWN_BIN": str(fake_chown),
            "DOCKER_BIN": str(fake_docker),
            "FLOCK_BIN": str(fake_flock),
            "FAKE_CRONTAB_FILE": str(store),
            "BACKUP_SCRIPT": str(backup_script),
            "DUMP_SCRIPT_SOURCE": str(dump_script),
            "RUNTIME_DIR": str(tmp_path / "runtime"),
            "CRON_LOCK_FILE": str(tmp_path / "cron.lock"),
            "BACKUP_LOG_FILE": str(tmp_path / "backup.log"),
        }
    )

    result = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "MIGRATE_LEGACY=1" in result.stderr
    assert store.read_text() == original


def test_backup_stats_stdout_remains_machine_readable_json() -> None:
    source = PG_DUMP_SCRIPT.read_text()
    assert 'print(f"Dumping PG to {out_path}...", file=sys.stderr)' in source
    assert "print(json.dumps(stats" in source
    for table in [
        "tenants",
        "api_keys",
        "admin_accounts",
        "admin_sessions",
        "threads",
        "pipeline_states",
        "brand_packages",
        "influencers",
        "video_metrics",
        "publish_logs",
        "error_logs",
        "audit_logs",
    ]:
        assert f'"{table}"' in source
    assert 'conn.transaction(isolation="repeatable_read", readonly=True)' in source


def test_restore_whitelists_tables_and_runs_as_one_transaction() -> None:
    source = PG_RESTORE_SCRIPT.read_text()
    assert "TABLES_TO_RESTORE" in source
    assert '"audit_logs"' in source
    assert "unknown table in backup" in source
    assert "async with conn.transaction()" in source
    assert "TRUNCATE TABLE" in source
    assert "ON CONFLICT DO NOTHING" not in source


def test_tracked_markdown_does_not_embed_production_tenant_keys() -> None:
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
    ).decode().split("\0")
    offenders = []
    pattern = re.compile(r"momcozy_mkt_[A-Za-z0-9]{16,}")
    for relative_path in tracked:
        if not relative_path.endswith(".md"):
            continue
        path = REPO_ROOT / relative_path
        if pattern.search(path.read_text(errors="replace")):
            offenders.append(relative_path)

    assert not offenders, f"tracked Markdown contains production-like tenant keys: {offenders}"


def test_disaster_recovery_commands_fail_closed_and_keep_ingress_stopped() -> None:
    runbook = DR_RUNBOOK.read_text()
    stop_ingress = runbook.index("stop nginx")
    restore_database = runbook.index("pg_restore_logical.py")
    restore_media = runbook.index('docker cp "$BACKUP_DIR/output/."')
    start_ingress = runbook.index("start nginx")

    assert stop_ingress < restore_database < restore_media < start_ingress
    assert 'test -z "$(sudo find /opt/ai-video-backups' in runbook
    assert 'hashlib.sha256()' in runbook
    assert 'media manifest file set mismatch' in runbook
    assert 'media snapshot contains a symlink' in runbook


def test_brand_asset_restore_reads_root_owned_backup_with_sudo() -> None:
    runbook = BRAND_ASSETS_RUNBOOK.read_text()
    assert "sudo find /opt/ai-video-backups" in runbook
    assert "sudo grep -Fx 'status: complete'" in runbook
