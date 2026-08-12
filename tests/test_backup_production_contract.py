"""Hermetic contracts for production backup and cron installation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.backup_manifest import (
    build_source_manifest,
    create_backup_manifest,
    validate_backup_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = REPO_ROOT / "scripts" / "backup_production.sh"
CRON_INSTALLER = REPO_ROOT / "scripts" / "install_backup_cron.sh"
PG_DUMP_SCRIPT = REPO_ROOT / "scripts" / "pg_dump_logical.py"
PG_RESTORE_SCRIPT = REPO_ROOT / "scripts" / "pg_restore_logical.py"
RESTORE_DATABASE_SCRIPT = REPO_ROOT / "scripts" / "restore_backup_database.sh"
VERIFY_RESTORE_SCRIPT = REPO_ROOT / "scripts" / "verify_restored_database.py"
INIT_SQL = REPO_ROOT / "src" / "storage" / "migrations" / "001_init.sql"
DR_RUNBOOK = REPO_ROOT / "docs" / "disaster_recovery_runbook.md"
BRAND_ASSETS_RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "brand-assets-refresh.md"
BACKUP_MANIFEST_SCRIPT = REPO_ROOT / "scripts" / "backup_manifest.py"
GIT_SHA = "a" * 40
BACKEND_IMAGE_ID = "sha256:" + ("2" * 64)

EXPECTED_RECOVERY_TABLES = [
    "tenants",
    "admin_accounts",
    "api_keys",
    "admin_sessions",
    "threads",
    "pipeline_states",
    "brand_packages",
    "influencers",
    "video_metrics",
    "publish_logs",
    "error_logs",
    "audit_logs",
    "idempotency_records",
    "acceptance_records",
    "job_budget_accounts",
    "provider_cost_attempts",
]


def _write_executable(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(0o755)
    return path


def _fake_backup_tools(tmp_path: Path) -> tuple[Path, Path]:
    dump_content = (
        '{"_table":"tenants","_data":{"id":"tenant-1"}}\n'
        '{"_table":"api_keys","_data":{"id":"key-1"}}\n'
    )
    dump_content_with_alembic = (
        dump_content
        + '{"_table":"alembic_version","_data":{"version_num":"c8d9e0f1a2b3"}}\n'
    )
    dump_size = len(dump_content.encode())
    dump_size_with_alembic = len(dump_content_with_alembic.encode())
    schema_tables = EXPECTED_RECOVERY_TABLES
    schema_archive_tables = [*schema_tables, "alembic_version"]
    schema_listing = "".join(
        f"1; 1259 1 TABLE public {table} owner\\n"
        for table in schema_archive_tables
    )
    schema_listing_without_audit = schema_listing.replace(
        "1; 1259 1 TABLE public audit_logs owner\\n", ""
    )
    schema_listing_without_alembic = schema_listing.replace(
        "1; 1259 1 TABLE public alembic_version owner\\n", ""
    )
    schema_listing_with_extra = (
        schema_listing + "1; 1259 1 TABLE public unexpected_table owner\\n"
    )
    schema_signature = "a" * 64
    schema_signature_mismatch = "b" * 64
    alembic_revision = "c8d9e0f1a2b3"
    postgres_digest = "postgres@sha256:" + ("1" * 64)
    dump_stats = json.dumps(
        {
            "timestamp": "2026-07-10T00:00:00Z",
            "server_version_num": "180004",
            "server_major": 18,
            "schema_signature": schema_signature,
            "alembic_revision": alembic_revision,
            "expected_tables": schema_tables,
            "tables": {
                table: {"rows": 1 if table in {"tenants", "api_keys"} else 0}
                for table in schema_tables
            },
            "total_rows": 2,
            "file_size": dump_size,
        },
        separators=(",", ":"),
    )
    dump_stats_with_alembic = json.dumps(
        {
            "timestamp": "2026-07-10T00:00:00Z",
            "server_version_num": "180004",
            "server_major": 18,
            "schema_signature": schema_signature,
            "alembic_revision": alembic_revision,
            "expected_tables": [*schema_tables, "alembic_version"],
            "tables": {
                **{
                    table: {"rows": 1 if table in {"tenants", "api_keys"} else 0}
                    for table in schema_tables
                },
                "alembic_version": {"rows": 1},
            },
            "total_rows": 3,
            "file_size": dump_size_with_alembic,
        },
        separators=(",", ":"),
    )
    docker = _write_executable(
        tmp_path / "docker",
        f"""#!/usr/bin/env bash
set -euo pipefail
command_name="$1"
shift
printf '%s %s\n' "$command_name" "$*" >>"${{FAKE_DOCKER_LOG:?}}"
case "$command_name" in
  cp)
    source_path="$1"
    destination_path="$2"
    if [[ "$source_path" == *":/tmp/pg_dump_"* ]]; then
      if [ "${{FAKE_STATS_INCLUDE_ALEMBIC:-0}}" = "1" ]; then
        cat >"$destination_path" <<'EOF'
{dump_content_with_alembic}EOF
      else
        cat >"$destination_path" <<'EOF'
{dump_content}EOF
      fi
    elif [[ "$source_path" == *":/app/output/." ]]; then
      if [ "${{FAKE_DOCKER_FAIL_MEDIA:-0}}" = "1" ]; then
        exit 42
      fi
      mkdir -p "$destination_path/brand_assets"
      printf 'media-fixture' >"$destination_path/brand_assets/fixture.bin"
    fi
    ;;
  exec)
    if [[ "$*" == *"DATABASE_URL"* ]]; then
      printf '%s\n' 'postgresql://fixture:fixture@database.example/ai_video'
    elif [[ "$*" == *"--schema-signature"* ]]; then
      if [ "${{FAKE_SCHEMA_SIGNATURE_MISMATCH:-0}}" = "1" ]; then
        printf '%s\n' '{{"schema_signature":"{schema_signature_mismatch}","alembic_revision":"{alembic_revision}"}}'
      else
        printf '%s\n' '{{"schema_signature":"{schema_signature}","alembic_revision":"{alembic_revision}"}}'
      fi
    elif [[ "$*" == *" python3 "* ]]; then
      if [ "${{FAKE_STATS_INCLUDE_ALEMBIC:-0}}" = "1" ]; then
        printf '%s\n' '{dump_stats_with_alembic}'
      else
        printf '%s\n' '{dump_stats}'
      fi
    fi
    ;;
  image)
    [ "$1" = "inspect" ]
    if [[ "$*" == *"org.opencontainers.image.revision"* ]]; then
      printf '%s\n' '{GIT_SHA}'
    elif [[ "$*" == *".RepoDigests"* && "$*" == *"sha256:{'2' * 64}"* ]]; then
      printf '\n'
    elif [[ "$*" == *"--format="* ]]; then
      printf '%s\n' '{postgres_digest}'
    fi
    ;;
  run)
    if [[ "$*" == *"pg_dump --schema-only"* ]]; then
      cat >/dev/null
      printf '%s' 'fixture-schema-archive'
    elif [[ "$*" == *"pg_dump --version"* ]]; then
      printf '%s\n' 'pg_dump (PostgreSQL) 18.4'
    elif [[ "$*" == *"pg_restore --list"* ]]; then
      cat >/dev/null
      if [ "${{FAKE_SCHEMA_MISSING_TABLE:-0}}" = "1" ]; then
        printf '%b' '{schema_listing_without_audit}'
      elif [ "${{FAKE_SCHEMA_MISSING_ALEMBIC:-0}}" = "1" ]; then
        printf '%b' '{schema_listing_without_alembic}'
      elif [ "${{FAKE_SCHEMA_EXTRA_TABLE:-0}}" = "1" ]; then
        printf '%b' '{schema_listing_with_extra}'
      else
        printf '%b' '{schema_listing}'
      fi
    else
      printf 'unexpected fake docker run command: %s\n' "$*" >&2
      exit 65
    fi
    ;;
  inspect)
    if [[ "$*" == *"{{.Config.Image}}"* ]]; then
      printf '%s\n' 'ai-video-backend:{GIT_SHA}'
    elif [[ "$*" == *"{{.Image}}"* ]]; then
      printf '%s\n' '{BACKEND_IMAGE_ID}'
    else
      exit 65
    fi
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
    source_manifest = build_source_manifest(
        project_root,
        GIT_SHA,
        ["scripts/pg_dump_logical.py"],
    )
    (project_root / "source-manifest.v1.json").write_text(
        json.dumps(source_manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )

    env = os.environ.copy()
    docker_log = tmp_path / "docker.log"
    docker_log.write_text("")
    env.update(
        {
            "BACKUP_ROOT": str(backup_root),
            "PROJECT_ROOT": str(project_root),
            "DOCKER_BIN": str(docker),
            "FLOCK_BIN": str(flock),
            "BACKUP_MANIFEST_SCRIPT": str(BACKUP_MANIFEST_SCRIPT),
            "BACKUP_TIMESTAMP": "2026-07-10_120000",
            "RETENTION_DAYS": "15",
            "FAKE_DOCKER_LOG": str(docker_log),
        }
    )
    return env, backup_root


def _age(path: Path, days: int) -> None:
    timestamp = time.time() - (days * 24 * 60 * 60)
    os.utime(path, (timestamp, timestamp))


def _age_seconds(path: Path, seconds: int) -> None:
    timestamp = time.time() - seconds
    os.utime(path, (timestamp, timestamp))


def _write_canonical_restore_marker(
    backup_dir: Path,
    *,
    detached_digest: str | None = None,
) -> None:
    canonical_manifest = backup_dir / "backup-manifest.v1.json"
    canonical_manifest.write_text(
        '{"schema_version":"backup-manifest.v1"}\n',
        encoding="utf-8",
    )
    digest = hashlib.sha256(canonical_manifest.read_bytes()).hexdigest()
    (backup_dir / "backup-manifest.v1.json.sha256").write_text(
        f"{detached_digest or digest}  backup-manifest.v1.json\n",
        encoding="utf-8",
    )
    (backup_dir / "restore_verified.json").write_text(
        json.dumps({"status": "passed", "manifest_sha256": digest}) + "\n",
        encoding="utf-8",
    )


def test_backup_publishes_only_validated_snapshot_then_applies_15_day_retention(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    backup_root.mkdir()
    expired = backup_root / "2026-06-01_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text("project: ai-video\nstatus: complete\n")
    (expired / "restore_verified.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "manifest_sha256": hashlib.sha256(
                    (expired / "manifest.txt").read_bytes()
                ).hexdigest(),
            }
        )
        + "\n"
    )
    _age(expired, 20)
    unverified_expired = backup_root / "2026-05-31_030000"
    unverified_expired.mkdir()
    (unverified_expired / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n"
    )
    _age(unverified_expired, 20)
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
    assert expired.is_dir(), "the latest restore-verified recovery point must be retained"
    assert not unverified_expired.exists()
    assert foreign_timestamp.is_dir(), "retention must require an AI Video manifest marker"
    assert unrelated.is_dir(), "retention must ignore non-AI-video backup namespaces"
    assert json.loads((completed / "pg_dump_stats.json").read_text())["total_rows"] == 2
    assert (completed / "pg_dump.jsonl").read_text().count("\n") == 2
    assert (completed / "pg_schema.dump").read_text() == "fixture-schema-archive"
    assert "TABLE public audit_logs" in (completed / "pg_schema.list").read_text()
    assert "TABLE public alembic_version" in (
        completed / "pg_schema.list"
    ).read_text()
    assert json.loads((completed / "pg_schema_signature_after.json").read_text()) == {
        "schema_signature": "a" * 64,
        "alembic_revision": "c8d9e0f1a2b3",
    }
    assert (completed / "output" / "brand_assets" / "fixture.bin").is_file()
    media_manifest = json.loads((completed / "media_manifest.json").read_text())
    assert media_manifest["file_count"] == 1
    assert media_manifest["files"][0]["path"] == "brand_assets/fixture.bin"
    assert re.fullmatch(r"[0-9a-f]{64}", media_manifest["files"][0]["sha256"])
    canonical_manifest = validate_backup_manifest(completed)
    canonical_typed = cast(dict[str, Any], canonical_manifest)
    assert canonical_manifest["schema_version"] == "backup-manifest.v1"
    assert canonical_manifest["git_sha"] == GIT_SHA
    assert canonical_typed["backend_image"]["image_id"] == BACKEND_IMAGE_ID
    assert (completed / "backup-manifest.v1.json.sha256").is_file()
    manifest = (completed / "manifest.txt").read_text()
    assert "status: complete" in manifest
    assert "retention_days: 15" in manifest
    assert re.search(r"pg_dump_sha256: [0-9a-f]{64}\n", manifest)
    assert re.search(r"pg_schema_sha256: [0-9a-f]{64}\n", manifest)
    assert re.search(r"pg_schema_list_sha256: [0-9a-f]{64}\n", manifest)
    manifest_fields = dict(
        line.split(": ", 1)
        for line in manifest.splitlines()
        if ": " in line
    )
    assert manifest_fields["pg_dump_sha256"] == hashlib.sha256(
        (completed / "pg_dump.jsonl").read_bytes()
    ).hexdigest()
    assert manifest_fields["pg_dump_stats_sha256"] == hashlib.sha256(
        (completed / "pg_dump_stats.json").read_bytes()
    ).hexdigest()
    assert manifest_fields["pg_schema_sha256"] == hashlib.sha256(
        (completed / "pg_schema.dump").read_bytes()
    ).hexdigest()
    assert manifest_fields["pg_schema_list_sha256"] == hashlib.sha256(
        (completed / "pg_schema.list").read_bytes()
    ).hexdigest()
    assert manifest_fields["pg_schema_signature_after_sha256"] == hashlib.sha256(
        (completed / "pg_schema_signature_after.json").read_bytes()
    ).hexdigest()
    assert "pg_server_major: 18" in manifest
    assert "pg_client_source_tag: postgres:18" in manifest
    assert f"pg_client_image: postgres@sha256:{'1' * 64}" in manifest
    assert f"pg_schema_signature: {'a' * 64}" in manifest
    assert "alembic_revision: c8d9e0f1a2b3" in manifest
    docker_log = Path(env["FAKE_DOCKER_LOG"]).read_text()
    assert "postgresql://" not in docker_log
    assert "--dbname=" not in docker_log


def test_backup_retention_rejects_canonical_marker_with_bad_detached_checksum(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    backup_root.mkdir()
    invalid_verified = backup_root / "2026-05-30_030000"
    invalid_verified.mkdir()
    (invalid_verified / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _write_canonical_restore_marker(
        invalid_verified,
        detached_digest="0" * 64,
    )
    _age(invalid_verified, 20)
    downgrade_attempt = backup_root / "2026-05-30_040000"
    downgrade_attempt.mkdir()
    downgrade_legacy = downgrade_attempt / "manifest.txt"
    downgrade_legacy.write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    (downgrade_attempt / "backup-manifest.v1.json").symlink_to("manifest.txt")
    (downgrade_attempt / "restore_verified.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "manifest_sha256": hashlib.sha256(
                    downgrade_legacy.read_bytes()
                ).hexdigest(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    _age(downgrade_attempt, 20)
    malformed_marker = backup_root / "2026-05-30_050000"
    malformed_marker.mkdir()
    (malformed_marker / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    (malformed_marker / "restore_verified.json").write_text("[]\n", encoding="utf-8")
    _age(malformed_marker, 20)
    expired = backup_root / "2026-05-31_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _age(expired, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert invalid_verified.is_dir()
    assert downgrade_attempt.is_dir()
    assert malformed_marker.is_dir()
    assert expired.is_dir(), "invalid canonical evidence must block retention deletion"
    assert "no restore-verified recovery point" in result.stdout


def test_backup_retention_uses_exact_72_hour_minute_boundary(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["RETENTION_DAYS"] = "3"
    backup_root.mkdir()
    verified = backup_root / "2026-05-30_030000"
    verified.mkdir()
    (verified / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _write_canonical_restore_marker(verified)
    _age(verified, 20)
    outside_boundary = backup_root / "2026-05-31_030000"
    outside_boundary.mkdir()
    (outside_boundary / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _age_seconds(outside_boundary, (3 * 24 * 60 * 60) + 300)
    inside_boundary = backup_root / "2026-06-01_030000"
    inside_boundary.mkdir()
    (inside_boundary / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _age_seconds(inside_boundary, (3 * 24 * 60 * 60) - 300)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert verified.is_dir()
    assert not outside_boundary.exists()
    assert inside_boundary.is_dir()


def test_backup_reports_failure_and_preserves_backups_when_retention_discovery_fails(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    backup_root.mkdir()
    expired = backup_root / "2026-05-31_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _age(expired, 20)
    failing_manifest = tmp_path / "failing_backup_manifest.py"
    failing_manifest.write_text(
        "\n".join(
            [
                "import os",
                "import sys",
                "",
                "if len(sys.argv) > 1 and sys.argv[1] == 'list-expired':",
                "    raise SystemExit(42)",
                "os.execv(",
                "    sys.executable,",
                f"    [sys.executable, {str(BACKUP_MANIFEST_SCRIPT)!r}, *sys.argv[1:]],",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env["BACKUP_MANIFEST_SCRIPT"] = str(failing_manifest)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "retention candidate discovery failed" in result.stderr
    assert "Backup Complete" not in result.stdout
    assert expired.is_dir()
    assert (backup_root / "2026-07-10_120000").is_dir()
    assert not list(backup_root.glob(".retention-expired.*"))


def test_backup_rejects_schema_archive_missing_a_required_table(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["FAKE_SCHEMA_MISSING_TABLE"] = "1"
    backup_root.mkdir()
    expired = backup_root / "2026-06-01_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text("project: ai-video\nstatus: complete\n")
    _age(expired, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "schema archive table set does not match business tables plus migration metadata"
        in result.stderr
    )
    assert expired.is_dir(), "retention must not run after schema validation fails"
    assert not (backup_root / "2026-07-10_120000").exists()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()
    assert ":/app/output/." not in Path(env["FAKE_DOCKER_LOG"]).read_text()


@pytest.mark.parametrize(
    "flag",
    ["FAKE_SCHEMA_MISSING_ALEMBIC", "FAKE_SCHEMA_EXTRA_TABLE"],
)
def test_backup_rejects_schema_archive_metadata_or_extra_table_drift(
    tmp_path: Path,
    flag: str,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env[flag] = "1"

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "schema archive table set does not match business tables plus migration metadata"
        in result.stderr
    )
    assert not (backup_root / "2026-07-10_120000").exists()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()
    assert ":/app/output/." not in Path(env["FAKE_DOCKER_LOG"]).read_text()


def test_backup_rejects_schema_metadata_in_business_stats_before_media_copy(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["FAKE_STATS_INCLUDE_ALEMBIC"] = "1"

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "backup stats must exclude schema metadata tables" in result.stderr
    assert not (backup_root / "2026-07-10_120000").exists()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()
    assert ":/app/output/." not in Path(env["FAKE_DOCKER_LOG"]).read_text()


def test_backup_rejects_postgres_client_image_with_wrong_major(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["PG_CLIENT_IMAGE"] = "postgres:16"

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "must match PostgreSQL server major 18" in result.stderr
    assert not (backup_root / "2026-07-10_120000").exists()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()


def test_backup_rejects_schema_signature_drift_before_retention(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["FAKE_SCHEMA_SIGNATURE_MISMATCH"] = "1"
    backup_root.mkdir()
    expired = backup_root / "2026-06-01_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text("project: ai-video\nstatus: complete\n")
    _age(expired, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "schema changed during backup" in result.stderr
    assert expired.is_dir()
    assert not (backup_root / "2026-07-10_120000").exists()
    assert not (backup_root / ".2026-07-10_120000.partial").exists()


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
    assert "RETENTION_DAYS must be a canonical decimal integer" in result.stderr
    assert not (backup_root / "2026-07-10_120000").exists()
    assert Path(env["FAKE_DOCKER_LOG"]).read_text() == ""


@pytest.mark.parametrize(
    "retention_days",
    ["09", "3651", "9223372036854775807"],
)
def test_backup_rejects_noncanonical_or_unbounded_retention_without_deletion(
    tmp_path: Path,
    retention_days: str,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    env["RETENTION_DAYS"] = retention_days
    backup_root.mkdir()
    verified = backup_root / "2026-05-30_030000"
    verified.mkdir()
    (verified / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _write_canonical_restore_marker(verified)
    _age(verified, 20)
    expired = backup_root / "2026-05-31_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text(
        "project: ai-video\nstatus: complete\n",
        encoding="utf-8",
    )
    _age(expired, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "RETENTION_DAYS must be a canonical decimal integer" in result.stderr
    assert verified.is_dir()
    assert expired.is_dir()
    assert not (backup_root / "2026-07-10_120000").exists()
    assert Path(env["FAKE_DOCKER_LOG"]).read_text() == ""


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
mode=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -d) directory_mode=1; shift ;;
    -m) mode="$2"; shift 2 ;;
    -o|-g) shift 2 ;;
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
[ -z "$mode" ] || chmod "$mode" "$destination"
""",
    )
    fake_chown = _write_executable(
        bin_dir / "chown",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    return fake_id, fake_crontab, fake_install, fake_chown, store


def _fake_root_stat(tmp_path: Path) -> Path:
    return _write_executable(
        tmp_path / "stat-command",
        """#!/usr/bin/env bash
set -euo pipefail
format="${2:?}"
path="${3:?}"
python3 - "$format" "$path" <<'PY'
import os
import stat
import sys

format_string, path = sys.argv[1:]
metadata = os.lstat(path)
if format_string == "%u":
    print(os.environ.get("FAKE_STAT_UID", "0"))
elif format_string == "%g":
    print(os.environ.get("FAKE_STAT_GID", "0"))
elif format_string in {"%a", "%Lp"}:
    print(f"{stat.S_IMODE(metadata.st_mode):o}")
else:
    raise SystemExit(f"unsupported fake stat format: {format_string}")
PY
""",
    )


def test_cron_installer_is_idempotent_and_preserves_unrelated_jobs(tmp_path: Path) -> None:
    _, fake_crontab, fake_install, fake_chown, store = _fake_crontab(tmp_path)
    current_release = tmp_path / "current"
    scripts_dir = current_release / "scripts"
    scripts_dir.mkdir(parents=True)
    backup_script = scripts_dir / "backup_production.sh"
    backup_script.write_text("#!/usr/bin/env bash\n")
    dump_script = scripts_dir / "pg_dump_logical.py"
    dump_script.write_text("# fixture\n")
    manifest_script = scripts_dir / "backup_manifest.py"
    manifest_script.write_text("# fixture\n")
    (current_release / "source-manifest.v1.json").write_text("{}\n")
    runtime_dir = tmp_path / "runtime"
    log_file = tmp_path / "hermes-backup.log"
    store.write_text(
        "15 4 * * * /usr/local/bin/unrelated-job\n"
        f"0 3 * * * {backup_script} >> /tmp/old-backup.log 2>&1\n"
        "0 2 * * * /bin/bash /opt/ai-video/scripts/backup_production.sh "
        ">> /tmp/old-shared-backup.log 2>&1\n"
        "30 2 * * * /bin/bash /opt/ai-video/current/scripts/backup_production.sh "
        ">> /tmp/old-current-backup.log 2>&1\n"
        f"0 1 * * * /bin/bash {runtime_dir}/backup_production.sh "
        ">> /tmp/old-runtime-backup.log 2>&1\n"
    )
    fake_flock = _write_executable(tmp_path / "flock", "#!/usr/bin/env bash\nexit 0\n")
    fake_docker = _write_executable(
        tmp_path / "docker-command",
        "#!/usr/bin/env bash\nexit 0\n",
    )
    fake_stat = _fake_root_stat(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_crontab.parent}:{env['PATH']}",
            "CRONTAB_BIN": str(fake_crontab),
            "INSTALL_BIN": str(fake_install),
            "CHOWN_BIN": str(fake_chown),
            "DOCKER_BIN": str(fake_docker),
            "FLOCK_BIN": str(fake_flock),
            "STAT_BIN": str(fake_stat),
            "FAKE_CRONTAB_FILE": str(store),
            "CURRENT_RELEASE_ROOT": str(current_release),
            "RUNTIME_DIR": str(runtime_dir),
            "CRON_LOCK_FILE": str(tmp_path / "cron.lock"),
            "BACKUP_LOG_FILE": str(log_file),
            "RETENTION_DAYS": "15",
            "MIGRATE_LEGACY": "1",
            "CRON_ENABLED": "1",
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
    assert "/opt/ai-video/scripts/backup_production.sh" not in installed
    assert "/opt/ai-video/current/scripts/backup_production.sh" not in installed
    assert installed.count(f"/bin/bash {runtime_dir}/backup_production.sh") == 1
    assert f"/bin/bash {runtime_dir}/backup_production.sh" in installed
    assert f"DUMP_SCRIPT={runtime_dir}/pg_dump_logical.py" in installed
    assert f"BACKUP_MANIFEST_SCRIPT={runtime_dir}/backup_manifest.py" in installed
    assert f"PROJECT_ROOT={current_release}" in installed
    assert f"SOURCE_MANIFEST_PATH={current_release}/source-manifest.v1.json" in installed
    assert not installed.startswith("# ai-video-production-backup-disabled")
    assert (runtime_dir / "backup_production.sh").is_file()
    assert (runtime_dir / "pg_dump_logical.py").is_file()
    assert (runtime_dir / "backup_manifest.py").is_file()
    assert (runtime_dir / "backup_production.sh").stat().st_mode & 0o777 == 0o755
    assert (runtime_dir / "pg_dump_logical.py").stat().st_mode & 0o777 == 0o644
    assert (runtime_dir / "backup_manifest.py").stat().st_mode & 0o777 == 0o644
    assert log_file.is_file()
    assert log_file.stat().st_mode & 0o777 == 0o600

    env["MODE"] = "verify"
    verified = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified.returncode == 0, verified.stderr
    assert "backup_runtime_verification=passed" in verified.stdout

    managed_crontab = store.read_text()
    store.write_text(
        managed_crontab
        + "0 2 * * * /bin/bash /opt/ai-video/scripts/backup_production.sh "
        ">> /tmp/old-shared-backup.log 2>&1\n"
    )
    unmanaged_before_verify = store.read_text()
    rejected_unmanaged = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_unmanaged.returncode != 0
    assert "unmanaged backup cron verification failed" in rejected_unmanaged.stderr
    assert store.read_text() == unmanaged_before_verify
    store.write_text(managed_crontab)

    drifted_runtime = runtime_dir / "backup_production.sh"
    drifted_runtime.write_text("#!/usr/bin/env bash\n# drift\n")
    crontab_before_verify = store.read_text()
    rejected = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode != 0
    assert "installed backup runtime differs from reviewed source" in rejected.stderr
    assert drifted_runtime.read_text() == "#!/usr/bin/env bash\n# drift\n"
    assert store.read_text() == crontab_before_verify

    drifted_runtime.write_text(backup_script.read_text())
    store.write_text(
        store.read_text().replace("RETENTION_DAYS=15", "RETENTION_DAYS=14")
    )
    cron_before_verify = store.read_text()
    rejected_cron = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_cron.returncode != 0
    assert "installed backup cron differs from expected" in rejected_cron.stderr
    assert store.read_text() == cron_before_verify

    store.write_text(store.read_text().replace("RETENTION_DAYS=14", "RETENTION_DAYS=15"))
    runtime_dump = runtime_dir / "pg_dump_logical.py"
    runtime_dump.chmod(0o666)
    store_before_metadata_verify = store.read_text()
    log_before_metadata_verify = log_file.read_bytes()
    lock_before_metadata_verify = (tmp_path / "cron.lock").read_bytes()
    rejected_mode = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_mode.returncode != 0
    assert "installed backup runtime metadata differs from expected" in rejected_mode.stderr
    assert runtime_dump.stat().st_mode & 0o777 == 0o666
    assert store.read_text() == store_before_metadata_verify
    assert log_file.read_bytes() == log_before_metadata_verify
    assert (tmp_path / "cron.lock").read_bytes() == lock_before_metadata_verify

    runtime_dump.chmod(0o644)
    env["FAKE_STAT_UID"] = "501"
    rejected_owner = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_owner.returncode != 0
    assert "installed backup runtime metadata differs from expected" in rejected_owner.stderr
    env.pop("FAKE_STAT_UID")

    runtime_manifest = runtime_dir / "backup_manifest.py"
    runtime_manifest.unlink()
    runtime_manifest.symlink_to(manifest_script)
    rejected_symlink = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert rejected_symlink.returncode != 0
    assert "installed backup runtime metadata differs from expected" in rejected_symlink.stderr
    assert runtime_manifest.is_symlink()
    assert store.read_text() == store_before_metadata_verify
    assert log_file.read_bytes() == log_before_metadata_verify
    assert (tmp_path / "cron.lock").read_bytes() == lock_before_metadata_verify


def test_cron_installer_stages_disabled_schedule_before_explicit_activation(
    tmp_path: Path,
) -> None:
    _, fake_crontab, fake_install, fake_chown, store = _fake_crontab(tmp_path)
    current_release = tmp_path / "current"
    scripts_dir = current_release / "scripts"
    scripts_dir.mkdir(parents=True)
    for name in ("backup_production.sh", "pg_dump_logical.py", "backup_manifest.py"):
        (scripts_dir / name).write_text(f"# {name}\n")
    (current_release / "source-manifest.v1.json").write_text("{}\n")
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
            "STAT_BIN": str(_fake_root_stat(tmp_path)),
            "FAKE_CRONTAB_FILE": str(store),
            "CURRENT_RELEASE_ROOT": str(current_release),
            "RUNTIME_DIR": str(tmp_path / "runtime"),
            "CRON_LOCK_FILE": str(tmp_path / "cron.lock"),
            "BACKUP_LOG_FILE": str(tmp_path / "backup.log"),
            "CRON_ENABLED": "0",
        }
    )

    staged = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert staged.returncode == 0, staged.stderr
    assert store.read_text().startswith("# ai-video-production-backup-disabled ")
    assert "ai-video-production-backup" in store.read_text()

    env["MODE"] = "verify"
    verified_disabled = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verified_disabled.returncode == 0, verified_disabled.stderr

    env.update({"MODE": "install", "CRON_ENABLED": "1"})
    activated = subprocess.run(
        ["bash", str(CRON_INSTALLER)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert activated.returncode == 0, activated.stderr
    assert store.read_text().startswith("0 3 * * * umask 077; ")
    assert "PROJECT_ROOT=" + str(current_release) in store.read_text()


def test_cron_installer_requires_explicit_legacy_migration(tmp_path: Path) -> None:
    _, fake_crontab, fake_install, fake_chown, store = _fake_crontab(tmp_path)
    backup_script = tmp_path / "backup_production.sh"
    backup_script.write_text("#!/usr/bin/env bash\n")
    dump_script = tmp_path / "pg_dump_logical.py"
    dump_script.write_text("# fixture\n")
    manifest_script = tmp_path / "backup_manifest.py"
    manifest_script.write_text("# fixture\n")
    current_release = tmp_path / "current"
    current_release.mkdir()
    (current_release / "source-manifest.v1.json").write_text("{}\n")
    original = (
        "0 3 * * * /bin/bash /opt/ai-video/scripts/backup_production.sh "
        ">> /tmp/legacy.log 2>&1\n"
    )
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
            "MANIFEST_SCRIPT_SOURCE": str(manifest_script),
            "CURRENT_RELEASE_ROOT": str(current_release),
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


@pytest.mark.parametrize(
    "retention_days",
    ["09", "3651", "9223372036854775807"],
)
def test_cron_installer_rejects_noncanonical_or_unbounded_retention_without_mutation(
    tmp_path: Path,
    retention_days: str,
) -> None:
    _, fake_crontab, _, _, store = _fake_crontab(tmp_path)
    original = "15 4 * * * /usr/local/bin/unrelated-job\n"
    store.write_text(original)
    env = os.environ.copy()
    env.update(
        {
            "CRONTAB_BIN": str(fake_crontab),
            "FAKE_CRONTAB_FILE": str(store),
            "RETENTION_DAYS": retention_days,
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
    assert "RETENTION_DAYS must be a canonical decimal integer" in result.stderr
    assert store.read_text() == original
    assert not (tmp_path / "runtime").exists()
    assert not (tmp_path / "backup.log").exists()
    assert not (tmp_path / "cron.lock").exists()


def test_backup_stats_stdout_remains_machine_readable_json() -> None:
    source = PG_DUMP_SCRIPT.read_text()
    assert 'print(f"Dumping PG to {out_path}...", file=sys.stderr)' in source
    assert "print(json.dumps(stats" in source
    assert "information_schema.tables" in source
    assert "table_name <> 'alembic_version'" in source
    assert "foreign-key cycle" in source
    assert 'conn.transaction(isolation="repeatable_read", readonly=True)' in source


def test_backup_runtime_defaults_match_exact_72_hour_policy() -> None:
    backup_source = BACKUP_SCRIPT.read_text()
    installer_source = CRON_INSTALLER.read_text()
    runbook = DR_RUNBOOK.read_text()

    assert 'RETENTION_DAYS="${RETENTION_DAYS:-3}"' in backup_source
    assert 'RETENTION_DAYS="${RETENTION_DAYS:-3}"' in installer_source
    assert "MAX_RETENTION_DAYS=3650" in backup_source
    assert "MAX_RETENTION_DAYS=3650" in installer_source
    assert "list-expired" in backup_source
    assert "--retention-seconds" in backup_source
    assert "-mmin" not in backup_source
    assert (
        'BACKUP_SCRIPT="${BACKUP_SCRIPT:-${CURRENT_RELEASE_ROOT}/scripts/'
        'backup_production.sh}"'
    ) in installer_source
    assert (
        installer_source.index('CURRENT_RELEASE_ROOT="${CURRENT_RELEASE_ROOT:-')
        < installer_source.index('BACKUP_SCRIPT="${BACKUP_SCRIPT:-')
    )
    assert "默认 3 天" in runbook


def test_logical_recovery_uses_dynamic_current_schema_contract() -> None:
    dump_source = PG_DUMP_SCRIPT.read_text()
    restore_source = PG_RESTORE_SCRIPT.read_text()
    verify_source = VERIFY_RESTORE_SCRIPT.read_text()

    assert "information_schema.tables" in dump_source
    assert "information_schema.tables" in restore_source
    assert 'stats.get("expected_tables")' in verify_source
    assert "TABLES_TO_DUMP" not in dump_source
    assert "TABLES_TO_RESTORE" not in restore_source
    assert "TABLES_TO_VERIFY" not in verify_source


def test_publish_log_recovery_schema_preserves_w123_attempt_columns() -> None:
    source = INIT_SQL.read_text(encoding="utf-8")
    publish_logs = source.split(
        "CREATE TABLE IF NOT EXISTS publish_logs (",
        1,
    )[1].split(");", 1)[0]

    assert "tenant_id VARCHAR(64)" in publish_logs
    assert "acceptance_id VARCHAR(36)" in publish_logs
    assert "updated_at TIMESTAMPTZ" in publish_logs
    assert "ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS tenant_id" in source
    assert "ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS acceptance_id" in source
    assert "ALTER TABLE publish_logs ADD COLUMN IF NOT EXISTS updated_at" in source
    restore_source = RESTORE_DATABASE_SCRIPT.read_text(encoding="utf-8")
    assert "pg_restore" in restore_source
    assert "--schema-only" in restore_source


def test_restore_whitelists_tables_and_runs_as_one_transaction() -> None:
    source = PG_RESTORE_SCRIPT.read_text()
    assert "information_schema.tables" in source
    assert "restore target table set does not match backup stats" in source
    assert 'if "--stats" not in args' in source
    assert "invalid database identifier in backup" in source
    assert "async with conn.transaction()" in source
    assert "TRUNCATE TABLE" in source
    assert "ON CONFLICT DO NOTHING" not in source


def _write_restore_backup_fixture(tmp_path: Path) -> tuple[Path, str]:
    backup_dir = tmp_path / "2026-07-10_120000"
    backup_dir.mkdir()
    dump = backup_dir / "pg_dump.jsonl"
    stats = backup_dir / "pg_dump_stats.json"
    schema = backup_dir / "pg_schema.dump"
    schema_list = backup_dir / "pg_schema.list"
    schema_after = backup_dir / "pg_schema_signature_after.json"
    dump.write_text('{"_table":"tenants","_data":{"id":"tenant-1"}}\n')
    stats.write_text(
        json.dumps(
            {
                "server_version_num": "180004",
                "server_major": 18,
                "total_rows": 1,
                "file_size": dump.stat().st_size,
                "expected_tables": ["tenants"],
                "tables": {"tenants": {"rows": 1}},
                "schema_signature": "a" * 64,
                "alembic_revision": "c8d9e0f1a2b3",
            }
        )
        + "\n"
    )
    schema.write_text("fixture-schema-archive")
    schema_list.write_text(
        "1; 1259 1 TABLE public tenants owner\n"
        "2; 1259 2 TABLE public alembic_version owner\n"
    )
    schema_after.write_text(
        json.dumps(
            {
                "schema_signature": "a" * 64,
                "alembic_revision": "c8d9e0f1a2b3",
            }
        )
        + "\n"
    )
    digest = "postgres@sha256:" + ("1" * 64)
    manifest = {
        "project": "ai-video",
        "status": "complete",
        "pg_server_major": "18",
        "pg_client_source_tag": "postgres:18",
        "pg_client_image": digest,
        "pg_dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "pg_dump_stats_sha256": hashlib.sha256(stats.read_bytes()).hexdigest(),
        "pg_schema_sha256": hashlib.sha256(schema.read_bytes()).hexdigest(),
        "pg_schema_list_sha256": hashlib.sha256(schema_list.read_bytes()).hexdigest(),
        "pg_schema_signature": "a" * 64,
        "alembic_revision": "c8d9e0f1a2b3",
        "pg_schema_signature_after_sha256": hashlib.sha256(
            schema_after.read_bytes()
        ).hexdigest(),
    }
    (backup_dir / "manifest.txt").write_text(
        "".join(f"{key}: {value}\n" for key, value in manifest.items())
    )
    output_dir = backup_dir / "output"
    output_dir.mkdir()
    media = output_dir / "fixture.bin"
    media.write_bytes(b"media")
    (backup_dir / "media_manifest.json").write_text(
        json.dumps(
            {
                "file_count": 1,
                "total_size_bytes": 5,
                "files": [
                    {
                        "path": "fixture.bin",
                        "size_bytes": 5,
                        "sha256": hashlib.sha256(b"media").hexdigest(),
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n"
    )
    source_root = tmp_path / "restore-source"
    source_root.mkdir()
    source_file = source_root / "app.py"
    source_file.write_text("# fixture\n")
    source_manifest = source_root / "source-manifest.v1.json"
    source_manifest.write_text(
        json.dumps(
            build_source_manifest(source_root, GIT_SHA, ["app.py"]),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    create_backup_manifest(
        backup_dir=backup_dir,
        source_root=source_root,
        source_manifest_path=source_manifest,
        backend_image_reference=f"lighthouse-backend:{GIT_SHA}",
        backend_image_id=BACKEND_IMAGE_ID,
        backend_repo_digest=None,
        oci_revision=GIT_SHA,
        pg_client_source_tag="postgres:18",
        pg_client_image=digest,
        completed_at="2026-07-22T12:00:00Z",
        backup_timestamp="2026-07-10_120000",
    )
    return backup_dir, digest


def test_restore_database_wrapper_uses_empty_target_one_shot_and_marks_success(
    tmp_path: Path,
) -> None:
    backup_dir, digest = _write_restore_backup_fixture(tmp_path)
    docker_log = tmp_path / "docker.log"
    docker_log.write_text("")
    schema_list = backup_dir / "pg_schema.list"
    fake_docker = _write_executable(
        tmp_path / "docker-restore",
        f"""#!/usr/bin/env bash
set -euo pipefail
command_name="$1"
shift
printf '%s %s\n' "$command_name" "$*" >>"${{FAKE_DOCKER_LOG:?}}"
case "$command_name" in
  image)
    [ "$1" = "inspect" ]
    if [[ "$*" == *"--format="* ]]; then
      printf '%s\n' '{digest}'
    fi
    ;;
  inspect)
    printf '%s\n' 'sha256:{'2' * 64}'
    ;;
  run)
    if [[ "$*" == *"pg_restore --list"* ]]; then
      cat >/dev/null
      cat '{schema_list}'
    elif [[ "$*" == *"psql --no-psqlrc"* ]]; then
      cat >/dev/null
      printf '0\n'
    elif [[ "$*" == *"pg_restore"*"--schema-only"* ]]; then
      cat >/dev/null
    elif [[ "$*" == *"/run/restore.py"* ]]; then
      IFS= read -r database_url
      [[ "$database_url" == postgresql://* ]]
      printf '%s\n' '{{"tables":{{"tenants":{{"available":1,"inserted":1}}}}}}'
    elif [[ "$*" == *"/run/verify.py"* ]]; then
      IFS= read -r database_url
      [[ "$database_url" == postgresql://* ]]
      printf '%s\n' '{{"status":"passed","table_count":1,"total_rows":1,"actual_counts":{{"tenants":1}},"alembic_revision":"c8d9e0f1a2b3"}}'
    else
      printf 'unexpected fake restore docker run command: %s\n' "$*" >&2
      exit 66
    fi
    ;;
  *)
    printf 'unexpected fake restore docker command: %s\n' "$command_name" >&2
    exit 64
    ;;
esac
""",
    )
    restore_tool = tmp_path / "pg_restore_logical.py"
    restore_tool.write_text("# fixture\n")
    verify_tool = tmp_path / "verify_restored_database.py"
    verify_tool.write_text("# fixture\n")
    env = os.environ.copy()
    env.update(
        {
            "DOCKER_BIN": str(fake_docker),
            "FAKE_DOCKER_LOG": str(docker_log),
            "BACKEND_CONTAINER": "ai_video_backend",
            "NETWORK_NAME": "lighthouse_ai_video_net",
            "RESTORE_SCRIPT": str(restore_tool),
            "VERIFY_SCRIPT": str(verify_tool),
            "BACKUP_MANIFEST_SCRIPT": str(BACKUP_MANIFEST_SCRIPT),
            "EXPECTED_RESTORE_HOST": "l4_restore_test",
            "RESTORE_SCOPE": "isolated",
            "RESTORE_CONFIRMATION": "RESTORE_EMPTY_DATABASE",
        }
    )

    result = subprocess.run(
        ["bash", str(RESTORE_DATABASE_SCRIPT), str(backup_dir)],
        cwd=REPO_ROOT,
        env=env,
        input="postgresql://fixture:secret@l4_restore_test:5432/postgres\n",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    marker = json.loads((backup_dir / "restore_verified.json").read_text())
    assert marker["status"] == "passed"
    assert marker["alembic_revision"] == "c8d9e0f1a2b3"
    assert marker["manifest_sha256"] == hashlib.sha256(
        (backup_dir / "backup-manifest.v1.json").read_bytes()
    ).hexdigest()
    log = docker_log.read_text()
    assert "postgresql://" not in log
    assert '--dbname="$database_url"' not in log
    assert "--dbname=$database_url" not in log
    assert "--truncate-first" not in log
    assert "--stats /backup/pg_dump_stats.json" in log
    assert "--single-transaction" in log


def test_backup_retention_skips_deletion_without_a_restore_verified_point(
    tmp_path: Path,
) -> None:
    env, backup_root = _backup_env(tmp_path)
    backup_root.mkdir()
    expired = backup_root / "2026-06-01_030000"
    expired.mkdir()
    (expired / "manifest.txt").write_text("project: ai-video\nstatus: complete\n")
    _age(expired, 20)

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert expired.is_dir()
    assert "no restore-verified recovery point" in result.stdout


def test_restore_database_wrapper_rejects_unexpected_target_before_docker_write(
    tmp_path: Path,
) -> None:
    backup_dir, _ = _write_restore_backup_fixture(tmp_path)
    docker_log = tmp_path / "docker.log"
    fake_docker = _write_executable(
        tmp_path / "docker-reject",
        "#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >>\"${FAKE_DOCKER_LOG:?}\"\n",
    )
    env = os.environ.copy()
    env.update(
        {
            "DOCKER_BIN": str(fake_docker),
            "FAKE_DOCKER_LOG": str(docker_log),
            "EXPECTED_RESTORE_HOST": "l4_restore_expected",
            "RESTORE_SCOPE": "isolated",
            "RESTORE_CONFIRMATION": "RESTORE_EMPTY_DATABASE",
        }
    )

    result = subprocess.run(
        ["bash", str(RESTORE_DATABASE_SCRIPT), str(backup_dir)],
        cwd=REPO_ROOT,
        env=env,
        input="postgresql://fixture:secret@wrong-host:5432/postgres\n",
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "restore target hostname mismatch" in result.stderr
    assert not docker_log.exists() or docker_log.read_text() == ""


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
    restore_wrapper = RESTORE_DATABASE_SCRIPT.read_text()
    stop_ingress = runbook.index("stop nginx")
    restore_database = runbook.index("restore_backup_database.sh", stop_ingress)
    restore_media = runbook.index("--volumes-from ai_video_backend", restore_database)
    start_backend = runbook.index("--force-recreate backend", restore_media)
    start_ingress = runbook.index("start nginx")

    assert (
        stop_ingress
        < restore_database
        < restore_media
        < start_backend
        < start_ingress
    )
    assert 'test -z "$(sudo find /opt/ai-video-backups' in runbook
    assert 'hashlib.sha256()' in runbook
    assert 'media manifest file set mismatch' in runbook
    assert 'media snapshot contains a symlink' in runbook
    assert "pg_restore --schema-only" in runbook
    assert "backup-manifest.v1.json.sha256" in runbook
    assert 'database["client_image"]' in runbook
    assert "schema archive table set does not match backup stats" in runbook
    assert "backup_manifest.py validate" in runbook
    assert "逐表核对 12 表" not in runbook
    assert '"tenants", "admin_accounts"' not in runbook
    assert "set -Eeuo pipefail" in restore_wrapper
    assert "--single-transaction" in restore_wrapper
    assert "--truncate-first" not in restore_wrapper
    assert '--dbname="$database_url"' not in restore_wrapper
    assert '--dbname="$PGDATABASE"' in restore_wrapper
    assert "PGPASSFILE" in restore_wrapper
    assert "docker compose" not in restore_wrapper


def test_restore_wrapper_rejects_symlinked_backup_root_before_docker(
    tmp_path: Path,
) -> None:
    real_backup = tmp_path / "real-backup"
    real_backup.mkdir()
    linked_backup = tmp_path / "2026-07-22_210000"
    linked_backup.symlink_to(real_backup, target_is_directory=True)

    result = subprocess.run(
        ["bash", str(RESTORE_DATABASE_SCRIPT), str(linked_backup)],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "backup directory must not be a symlink" in result.stderr


def test_brand_asset_restore_reads_root_owned_backup_with_sudo() -> None:
    runbook = BRAND_ASSETS_RUNBOOK.read_text()
    assert "sudo find /opt/ai-video-backups" in runbook
    assert "sudo grep -Fx 'status: complete'" in runbook
