from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.backup_manifest import (
    BackupManifestError,
    build_source_manifest,
    create_backup_manifest,
    validate_backup_manifest,
    validate_source_manifest,
)

GIT_SHA = "a" * 40
IMAGE_ID = "sha256:" + ("b" * 64)
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _backup_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "src").mkdir()
    (source_root / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    source_manifest_path = source_root / "source-manifest.v1.json"
    source_manifest = build_source_manifest(
        source_root,
        GIT_SHA,
        ["src/app.py"],
    )
    _write_json(source_manifest_path, source_manifest)

    backup_dir = tmp_path / "backup"
    backup_dir.mkdir()
    (backup_dir / "pg_dump.jsonl").write_text(
        '{"_table":"tenants","_data":{"id":"tenant-1"}}\n',
        encoding="utf-8",
    )
    dump_size = (backup_dir / "pg_dump.jsonl").stat().st_size
    _write_json(
        backup_dir / "pg_dump_stats.json",
        {
            "server_version_num": "180004",
            "server_major": 18,
            "schema_signature": "c" * 64,
            "alembic_revision": "c8d9e0f1a2b3",
            "expected_tables": ["tenants", "empty_jobs"],
            "tables": {"tenants": {"rows": 1}, "empty_jobs": {"rows": 0}},
            "total_rows": 1,
            "file_size": dump_size,
        },
    )
    (backup_dir / "pg_schema.dump").write_bytes(b"schema")
    (backup_dir / "pg_schema.list").write_text(
        "1; 1259 1 TABLE public tenants owner\n"
        "2; 1259 2 TABLE public empty_jobs owner\n",
        encoding="utf-8",
    )
    _write_json(
        backup_dir / "pg_schema_signature_after.json",
        {
            "schema_signature": "c" * 64,
            "alembic_revision": "c8d9e0f1a2b3",
        },
    )
    media_path = backup_dir / "output" / "nested" / "clip.bin"
    media_path.parent.mkdir(parents=True)
    media_path.write_bytes(b"media")
    _write_json(
        backup_dir / "media_manifest.json",
        {
            "file_count": 1,
            "total_size_bytes": 5,
            "files": [
                {
                    "path": "nested/clip.bin",
                    "size_bytes": 5,
                    "sha256": hashlib.sha256(b"media").hexdigest(),
                }
            ],
        },
    )
    return backup_dir, source_root, source_manifest_path


def test_source_manifest_is_deterministic_and_validates_exact_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    (root / "a.txt").write_text("a\n", encoding="utf-8")

    first = build_source_manifest(root, GIT_SHA, ["b.txt", "a.txt"])
    second = build_source_manifest(root, GIT_SHA, ["a.txt", "b.txt"])

    assert first == second
    first_typed = cast(dict[str, Any], first)
    assert [entry["path"] for entry in first_typed["files"]] == ["a.txt", "b.txt"]
    validate_source_manifest(first, root)
    (root / "a.txt").write_text("changed\n", encoding="utf-8")
    with pytest.raises(BackupManifestError, match="source file checksum"):
        validate_source_manifest(first, root)


def test_source_manifest_rejects_symlinked_source_components(tmp_path: Path) -> None:
    root = tmp_path / "source"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "app.py").write_text("print('outside')\n")
    (root / "linked").symlink_to(outside, target_is_directory=True)

    with pytest.raises(BackupManifestError, match="source file is missing or unsafe"):
        build_source_manifest(root, GIT_SHA, ["linked/app.py"])


def test_source_manifest_allows_one_resolved_release_root_symlink(tmp_path: Path) -> None:
    release = tmp_path / "releases" / GIT_SHA
    release.mkdir(parents=True)
    (release / "app.py").write_text("print('reviewed')\n")
    current = tmp_path / "current"
    current.symlink_to(release, target_is_directory=True)

    manifest = build_source_manifest(current, GIT_SHA, ["app.py"])

    assert validate_source_manifest(manifest, current) == manifest


def test_source_create_cli_refuses_to_overwrite_existing_output(tmp_path: Path) -> None:
    root = tmp_path / "source"
    root.mkdir()
    (root / "app.py").write_text("print('ok')\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "app.py"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=root,
        check=True,
    )
    git_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    output = root / "source-manifest.v1.json"
    output.write_text("do-not-overwrite\n")

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "backup_manifest.py"),
            "source-create",
            "--root",
            str(root),
            "--git-sha",
            git_sha,
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert output.read_text() == "do-not-overwrite\n"


def test_canonical_backup_manifest_records_and_validates_all_recovery_identity(
    tmp_path: Path,
) -> None:
    backup_dir, source_root, source_manifest_path = _backup_fixture(tmp_path)

    manifest = create_backup_manifest(
        backup_dir=backup_dir,
        source_root=source_root,
        source_manifest_path=source_manifest_path,
        backend_image_reference=f"lighthouse-backend:{GIT_SHA}",
        backend_image_id=IMAGE_ID,
        backend_repo_digest=None,
        oci_revision=GIT_SHA,
        pg_client_source_tag="postgres:18",
        pg_client_image="postgres@sha256:" + ("d" * 64),
        completed_at="2026-07-22T12:00:00Z",
        backup_timestamp="2026-07-22_200000",
    )
    manifest_typed = cast(dict[str, Any], manifest)

    assert manifest_typed["schema_version"] == "backup-manifest.v1"
    assert manifest_typed["git_sha"] == GIT_SHA
    assert manifest_typed["backend_image"]["image_id"] == IMAGE_ID
    assert manifest_typed["backend_image"]["oci_revision"] == GIT_SHA
    assert manifest_typed["database"]["tables"] == {
        "empty_jobs": {"rows": 0},
        "tenants": {"rows": 1},
    }
    assert manifest_typed["media"]["files"][0]["path"] == "nested/clip.bin"
    assert set(manifest_typed["artifacts"]) == {
        "media_manifest.json",
        "pg_dump.jsonl",
        "pg_dump_stats.json",
        "pg_schema.dump",
        "pg_schema.list",
        "pg_schema_signature_after.json",
        "source-manifest.v1.json",
    }
    validated = validate_backup_manifest(backup_dir)
    assert validated == manifest
    detached = (backup_dir / "backup-manifest.v1.json.sha256").read_text()
    assert detached == (
        hashlib.sha256((backup_dir / "backup-manifest.v1.json").read_bytes()).hexdigest()
        + "  backup-manifest.v1.json\n"
    )


def test_backup_manifest_rejects_git_image_source_identity_mismatch(
    tmp_path: Path,
) -> None:
    backup_dir, source_root, source_manifest_path = _backup_fixture(tmp_path)

    with pytest.raises(BackupManifestError, match="Git and OCI revision"):
        create_backup_manifest(
            backup_dir=backup_dir,
            source_root=source_root,
            source_manifest_path=source_manifest_path,
            backend_image_reference="lighthouse-backend:wrong",
            backend_image_id=IMAGE_ID,
            backend_repo_digest=None,
            oci_revision="e" * 40,
            pg_client_source_tag="postgres:18",
            pg_client_image="postgres@sha256:" + ("d" * 64),
            completed_at="2026-07-22T12:00:00Z",
            backup_timestamp="2026-07-22_200000",
        )


def test_backup_manifest_detects_artifact_media_and_detached_hash_drift(
    tmp_path: Path,
) -> None:
    backup_dir, source_root, source_manifest_path = _backup_fixture(tmp_path)
    create_backup_manifest(
        backup_dir=backup_dir,
        source_root=source_root,
        source_manifest_path=source_manifest_path,
        backend_image_reference=f"lighthouse-backend:{GIT_SHA}",
        backend_image_id=IMAGE_ID,
        backend_repo_digest=None,
        oci_revision=GIT_SHA,
        pg_client_source_tag="postgres:18",
        pg_client_image="postgres@sha256:" + ("d" * 64),
        completed_at="2026-07-22T12:00:00Z",
        backup_timestamp="2026-07-22_200000",
    )

    (backup_dir / "output" / "nested" / "clip.bin").write_bytes(b"tampered")
    with pytest.raises(BackupManifestError, match="media file"):
        validate_backup_manifest(backup_dir)
    (backup_dir / "output" / "nested" / "clip.bin").write_bytes(b"media")
    (backup_dir / "pg_schema.dump").write_bytes(b"tampered")
    with pytest.raises(BackupManifestError, match="artifact checksum"):
        validate_backup_manifest(backup_dir)
    (backup_dir / "pg_schema.dump").write_bytes(b"schema")
    (backup_dir / "backup-manifest.v1.json.sha256").write_text(
        ("0" * 64) + "  backup-manifest.v1.json\n",
        encoding="utf-8",
    )
    with pytest.raises(BackupManifestError, match="detached manifest checksum"):
        validate_backup_manifest(backup_dir)


@pytest.mark.parametrize(
    "target_name",
    [
        "source-manifest.v1.json",
        "backup-manifest.v1.json",
        "backup-manifest.v1.json.sha256",
    ],
)
def test_backup_manifest_create_refuses_to_clobber_any_output(
    tmp_path: Path,
    target_name: str,
) -> None:
    backup_dir, source_root, source_manifest_path = _backup_fixture(tmp_path)
    target = backup_dir / target_name
    target.write_bytes(b"sentinel-do-not-overwrite\n")

    with pytest.raises(BackupManifestError, match="output already exists"):
        create_backup_manifest(
            backup_dir=backup_dir,
            source_root=source_root,
            source_manifest_path=source_manifest_path,
            backend_image_reference=f"lighthouse-backend:{GIT_SHA}",
            backend_image_id=IMAGE_ID,
            backend_repo_digest=None,
            oci_revision=GIT_SHA,
            pg_client_source_tag="postgres:18",
            pg_client_image="postgres@sha256:" + ("d" * 64),
            completed_at="2026-07-22T12:00:00Z",
            backup_timestamp="2026-07-22_200000",
        )

    assert target.read_bytes() == b"sentinel-do-not-overwrite\n"


def test_backup_manifest_failed_create_cleans_outputs_and_can_retry(
    tmp_path: Path,
) -> None:
    backup_dir, source_root, source_manifest_path = _backup_fixture(tmp_path)
    stats_path = backup_dir / "pg_dump_stats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    stats["total_rows"] = 2
    _write_json(stats_path, stats)
    kwargs = {
        "backup_dir": backup_dir,
        "source_root": source_root,
        "source_manifest_path": source_manifest_path,
        "backend_image_reference": f"lighthouse-backend:{GIT_SHA}",
        "backend_image_id": IMAGE_ID,
        "backend_repo_digest": None,
        "oci_revision": GIT_SHA,
        "pg_client_source_tag": "postgres:18",
        "pg_client_image": "postgres@sha256:" + ("d" * 64),
        "completed_at": "2026-07-22T12:00:00Z",
        "backup_timestamp": "2026-07-22_200000",
    }

    with pytest.raises(BackupManifestError, match="total row count"):
        create_backup_manifest(**kwargs)

    canonical_outputs = (
        backup_dir / "source-manifest.v1.json",
        backup_dir / "backup-manifest.v1.json",
        backup_dir / "backup-manifest.v1.json.sha256",
    )
    assert all(not path.exists() for path in canonical_outputs)

    stats["total_rows"] = 1
    _write_json(stats_path, stats)
    create_backup_manifest(**kwargs)
    assert all(path.is_file() for path in canonical_outputs)


def test_backup_manifest_validator_rejects_symlinked_backup_root(tmp_path: Path) -> None:
    backup_dir, source_root, source_manifest_path = _backup_fixture(tmp_path)
    create_backup_manifest(
        backup_dir=backup_dir,
        source_root=source_root,
        source_manifest_path=source_manifest_path,
        backend_image_reference=f"lighthouse-backend:{GIT_SHA}",
        backend_image_id=IMAGE_ID,
        backend_repo_digest=None,
        oci_revision=GIT_SHA,
        pg_client_source_tag="postgres:18",
        pg_client_image="postgres@sha256:" + ("d" * 64),
        completed_at="2026-07-22T12:00:00Z",
        backup_timestamp="2026-07-22_200000",
    )
    linked = tmp_path / "linked-backup"
    linked.symlink_to(backup_dir, target_is_directory=True)

    with pytest.raises(BackupManifestError, match="backup root is missing or unsafe"):
        validate_backup_manifest(linked)


def test_release_sync_paths_generate_exact_source_manifest_before_rsync() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "deploy.yml").read_text()
    wrapper = (
        REPO_ROOT / "deploy" / "lighthouse" / "build-and-deploy.sh"
    ).read_text()

    assert workflow.count("scripts/backup_manifest.py source-create") >= 2
    assert workflow.count("--git-sha ${{ github.sha }}") >= 2
    dry_run_job = workflow.split("  remote-dry-run:", 1)[1].split("  deploy:", 1)[0]
    deploy_job = workflow.split("  deploy:", 1)[1]
    for job in (dry_run_job, deploy_job):
        assert job.index("scripts/backup_manifest.py source-create") < job.index(
            "rsync -avz"
        )
    assert "scripts/backup_manifest.py source-create" in wrapper
    assert wrapper.index("scripts/backup_manifest.py source-create") < wrapper.index(
        '"$RSYNC_BIN" "${RSYNC_ARGS[@]}"'
    )


def test_makefile_has_one_no_external_recovery_contract_gate() -> None:
    makefile = (REPO_ROOT / "Makefile").read_text()
    target = makefile.split("recovery-check:", 1)[1].split("\n\n", 1)[0]

    assert "test_backup_manifest.py" in target
    assert "test_offhost_backup.py" in target
    assert "test_pg_restore_logical.py" in target
    assert "test_backup_production_contract.py" in target
    assert "bash -n" in target
    assert "scripts/pg_restore_logical.py" in target
    assert "scripts/verify_restored_database.py" in target
    assert "scripts/backup_manifest.py" in target
    assert "scripts/offhost_backup.py" in target
    assert "docker run" not in target
    assert "curl " not in target


def test_restore_uses_only_canonical_manifest_as_required_identity() -> None:
    restore = (REPO_ROOT / "scripts" / "restore_backup_database.sh").read_text()
    required_files = restore.split("for required_file in", 1)[1].split("done", 1)[0]

    assert "backup-manifest.v1.json" in required_files
    assert "source-manifest.v1.json" in required_files
    assert "manifest.txt" not in required_files
