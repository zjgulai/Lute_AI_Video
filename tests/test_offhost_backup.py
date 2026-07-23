from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from scripts.backup_manifest import build_source_manifest, create_backup_manifest
from scripts.offhost_backup import (
    ObjectReceipt,
    OffHostBackupError,
    OffHostOutcomeAmbiguous,
    build_dry_run_plan,
    upload_backup_create_only,
)

GIT_SHA = "a" * 40


def _make_backup(tmp_path: Path) -> Path:
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "app.py").write_text("# source\n")
    source_manifest = source_root / "source-manifest.v1.json"
    source_manifest.write_text(
        json.dumps(
            build_source_manifest(source_root, GIT_SHA, ["app.py"]),
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    backup = tmp_path / "2026-07-22_200000"
    backup.mkdir()
    dump = backup / "pg_dump.jsonl"
    dump.write_text('{"_table":"tenants","_data":{"id":"1"}}\n')
    (backup / "pg_dump_stats.json").write_text(
        json.dumps(
            {
                "server_version_num": "180004",
                "server_major": 18,
                "schema_signature": "c" * 64,
                "alembic_revision": "c8d9e0f1a2b3",
                "expected_tables": ["tenants"],
                "tables": {"tenants": {"rows": 1}},
                "total_rows": 1,
                "file_size": dump.stat().st_size,
            }
        )
        + "\n"
    )
    (backup / "pg_schema.dump").write_bytes(b"schema")
    (backup / "pg_schema.list").write_text(
        "1; 1259 1 TABLE public tenants owner\n"
    )
    (backup / "pg_schema_signature_after.json").write_text(
        json.dumps(
            {
                "schema_signature": "c" * 64,
                "alembic_revision": "c8d9e0f1a2b3",
            }
        )
        + "\n"
    )
    output = backup / "output"
    output.mkdir()
    (output / "clip.bin").write_bytes(b"media")
    (backup / "media_manifest.json").write_text(
        json.dumps(
            {
                "file_count": 1,
                "total_size_bytes": 5,
                "files": [
                    {
                        "path": "clip.bin",
                        "size_bytes": 5,
                        "sha256": hashlib.sha256(b"media").hexdigest(),
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n"
    )
    create_backup_manifest(
        backup_dir=backup,
        source_root=source_root,
        source_manifest_path=source_manifest,
        backend_image_reference=f"lighthouse-backend:{GIT_SHA}",
        backend_image_id="sha256:" + ("b" * 64),
        backend_repo_digest=None,
        oci_revision=GIT_SHA,
        pg_client_source_tag="postgres:18",
        pg_client_image="postgres@sha256:" + ("d" * 64),
        completed_at="2026-07-22T12:00:00Z",
        backup_timestamp=backup.name,
    )
    (backup / "manifest.txt").write_text("project: ai-video\nstatus: complete\n")
    return backup


class FakeStore:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, ObjectReceipt]] = {}
        self.put_calls = 0
        self.drift_readback = False
        self.omit_version = False
        self.omit_encryption = False
        self.raise_ambiguous = False
        self.raise_readback_ambiguous = False

    def head(self, key: str) -> ObjectReceipt | None:
        if self.raise_readback_ambiguous and self.objects:
            raise RuntimeError("fixture readback transport failure")
        stored = self.objects.get(key)
        if stored is None:
            return None
        receipt = stored[1]
        if self.drift_readback:
            return ObjectReceipt(
                key=receipt.key,
                version_id=receipt.version_id,
                sha256="0" * 64,
                size_bytes=receipt.size_bytes,
                encryption=receipt.encryption,
            )
        return receipt

    def put(
        self,
        key: str,
        source: Path,
        *,
        sha256: str,
        create_only: bool,
    ) -> ObjectReceipt:
        self.put_calls += 1
        if self.raise_ambiguous:
            raise OffHostOutcomeAmbiguous("offhost_put_outcome_ambiguous")
        if create_only and key in self.objects:
            raise OffHostBackupError("offhost_object_already_exists")
        payload = source.read_bytes()
        receipt = ObjectReceipt(
            key=key,
            version_id="" if self.omit_version else f"version-{self.put_calls}",
            sha256=sha256,
            size_bytes=len(payload),
            encryption=(
                {}
                if self.omit_encryption
                else {
                    "mode": "fake-managed-encryption",
                    "key_ref": "fake-key-ref",
                    "algorithm": "fake-aead",
                }
            ),
        )
        self.objects[key] = (payload, receipt)
        return receipt

    def download(self, key: str, version_id: str, destination: Path) -> ObjectReceipt:
        payload, receipt = self.objects[key]
        assert receipt.version_id == version_id
        destination.write_bytes(payload)
        return receipt


def test_dry_run_validates_manifest_and_constructs_no_store(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path)
    constructed = False

    def forbidden_factory() -> FakeStore:
        nonlocal constructed
        constructed = True
        return FakeStore()

    plan = build_dry_run_plan(backup, "tenant-safe-prefix")
    plan_typed = cast(dict[str, Any], plan)

    assert plan_typed["mode"] == "dry-run"
    assert plan_typed["object_count"] >= 10
    assert plan_typed["total_size_bytes"] > 0
    assert plan_typed["backup_manifest_sha256"] == hashlib.sha256(
        (backup / "backup-manifest.v1.json").read_bytes()
    ).hexdigest()
    assert "local_path" not in json.dumps(plan)
    assert constructed is False
    assert forbidden_factory  # the dry-run API accepts no factory or client


def test_dry_run_excludes_unbound_compatibility_and_rejects_unknown_files(
    tmp_path: Path,
) -> None:
    backup = _make_backup(tmp_path)
    plan = cast(dict[str, Any], build_dry_run_plan(backup, "tenant-safe-prefix"))
    object_keys = {str(item["key"]) for item in plan["objects"]}

    assert not any(key.endswith("/manifest.txt") for key in object_keys)
    (backup / "unexpected-private.txt").write_text("must not leave host\n")
    with pytest.raises(OffHostBackupError, match="offhost_local_file_set_invalid"):
        build_dry_run_plan(backup, "tenant-safe-prefix")


def test_dry_run_rejects_symlinked_backup_root(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path)
    linked = tmp_path / "2026-07-22_210000"
    linked.symlink_to(backup, target_is_directory=True)

    with pytest.raises(OffHostBackupError, match="offhost_local_manifest_invalid"):
        build_dry_run_plan(linked, "tenant-safe-prefix")


def test_fake_store_upload_head_and_download_readback_pass(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path)
    store = FakeStore()

    summary = upload_backup_create_only(store, backup, "tenant-safe-prefix")

    assert summary["status"] == "passed"
    assert summary["object_count"] == store.put_calls
    assert summary["object_count"] == len(store.objects)
    assert all(receipt.version_id for _, receipt in store.objects.values())
    assert all(receipt.encryption for _, receipt in store.objects.values())


def test_prefix_containing_backup_name_does_not_corrupt_local_source_resolution(
    tmp_path: Path,
) -> None:
    backup = _make_backup(tmp_path)
    store = FakeStore()

    summary = upload_backup_create_only(
        store,
        backup,
        f"archive/{backup.name}/nested",
    )

    assert summary["status"] == "passed"
    assert summary["object_count"] == len(store.objects)


def test_duplicate_key_fails_before_put(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path)
    store = FakeStore()
    first_plan = build_dry_run_plan(backup, "tenant-safe-prefix")
    first_key = cast(dict[str, Any], first_plan)["objects"][0]["key"]
    store.objects[first_key] = (
        b"existing",
        ObjectReceipt(
            key=first_key,
            version_id="existing-version",
            sha256=hashlib.sha256(b"existing").hexdigest(),
            size_bytes=8,
            encryption={
                "mode": "fake-managed-encryption",
                "key_ref": "fake-key-ref",
                "algorithm": "fake-aead",
            },
        ),
    )

    with pytest.raises(OffHostBackupError, match="offhost_object_already_exists"):
        upload_backup_create_only(store, backup, "tenant-safe-prefix")
    assert store.put_calls == 0


@pytest.mark.parametrize("defect", ["version", "encryption", "readback"])
def test_missing_receipt_facts_or_checksum_drift_fail_closed(
    tmp_path: Path,
    defect: str,
) -> None:
    backup = _make_backup(tmp_path)
    store = FakeStore()
    store.omit_version = defect == "version"
    store.omit_encryption = defect == "encryption"
    store.drift_readback = defect == "readback"

    with pytest.raises(OffHostOutcomeAmbiguous):
        upload_backup_create_only(store, backup, "tenant-safe-prefix")


def test_ambiguous_put_is_not_retried_and_error_is_stable(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path)
    store = FakeStore()
    store.raise_ambiguous = True

    with pytest.raises(
        OffHostOutcomeAmbiguous,
        match="^offhost_put_outcome_ambiguous$",
    ):
        upload_backup_create_only(store, backup, "tenant-safe-prefix")
    assert store.put_calls == 1


def test_ambiguous_readback_after_put_is_not_retried(tmp_path: Path) -> None:
    backup = _make_backup(tmp_path)
    store = FakeStore()
    store.raise_readback_ambiguous = True

    with pytest.raises(
        OffHostOutcomeAmbiguous,
        match="^offhost_readback_outcome_ambiguous$",
    ):
        upload_backup_create_only(store, backup, "tenant-safe-prefix")
    assert store.put_calls == 1


def test_cli_is_dry_run_only_and_has_no_provider_or_credential_path() -> None:
    source = (Path(__file__).resolve().parents[1] / "scripts" / "offhost_backup.py").read_text()

    assert "--execute" not in source
    assert "boto" not in source.lower()
    assert "credential" not in source.lower()
    assert "secret" not in source.lower()


def test_cli_dry_run_executes_without_client_or_local_path_disclosure(
    tmp_path: Path,
) -> None:
    backup = _make_backup(tmp_path)
    script = Path(__file__).resolve().parents[1] / "scripts" / "offhost_backup.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--backup-dir",
            str(backup),
            "--prefix",
            "tenant-safe-prefix",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["mode"] == "dry-run"
    assert str(tmp_path) not in result.stdout + result.stderr
